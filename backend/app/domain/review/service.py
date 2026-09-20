"""Review domain service.

Business logic for review submission, eligibility checking, business
responses, and rating aggregation.

Eligibility is deterministic.  AI never determines review eligibility.
The trust chain requires:
  1. Service execution must exist and be COMPLETED
  2. Execution must NOT be CANCELLED or NO_SHOW
  3. Customer must own the transaction (customer_id matches)
  4. Business must match (business_id matches)
  5. Linked booking must NOT be CANCELLED or DECLINED
  6. Linked enquiry must NOT be DECLINED or CANCELLED
  7. No existing review for this execution (UNIQUE constraint)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.booking.models import Booking
from app.domain.booking.repository import BookingRepository
from app.domain.common.enums import AuditEventType
from app.domain.enquiry.repository import EnquiryRepository
from app.domain.identity.repository import BusinessRepository
from app.domain.outbox.models import OutboxEvent
from app.domain.review.models import Review
from app.domain.review.repository import ReviewRepository
from app.domain.service_execution.models import ServiceExecution
from app.domain.service_execution.repository import ServiceExecutionRepository


class ReviewEligibilityError(Exception):
    """Raised when a review is not eligible for submission."""


class ReviewNotFoundError(Exception):
    """Raised when a review is not found."""


class ReviewService:
    """Review business logic with deterministic eligibility."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.review_repo = ReviewRepository(session)
        self.execution_repo = ServiceExecutionRepository(session)
        self.booking_repo = BookingRepository(session)
        self.enquiry_repo = EnquiryRepository(session)
        self.business_repo = BusinessRepository(session)

    async def submit_review(
        self,
        *,
        customer_id: uuid.UUID,
        service_execution_id: uuid.UUID,
        rating: int,
        title: str | None = None,
        body: str | None = None,
    ) -> Review:
        """Submit a review for a completed service.

        All eligibility checks are deterministic.  No AI involvement.
        """
        # 1. Load the service execution
        execution = await self.execution_repo.get_by_id(service_execution_id)
        if execution is None:
            raise ReviewEligibilityError("Service execution not found")

        # 2. Execution must be COMPLETED
        if execution.status != "completed":
            raise ReviewEligibilityError(
                "Service execution is not completed — review not eligible"
            )

        # 3. Execution must NOT be CANCELLED or NO_SHOW
        #    (already covered by status == "completed" check above,
        #    but explicit for clarity per spec)
        if execution.status in ("cancelled", "no_show"):
            raise ReviewEligibilityError(
                "Service execution was cancelled or no-show — review not eligible"
            )

        # 4. Customer must own the transaction
        if execution.customer_id != customer_id:
            raise ReviewEligibilityError(
                "Customer does not own this service execution"
            )

        # 5. Load linked booking and verify status
        booking = await self.booking_repo.get_by_id(execution.booking_id)
        if booking is None:
            raise ReviewEligibilityError("Linked booking not found")
        if booking.status in ("cancelled", "declined"):
            raise ReviewEligibilityError(
                "Linked booking was cancelled or declined — review not eligible"
            )

        # 6. Load linked enquiry and verify status
        enquiry = await self.enquiry_repo.get_by_id(booking.enquiry_id)
        if enquiry is None:
            raise ReviewEligibilityError("Linked enquiry not found")
        if enquiry.status in ("declined", "cancelled"):
            raise ReviewEligibilityError(
                "Linked enquiry was declined or cancelled — review not eligible"
            )

        # 7. No existing review for this execution (UNIQUE constraint)
        existing = await self.review_repo.get_by_service_execution(
            service_execution_id
        )
        if existing is not None:
            raise ReviewEligibilityError(
                "A review already exists for this service execution"
            )

        # All checks passed — create the review
        review = Review(
            business_id=execution.business_id,
            customer_id=customer_id,
            service_execution_id=service_execution_id,
            booking_id=execution.booking_id,
            enquiry_id=booking.enquiry_id,
            service_offer_id=execution.service_offer_id,
            rating=rating,
            title=title,
            body=body,
            status="visible",
        )
        review = await self.review_repo.create(review)

        # Update rating aggregates on BusinessProfile
        await self._update_rating_aggregates(execution.business_id)

        # Emit outbox event for notification pipeline
        await self._emit_outbox_event(
            business_id=execution.business_id,
            event_type=AuditEventType.REVIEW_SUBMITTED.value,
            aggregate_id=review.id,
            payload={
                "review_id": str(review.id),
                "customer_id": str(customer_id),
                "service_execution_id": str(service_execution_id),
                "rating": rating,
                "business_id": str(execution.business_id),
            },
        )

        return review

    async def respond_to_review(
        self,
        *,
        business_id: uuid.UUID,
        review_id: uuid.UUID,
        responder_id: uuid.UUID,
        response_body: str,
    ) -> Review:
        """Add a business response to an existing review."""
        review = await self.review_repo.get_by_id(review_id)
        if review is None:
            raise ReviewNotFoundError("Review not found")

        # Verify the review belongs to this business
        if review.business_id != business_id:
            raise ReviewNotFoundError(
                "Review does not belong to this business"
            )

        # Set response
        review.response_body = response_body
        review.responded_at = datetime.now(timezone.utc)
        review.responded_by = responder_id
        review = await self.review_repo.update(review)

        # Emit outbox event
        await self._emit_outbox_event(
            business_id=business_id,
            event_type=AuditEventType.REVIEW_RESPONDED.value,
            aggregate_id=review.id,
            payload={
                "review_id": str(review.id),
                "responder_id": str(responder_id),
                "business_id": str(business_id),
            },
        )

        return review

    async def _update_rating_aggregates(self, business_id: uuid.UUID) -> None:
        """Recalculate and persist average_rating and review_count.

        Database-driven, deterministic.  Uses AVG(rating) and COUNT(*)
        across all visible reviews for the business.
        """
        avg_rating, count = await self.review_repo.get_average_rating_for_business(
            business_id
        )

        business = await self.business_repo.get_by_id(business_id)
        if business is not None and business.profile is not None:
            business.profile.average_rating = avg_rating
            business.profile.review_count = count
            await self.session.flush()

    async def _emit_outbox_event(
        self,
        *,
        business_id: uuid.UUID,
        event_type: str,
        aggregate_id: uuid.UUID,
        payload: dict,
    ) -> None:
        """Create an outbox event in the same transaction."""
        event = OutboxEvent(
            business_id=business_id,
            event_type=event_type,
            aggregate_type="review",
            aggregate_id=aggregate_id,
            payload=payload,
            idempotency_key=f"{event_type}:review:{aggregate_id}",
            status="PENDING",
            available_at=datetime.now(timezone.utc),
        )
        self.session.add(event)
        await self.session.flush()
