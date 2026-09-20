"""Booking domain service.

Contains business logic for booking creation, lifecycle transitions,
availability evaluation, and authorization enforcement.

The booking creation flow:
    1. Resolve accepted quote (server-side, tenant-verified)
    2. Resolve active BrainVersion (if any)
    3. Evaluate Brain booking/availability rules
    4. Evaluate deterministic availability
    5. Persist Booking with full BrainVersion traceability
    6. Transition enquiry to BOOKED

The Brain must NOT directly create or confirm a booking.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.booking.availability import AvailabilityEvaluator, AvailabilityResult
from app.domain.booking.models import Booking
from app.domain.booking.repository import BookingRepository
from app.domain.business.evaluator import BrainEvaluator, BrainDecision, BrainDecisionOutcome, DecisionContext
from app.domain.business.models import BrainVersion
from app.domain.business.repository import BusinessBrainRepository, BrainVersionRepository
from app.domain.common.enums import (
    BOOKING_TRANSITIONS,
    BookingStatus,
    EnquiryStatus,
    QuoteStatus,
)
from app.domain.enquiry.models import Enquiry
from app.domain.enquiry.repository import EnquiryRepository
from app.domain.outbox.models import OutboxEvent
from app.domain.quote.models import Quote
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
    """Generate a customer-friendly booking reference number."""
    return f"BKG-{uuid.uuid4().hex[:8]}"


class BookingService:
    """Booking lifecycle management with Brain-governed availability."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.booking_repo = BookingRepository(session)
        self.quote_repo = QuoteRepository(session)
        self.enquiry_repo = EnquiryRepository(session)
        self._availability_evaluator = AvailabilityEvaluator()
        self._brain_evaluator = BrainEvaluator()

    # --- Booking creation ---

    async def create_booking(
        self,
        *,
        customer_id: uuid.UUID,
        quote_id: uuid.UUID,
        requested_at: datetime,
        notes: str | None = None,
    ) -> Booking:
        """Create a booking from an accepted quote.

        The customer creates a booking after accepting a quote.
        The booking is subject to Brain availability evaluation.

        Concurrency safety:
        Availability is evaluated and the booking is persisted inside
        a single transaction with a PostgreSQL advisory lock scoped to
        the business + time slot.  This prevents two concurrent requests
        from both consuming the same constrained capacity.

        The requested_at must be timezone-aware.
        """
        if requested_at.tzinfo is None:
            requested_at = requested_at.replace(tzinfo=timezone.utc)

        # 1. Resolve and validate the quote
        quote = await self._resolve_accepted_quote(quote_id, customer_id)

        # 2. Resolve the service offer
        service_offer = await self._resolve_service_offer(quote.service_offer_id)

        # 3. Resolve the active BrainVersion (if any)
        brain_version = await self._resolve_active_brain_version(quote.business_id)

        # 4. Build the decision context
        context = DecisionContext(
            business_id=quote.business_id,
            service_offer_id=service_offer.id,
            customer_id=customer_id,
            context_data={
                "business_id": str(quote.business_id),
                "service_offer_id": str(service_offer.id),
                "customer_id": str(customer_id),
                "requested_at": requested_at.isoformat(),
                "service_offer": {
                    "pricing_model": service_offer.pricing_model,
                    "delivery_mode": service_offer.delivery_mode,
                    "name": service_offer.name,
                },
            },
        )

        # 5. Evaluate Brain booking policy (if configured)
        brain_decision = await self._evaluate_brain_booking_policy(
            brain_version=brain_version,
            context=context,
            business_id=quote.business_id,
        )

        # 6. Acquire a transaction-scoped advisory lock for this business + time slot.
        #    This serialises concurrent booking attempts for the same business
        #    around the same time, preventing capacity oversubscription.
        lock_key = self._compute_advisory_lock_key(
            quote.business_id, requested_at,
        )
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": lock_key},
        )

        # 7. Evaluate availability INSIDE the transaction (after lock)
        existing_bookings = await self._get_existing_bookings_for_availability(
            business_id=quote.business_id,
            requested_at=requested_at,
        )

        availability_result = self._availability_evaluator.evaluate(
            requested_at=requested_at,
            service_offer=service_offer,
            brain_version=brain_version,
            context=context,
            existing_bookings=existing_bookings,
        )

        # 8. Check if booking is blocked
        if not availability_result.available:
            raise ValidationError(
                f"Requested time is not available: {availability_result.reason}",
                details=availability_result.to_evidence_dict(),
            )

        # If brain denied the booking, block it
        if brain_decision and brain_decision.is_denied:
            raise ValidationError(
                f"Booking denied by Business Brain: {brain_decision.reason}",
                details=brain_decision.to_dict(),
            )

        # 9. Create the booking
        decision_evidence = {
            "brain_decision": brain_decision.to_dict() if brain_decision else None,
            "availability": availability_result.to_evidence_dict(),
        }

        booking = Booking(
            reference=_generate_reference(),
            customer_id=customer_id,
            business_id=quote.business_id,
            quote_id=quote.id,
            enquiry_id=quote.enquiry_id,
            service_offer_id=quote.service_offer_id,
            requested_at=requested_at,
            currency=quote.currency,
            status=BookingStatus.REQUESTED,
            brain_version_id=brain_version.id if brain_version else None,
            decision_evidence=decision_evidence,
            notes=notes,
        )
        booking = await self.booking_repo.create(booking)

        # 10. Transition enquiry to BOOKING_PROPOSED
        enquiry = await self.enquiry_repo.get_by_id(quote.enquiry_id)
        if enquiry and EnquiryStatus(enquiry.status) == EnquiryStatus.CUSTOMER_ACCEPTED:
            enquiry.status = EnquiryStatus.BOOKING_PROPOSED
            await self.enquiry_repo.update(enquiry)

        logger.info(
            "booking_created",
            booking_id=str(booking.id),
            reference=booking.reference,
            quote_id=str(quote.id),
            customer_id=str(customer_id),
            business_id=str(quote.business_id),
            requested_at=requested_at.isoformat(),
            brain_version_id=str(brain_version.id) if brain_version else None,
            available=availability_result.available,
        )

        return booking

    # --- Booking lifecycle ---

    async def transition_booking(
        self,
        booking: Booking,
        target_status: BookingStatus,
        *,
        actor: str = "business",
    ) -> Booking:
        """Transition a booking to a new status.

        Validates the transition against the state machine.
        - Business can propose/accept/confirm/decline/cancel/no-show.
        - Customer can cancel.
        - System can mark expired.
        """
        current = BookingStatus(booking.status)
        allowed = BOOKING_TRANSITIONS.get(current, set())

        if target_status not in allowed:
            raise StateTransitionError(
                f"Cannot transition booking from '{current.value}' to "
                f"'{target_status.value}'. "
                f"Allowed: {[s.value for s in allowed] or 'none (terminal state)'}"
            )

        # Actor-specific authority
        if actor == "customer" and target_status != BookingStatus.CANCELLED:
            raise AuthorizationError(
                "Customers can only cancel their own bookings"
            )

        old_status = booking.status
        booking.status = target_status
        result = await self.booking_repo.update(booking)

        # If booking is confirmed, transition enquiry to BOOKED
        if target_status == BookingStatus.CONFIRMED:
            enquiry = await self.enquiry_repo.get_by_id(booking.enquiry_id)
            if enquiry and EnquiryStatus(enquiry.status) == EnquiryStatus.BOOKING_PROPOSED:
                enquiry.status = EnquiryStatus.BOOKED
                await self.enquiry_repo.update(enquiry)

        # If booking is completed, transition enquiry to COMPLETED
        if target_status == BookingStatus.COMPLETED:
            enquiry = await self.enquiry_repo.get_by_id(booking.enquiry_id)
            if enquiry and EnquiryStatus(enquiry.status) == EnquiryStatus.BOOKED:
                enquiry.status = EnquiryStatus.COMPLETED
                await self.enquiry_repo.update(enquiry)

        logger.info(
            "booking_transition",
            booking_id=str(booking.id),
            actor=actor,
            from_status=old_status,
            to_status=target_status.value,
        )

        # Emit outbox event for communication pipeline
        await self._emit_outbox_event(
            business_id=booking.business_id,
            event_type=f"BOOKING_{target_status.value.upper()}",
            aggregate_id=booking.id,
            payload={
                "booking_id": str(booking.id),
                "enquiry_id": str(booking.enquiry_id),
                "quote_id": str(booking.quote_id),
                "customer_id": str(booking.customer_id),
                "status": target_status.value,
            },
        )

        return result

    # --- Availability evaluation ---

    async def check_availability(
        self,
        *,
        business_id: uuid.UUID,
        service_offer_id: uuid.UUID,
        requested_at: datetime,
    ) -> AvailabilityResult:
        """Check availability for a proposed booking time.

        This is a read-only evaluation — it does not create any entities.
        """
        if requested_at.tzinfo is None:
            requested_at = requested_at.replace(tzinfo=timezone.utc)

        service_offer = await self._resolve_service_offer(service_offer_id)
        if service_offer.business_id != business_id:
            raise AuthorizationError("Service offer does not belong to this business")

        brain_version = await self._resolve_active_brain_version(business_id)

        context = DecisionContext(
            business_id=business_id,
            service_offer_id=service_offer.id,
            customer_id=uuid.UUID(int=0),  # No specific customer for availability check
            context_data={
                "business_id": str(business_id),
                "service_offer_id": str(service_offer.id),
                "requested_at": requested_at.isoformat(),
            },
        )

        existing_bookings = await self._get_existing_bookings_for_availability(
            business_id=business_id,
            requested_at=requested_at,
        )

        return self._availability_evaluator.evaluate(
            requested_at=requested_at,
            service_offer=service_offer,
            brain_version=brain_version,
            context=context,
            existing_bookings=existing_bookings,
        )

    # --- Retrieval ---

    async def get_booking(self, booking_id: uuid.UUID) -> Booking:
        """Get a booking by ID."""
        booking = await self.booking_repo.get_by_id(booking_id)
        if booking is None:
            raise NotFoundError("Booking not found")
        return booking

    async def get_customer_booking(
        self, booking_id: uuid.UUID, customer_id: uuid.UUID
    ) -> Booking:
        """Get a booking, verifying customer ownership."""
        booking = await self.get_booking(booking_id)
        if booking.customer_id != customer_id:
            raise AuthorizationError("Not your booking")
        return booking

    async def get_business_booking(
        self, booking_id: uuid.UUID, business_id: uuid.UUID
    ) -> Booking:
        """Get a booking, verifying it belongs to the business."""
        booking = await self.get_booking(booking_id)
        if booking.business_id != business_id:
            raise AuthorizationError("Booking does not belong to this business")
        return booking

    async def list_customer_bookings(
        self,
        customer_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Booking]:
        """List bookings for a customer."""
        return await self.booking_repo.get_by_customer(
            customer_id, status=status, limit=limit, offset=offset
        )

    async def list_business_bookings(
        self,
        business_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Booking]:
        """List bookings for a business."""
        return await self.booking_repo.get_by_business(
            business_id, status=status, limit=limit, offset=offset
        )

    # --- Internal helpers ---

    async def _resolve_accepted_quote(
        self, quote_id: uuid.UUID, customer_id: uuid.UUID
    ) -> Quote:
        """Resolve a quote that has been accepted by the customer."""
        quote = await self.quote_repo.get_by_id(quote_id)
        if quote is None:
            raise NotFoundError("Quote not found")
        if quote.customer_id != customer_id:
            raise AuthorizationError("Not your quote")
        if QuoteStatus(quote.status) != QuoteStatus.ACCEPTED:
            raise ValidationError(
                f"Quote must be accepted before creating a booking. "
                f"Current status: {quote.status}"
            )
        return quote

    async def _resolve_service_offer(
        self, service_offer_id: uuid.UUID
    ) -> ServiceOffer:
        """Resolve a service offer."""
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

    async def _evaluate_brain_booking_policy(
        self,
        *,
        brain_version: BrainVersion | None,
        context: DecisionContext,
        business_id: uuid.UUID,
    ) -> BrainDecision | None:
        """Evaluate the Brain for booking policy.

        Returns None if no Brain is configured.
        Returns the decision if a Brain is configured.
        """
        if brain_version is None:
            return None

        try:
            return self._brain_evaluator.evaluate(brain_version, context)
        except Exception:
            logger.exception(
                "brain_booking_evaluation_failed",
                business_id=str(business_id),
                brain_version_id=str(brain_version.id),
            )
            # Evaluation failure returns a failed decision
            return BrainDecision(
                decision=BrainDecisionOutcome.REQUIRE_APPROVAL,
                brain_version_id=brain_version.id,
                reason="Brain evaluation error — manual approval required",
            )

    async def _get_existing_bookings_for_availability(
        self,
        *,
        business_id: uuid.UUID,
        requested_at: datetime,
    ) -> list[Booking]:
        """Get existing bookings around the requested time for capacity checks."""
        from datetime import timedelta
        window_start = requested_at - timedelta(hours=12)
        window_end = requested_at + timedelta(hours=12)

        result = await self.session.execute(
            select(Booking).where(
                Booking.business_id == business_id,
                Booking.requested_at >= window_start,
                Booking.requested_at <= window_end,
                Booking.deleted_at.is_(None),
                Booking.status.notin_(["cancelled", "declined", "expired"]),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    def _compute_advisory_lock_key(
        business_id: uuid.UUID,
        requested_at: datetime,
    ) -> int:
        """Compute a deterministic 64-bit advisory lock key.

        The key is scoped to the business + a 1-hour time bucket so that
        concurrent booking attempts for the same business around the same
        time are serialised, while bookings for different businesses or
        very different times do not block each other.

        PostgreSQL advisory locks are 64-bit signed integers (-2^63 to 2^63-1).
        We derive one from the business_id UUID combined with a time-bucket hash,
        then clamp to the valid signed range.
        """
        import hashlib
        # Use a 1-hour bucket so nearby slots contend, distant ones don't
        bucket = requested_at.replace(minute=0, second=0, microsecond=0)
        raw = f"{business_id}:{bucket.isoformat()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:15]
        # 15 hex digits = 60 bits, max value 0xFFFFFFFFFFFFFFF = 1,152,921,504,606,846,975
        # This fits within the signed 64-bit range (max 9,223,372,036,854,775,807)
        return int(digest, 16)

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
            aggregate_type="booking",
            aggregate_id=aggregate_id,
            payload=payload,
            idempotency_key=f"{event_type}:booking:{aggregate_id}",
            status="PENDING",
            available_at=datetime.now(timezone.utc),
        )
        self.session.add(event)
        await self.session.flush()
