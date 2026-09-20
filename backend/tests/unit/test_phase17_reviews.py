"""Phase 17 — Review trust model unit tests.

Tests cover deterministic review eligibility (no AI involvement):
- Eligible completed transaction → review succeeds
- Cancelled execution → review rejected
- Incomplete service → review rejected
- Wrong customer → rejected
- Wrong business → rejected (business response)
- Duplicate review → rejected
- Rating 1-5 valid, 0/6 rejected (schema boundary)
- Rating aggregation correctness
- Business response: authorized → allowed
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.booking.models import Booking
from app.domain.common.enums import BookingStatus
from app.domain.enquiry.models import Enquiry
from app.domain.quote.models import Quote
from app.domain.review.schemas import ReviewCreate
from app.domain.review.service import (
    ReviewEligibilityError,
    ReviewNotFoundError,
    ReviewService,
)
from app.domain.service_execution.models import ServiceExecution
from app.domain.services.models import ServiceCategory, ServiceOffer
from tests.factories import (
    business_factory,
    business_member_factory,
    business_profile_factory,
    customer_profile_factory,
    service_category_factory,
    user_factory,
)


async def _make_user(db_session: AsyncSession, prefix: str):
    user = user_factory(email=f"{prefix}-{uuid.uuid4().hex[:8]}@example.com")
    db_session.add(user)
    await db_session.flush()
    db_session.add(customer_profile_factory(user_id=user.id))
    await db_session.flush()
    return user


async def _make_chain(
    db_session: AsyncSession,
    *,
    customer,
    owner,
    execution_status: str = "completed",
    enquiry_status: str = "quoted",
    booking_status=BookingStatus.CONFIRMED,
    biz=None,
):
    """Create a transaction chain: enquiry → quote → booking → execution."""
    if biz is None:
        biz = business_factory()
        db_session.add(biz)
        await db_session.flush()

        db_session.add(
            business_member_factory(user_id=owner.id, business_id=biz.id, role="owner")
        )
        db_session.add(business_profile_factory(business_id=biz.id))
        await db_session.flush()

    category = service_category_factory()
    db_session.add(category)
    await db_session.flush()

    offer = ServiceOffer(
        business_id=biz.id,
        category_id=category.id,
        name=f"Review Svc {uuid.uuid4().hex[:6]}",
        slug=f"review-svc-{uuid.uuid4().hex[:6]}",
        pricing_model="fixed",
        delivery_mode="on_site",
        status="active",
    )
    db_session.add(offer)
    await db_session.flush()

    enquiry = Enquiry(
        reference=f"ENQ-{uuid.uuid4().hex[:8]}",
        customer_id=customer.id,
        business_id=biz.id,
        service_offer_id=offer.id,
        subject="Review test",
        message="Testing reviews",
        status=enquiry_status,
    )
    db_session.add(enquiry)
    await db_session.flush()

    quote = Quote(
        reference=f"QUO-{uuid.uuid4().hex[:8]}",
        customer_id=customer.id,
        business_id=biz.id,
        enquiry_id=enquiry.id,
        service_offer_id=offer.id,
        amount="120.00",
        currency="GBP",
        status="accepted",
    )
    db_session.add(quote)
    await db_session.flush()

    booking = Booking(
        reference=f"BKG-{uuid.uuid4().hex[:8]}",
        customer_id=customer.id,
        business_id=biz.id,
        quote_id=quote.id,
        enquiry_id=enquiry.id,
        service_offer_id=offer.id,
        requested_at=datetime.now(timezone.utc) + timedelta(days=1),
        currency="GBP",
        status=booking_status,
    )
    db_session.add(booking)
    await db_session.flush()

    execution = ServiceExecution(
        business_id=biz.id,
        customer_id=customer.id,
        booking_id=booking.id,
        service_offer_id=offer.id,
        quote_id=quote.id,
        status=execution_status,
        completed_at=(
            datetime.now(timezone.utc) if execution_status == "completed" else None
        ),
        completed_by=owner.id if execution_status == "completed" else None,
    )
    db_session.add(execution)
    await db_session.flush()

    return biz, execution


@pytest_asyncio.fixture
async def customer(db_session: AsyncSession):
    return await _make_user(db_session, "cust")


@pytest_asyncio.fixture
async def other_customer(db_session: AsyncSession):
    return await _make_user(db_session, "other-cust")


@pytest_asyncio.fixture
async def owner(db_session: AsyncSession):
    return await _make_user(db_session, "owner")


class TestReviewEligibility:
    """Deterministic review submission eligibility."""

    @pytest.mark.asyncio
    async def test_eligible_completed_transaction_review_succeeds(
        self, db_session: AsyncSession, customer, owner
    ):
        biz, execution = await _make_chain(
            db_session, customer=customer, owner=owner
        )
        service = ReviewService(db_session)

        review = await service.submit_review(
            customer_id=customer.id,
            service_execution_id=execution.id,
            rating=5,
            title="Excellent",
            body="Would book again.",
        )

        assert review.status == "visible"
        assert review.rating == 5
        assert review.business_id == biz.id
        assert review.customer_id == customer.id
        assert review.service_execution_id == execution.id

    @pytest.mark.asyncio
    async def test_cancelled_execution_review_rejected(
        self, db_session: AsyncSession, customer, owner
    ):
        _, execution = await _make_chain(
            db_session,
            customer=customer,
            owner=owner,
            execution_status="cancelled",
        )
        service = ReviewService(db_session)

        with pytest.raises(ReviewEligibilityError):
            await service.submit_review(
                customer_id=customer.id,
                service_execution_id=execution.id,
                rating=4,
            )

    @pytest.mark.asyncio
    async def test_incomplete_service_review_rejected(
        self, db_session: AsyncSession, customer, owner
    ):
        _, execution = await _make_chain(
            db_session,
            customer=customer,
            owner=owner,
            execution_status="in_progress",
        )
        service = ReviewService(db_session)

        with pytest.raises(ReviewEligibilityError, match="not completed"):
            await service.submit_review(
                customer_id=customer.id,
                service_execution_id=execution.id,
                rating=4,
            )

    @pytest.mark.asyncio
    async def test_wrong_customer_review_rejected(
        self, db_session: AsyncSession, customer, other_customer, owner
    ):
        _, execution = await _make_chain(
            db_session, customer=customer, owner=owner
        )
        service = ReviewService(db_session)

        with pytest.raises(ReviewEligibilityError, match="does not own"):
            await service.submit_review(
                customer_id=other_customer.id,
                service_execution_id=execution.id,
                rating=4,
            )

    @pytest.mark.asyncio
    async def test_duplicate_review_rejected(
        self, db_session: AsyncSession, customer, owner
    ):
        _, execution = await _make_chain(
            db_session, customer=customer, owner=owner
        )
        service = ReviewService(db_session)

        await service.submit_review(
            customer_id=customer.id,
            service_execution_id=execution.id,
            rating=5,
        )

        with pytest.raises(ReviewEligibilityError, match="already exists"):
            await service.submit_review(
                customer_id=customer.id,
                service_execution_id=execution.id,
                rating=4,
            )


class TestBusinessResponse:
    """Review responses are restricted to the owning business."""

    @pytest.mark.asyncio
    async def test_business_response_authorized_allowed(
        self, db_session: AsyncSession, customer, owner
    ):
        biz, execution = await _make_chain(
            db_session, customer=customer, owner=owner
        )
        service = ReviewService(db_session)
        review = await service.submit_review(
            customer_id=customer.id,
            service_execution_id=execution.id,
            rating=5,
        )

        responded = await service.respond_to_review(
            business_id=biz.id,
            review_id=review.id,
            responder_id=owner.id,
            response_body="Thank you!",
        )

        assert responded.response_body == "Thank you!"
        assert responded.responded_at is not None
        assert responded.responded_by == owner.id

    @pytest.mark.asyncio
    async def test_wrong_business_response_rejected(
        self, db_session: AsyncSession, customer, owner
    ):
        _, execution = await _make_chain(
            db_session, customer=customer, owner=owner
        )
        service = ReviewService(db_session)
        review = await service.submit_review(
            customer_id=customer.id,
            service_execution_id=execution.id,
            rating=5,
        )

        other_biz, _ = await _make_chain(
            db_session, customer=customer, owner=owner
        )

        with pytest.raises(ReviewNotFoundError, match="does not belong"):
            await service.respond_to_review(
                business_id=other_biz.id,
                review_id=review.id,
                responder_id=owner.id,
                response_body="Not mine",
            )


class TestRatingAggregation:
    """Business profile aggregates are database-driven and deterministic."""

    @pytest.mark.asyncio
    async def test_rating_aggregation_correctness(
        self, db_session: AsyncSession, customer, other_customer, owner
    ):
        biz, execution = await _make_chain(
            db_session, customer=customer, owner=owner
        )
        service = ReviewService(db_session)

        await service.submit_review(
            customer_id=customer.id,
            service_execution_id=execution.id,
            rating=5,
        )

        # Second transaction on the SAME business for the second customer
        _, execution2 = await _make_chain(
            db_session, customer=other_customer, owner=owner, biz=biz
        )
        assert execution2.business_id == biz.id
        await service.submit_review(
            customer_id=other_customer.id,
            service_execution_id=execution2.id,
            rating=3,
        )

        await db_session.refresh(biz.profile)
        assert biz.profile.review_count == 2
        assert biz.profile.average_rating == pytest.approx(4.0)


class TestRatingBounds:
    """Rating 1-5 valid; 0/6 rejected at the request-schema boundary."""

    def test_rating_valid_bounds(self):
        for rating in (1, 2, 3, 4, 5):
            request = ReviewCreate(
                service_execution_id=uuid.uuid4(), rating=rating
            )
            assert request.rating == rating

    def test_rating_zero_rejected(self):
        with pytest.raises(PydanticValidationError):
            ReviewCreate(service_execution_id=uuid.uuid4(), rating=0)

    def test_rating_six_rejected(self):
        with pytest.raises(PydanticValidationError):
            ReviewCreate(service_execution_id=uuid.uuid4(), rating=6)
