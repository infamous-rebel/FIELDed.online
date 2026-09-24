"""Phase 17 — Public availability integration tests.

Tests the customer-safe public availability endpoint:
- Public availability returns safe data
- Does not expose Brain internals
- Respects the existing deterministic AvailabilityEvaluator
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.booking.service import BookingService
from app.domain.identity.models import Business, BusinessProfile, User
from app.domain.services.models import ServiceCategory, ServiceOffer
from tests.factories import business_member_factory


@pytest_asyncio.fixture
async def public_biz(db_session: AsyncSession, second_user: User) -> tuple[Business, ServiceOffer]:
    """Active public business with an active service offer."""
    biz = Business(
        name=f"Avail Biz {uuid.uuid4().hex[:6]}",
        slug=f"avail-biz-{uuid.uuid4().hex[:8]}",
        status="active",
    )
    db_session.add(biz)
    await db_session.flush()

    db_session.add(business_member_factory(user_id=second_user.id, business_id=biz.id, role="owner"))
    db_session.add(BusinessProfile(business_id=biz.id, public_status="active"))
    await db_session.flush()

    category = ServiceCategory(name="Avail Cat", slug=f"avail-cat-{uuid.uuid4().hex[:8]}")
    db_session.add(category)
    await db_session.flush()

    offer = ServiceOffer(
        business_id=biz.id,
        category_id=category.id,
        name="Avail Service",
        slug=f"avail-service-{uuid.uuid4().hex[:8]}",
        pricing_model="fixed",
        delivery_mode="on_site",
        status="active",
    )
    db_session.add(offer)
    await db_session.flush()

    return biz, offer


class TestPublicAvailability:
    """Customer-safe availability summary."""

    @pytest.mark.asyncio
    async def test_public_availability_returns_safe_data(self, client: AsyncClient, public_biz):
        biz, _ = public_biz

        response = await client.get(f"/api/v1/public/business/{biz.slug}/availability")
        assert response.status_code == 200
        data = response.json()
        # Exactly the customer-safe fields, nothing else
        assert set(data.keys()) == {"available", "next_available", "lead_time_hours"}
        assert isinstance(data["available"], bool)
        assert data["available"] is True
        assert "customer" not in data

    @pytest.mark.asyncio
    async def test_does_not_expose_brain_internals(self, client: AsyncClient, public_biz):
        biz, offer = public_biz

        response = await client.get(
            f"/api/v1/public/business/{biz.slug}/availability",
            params={"service_offer_id": str(offer.id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert set(data.keys()) == {"available", "next_available", "lead_time_hours"}
        body = response.text.lower()
        assert "brain" not in body
        assert "rules" not in body
        assert "config" not in body
        assert "matched" not in body

    @pytest.mark.asyncio
    async def test_respects_existing_deterministic_evaluator(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        public_biz,
    ):
        biz, offer = public_biz

        check_time = datetime.now(UTC) + timedelta(hours=1)
        direct = await BookingService(db_session).check_availability(
            business_id=biz.id,
            service_offer_id=offer.id,
            requested_at=check_time,
        )

        response = await client.get(
            f"/api/v1/public/business/{biz.slug}/availability",
            params={"service_offer_id": str(offer.id)},
        )
        assert response.status_code == 200
        data = response.json()

        # The endpoint delegates to the same evaluator — results agree
        assert data["available"] == direct.available
        if data["available"]:
            # next_available is a parseable ISO datetime
            parsed = datetime.fromisoformat(data["next_available"])
            assert parsed.tzinfo is not None
        else:
            assert data["next_available"] is None
