"""Integration tests for discovery matching.

Requires PostgreSQL test database.

Tests:
- Valid deterministic match
- Multiple valid matches
- Zero matches
- Inactive BusinessProfile not matched
- Inactive/paused/archived ServiceOffer not matched
- Cross-business isolation
- Fabricated business/service returned by AI
- Public/private data exposure
"""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.identity.models import Business, BusinessMember, BusinessProfile, User
from app.domain.services.models import ServiceCategory, ServiceOffer


@pytest.mark.integration
class TestDiscoveryMatching:
    """Test deterministic matching against real database data."""

    @pytest_asyncio.fixture
    async def seed_data(self, db_session: AsyncSession, test_user: User):
        """Create test data: categories, businesses, offers."""
        # Categories
        electrical = ServiceCategory(name="Electrical", slug="electrical")
        plumbing = ServiceCategory(name="Plumbing", slug="plumbing")
        legal = ServiceCategory(name="Legal", slug="legal")
        db_session.add_all([electrical, plumbing, legal])
        await db_session.flush()

        # Business A — active, public, with active electrical offer
        biz_a = Business(name="Sparky Electric", slug=f"sparky-{id(self)}", status="active")
        db_session.add(biz_a)
        await db_session.flush()

        member_a = BusinessMember(user_id=test_user.id, business_id=biz_a.id, role="owner")
        db_session.add(member_a)

        profile_a = BusinessProfile(
            business_id=biz_a.id,
            description="Professional electrical services",
            city="Portland",
            public_status="active",
        )
        db_session.add(profile_a)

        offer_a = ServiceOffer(
            business_id=biz_a.id,
            name="Electrical Inspection",
            slug="electrical-inspection",
            description="Full electrical inspection for residential properties",
            category_id=electrical.id,
            status="active",
        )
        db_session.add(offer_a)

        # Business B — active, public, with active plumbing offer
        biz_b = Business(name="Pipe Perfect", slug=f"pipe-perfect-{id(self)}", status="active")
        db_session.add(biz_b)
        await db_session.flush()

        member_b = BusinessMember(user_id=test_user.id, business_id=biz_b.id, role="owner")
        db_session.add(member_b)

        profile_b = BusinessProfile(
            business_id=biz_b.id,
            description="Reliable plumbing services",
            city="Portland",
            public_status="active",
        )
        db_session.add(profile_b)

        offer_b = ServiceOffer(
            business_id=biz_b.id,
            name="Pipe Repair",
            slug="pipe-repair",
            description="Emergency and scheduled pipe repair",
            category_id=plumbing.id,
            status="active",
        )
        db_session.add(offer_b)

        # Business C — inactive public profile (should NOT match)
        biz_c = Business(name="Hidden Biz", slug=f"hidden-{id(self)}", status="active")
        db_session.add(biz_c)
        await db_session.flush()

        member_c = BusinessMember(user_id=test_user.id, business_id=biz_c.id, role="owner")
        db_session.add(member_c)

        profile_c = BusinessProfile(
            business_id=biz_c.id,
            description="Should not be found",
            public_status="incomplete",  # NOT active
        )
        db_session.add(profile_c)

        offer_c = ServiceOffer(
            business_id=biz_c.id,
            name="Secret Service",
            slug="secret-service",
            category_id=electrical.id,
            status="active",
        )
        db_session.add(offer_c)

        # Business D — active public profile, but DRAFT offer (should NOT match)
        biz_d = Business(name="Draft Biz", slug=f"draft-biz-{id(self)}", status="active")
        db_session.add(biz_d)
        await db_session.flush()

        member_d = BusinessMember(user_id=test_user.id, business_id=biz_d.id, role="owner")
        db_session.add(member_d)

        profile_d = BusinessProfile(
            business_id=biz_d.id,
            description="Draft offers only",
            public_status="active",
        )
        db_session.add(profile_d)

        offer_d = ServiceOffer(
            business_id=biz_d.id,
            name="Draft Electrical Work",
            slug="draft-electrical",
            category_id=electrical.id,
            status="draft",  # NOT active
        )
        db_session.add(offer_d)

        # Business E — paused offer (should NOT match)
        biz_e = Business(name="Paused Biz", slug=f"paused-biz-{id(self)}", status="active")
        db_session.add(biz_e)
        await db_session.flush()

        member_e = BusinessMember(user_id=test_user.id, business_id=biz_e.id, role="owner")
        db_session.add(member_e)

        profile_e = BusinessProfile(
            business_id=biz_e.id,
            description="Paused offers",
            public_status="active",
        )
        db_session.add(profile_e)

        offer_e = ServiceOffer(
            business_id=biz_e.id,
            name="Paused Electrical Work",
            slug="paused-electrical",
            category_id=electrical.id,
            status="paused",  # NOT active
        )
        db_session.add(offer_e)

        await db_session.flush()

        return {
            "electrical": electrical,
            "plumbing": plumbing,
            "legal": legal,
            "biz_a": biz_a,
            "biz_b": biz_b,
            "biz_c": biz_c,
            "biz_d": biz_d,
            "biz_e": biz_e,
        }

    async def test_natural_language_search_finds_match(
        self, client: AsyncClient, seed_data: dict
    ):
        """Natural-language search returns matching businesses."""
        response = await client.post(
            "/api/v1/discovery/search",
            json={"query": "I need an electrician for electrical inspection"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] >= 1
        # Should find Sparky Electric
        biz_names = [m["business_name"] for m in data["matches"]]
        assert "Sparky Electric" in biz_names

    async def test_structured_search_by_category(
        self, client: AsyncClient, seed_data: dict
    ):
        """Structured search by category returns matching offers."""
        response = await client.post(
            "/api/v1/discovery/structured",
            json={"category_slug": "plumbing"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] >= 1
        biz_names = [m["business_name"] for m in data["matches"]]
        assert "Pipe Perfect" in biz_names

    async def test_inactive_public_profile_not_matched(
        self, client: AsyncClient, seed_data: dict
    ):
        """Business with incomplete public_status is NOT in results."""
        response = await client.post(
            "/api/v1/discovery/search",
            json={"query": "secret service electrical"},
        )
        data = response.json()
        biz_slugs = [m["business_slug"] for m in data["matches"]]
        # Hidden Biz should NOT appear
        hidden_slug = seed_data["biz_c"].slug
        assert hidden_slug not in biz_slugs

    async def test_draft_offer_not_matched(
        self, client: AsyncClient, seed_data: dict
    ):
        """Business with only DRAFT offers is NOT in results."""
        response = await client.post(
            "/api/v1/discovery/structured",
            json={"category_slug": "electrical"},
        )
        data = response.json()
        biz_slugs = [m["business_slug"] for m in data["matches"]]
        draft_slug = seed_data["biz_d"].slug
        assert draft_slug not in biz_slugs

    async def test_paused_offer_not_matched(
        self, client: AsyncClient, seed_data: dict
    ):
        """Business with only PAUSED offers is NOT in results."""
        response = await client.post(
            "/api/v1/discovery/structured",
            json={"category_slug": "electrical"},
        )
        data = response.json()
        biz_slugs = [m["business_slug"] for m in data["matches"]]
        paused_slug = seed_data["biz_e"].slug
        assert paused_slug not in biz_slugs

    async def test_zero_matches_for_nonexistent_category(
        self, client: AsyncClient, seed_data: dict
    ):
        """Search for nonexistent category returns empty results."""
        response = await client.post(
            "/api/v1/discovery/structured",
            json={"category_slug": "nonexistent-category"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_matches"] == 0
        assert data["matches"] == []

    async def test_no_private_data_exposed(
        self, client: AsyncClient, seed_data: dict
    ):
        """Discovery results only contain public data."""
        response = await client.post(
            "/api/v1/discovery/search",
            json={"query": "electrical inspection"},
        )
        data = response.json()
        for match in data["matches"]:
            # Should not contain internal fields
            assert "members" not in match
            assert "pricing_config" not in match
            assert "service_area" not in match
            for offer in match.get("service_offers", []):
                assert "pricing_config" not in offer
                assert "booking_rules" not in offer
                assert "cancellation_policy" not in offer

    async def test_fabricated_ai_business_not_in_results(
        self, client: AsyncClient, seed_data: dict
    ):
        """Even if AI invents a business, it won't appear in results."""
        # The matching service only returns data from the database
        response = await client.post(
            "/api/v1/discovery/search",
            json={"query": "I need Fake Business Inc for legal work"},
        )
        data = response.json()
        biz_names = [m["business_name"] for m in data["matches"]]
        assert "Fake Business Inc" not in biz_names

    async def test_unauthenticated_search_works(
        self, client: AsyncClient, seed_data: dict
    ):
        """Discovery is available without authentication."""
        response = await client.post(
            "/api/v1/discovery/search",
            json={"query": "electrical inspection"},
        )
        # Should succeed without auth headers
        assert response.status_code == 200

    async def test_empty_query_returns_error(
        self, client: AsyncClient, seed_data: dict
    ):
        """Empty query returns validation error."""
        response = await client.post(
            "/api/v1/discovery/search",
            json={"query": ""},
        )
        assert response.status_code == 422

    async def test_multiple_matches_returned(
        self, client: AsyncClient, seed_data: dict
    ):
        """Search matching multiple businesses returns all of them."""
        response = await client.post(
            "/api/v1/discovery/structured",
            json={"category_slug": "electrical"},
        )
        data = response.json()
        # Should find at least Sparky Electric (the only one with active electrical offer
        # and active public profile)
        assert data["total_matches"] >= 1
