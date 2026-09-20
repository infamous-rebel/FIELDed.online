"""Business identity and profile API endpoints.

Provides business creation, listing, membership management, and
full business profile management.
All endpoints enforce strict tenant isolation.
"""

from __future__ import annotations

import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db_session
from app.domain.common.enums import (
    BUSINESS_PROFILE_TRANSITIONS,
    BUSINESS_TRANSITIONS,
    AuditEventType,
    BusinessMemberRole,
    BusinessProfileStatus,
    BusinessStatus,
)
from app.domain.identity.models import (
    Business,
    BusinessMember,
    BusinessProfile,
    User,
)
from app.domain.identity.token_models import MemberInvitation
from app.domain.outbox.models import OutboxEvent
from app.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    StateTransitionError,
    ValidationError,
)
from app.security.authorization import get_current_user

router = APIRouter()

# Mounted at the API root for the public invitation-acceptance path.
accept_router = APIRouter()


# --- Schemas ---


class BusinessCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SocialLinksUpdate(BaseModel):
    """Structured social media links."""

    website: str | None = Field(default=None, max_length=500)
    facebook: str | None = Field(default=None, max_length=500)
    instagram: str | None = Field(default=None, max_length=500)
    linkedin: str | None = Field(default=None, max_length=500)

    @field_validator("website", "facebook", "instagram", "linkedin")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is not None and v != "":
            _validate_url(v)
        return v or None


class BusinessProfileUpdateRequest(BaseModel):
    """Full business profile update."""

    description: str | None = Field(default=None, max_length=2000)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=320)
    # Address
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, max_length=100)
    # Service area
    service_area: dict[str, Any] | None = None
    # Social links
    social_links: SocialLinksUpdate | None = None
    # Images (URLs — actual upload comes later)
    logo_url: str | None = Field(default=None, max_length=500)
    cover_image_url: str | None = Field(default=None, max_length=500)
    # Public status
    public_status: str | None = Field(default=None, pattern=r"^(incomplete|active|suspended)$")

    @field_validator("logo_url", "cover_image_url")
    @classmethod
    def validate_image_url(cls, v: str | None) -> str | None:
        if v is not None and v != "":
            _validate_url(v)
        return v or None


class BusinessUpdateRequest(BaseModel):
    """Update business entity fields (name, etc)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)


class BusinessTransitionRequest(BaseModel):
    """Business lifecycle transition request."""

    target_status: str = Field(pattern=r"^(active|suspended|deactivated)$")


class SocialLinksRead(BaseModel):
    website: str | None = None
    facebook: str | None = None
    instagram: str | None = None
    linkedin: str | None = None


class BusinessProfileRead(BaseModel):
    description: str | None = None
    phone: str | None = None
    email: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    service_area: dict[str, Any] | None = None
    social_links: SocialLinksRead | None = None
    logo_url: str | None = None
    cover_image_url: str | None = None
    public_status: str
    is_verified: bool = False
    average_rating: float | None = None
    review_count: int = 0


class BusinessRead(BaseModel):
    id: str
    name: str
    slug: str
    status: str
    created_at: str
    updated_at: str


class BusinessDetailRead(BusinessRead):
    profile: BusinessProfileRead | None = None


class MemberCreateRequest(BaseModel):
    user_email: str
    role: str = Field(default="staff", pattern=r"^(owner|admin|staff)$")


class MemberInviteRequest(BaseModel):
    """Invite a person (who may not yet be on FIELDed) by email."""

    email: str = Field(min_length=3, max_length=320)
    role: str = Field(default="staff", pattern=r"^(owner|admin|staff)$")


class MemberRoleUpdateRequest(BaseModel):
    """Change an existing member's role."""

    role: str = Field(pattern=r"^(owner|admin|staff)$")


class MemberInvitationRead(BaseModel):
    id: str
    business_id: str
    email: str
    role: str
    expires_at: str
    created_at: str


class MemberRead(BaseModel):
    id: str
    user_id: str
    business_id: str
    role: str
    user_email: str | None = None
    created_at: str


class MessageResponse(BaseModel):
    message: str


# --- URL validation ---

_TRUSTED_SCHEMES = ("https://", "http://")
_URL_PATTERN = re.compile(
    r"^https?://"
    r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"[a-zA-Z]{2,}"
    r"(?::\d{1,5})?"
    r"(?:/[^\s]*)?$"
)


