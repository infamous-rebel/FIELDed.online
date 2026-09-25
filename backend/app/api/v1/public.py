"""Public business profile API endpoints.

These endpoints are accessible without authentication.
They expose ONLY intentionally public information.

Never expose:
- Business Brain internals
- Private rules / internal notes
- Private customer information
- Non-public staff information
- Audit records
- Internal pricing logic (pricing_config raw JSONB)
- Credentials / secrets
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from pydantic import BaseModel as _BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db_session
from app.domain.common.enums import BusinessProfileStatus, ServiceOfferStatus
from app.domain.identity.models import Business, BusinessProfile
from app.domain.services.models import ServiceOffer
from app.exceptions import NotFoundError


class PublicAvailabilityResponse(_BaseModel):
    """Customer-safe availability summary."""

    available: bool
    next_available: str | None = None  # ISO datetime or null
    lead_time_hours: int | None = None


router = APIRouter()


# --- Schemas ---


class PublicSocialLinks(BaseModel):
    website: str | None = None
    facebook: str | None = None
    instagram: str | None = None
    linkedin: str | None = None


class PublicBusinessProfile(BaseModel):
    """Public-facing business profile — only intentionally public fields."""

    name: str
    slug: str
    description: str | None = None
    phone: str | None = None
    email: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    service_area: dict[str, Any] | None = None
    social_links: PublicSocialLinks | None = None
    logo_url: str | None = None
    cover_image_url: str | None = None
    is_verified: bool = False
    average_rating: float | None = None
    review_count: int = 0


class PublicPricingSummary(BaseModel):
    """Customer-visible pricing summary — derived from pricing_config, never raw JSONB."""

    pricing_model: str
    starting_price: str | None = None
    hourly_rate: str | None = None
    fixed_price: str | None = None
    currency: str | None = None


class PublicServiceOffer(BaseModel):
    """Public-facing service offer — only ACTIVE offers are visible."""

    id: str
    name: str
    slug: str
    description: str | None = None
    delivery_mode: str
    pricing_model: str
    category_name: str | None = None
    category_slug: str | None = None


class PublicServiceOfferDetail(PublicServiceOffer):
    """Detailed public service offer with pricing summary and business context."""

    business_id: str  # Business UUID — minimum identifier for enquiry creation
    business_name: str
    business_slug: str
    business_is_verified: bool = False
    pricing_summary: PublicPricingSummary | None = None
    service_area: dict[str, Any] | None = None
    qualification_requirements: dict[str, Any] | None = None


class PublicBusinessDetail(PublicBusinessProfile):
    """Full public business page including active service offers."""

    id: str  # Business UUID — minimum identifier for enquiry creation
    service_offers: list[PublicServiceOffer] = []
    active_offer_count: int = 0


class PublicBusinessDirectoryItem(BaseModel):
    """Compact business listing for the network directory."""

    name: str
    slug: str
    description: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    logo_url: str | None = None
    is_verified: bool = False
    average_rating: float | None = None
    review_count: int = 0
    active_offer_count: int = 0
    top_categories: list[str] = []


class PublicBusinessDirectoryResponse(BaseModel):
    """Paginated directory of active public businesses."""

    businesses: list[PublicBusinessDirectoryItem] = []
    total: int = 0
    limit: int = 20
    offset: int = 0


# --- Helpers ---


def _build_pricing_summary(offer: ServiceOffer, currency: str | None = None) -> PublicPricingSummary | None:
    """Derive a customer-visible pricing summary from pricing_config.

    Never exposes raw JSONB — only extracts safe display values.
    """
    config = offer.pricing_config
    if not config:
        return PublicPricingSummary(pricing_model=offer.pricing_model, currency=currency)

    return PublicPricingSummary(
        pricing_model=offer.pricing_model,
        starting_price=config.get("starting_price") or config.get("starting_at"),
        hourly_rate=config.get("hourly_rate") or config.get("rate"),
        fixed_price=config.get("fixed_price") or config.get("price") or config.get("amount"),
        currency=currency,
    )


def _build_public_profile(business: Business) -> PublicBusinessDetail:
    """Build a public business profile from the model, filtering safe fields only."""
    profile = business.profile
    social_links = None
    if profile:
        social_links = PublicSocialLinks(
            website=profile.website,
            facebook=profile.facebook_url,
            instagram=profile.instagram_url,
            linkedin=profile.linkedin_url,
        )

    # Collect only ACTIVE service offers
    active_offers = [
        offer
        for offer in (business.service_offers or [])
        if offer.status == ServiceOfferStatus.ACTIVE and offer.deleted_at is None
    ]

    service_offers = [
        PublicServiceOffer(
            id=str(offer.id),
            name=offer.name,
            slug=offer.slug,
            description=offer.description,
            delivery_mode=offer.delivery_mode,
            pricing_model=offer.pricing_model,
            category_name=offer.category.name if offer.category else None,
            category_slug=offer.category.slug if offer.category else None,
        )
        for offer in active_offers
    ]

    return PublicBusinessDetail(
        id=str(business.id),
        name=business.name,
        slug=business.slug,
        description=profile.description if profile else None,
        phone=profile.phone if profile else None,
        email=profile.email if profile else None,
        city=profile.city if profile else None,
        state=profile.state if profile else None,
        country=profile.country if profile else None,
        service_area=profile.service_area if profile else None,
        social_links=social_links,
        logo_url=profile.logo_url if profile else None,
        cover_image_url=profile.cover_image_url if profile else None,
        is_verified=profile.is_verified if profile else False,
        average_rating=profile.average_rating if profile else None,
        review_count=profile.review_count if profile else 0,
        service_offers=service_offers,
        active_offer_count=len(service_offers),
    )


# --- Endpoints ---


@router.get(
    "/business/{slug}",
    response_model=PublicBusinessDetail,
)
async def get_public_business_profile(
    slug: str,
    db: AsyncSession = Depends(get_db_session),
) -> PublicBusinessDetail:
    """Get the public business profile by slug.

    Only exposes intentionally public information.
    Only returns businesses with an ACTIVE public profile status.
    """
    result = await db.execute(
        select(Business)
        .where(
            Business.slug == slug,
            Business.deleted_at.is_(None),
            Business.status.in_(["active", "pending"]),
        )
        .options(
            selectinload(Business.profile),
            selectinload(Business.service_offers).selectinload(ServiceOffer.category),
        )
    )
    business = result.scalar_one_or_none()
    if business is None:
        raise NotFoundError("Business not found")

    # Only expose if public profile is active
    if business.profile and business.profile.public_status != BusinessProfileStatus.ACTIVE:
        raise NotFoundError("Business not found")

    return _build_public_profile(business)


@router.get(
    "/business/{slug}/services",
    response_model=list[PublicServiceOffer],
)
async def get_public_business_services(
    slug: str,
    db: AsyncSession = Depends(get_db_session),
) -> list[PublicServiceOffer]:
    """Get only ACTIVE service offers for a public business."""
    result = await db.execute(
        select(Business)
        .where(
            Business.slug == slug,
            Business.deleted_at.is_(None),
            Business.status.in_(["active", "pending"]),
        )
        .options(selectinload(Business.profile))
    )
    business = result.scalar_one_or_none()
    if business is None:
        raise NotFoundError("Business not found")

    if business.profile and business.profile.public_status != BusinessProfileStatus.ACTIVE:
        raise NotFoundError("Business not found")

    # Fetch active offers
    offers_result = await db.execute(
        select(ServiceOffer)
        .where(
            ServiceOffer.business_id == business.id,
            ServiceOffer.status == ServiceOfferStatus.ACTIVE,
            ServiceOffer.deleted_at.is_(None),
        )
        .options(selectinload(ServiceOffer.category))
        .order_by(ServiceOffer.name)
    )
    offers = offers_result.scalars().all()

    return [
        PublicServiceOffer(
            id=str(o.id),
            name=o.name,
            slug=o.slug,
            description=o.description,
            delivery_mode=o.delivery_mode,
            pricing_model=o.pricing_model,
            category_name=o.category.name if o.category else None,
            category_slug=o.category.slug if o.category else None,
        )
        for o in offers
    ]


@router.get(
    "/business/{slug}/services/{offer_slug}",
    response_model=PublicServiceOfferDetail,
)
async def get_public_service_detail(
    slug: str,
    offer_slug: str,
    db: AsyncSession = Depends(get_db_session),
) -> PublicServiceOfferDetail:
    """Get a single ACTIVE service offer with full public detail.

    Requires the business to have an ACTIVE public profile.
    Only ACTIVE offers are accessible.
    """
    result = await db.execute(
        select(Business)
        .where(
            Business.slug == slug,
            Business.deleted_at.is_(None),
            Business.status.in_(["active", "pending"]),
        )
        .options(selectinload(Business.profile))
    )
    business = result.scalar_one_or_none()
    if business is None:
        raise NotFoundError("Business not found")

    if business.profile and business.profile.public_status != BusinessProfileStatus.ACTIVE:
        raise NotFoundError("Business not found")

    # Fetch the specific active offer
    offer_result = await db.execute(
        select(ServiceOffer)
        .where(
            ServiceOffer.business_id == business.id,
            ServiceOffer.slug == offer_slug,
            ServiceOffer.status == ServiceOfferStatus.ACTIVE,
            ServiceOffer.deleted_at.is_(None),
        )
        .options(selectinload(ServiceOffer.category))
    )
    offer = offer_result.scalar_one_or_none()
    if offer is None:
        raise NotFoundError("Service offer not found")

    profile = business.profile
    currency = business.currency if hasattr(business, "currency") else None

    return PublicServiceOfferDetail(
        id=str(offer.id),
        name=offer.name,
        slug=offer.slug,
        description=offer.description,
        delivery_mode=offer.delivery_mode,
        pricing_model=offer.pricing_model,
        category_name=offer.category.name if offer.category else None,
        category_slug=offer.category.slug if offer.category else None,
        business_id=str(business.id),
        business_name=business.name,
        business_slug=business.slug,
        business_is_verified=profile.is_verified if profile else False,
        pricing_summary=_build_pricing_summary(offer, currency),
        service_area=offer.service_area,
        qualification_requirements=offer.qualification_requirements,
    )


@router.get(
    "/businesses",
    response_model=PublicBusinessDirectoryResponse,
)
async def list_public_businesses(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    city: str | None = Query(default=None, max_length=100),
    state: str | None = Query(default=None, max_length=100),
    country: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None, max_length=255),
    search: str | None = Query(default=None, max_length=200, description="Text search across name and description"),
    min_rating: float | None = Query(default=None, ge=0, le=5, description="Minimum average rating"),
    verified_only: bool = Query(default=False, description="Only verified businesses"),
    delivery_mode: str | None = Query(default=None, max_length=50, description="Filter by service delivery mode"),
    pricing_model: str | None = Query(default=None, max_length=50, description="Filter by pricing model"),
    sort: str = Query(default="name", description="Sort order: name, rating, newest, review_count"),
    db: AsyncSession = Depends(get_db_session),
) -> PublicBusinessDirectoryResponse:
    """Browse active public businesses — the FIELDed network directory.

    Returns paginated businesses with active public profiles.
    Supports advanced filtering: location, category, text search,
    rating, verification status, delivery mode, pricing model.
    Supports sorting by name, rating, newest, or review count.
    """
    # Base query: active businesses with active public profiles
    base_query = (
        select(Business)
        .join(BusinessProfile, BusinessProfile.business_id == Business.id)
        .where(
            Business.status.in_(["active", "pending"]),
            Business.deleted_at.is_(None),
            BusinessProfile.public_status == BusinessProfileStatus.ACTIVE,
            BusinessProfile.deleted_at.is_(None),
        )
    )

    # Apply location filters
    if city:
        base_query = base_query.where(func.lower(BusinessProfile.city) == func.lower(city))
    if state:
        base_query = base_query.where(func.lower(BusinessProfile.state) == func.lower(state))
    if country:
        base_query = base_query.where(func.lower(BusinessProfile.country) == func.lower(country))

    # Text search across name and description
    if search:
        search_pattern = f"%{search.lower()}%"
        base_query = base_query.where(
            (func.lower(Business.name).ilike(search_pattern))
            | (func.lower(BusinessProfile.description).ilike(search_pattern))
        )

    # Verified only
    if verified_only:
        base_query = base_query.where(BusinessProfile.is_verified.is_(True))

    # Minimum rating filter
    if min_rating is not None:
        base_query = base_query.where(
            BusinessProfile.average_rating.isnot(None),
            BusinessProfile.average_rating >= min_rating,
        )

    # Count total before pagination
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Sort order
    if sort == "rating":
        order_clause = BusinessProfile.average_rating.desc().nullslast()
    elif sort == "newest":
        order_clause = Business.created_at.desc()
    elif sort == "review_count":
        order_clause = BusinessProfile.review_count.desc().nullslast()
    else:
        order_clause = Business.name.asc()

    # Paginate
    result = await db.execute(
        base_query.options(
            selectinload(Business.profile),
            selectinload(Business.service_offers).selectinload(ServiceOffer.category),
        )
        .order_by(order_clause)
        .offset(offset)
        .limit(limit)
    )
    businesses_list = result.scalars().all()

    items = []
    for biz in businesses_list:
        profile = biz.profile
        active_offers = [
            o for o in (biz.service_offers or []) if o.status == ServiceOfferStatus.ACTIVE and o.deleted_at is None
        ]

        # Extract top categories from active offers
        category_names: list[str] = []
        seen_cats: set[str] = set()
        for o in active_offers:
            if o.category and o.category.name not in seen_cats:
                category_names.append(o.category.name)
                seen_cats.add(o.category.name)

        # If filtering by category, only include businesses with matching offers
        if category:
            matching = [o for o in active_offers if o.category and o.category.slug == category]
            if not matching:
                continue

        # If filtering by delivery_mode, only include businesses with matching offers
        if delivery_mode:
            matching_dm = [o for o in active_offers if o.delivery_mode == delivery_mode]
            if not matching_dm:
                continue

        # If filtering by pricing_model, only include businesses with matching offers
        if pricing_model:
            matching_pm = [o for o in active_offers if o.pricing_model == pricing_model]
            if not matching_pm:
                continue

        items.append(
            PublicBusinessDirectoryItem(
                name=biz.name,
                slug=biz.slug,
                description=profile.description if profile else None,
                city=profile.city if profile else None,
                state=profile.state if profile else None,
                country=profile.country if profile else None,
                logo_url=profile.logo_url if profile else None,
                is_verified=profile.is_verified if profile else False,
                average_rating=profile.average_rating if profile else None,
                review_count=profile.review_count if profile else 0,
                active_offer_count=len(active_offers),
                top_categories=category_names[:5],
            )
        )

    return PublicBusinessDirectoryResponse(
        businesses=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/business/{slug}/availability",
    response_model=PublicAvailabilityResponse,
)
async def get_public_availability(
    slug: str,
    service_offer_id: str | None = Query(None, description="Service offer ID"),
    db: AsyncSession = Depends(get_db_session),
) -> PublicAvailabilityResponse:
    """Get customer-safe availability information for a business.

    Reuses the existing AvailabilityEvaluator. Never exposes raw Brain
    rules, internal staff info, or JSONB config.
    """
    from app.domain.booking.service import BookingService

    # 1. Resolve business by slug
    result = await db.execute(
        select(Business)
        .where(
            Business.slug == slug,
            Business.deleted_at.is_(None),
            Business.status.in_(["active", "pending"]),
        )
        .options(selectinload(Business.profile))
    )
    business = result.scalar_one_or_none()
    if business is None:
        raise NotFoundError("Business not found")

    if business.profile and business.profile.public_status != BusinessProfileStatus.ACTIVE:
        raise NotFoundError("Business not found")

    # 2. If no service_offer_id, return general availability
    if not service_offer_id:
        return PublicAvailabilityResponse(
            available=True,
            next_available=None,
            lead_time_hours=None,
        )

    # 3. Verify service offer is ACTIVE
    import uuid as _uuid

    try:
        offer_uuid = _uuid.UUID(service_offer_id)
    except ValueError:
        raise NotFoundError("Invalid service offer ID") from None

    offer_result = await db.execute(
        select(ServiceOffer).where(
            ServiceOffer.id == offer_uuid,
            ServiceOffer.business_id == business.id,
            ServiceOffer.status == ServiceOfferStatus.ACTIVE,
            ServiceOffer.deleted_at.is_(None),
        )
    )
    offer = offer_result.scalar_one_or_none()
    if offer is None:
        raise NotFoundError("Service offer not found")

    # 4. Use existing BookingService.check_availability
    booking_service = BookingService(db)
    now = datetime.now(UTC)
    # Check availability for 1 hour from now as a reasonable default
    check_time = now + timedelta(hours=1)

    availability = await booking_service.check_availability(
        business_id=business.id,
        service_offer_id=offer.id,
        requested_at=check_time,
    )

    # 5. Return only customer-safe information
    lead_time = None
    next_available = None
    if availability.available:
        next_available = check_time.isoformat()
        # Extract lead time from brain rules if available
        for rule in availability.matched_rules:
            min_notice = rule.get("min_notice_hours")
            if min_notice is not None:
                lead_time = int(min_notice)
                break

    return PublicAvailabilityResponse(
        available=availability.available,
        next_available=next_available,
        lead_time_hours=lead_time,
    )
