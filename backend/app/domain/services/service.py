"""Service Offer domain service.

Contains business logic for service category and service offer management.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.common.enums import (
    SERVICE_OFFER_TRANSITIONS,
    DeliveryMode,
    PricingModel,
    ServiceOfferStatus,
)
from app.domain.services.models import ServiceCategory, ServiceOffer
from app.domain.services.repository import (
    ServiceCategoryRepository,
    ServiceOfferRepository,
)
from app.exceptions import ConflictError, NotFoundError, StateTransitionError, ValidationError


class ServiceCategoryService:
    """Service category management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.category_repo = ServiceCategoryRepository(session)

    async def create_category(
        self,
        name: str,
        slug: str,
        description: str | None = None,
        parent_id: uuid.UUID | None = None,
    ) -> ServiceCategory:
        """Create a new service category."""
        existing = await self.category_repo.get_by_slug(slug)
        if existing is not None:
            raise ConflictError(f"Service category with slug '{slug}' already exists")

        # Validate parent exists if provided
        if parent_id is not None:
            parent = await self.category_repo.get_by_id(parent_id)
            if parent is None:
                raise NotFoundError("Parent category not found")

        category = ServiceCategory(
            name=name,
            slug=slug,
            description=description,
            parent_id=parent_id,
        )
        return await self.category_repo.create(category)

    async def get_all_categories(self) -> list[ServiceCategory]:
        """Get all categories."""
        return await self.category_repo.get_all()

    async def get_root_categories(self) -> list[ServiceCategory]:
        """Get top-level categories only."""
        return await self.category_repo.get_root_categories()

    async def get_category(self, category_id: uuid.UUID) -> ServiceCategory:
        """Get a single category by ID."""
        category = await self.category_repo.get_by_id(category_id)
        if category is None:
            raise NotFoundError("Service category not found")
        return category

    async def get_category_by_slug(self, slug: str) -> ServiceCategory:
        """Get a single category by slug."""
        category = await self.category_repo.get_by_slug(slug)
        if category is None:
            raise NotFoundError("Service category not found")
        return category


def _generate_slug(name: str) -> str:
    """Generate a URL-friendly slug from a name."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug)
    return slug.strip("-")


class ServiceOfferService:
    """Service offer management with lifecycle control."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.offer_repo = ServiceOfferRepository(session)
        self.category_repo = ServiceCategoryRepository(session)

    async def create_offer(
        self,
        business_id: uuid.UUID,
        name: str,
        category_id: uuid.UUID | None = None,
        description: str | None = None,
        delivery_mode: str = "on_site",
        pricing_model: str = "quote_required",
        pricing_config: dict | None = None,
        qualification_requirements: dict | None = None,
        booking_rules: dict | None = None,
        cancellation_policy: dict | None = None,
        service_area: dict | None = None,
    ) -> ServiceOffer:
        """Create a new service offer in DRAFT status."""
        # Validate delivery mode
        try:
            DeliveryMode(delivery_mode)
        except ValueError:
            raise ValidationError(f"Invalid delivery mode: {delivery_mode}") from None

        # Validate pricing model
        try:
            PricingModel(pricing_model)
        except ValueError:
            raise ValidationError(f"Invalid pricing model: {pricing_model}") from None

        # Validate category exists if provided
        if category_id is not None:
            category = await self.category_repo.get_by_id(category_id)
            if category is None:
                raise NotFoundError("Service category not found")

        slug = _generate_slug(name)

        offer = ServiceOffer(
            business_id=business_id,
            name=name,
            slug=slug,
            description=description,
            delivery_mode=delivery_mode,
            pricing_model=pricing_model,
            pricing_config=pricing_config,
            qualification_requirements=qualification_requirements,
            booking_rules=booking_rules,
            cancellation_policy=cancellation_policy,
            service_area=service_area,
            category_id=category_id,
            status=ServiceOfferStatus.DRAFT,
        )
        return await self.offer_repo.create(offer)

    async def get_offer(self, offer_id: uuid.UUID) -> ServiceOffer:
        """Get a service offer by ID."""
        offer = await self.offer_repo.get_by_id(offer_id)
        if offer is None:
            raise NotFoundError("Service offer not found")
        return offer

    async def get_business_offers(self, business_id: uuid.UUID) -> list[ServiceOffer]:
        """Get all service offers for a business."""
        return await self.offer_repo.get_by_business_id(business_id)

    async def get_active_offers_for_business(self, business_id: uuid.UUID) -> list[ServiceOffer]:
        """Get only ACTIVE service offers for public display."""
        return await self.offer_repo.get_by_business_and_status(business_id, ServiceOfferStatus.ACTIVE)

    async def update_offer(
        self,
        offer: ServiceOffer,
        **fields: object,
    ) -> ServiceOffer:
        """Update a service offer's fields.

        Only allows updates to mutable fields.
        Status changes must go through transition_offer().
        """
        allowed_fields = {
            "name",
            "description",
            "delivery_mode",
            "pricing_model",
            "pricing_config",
            "qualification_requirements",
            "booking_rules",
            "cancellation_policy",
            "service_area",
            "category_id",
        }
        for field, value in fields.items():
            if field not in allowed_fields:
                raise ValidationError(f"Cannot update field: {field}")
            if field == "category_id" and value is not None:
                category = await self.category_repo.get_by_id(value)  # type: ignore[arg-type]
                if category is None:
                    raise NotFoundError("Service category not found")
            if field == "delivery_mode" and value is not None:
                try:
                    DeliveryMode(value)  # type: ignore[arg-type]
                except ValueError:
                    raise ValidationError(f"Invalid delivery mode: {value}") from None
            if field == "pricing_model" and value is not None:
                try:
                    PricingModel(value)  # type: ignore[arg-type]
                except ValueError:
                    raise ValidationError(f"Invalid pricing model: {value}") from None
            setattr(offer, field, value)

        # Regenerate slug if name changed
        if "name" in fields:
            offer.slug = _generate_slug(offer.name)

        return await self.offer_repo.update(offer)

    async def transition_offer(
        self,
        offer: ServiceOffer,
        target_status: ServiceOfferStatus,
    ) -> ServiceOffer:
        """Transition a service offer to a new status.

        Validates the transition against the state machine.
        """
        current = ServiceOfferStatus(offer.status)
        allowed = SERVICE_OFFER_TRANSITIONS.get(current, set())

        if target_status not in allowed:
            raise StateTransitionError(
                f"Cannot transition from '{current.value}' to '{target_status.value}'. "
                f"Allowed: {[s.value for s in allowed] or 'none (terminal state)'}"
            )

        offer.status = target_status
        return await self.offer_repo.update(offer)

    async def search_offers(
        self,
        *,
        category_id: uuid.UUID | None = None,
    ) -> list[ServiceOffer]:
        """Search active service offers (for future discovery engine)."""
        return await self.offer_repo.search(category_id=category_id)