def _validate_url(value: str) -> None:
    """Validate that a URL is well-formed and uses an allowed scheme."""
    if not value.startswith(_TRUSTED_SCHEMES):
        raise ValidationError("URLs must start with http:// or https://")
    if not _URL_PATTERN.match(value):
        raise ValidationError(f"Malformed URL: {value}")


# --- Helpers ---

ROLE_HIERARCHY = {
    BusinessMemberRole.OWNER: 3,
    BusinessMemberRole.ADMIN: 2,
    BusinessMemberRole.STAFF: 1,
}


async def _get_user_business(
    business_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> tuple[Business, BusinessMember]:
    """Get a business and the user's membership, enforcing tenant isolation."""
    result = await db.execute(
        select(Business)
        .where(Business.id == business_id, Business.deleted_at.is_(None))
        .options(selectinload(Business.profile))
    )
    business = result.scalar_one_or_none()
    if business is None:
        raise NotFoundError("Business not found")

    result = await db.execute(
        select(BusinessMember).where(
            BusinessMember.user_id == user.id,
            BusinessMember.business_id == business_id,
            BusinessMember.deleted_at.is_(None),
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise AuthorizationError("Not a member of this business")

    return business, membership


def _check_minimum_role(membership: BusinessMember, minimum: BusinessMemberRole) -> None:
    """Check if a membership meets the minimum role requirement."""
    member_level = ROLE_HIERARCHY.get(BusinessMemberRole(membership.role), 0)
    required_level = ROLE_HIERARCHY.get(minimum, 0)
    if member_level < required_level:
        raise AuthorizationError(f"Requires {minimum.value} role or higher")


def _profile_to_read(profile: BusinessProfile) -> BusinessProfileRead:
    """Convert a BusinessProfile model to the read schema."""
    social_links = SocialLinksRead(
        website=profile.website,
        facebook=profile.facebook_url,
        instagram=profile.instagram_url,
        linkedin=profile.linkedin_url,
    )
    return BusinessProfileRead(
        description=profile.description,
        phone=profile.phone,
        email=profile.email,
        address_line1=profile.address_line1,
        address_line2=profile.address_line2,
        city=profile.city,
        state=profile.state,
        postal_code=profile.postal_code,
        country=profile.country,
        service_area=profile.service_area,
        social_links=social_links,
        logo_url=profile.logo_url,
        cover_image_url=profile.cover_image_url,
        public_status=profile.public_status,
        is_verified=profile.is_verified,
        average_rating=profile.average_rating,
        review_count=profile.review_count,
    )


def _business_to_read(business: Business) -> BusinessDetailRead:
    """Convert a Business model to the response schema."""
    profile_read = None
    if business.profile:
        profile_read = _profile_to_read(business.profile)
    return BusinessDetailRead(
        id=str(business.id),
        name=business.name,
        slug=business.slug,
        status=business.status,
        created_at=business.created_at.isoformat(),
        updated_at=business.updated_at.isoformat(),
        profile=profile_read,
    )


# --- Endpoints ---


@router.post("", response_model=BusinessRead, status_code=201)
async def create_business(
    body: BusinessCreateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BusinessRead:
    """Create a new business. The authenticated user becomes the owner."""
    result = await db.execute(select(Business).where(Business.slug == body.slug))
    if result.scalar_one_or_none() is not None:
        raise ConflictError("A business with this slug already exists")

    business = Business(name=body.name, slug=body.slug, status="pending")
    db.add(business)
    await db.flush()

    member = BusinessMember(
        user_id=user.id,
        business_id=business.id,
        role=BusinessMemberRole.OWNER,
    )
    db.add(member)

    profile = BusinessProfile(business_id=business.id)
    db.add(profile)

    await db.flush()

    return BusinessRead(
        id=str(business.id),
        name=business.name,
        slug=business.slug,
        status=business.status,
        created_at=business.created_at.isoformat(),
        updated_at=business.updated_at.isoformat(),
    )


@router.get("", response_model=list[BusinessRead])
async def list_businesses(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[BusinessRead]:
    """List all businesses the current user is a member of."""
    result = await db.execute(
        select(Business)
        .join(BusinessMember, BusinessMember.business_id == Business.id)
        .where(
            BusinessMember.user_id == user.id,
            BusinessMember.deleted_at.is_(None),
            Business.deleted_at.is_(None),
        )
        .order_by(Business.name)
    )
    businesses = result.scalars().all()

    return [
        BusinessRead(
            id=str(b.id),
            name=b.name,
            slug=b.slug,
            status=b.status,
            created_at=b.created_at.isoformat(),
            updated_at=b.updated_at.isoformat(),
        )
        for b in businesses
    ]


@router.get("/{business_id}", response_model=BusinessDetailRead)
async def get_business(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BusinessDetailRead:
    """Get business details. Only members can access."""
    business, _ = await _get_user_business(business_id, user, db)
    return _business_to_read(business)


@router.put("/{business_id}", response_model=BusinessDetailRead)
async def update_business(
    business_id: uuid.UUID,
    body: BusinessUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BusinessDetailRead:
    """Update business entity fields (name). Requires admin+."""
    business, membership = await _get_user_business(business_id, user, db)
    _check_minimum_role(membership, BusinessMemberRole.ADMIN)

    if body.name is not None:
        business.name = body.name
        await _emit_business_outbox_event(
            db,
            business_id=business_id,
            event_type=AuditEventType.BUSINESS_SETTINGS_UPDATED,
            aggregate_type="business",
            aggregate_id=business_id,
            payload={
                "notification_title": "Business settings updated",
                "notification_body": "Business name was updated.",
                "updated_fields": ["name"],
            },
            idempotency_key=(
                f"BUSINESS_SETTINGS_UPDATED:business:{business_id}"
                f":{int(datetime.now(UTC).timestamp())}"
            ),
        )

    await db.flush()
    await db.refresh(business, attribute_names=["profile"])
    return _business_to_read(business)


@router.post("/{business_id}/transition", response_model=BusinessDetailRead)
async def transition_business(
    business_id: uuid.UUID,
    body: BusinessTransitionRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BusinessDetailRead:
    """Transition the business lifecycle status. Requires owner role.

    Valid transitions:
    - PENDING -> ACTIVE, DEACTIVATED
    - ACTIVE -> SUSPENDED, DEACTIVATED
    - SUSPENDED -> ACTIVE, DEACTIVATED
    - DEACTIVATED -> (terminal)
    """
    business, membership = await _get_user_business(business_id, user, db)
    _check_minimum_role(membership, BusinessMemberRole.OWNER)

    current = BusinessStatus(business.status)
    target = BusinessStatus(body.target_status)
    allowed = BUSINESS_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise StateTransitionError(
            f"Cannot transition business from '{current.value}' to '{target.value}'. "
            f"Allowed: {[s.value for s in allowed] or 'none (terminal state)'}"
        )

    previous = current.value
    business.status = target
    await db.flush()
    await db.refresh(business, attribute_names=["profile"])

    await _emit_business_outbox_event(
        db,
        business_id=business_id,
        event_type=AuditEventType.BUSINESS_STATUS_CHANGED,
        aggregate_type="business",
        aggregate_id=business_id,
        payload={
            "previous_status": previous,
            "new_status": target.value,
            "changed_by": str(user.id),
        },
        idempotency_key=(
            f"BUSINESS_STATUS_CHANGED:business:{business_id}"
            f":{previous}:{target.value}:{int(datetime.now(UTC).timestamp())}"
        ),
    )

    return _business_to_read(business)


@router.get("/{business_id}/profile", response_model=BusinessProfileRead)
async def get_business_profile(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BusinessProfileRead:
    """Get the full business profile. Only members can access."""
    business, _ = await _get_user_business(business_id, user, db)
    if business.profile is None:
        raise NotFoundError("Business profile not found")
    return _profile_to_read(business.profile)


@router.put("/{business_id}/profile", response_model=BusinessProfileRead)
async def update_business_profile(
    business_id: uuid.UUID,
    body: BusinessProfileUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BusinessProfileRead:
    """Update the full business profile. Requires admin+."""
    business, membership = await _get_user_business(business_id, user, db)
    _check_minimum_role(membership, BusinessMemberRole.ADMIN)

    if business.profile is None:
        raise NotFoundError("Business profile not found")

    profile = business.profile
    update_data = body.model_dump(exclude_unset=True, exclude={"social_links"})

    # public_status is a state-machine-governed field — validate the
    # transition instead of assigning it like a plain profile field.
    if "public_status" in update_data:
        raw_status = update_data.pop("public_status")
        if raw_status is not None:
            current_public = BusinessProfileStatus(profile.public_status)
            target_public = BusinessProfileStatus(raw_status)
            if target_public is not current_public:
                allowed_public = BUSINESS_PROFILE_TRANSITIONS.get(current_public, set())
                if target_public not in allowed_public:
                    raise StateTransitionError(
                        f"Cannot transition public profile from "
                        f"'{current_public.value}' to '{target_public.value}'. "
                        f"Allowed: {[s.value for s in allowed_public] or 'none'}"
                    )
            profile.public_status = target_public

    for field, value in update_data.items():
        setattr(profile, field, value)

    # Handle social links separately
    if body.social_links is not None:
        social = body.social_links
        if social.website is not None:
            profile.website = social.website
        if social.facebook is not None:
            profile.facebook_url = social.facebook
        if social.instagram is not None:
            profile.instagram_url = social.instagram
        if social.linkedin is not None:
            profile.linkedin_url = social.linkedin

    await db.flush()
    await db.refresh(profile)

    await _emit_business_outbox_event(
        db,
        business_id=business_id,
        event_type=AuditEventType.BUSINESS_SETTINGS_UPDATED,
        aggregate_type="business_profile",
        aggregate_id=profile.id,
        payload={
            "notification_title": "Business settings updated",
            "notification_body": "Business profile settings were updated.",
            "updated_fields": sorted(
                set(update_data) | ({"social_links"} if body.social_links is not None else set())
            ),
        },
        idempotency_key=(
            f"BUSINESS_SETTINGS_UPDATED:business_profile:{profile.id}"
            f":{int(datetime.now(UTC).timestamp())}"
        ),
    )

    return _profile_to_read(profile)


# --- Members ---


@router.get("/{business_id}/members", response_model=list[MemberRead])
async def list_members(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[MemberRead]:
    """List all members of a business. Only members can see."""
    await _get_user_business(business_id, user, db)

    result = await db.execute(
        select(BusinessMember)
        .where(
            BusinessMember.business_id == business_id,
            BusinessMember.deleted_at.is_(None),
        )
        .options(selectinload(BusinessMember.user))
        .order_by(BusinessMember.created_at)
    )
    members = result.scalars().all()

    return [
        MemberRead(
            id=str(m.id),
            user_id=str(m.user_id),
            business_id=str(m.business_id),
            role=m.role,
            user_email=m.user.email if m.user else None,
            created_at=m.created_at.isoformat(),
        )
        for m in members
    ]


@router.post("/{business_id}/members", response_model=MemberRead, status_code=201)
async def add_member(
    business_id: uuid.UUID,
    body: MemberCreateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> MemberRead:
    """Add a member to a business. Requires owner role."""
    _, membership = await _get_user_business(business_id, user, db)
    _check_minimum_role(membership, BusinessMemberRole.OWNER)

    result = await db.execute(
        select(User).where(User.email == body.user_email, User.deleted_at.is_(None))
    )
    target_user = result.scalar_one_or_none()
    if target_user is None:
        raise NotFoundError(f"User with email {body.user_email} not found")

    result = await db.execute(
        select(BusinessMember).where(
            BusinessMember.user_id == target_user.id,
            BusinessMember.business_id == business_id,
            BusinessMember.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is not None:
        raise ConflictError("User is already a member of this business")

    new_member = BusinessMember(
        user_id=target_user.id,
        business_id=business_id,
        role=body.role,
    )
    db.add(new_member)
    await db.flush()

    return MemberRead(
        id=str(new_member.id),
        user_id=str(new_member.user_id),
        business_id=str(new_member.business_id),
        role=new_member.role,
        user_email=target_user.email,
        created_at=new_member.created_at.isoformat(),
    )


@router.delete("/{business_id}/members/{member_id}", response_model=MessageResponse)
async def remove_member(
    business_id: uuid.UUID,
    member_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    """Remove a member from a business. Requires owner role."""
    _, membership = await _get_user_business(business_id, user, db)
    _check_minimum_role(membership, BusinessMemberRole.OWNER)

    result = await db.execute(
        select(BusinessMember)
        .where(
            BusinessMember.id == member_id,
            BusinessMember.business_id == business_id,
            BusinessMember.deleted_at.is_(None),
        )
        .options(selectinload(BusinessMember.user))
    )
    target_member = result.scalar_one_or_none()
    if target_member is None:
        raise NotFoundError("Member not found")

    if target_member.user_id == user.id:
        raise ConflictError("Cannot remove yourself from the business")

    if target_member.role == BusinessMemberRole.OWNER:
        result = await db.execute(
            select(BusinessMember).where(
                BusinessMember.business_id == business_id,
                BusinessMember.role == BusinessMemberRole.OWNER,
                BusinessMember.deleted_at.is_(None),
            )
        )
        owners = result.scalars().all()
        if len(owners) <= 1:
            raise ConflictError("Cannot remove the last owner of a business")

    target_member.deleted_at = datetime.now(UTC)
    await db.flush()

    await _emit_business_outbox_event(
        db,
        business_id=business_id,
        event_type=AuditEventType.MEMBER_REMOVED,
        aggregate_type="member",
        aggregate_id=target_member.id,
        payload={
            "notification_title": "Member removed",
            "notification_body": (
                f"{(target_member.user.email if target_member.user else target_member.user_id)}"
                " was removed from the business."
            ),
        },
        idempotency_key=(
            f"MEMBER_REMOVED:member:{target_member.id}:{int(datetime.now(UTC).timestamp())}"
        ),
    )

    return MessageResponse(message="Member removed successfully")


# --- Member invitations (Phase 17) ---


async def _emit_business_outbox_event(
    db: AsyncSession,
    *,
    business_id: uuid.UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    payload: dict,
    idempotency_key: str,
) -> None:
    """Create a member outbox event in the same transaction."""
    event = OutboxEvent(
        business_id=business_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
        idempotency_key=idempotency_key,
        status="PENDING",
        available_at=datetime.now(UTC),
    )
    db.add(event)
    await db.flush()


@router.post(
    "/{business_id}/members/invite",
    response_model=MemberInvitationRead,
    status_code=201,
)
async def invite_member(
    business_id: uuid.UUID,
    body: MemberInviteRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> MemberInvitationRead:
    """Invite a person (who may not yet be on FIELDed) to join the business.

    Requires owner role. Sends the invitation email through the existing
    governed communications pipeline (outbox + policy + templates).
    """
    business, membership = await _get_user_business(business_id, user, db)
    _check_minimum_role(membership, BusinessMemberRole.OWNER)

    email = body.email.strip().lower()

    # Already an active member?
    result = await db.execute(
        select(BusinessMember)
        .join(User, BusinessMember.user_id == User.id)
        .where(
            User.email == email,
            BusinessMember.business_id == business_id,
            BusinessMember.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is not None:
        raise ConflictError("User is already a member of this business")

    # Pending invitation already exists?
    result = await db.execute(
        select(MemberInvitation).where(
            MemberInvitation.business_id == business_id,
            MemberInvitation.email == email,
            MemberInvitation.used_at.is_(None),
            MemberInvitation.deleted_at.is_(None),
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None and not existing.is_expired:
        raise ConflictError("A pending invitation for this email already exists")

    invitation = MemberInvitation(
        business_id=business_id,
        email=email,
        role=body.role,
        token=secrets.token_urlsafe(48),
        invited_by=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db.add(invitation)
    await db.flush()

    await _emit_business_outbox_event(
        db,
        business_id=business_id,
        event_type=AuditEventType.MEMBER_INVITED,
        aggregate_type="member_invitation",
        aggregate_id=invitation.id,
        payload={
            "notification_title": "Member invited",
            "notification_body": (f"{email} was invited to join {business.name} as {body.role}."),
            "communication_targets": [
                {
                    "channel": "email",
                    "purpose": "member_invitation",
                    "recipient_address": email,
                    "recipient_type": "MEMBER",
                }
            ],
            "template_variables": {
                "business_name": business.name,
                "role": body.role,
                "invitation_token": invitation.token,
            },
        },
        idempotency_key=f"MEMBER_INVITED:member_invitation:{invitation.id}",
    )

    return MemberInvitationRead(
        id=str(invitation.id),
        business_id=str(invitation.business_id),
        email=invitation.email,
        role=invitation.role,
        expires_at=invitation.expires_at.isoformat(),
        created_at=invitation.created_at.isoformat(),
    )


@router.get(
    "/{business_id}/members/invitations",
    response_model=list[MemberInvitationRead],
)
async def list_member_invitations(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[MemberInvitationRead]:
    """List pending (unused, unexpired) member invitations."""
    await _get_user_business(business_id, user, db)

    now = datetime.now(UTC)
    result = await db.execute(
        select(MemberInvitation)
        .where(
            MemberInvitation.business_id == business_id,
            MemberInvitation.used_at.is_(None),
            MemberInvitation.expires_at > now,
            MemberInvitation.deleted_at.is_(None),
        )
        .order_by(MemberInvitation.created_at)
    )
    invitations = result.scalars().all()

    return [
        MemberInvitationRead(
            id=str(i.id),
            business_id=str(i.business_id),
            email=i.email,
            role=i.role,
            expires_at=i.expires_at.isoformat(),
            created_at=i.created_at.isoformat(),
        )
        for i in invitations
    ]


@router.patch("/{business_id}/members/{member_id}", response_model=MemberRead)
async def update_member_role(
    business_id: uuid.UUID,
    member_id: uuid.UUID,
    body: MemberRoleUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> MemberRead:
    """Change a member's role. Requires owner role."""
    _, membership = await _get_user_business(business_id, user, db)
    _check_minimum_role(membership, BusinessMemberRole.OWNER)

    result = await db.execute(
        select(BusinessMember)
        .where(
            BusinessMember.id == member_id,
            BusinessMember.business_id == business_id,
            BusinessMember.deleted_at.is_(None),
        )
        .options(selectinload(BusinessMember.user))
    )
    target_member = result.scalar_one_or_none()
    if target_member is None:
        raise NotFoundError("Member not found")

    new_role = BusinessMemberRole(body.role)

    # Guard: cannot demote the last owner
    if target_member.role == BusinessMemberRole.OWNER and new_role != BusinessMemberRole.OWNER:
        result = await db.execute(
            select(BusinessMember).where(
                BusinessMember.business_id == business_id,
                BusinessMember.role == BusinessMemberRole.OWNER,
                BusinessMember.deleted_at.is_(None),
            )
        )
        if len(result.scalars().all()) <= 1:
            raise ConflictError("Cannot demote the last owner of a business")

    previous_role = target_member.role
    target_member.role = new_role.value
    await db.flush()

    if previous_role != new_role.value:
        await _emit_business_outbox_event(
            db,
            business_id=business_id,
            event_type=AuditEventType.MEMBER_ROLE_CHANGED,
            aggregate_type="member",
            aggregate_id=target_member.id,
            payload={
                "notification_title": "Member role changed",
                "notification_body": (
                    f"{(target_member.user.email if target_member.user else target_member.user_id)}"
                    f" role changed from {previous_role} to {new_role.value}."
                ),
            },
            idempotency_key=(
                f"MEMBER_ROLE_CHANGED:member:{target_member.id}"
                f":{new_role.value}:{int(datetime.now(UTC).timestamp())}"
            ),
        )

    return MemberRead(
        id=str(target_member.id),
        user_id=str(target_member.user_id),
        business_id=str(target_member.business_id),
        role=target_member.role,
        user_email=target_member.user.email if target_member.user else None,
        created_at=target_member.created_at.isoformat(),
    )


@accept_router.post(
    "/members/accept-invitation/{token}",
    response_model=MemberRead,
    status_code=201,
)
async def accept_invitation(
    token: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> MemberRead:
    """Accept a pending member invitation.

    The signed-in user's email must match the invitation email. If the
    invited person has no account yet, they register first, then accept.
    """
    result = await db.execute(
        select(MemberInvitation).where(
            MemberInvitation.token == token,
            MemberInvitation.deleted_at.is_(None),
        )
    )
    invitation = result.scalar_one_or_none()
    if invitation is None:
        raise NotFoundError("Invitation not found")

    if invitation.is_used:
        raise ValidationError("Invitation has already been used")

    if invitation.is_expired:
        raise ValidationError("Invitation has expired")

    if user.email.strip().lower() != invitation.email:
        raise AuthorizationError("This invitation was issued to a different email address")

    # Already a member?
    result = await db.execute(
        select(BusinessMember).where(
            BusinessMember.user_id == user.id,
            BusinessMember.business_id == invitation.business_id,
            BusinessMember.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is not None:
        raise ConflictError("You are already a member of this business")

    new_member = BusinessMember(
        user_id=user.id,
        business_id=invitation.business_id,
        role=invitation.role,
    )
    db.add(new_member)
    invitation.used_at = datetime.now(UTC)
    await db.flush()

    await _emit_business_outbox_event(
        db,
        business_id=invitation.business_id,
        event_type=AuditEventType.MEMBER_ACCEPTED,
        aggregate_type="member_invitation",
        aggregate_id=invitation.id,
        payload={
            "notification_title": "Member joined",
            "notification_body": (f"{user.email} joined as {invitation.role}."),
        },
        idempotency_key=f"MEMBER_ACCEPTED:member_invitation:{invitation.id}",
    )

    return MemberRead(
        id=str(new_member.id),
        user_id=str(user.id),
        business_id=str(invitation.business_id),
        role=new_member.role,
        user_email=user.email,
        created_at=new_member.created_at.isoformat(),
    )
