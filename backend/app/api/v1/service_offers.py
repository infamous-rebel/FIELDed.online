"""Service Offer API endpoints.

Provides CRUD and lifecycle management for service offers.
All endpoints enforce tenant isolation — only authorized business
members can manage their business's service offers.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db_session
from app.domain.common.enums import (
    BusinessMemberRole,
    ServiceOfferStatus,
    SERVICE_OFFER_TRANSITIONS,
)
from app.domain.identity.models import Business, BusinessMember, User
from app.domain.services.models import ServiceOffer
from app.domain.services.schemas import (
    ServiceOfferCreate,
    ServiceOfferRead,
    ServiceOfferTransitionRequest,
    ServiceOfferUpdate,
)
from app.exceptions import AuthorizationError, NotFoundError, StateTransitionError
from app.security.authorization import get_current_user

router = APIRouter()


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


async def _get_business_offer(
    business_id: uuid.UUID,
    offer_id: uuid.UUID,
    db: AsyncSession,
) -> ServiceOffer:
    """Get a service offer, verifying it belongs to the specified business."""
    result = await db.execute(
        select(ServiceOffer)
        .where(
            ServiceOffer.id == offer_id,
            ServiceOffer.business_id == business_id,
            ServiceOffer.deleted_at.is_(None),
        )
        .options(selectinload(ServiceOffer.category))
    )
    offer = result.scalar_one_or_none()
    if offer is None:
        raise NotFoundError("Service offer not found")
    return offer


def _offer_to_read(offer: ServiceOffer) -> ServiceOfferRead:
    """Convert a ServiceOffer model to the read schema."""
    return ServiceOfferRead(
        id=offer.id,
        business_id=offer.business_id,
        category_id=offer.category_id,
        name=offer.name,
        slug=offer.slug,
        description=offer.description,
        delivery_mode=offer.delivery_mode,
        pricing_model=offer.pricing_model,
        pricing_config=offer.pricing_config,
        qualification_requirements=offer.qualification_requirements,
        booking_rules=offer.booking_rules,
        cancellation_policy=offer.cancellation_policy,
        service_area=offer.service_area,
        status=offer.status,
        created_at=offer.created_at,
        updated_at=offer.updated_at,
    )


# --- Endpoints ---


@router.post(
    "/{business_id}/offers",
    response_model=ServiceOfferRead,
    status_code=201,
)
async def create_service_offer(
    business_id: uuid.UUID,
    body: ServiceOfferCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ServiceOfferRead:
    """Create a new service offer. Requires admin+ role."""
    _, membership = await _get_user_business(business_id, user, db)
    _check_minimum_role(membership, BusinessMemberRole.ADMIN)

    from app.domain.services.service import ServiceOfferService
    service = ServiceOfferService(db)

    offer = await service.create_offer(
        business_id=business_id,
        name=body.name,
        category_id=body.category_id,
        description=body.description,
        delivery_mode=body.delivery_mode,
        pricing_model=body.pricing_model,
        pricing_config=body.pricing_config,
        qualification_requirements=body.qualification_requirements,
        booking_rules=body.booking_rules,
        cancellation_policy=body.cancellation_policy,
        service_area=body.service_area,
    )

    return _offer_to_read(offer)


@router.get("/{business_id}/offers", response_model=list[ServiceOfferRead])
async def list_service_offers(
    business_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[ServiceOfferRead]:
    """List all service offers for a business. Any member can read."""
    await _get_user_business(business_id, user, db)

    result = await db.execute(
        select(ServiceOffer)
        .where(
            ServiceOffer.business_id == business_id,
            ServiceOffer.deleted_at.is_(None),
        )
        .options(selectinload(ServiceOffer.category))
        .order_by(ServiceOffer.name)
    )
    offers = result.scalars().all()

    return [_offer_to_read(o) for o in offers]


@router.get("/{business_id}/offers/{offer_id}", response_model=ServiceOfferRead)
async def get_service_offer(
    business_id: uuid.UUID,
    offer_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ServiceOfferRead:
    """Get a specific service offer. Any member can read."""
    await _get_user_business(business_id, user, db)
    offer = await _get_business_offer(business_id, offer_id, db)
    return _offer_to_read(offer)


@router.put("/{business_id}/offers/{offer_id}", response_model=ServiceOfferRead)
async def update_service_offer(
    business_id: uuid.UUID,
    offer_id: uuid.UUID,
    body: ServiceOfferUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ServiceOfferRead:
    """Update a service offer. Requires admin+ role."""
    _, membership = await _get_user_business(business_id, user, db)
    _check_minimum_role(membership, BusinessMemberRole.ADMIN)

    offer = await _get_business_offer(business_id, offer_id, db)

    from app.domain.services.service import ServiceOfferService
    service = ServiceOfferService(db)

    update_data = body.model_dump(exclude_unset=True)
    await service.update_offer(offer, **update_data)

    # Refresh to reload attributes expired by the flush
    await db.refresh(offer)
    return _offer_to_read(offer)


@router.post(
    "/{business_id}/offers/{offer_id}/transition",
    response_model=ServiceOfferRead,
)
async def transition_service_offer(
    business_id: uuid.UUID,
    offer_id: uuid.UUID,
    body: ServiceOfferTransitionRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ServiceOfferRead:
    """Transition a service offer's lifecycle status. Requires admin+ role.

    Valid transitions:
    - DRAFT -> ACTIVE, ARCHIVED
    - ACTIVE -> PAUSED, ARCHIVED
    - PAUSED -> ACTIVE, ARCHIVED
    - ARCHIVED -> (terminal)
    """
    _, membership = await _get_user_business(business_id, user, db)
    _check_minimum_role(membership, BusinessMemberRole.ADMIN)

    offer = await _get_business_offer(business_id, offer_id, db)

    from app.domain.services.service import ServiceOfferService
    service = ServiceOfferService(db)

    target_status = ServiceOfferStatus(body.target_status)
    await service.transition_offer(offer, target_status)

    # Refresh to reload attributes expired by the flush
    await db.refresh(offer)
    return _offer_to_read(offer)
