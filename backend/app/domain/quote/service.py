"""Quote domain service.

Contains business logic for quote creation (pricing calculation),
lifecycle transitions, and authorization enforcement.

The quote creation flow:
    1. Resolve enquiry (server-side, tenant-verified)
    2. Resolve active BrainVersion (if any)
    3. Run deterministic pricing engine
    4. Persist Quote with full BrainVersion traceability
    5. Transition enquiry to QUOTED
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.business.evaluator import BrainEvaluator, DecisionContext
from app.domain.business.models import BrainVersion, BusinessBrain
from app.domain.business.repository import BusinessBrainRepository, BrainVersionRepository
from app.domain.common.enums import (
    EnquiryStatus,
    QuoteStatus,
    QUOTE_TRANSITIONS,
    ServiceOfferStatus,
)
from app.domain.enquiry.models import Enquiry
from app.domain.enquiry.repository import EnquiryRepository
from app.domain.identity.models import Business
from app.domain.outbox.models import OutboxEvent
from app.domain.quote.models import Quote
from app.domain.quote.pricing import PricingEngine, PricingResult
from app.domain.quote.repository import QuoteRepository
from app.domain.services.models import ServiceOffer
from app.exceptions import (
    AuthorizationError,
    NotFoundError,
    StateTransitionError,
    ValidationError,
)
from app.logging import get_logger

logger = get_logger(__name__)


def _generate_reference() -> str:
    """Generate a customer-friendly quote reference number."""
    return f"QUO-{uuid.uuid4().hex[:8]}"


class QuoteService:
    """Quote lifecycle management with Brain-governed pricing."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.quote_repo = QuoteRepository(session)
        self.enquiry_repo = EnquiryRepository(session)
        self._pricing_engine = PricingEngine()

    # --- Quote creation (business-side) ---

    async def create_quote(
        self,
        *,
        business_id: uuid.UUID,
        enquiry_id: uuid.UUID,
        notes: str | None = None,
    ) -> Quote:
        """Create a quote for an enquiry.

        The business creates a quote after reviewing the enquiry.
        The pricing is calculated deterministically from:
        - ServiceOffer.pricing_config (base pricing)
        - Active BrainVersion pricing rules (surcharges, discounts, floors, caps)

        The enquiry must be in a quotable state (IN_REVIEW or RECEIVED).
        """
        # 1. Resolve and validate the enquiry
        enquiry = await self._resolve_enquiry(enquiry_id, business_id)

        # 2. Verify enquiry is in a quotable state
        quotable_states = {
            EnquiryStatus.RECEIVED,
            EnquiryStatus.IN_REVIEW,
            EnquiryStatus.NEEDS_INFORMATION,
        }
        if EnquiryStatus(enquiry.status) not in quotable_states:
            raise ValidationError(
                f"Enquiry is in '{enquiry.status}' state and cannot be quoted. "
                f"Quotable states: {[s.value for s in quotable_states]}"
            )

        # 3. Resolve the service offer
        service_offer = await self._resolve_service_offer(enquiry.service_offer_id)

        # 4. Resolve the business (for currency)
        business = await self._resolve_business(business_id)

        # 5. Resolve the active BrainVersion (if any)
        brain_version = await self._resolve_active_brain_version(business_id)

        # 6. Build the pricing context
        context = DecisionContext(
            business_id=business_id,
            service_offer_id=service_offer.id,
            customer_id=enquiry.customer_id,
            context_data={
                "business_id": str(business_id),
                "service_offer_id": str(service_offer.id),
                "customer_id": str(enquiry.customer_id),
                "service_offer": {
                    "pricing_model": service_offer.pricing_model,
                    "delivery_mode": service_offer.delivery_mode,
                    "name": service_offer.name,
                },
            },
        )

        # 7. Calculate pricing
        try:
            pricing_result = self._pricing_engine.calculate(
                service_offer=service_offer,
                brain_version=brain_version,
                context=context,
                business_currency=business.currency,
            )
        except ValueError as exc:
            raise ValidationError(f"Pricing calculation failed: {exc}")

        # 8. Handle quote_required pricing model
        if service_offer.pricing_model == "quote_required" and pricing_result.amount == Decimal("0"):
            raise ValidationError(
                "This service requires a manual quote. "
                "Please set a custom amount in the pricing configuration."
            )

        # 9. Create the quote
        quote = Quote(
            reference=_generate_reference(),
            customer_id=enquiry.customer_id,
            business_id=business_id,
            enquiry_id=enquiry.id,
            service_offer_id=service_offer.id,
            amount=str(pricing_result.amount),
            currency=pricing_result.currency,
            status=QuoteStatus.DRAFT,
            brain_version_id=brain_version.id if brain_version else None,
            pricing_evidence=pricing_result.to_evidence_dict(),
            notes=notes,
        )
        quote = await self.quote_repo.create(quote)

        # 10. Transition enquiry to QUOTED
        enquiry.status = EnquiryStatus.QUOTED
        await self.enquiry_repo.update(enquiry)

        logger.info(
            "quote_created",
            quote_id=str(quote.id),
            reference=quote.reference,
            enquiry_id=str(enquiry.id),
            business_id=str(business_id),
            amount=str(pricing_result.amount),
            currency=pricing_result.currency,
            brain_version_id=str(brain_version.id) if brain_version else None,
        )

        return quote

    # --- Quote lifecycle ---

    async def transition_quote(
        self,
        quote: Quote,
        target_status: QuoteStatus,
        *,
        actor: str = "business",
    ) -> Quote:
        """Transition a quote to a new status.

        Validates the transition against the state machine.
        - Business can issue/expire quotes.
        - Customer can accept/decline quotes.
        """
        current = QuoteStatus(quote.status)
        allowed = QUOTE_TRANSITIONS.get(current, set())

        if target_status not in allowed:
            raise StateTransitionError(
                f"Cannot transition quote from '{current.value}' to "
                f"'{target_status.value}'. "
                f"Allowed: {[s.value for s in allowed] or 'none (terminal state)'}"
            )

        # Actor-specific authority
        if actor == "customer" and target_status not in {
            QuoteStatus.ACCEPTED, QuoteStatus.DECLINED
        }:
            raise AuthorizationError(
                "Customers can only accept or decline quotes"
            )
        if actor == "business" and target_status not in {
            QuoteStatus.ISSUED, QuoteStatus.EXPIRED
        }:
            raise AuthorizationError(
                "Business can only issue or expire quotes"
            )

        old_status = quote.status
        quote.status = target_status
        result = await self.quote_repo.update(quote)

        # Emit outbox event for communication pipeline
        await self._emit_outbox_event(
            business_id=quote.business_id,
            event_type=f"QUOTE_{target_status.value.upper()}",
            aggregate_id=quote.id,
            payload={
                "quote_id": str(quote.id),
                "enquiry_id": str(quote.enquiry_id),
                "customer_id": str(quote.customer_id),
                "status": target_status.value,
                "quote_reference": quote.reference,
            },
        )

        logger.info(
            "quote_transition",
            quote_id=str(quote.id),
            actor=actor,
            from_status=old_status,
            to_status=target_status.value,
        )

        return result

    # --- Retrieval ---

    async def get_quote(self, quote_id: uuid.UUID) -> Quote:
        """Get a quote by ID."""
        quote = await self.quote_repo.get_by_id(quote_id)
        if quote is None:
            raise NotFoundError("Quote not found")
        return quote

    async def get_customer_quote(
        self, quote_id: uuid.UUID, customer_id: uuid.UUID
    ) -> Quote:
        """Get a quote, verifying customer ownership."""
        quote = await self.get_quote(quote_id)
        if quote.customer_id != customer_id:
            raise AuthorizationError("Not your quote")
        return quote

    async def get_business_quote(
        self, quote_id: uuid.UUID, business_id: uuid.UUID
    ) -> Quote:
        """Get a quote, verifying it belongs to the business."""
        quote = await self.get_quote(quote_id)
        if quote.business_id != business_id:
            raise AuthorizationError("Quote does not belong to this business")
        return quote

    async def list_customer_quotes(
        self,
        customer_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Quote]:
        """List quotes for a customer."""
        return await self.quote_repo.get_by_customer(
            customer_id, status=status, limit=limit, offset=offset
        )

    async def list_business_quotes(
        self,
        business_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Quote]:
        """List quotes for a business."""
        return await self.quote_repo.get_by_business(
            business_id, status=status, limit=limit, offset=offset
        )

    # --- Internal helpers ---

    async def _resolve_enquiry(
        self, enquiry_id: uuid.UUID, business_id: uuid.UUID
    ) -> Enquiry:
        """Resolve and validate an enquiry for quote creation."""
        enquiry = await self.enquiry_repo.get_by_id(enquiry_id)
        if enquiry is None:
            raise NotFoundError("Enquiry not found")
        if enquiry.business_id != business_id:
            raise AuthorizationError("Enquiry does not belong to this business")
        return enquiry

    async def _resolve_service_offer(
        self, service_offer_id: uuid.UUID
    ) -> ServiceOffer:
        """Resolve a service offer."""
        from sqlalchemy import select
        result = await self.session.execute(
            select(ServiceOffer).where(
                ServiceOffer.id == service_offer_id,
                ServiceOffer.deleted_at.is_(None),
            )
        )
        offer = result.scalar_one_or_none()
        if offer is None:
            raise NotFoundError("Service offer not found")
        return offer

    async def _resolve_business(self, business_id: uuid.UUID) -> Business:
        """Resolve a business entity."""
        from sqlalchemy import select
        result = await self.session.execute(
            select(Business).where(
                Business.id == business_id,
                Business.deleted_at.is_(None),
            )
        )
        business = result.scalar_one_or_none()
        if business is None:
            raise NotFoundError("Business not found")
        return business

    async def _resolve_active_brain_version(
        self, business_id: uuid.UUID
    ) -> BrainVersion | None:
        """Resolve the active BrainVersion for a business."""
        brain_repo = BusinessBrainRepository(self.session)
        brain = await brain_repo.get_by_business_id(business_id)
        if brain is None or brain.active_version_id is None:
            return None

        version_repo = BrainVersionRepository(self.session)
        return await version_repo.get_by_id(brain.active_version_id)

    async def _emit_outbox_event(
        self,
        *,
        business_id: uuid.UUID,
        event_type: str,
        aggregate_id: uuid.UUID,
        payload: dict,
    ) -> None:
        """Create an outbox event in the same transaction."""
        from datetime import datetime, timezone

        event = OutboxEvent(
            business_id=business_id,
            event_type=event_type,
            aggregate_type="quote",
            aggregate_id=aggregate_id,
            payload=payload,
            idempotency_key=f"{event_type}:quote:{aggregate_id}",
            status="PENDING",
            available_at=datetime.now(timezone.utc),
        )
        self.session.add(event)
        await self.session.flush()
