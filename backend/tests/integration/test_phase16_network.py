"""Integration tests for Phase 16: Business Network.

Requires PostgreSQL test database.

Tests:
- Public business directory listing
- Public business directory filtering (city, country, category)
- Public business directory pagination
- Public service offer detail endpoint
- Inactive public profile not in directory
- Draft/paused/archived offers not accessible via public detail
- Tenant isolation: public endpoints expose no private data
- Pricing summary derived safely from pricing_config
- Active offer count accuracy
- Cross-tenant isolation on public endpoints
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.identity.models import Business, BusinessMember, BusinessProfile, User
from app.domain.services.models import ServiceCategory, ServiceOffer


@pytest.mark.integration
class TestPublicBusinessDirectory:
    """Test the public business directory endpoint."""

    @pytest_asyncio.fixture
    async def seed_network_data(self, db_session: AsyncSession, test_user: User):
        """Create test data for network directory tests."""
        # Categories
        electrical = ServiceCategory(name="Electrical P16", slug="electrical-p16")
        plumbing = ServiceCategory(name="Plumbing P16", slug="plumbing-p16")
        db_session.add_all([electrical, plumbing])
        await db_session.flush()

        # Business A — active, public, with 2 active offers
        biz_a = Business(name="Network Electric", slug=f"net-electric-{id(self)}", status="active")
        db_session.add(biz_a)
        await db_session.flush()
        db_session.add(BusinessMember(user_id=test_user.id, business_id=biz_a.id, role="owner"))
        db_session.add(
            BusinessProfile(
                business_id=biz_a.id,
                description="Trusted electrical services",
                city="London",
                country="UK",
                public_status="active",
                is_verified=True,
                average_rating=4.5,
                review_count=12,
            )
        )
        db_session.add(
            ServiceOffer(
                business_id=biz_a.id,
                name="Home Wiring",
                slug="home-wiring-p16",
                description="Residential wiring services",
                category_id=electrical.id,
                delivery_mode="on_site",
                pricing_model="starting_at",
                pricing_config={"starting_price": "150.00", "currency": "GBP"},
                status="active",
            )
        )
        db_session.add(
            ServiceOffer(
                business_id=biz_a.id,
                name="Fuse Board Upgrade",
                slug="fuse-board-p16",
                description="Modern fuse board installation",
                category_id=electrical.id,
                delivery_mode="on_site",
                pricing_model="fixed",
                pricing_config={"fixed_price": "450.00", "currency": "GBP"},
                status="active",
            )
        )

        # Business B — active, public, with 1 active plumbing offer
        biz_b = Business(name="Aqua Plumbing", slug=f"aqua-plumb-{id(self)}", status="active")
        db_session.add(biz_b)
        await db_session.flush()
        db_session.add(BusinessMember(user_id=test_user.id, business_id=biz_b.id, role="owner"))
        db_session.add(
            BusinessProfile(
                business_id=biz_b.id,
                description="Emergency plumbing services",
                city="Manchester",
                country="UK",
                public_status="active",
            )
        )
        db_session.add(
            ServiceOffer(
                business_id=biz_b.id,
                name="Pipe Repair",
                slug="pipe-repair-p16",
                category_id=plumbing.id,
                delivery_mode="on_site",
                pricing_model="quote_required",
                status="active",
            )
        )

        # Business C — inactive public profile (should NOT appear in directory)
        biz_c = Business(name="Hidden Services", slug=f"hidden-svc-{id(self)}", status="active")
        db_session.add(biz_c)
        await db_session.flush()
        db_session.add(BusinessMember(user_id=test_user.id, business_id=biz_c.id, role="owner"))
        db_session.add(
            BusinessProfile(
                business_id=biz_c.id,
                description="Should not appear",
                public_status="incomplete",
            )
        )
        db_session.add(
            ServiceOffer(
                business_id=biz_c.id,
                name="Secret Work",
                slug="secret-work-p16",
                category_id=electrical.id,
                status="active",
            )
        )

        # Business D — active public, but only draft offers
        biz_d = Business(name="Draft Only Biz", slug=f"draft-only-{id(self)}", status="active")
        db_session.add(biz_d)
        await db_session.flush()
        db_session.add(BusinessMember(user_id=test_user.id, business_id=biz_d.id, role="owner"))
        db_session.add(
            BusinessProfile(
                business_id=biz_d.id,
                description="Only draft offers",
                city="London",
                public_status="active",
            )
        )
        db_session.add(
            ServiceOffer(
                business_id=biz_d.id,
                name="Draft Service",
                slug="draft-service-p16",
                category_id=electrical.id,
                status="draft",
            )
        )

        await db_session.flush()

        return {
            "electrical": electrical,
            "plumbing": plumbing,
            "biz_a": biz_a,
            "biz_b": biz_b,
            "biz_c": biz_c,
            "biz_d": biz_d,
        }

    async def test_directory_lists_active_businesses(self, client: AsyncClient, seed_network_data: dict):
        """Directory returns businesses with active public profiles."""
        response = await client.get("/api/v1/public/businesses")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 2
        slugs = [b["slug"] for b in data["businesses"]]
        assert seed_network_data["biz_a"].slug in slugs
        assert seed_network_data["biz_b"].slug in slugs

    async def test_directory_excludes_inactive_profiles(self, client: AsyncClient, seed_network_data: dict):
        """Businesses with incomplete public_status are NOT in directory."""
        response = await client.get("/api/v1/public/businesses")
        data = response.json()
        slugs = [b["slug"] for b in data["businesses"]]
        assert seed_network_data["biz_c"].slug not in slugs

    async def test_directory_filter_by_city(self, client: AsyncClient, seed_network_data: dict):
        """Directory can be filtered by city."""
        response = await client.get("/api/v1/public/businesses?city=London")
        data = response.json()
        for biz in data["businesses"]:
            assert biz["city"] == "London"

    async def test_directory_filter_by_category(self, client: AsyncClient, seed_network_data: dict):
        """Directory can be filtered by service category slug."""
        response = await client.get("/api/v1/public/businesses?category=plumbing-p16")
        data = response.json()
        for biz in data["businesses"]:
            assert "Plumbing P16" in biz["top_categories"]

    async def test_directory_pagination(self, client: AsyncClient, seed_network_data: dict):
        """Directory supports pagination."""
        response = await client.get("/api/v1/public/businesses?limit=1&offset=0")
        data = response.json()
        assert len(data["businesses"]) == 1
        assert data["limit"] == 1
        assert data["offset"] == 0
        assert data["total"] >= 2

    async def test_directory_item_has_offer_count(self, client: AsyncClient, seed_network_data: dict):
        """Directory items include active offer count."""
        response = await client.get("/api/v1/public/businesses")
        data = response.json()
        biz_a_item = next(b for b in data["businesses"] if b["slug"] == seed_network_data["biz_a"].slug)
        assert biz_a_item["active_offer_count"] == 2

    async def test_directory_no_auth_required(self, client: AsyncClient, seed_network_data: dict):
        """Directory is accessible without authentication."""
        response = await client.get("/api/v1/public/businesses")
        assert response.status_code == 200


@pytest.mark.integration
class TestPublicServiceDetail:
    """Test the public service offer detail endpoint."""

    @pytest_asyncio.fixture
    async def seed_service_data(self, db_session: AsyncSession, test_user: User):
        """Create test data for service detail tests."""
        category = ServiceCategory(name="Testing P16", slug="testing-p16")
        db_session.add(category)
        await db_session.flush()

        biz = Business(name="Test Biz Detail", slug=f"test-detail-{id(self)}", status="active")
        db_session.add(biz)
        await db_session.flush()
        db_session.add(BusinessMember(user_id=test_user.id, business_id=biz.id, role="owner"))
        db_session.add(
            BusinessProfile(
                business_id=biz.id,
                description="Test business for service detail",
                public_status="active",
                is_verified=True,
            )
        )

        # Active offer with pricing
        active_offer = ServiceOffer(
            business_id=biz.id,
            name="Active Test Service",
            slug="active-test-svc-p16",
            description="A test service that is active",
            category_id=category.id,
            delivery_mode="remote",
            pricing_model="starting_at",
            pricing_config={"starting_price": "99.00"},
            status="active",
        )
        db_session.add(active_offer)

        # Draft offer (should NOT be accessible)
        draft_offer = ServiceOffer(
            business_id=biz.id,
            name="Draft Test Service",
            slug="draft-test-svc-p16",
            category_id=category.id,
            status="draft",
        )
        db_session.add(draft_offer)

        await db_session.flush()

        return {
            "biz": biz,
            "category": category,
            "active_offer": active_offer,
            "draft_offer": draft_offer,
        }

    async def test_service_detail_returns_active_offer(self, client: AsyncClient, seed_service_data: dict):
        """Public service detail returns an active offer with full detail."""
        biz = seed_service_data["biz"]
        offer = seed_service_data["active_offer"]
        response = await client.get(f"/api/v1/public/business/{biz.slug}/services/{offer.slug}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Active Test Service"
        assert data["business_slug"] == biz.slug
        assert data["business_is_verified"] is True
        assert data["pricing_summary"] is not None
        assert data["pricing_summary"]["pricing_model"] == "starting_at"
        assert data["pricing_summary"]["starting_price"] == "99.00"

    async def test_service_detail_excludes_draft_offer(self, client: AsyncClient, seed_service_data: dict):
        """Draft offers are NOT accessible via public detail."""
        biz = seed_service_data["biz"]
        draft = seed_service_data["draft_offer"]
        response = await client.get(f"/api/v1/public/business/{biz.slug}/services/{draft.slug}")
        assert response.status_code == 404

    async def test_service_detail_no_private_data(self, client: AsyncClient, seed_service_data: dict):
        """Public service detail does not expose raw pricing_config."""
        biz = seed_service_data["biz"]
        offer = seed_service_data["active_offer"]
        response = await client.get(f"/api/v1/public/business/{biz.slug}/services/{offer.slug}")
        data = response.json()
        # Should not expose raw config
        assert "pricing_config" not in data
        assert "booking_rules" not in data
        assert "cancellation_policy" not in data
        # Should have the safe summary instead
        assert "pricing_summary" in data

    async def test_service_detail_nonexistent_business(self, client: AsyncClient, seed_service_data: dict):
        """Nonexistent business returns 404."""
        response = await client.get("/api/v1/public/business/nonexistent-biz/services/some-service")
        assert response.status_code == 404

    async def test_service_detail_no_auth_required(self, client: AsyncClient, seed_service_data: dict):
        """Service detail is accessible without authentication."""
        biz = seed_service_data["biz"]
        offer = seed_service_data["active_offer"]
        response = await client.get(f"/api/v1/public/business/{biz.slug}/services/{offer.slug}")
        assert response.status_code == 200


@pytest.mark.integration
class TestPublicProfileEnhancements:
    """Test enhanced public business profile fields."""

    @pytest_asyncio.fixture
    async def seed_profile_data(self, db_session: AsyncSession, test_user: User):
        """Create test data for profile enhancement tests."""
        biz = Business(name="Enhanced Profile Biz", slug=f"enhanced-{id(self)}", status="active")
        db_session.add(biz)
        await db_session.flush()
        db_session.add(BusinessMember(user_id=test_user.id, business_id=biz.id, role="owner"))
        db_session.add(
            BusinessProfile(
                business_id=biz.id,
                description="Enhanced profile test",
                public_status="active",
                average_rating=4.8,
                review_count=25,
                is_verified=True,
            )
        )
        cat = ServiceCategory(name="Cat P16", slug="cat-p16")
        db_session.add(cat)
        await db_session.flush()
        db_session.add(
            ServiceOffer(
                business_id=biz.id,
                name="Offer One",
                slug="offer-one-p16",
                category_id=cat.id,
                status="active",
            )
        )
        db_session.add(
            ServiceOffer(
                business_id=biz.id,
                name="Offer Two",
                slug="offer-two-p16",
                category_id=cat.id,
                status="active",
            )
        )
        db_session.add(
            ServiceOffer(
                business_id=biz.id,
                name="Draft Offer",
                slug="draft-offer-p16",
                category_id=cat.id,
                status="draft",
            )
        )
        await db_session.flush()
        return {"biz": biz}

    async def test_public_profile_has_offer_count(self, client: AsyncClient, seed_profile_data: dict):
        """Public business profile includes active_offer_count."""
        biz = seed_profile_data["biz"]
        response = await client.get(f"/api/v1/public/business/{biz.slug}")
        assert response.status_code == 200
        data = response.json()
        assert data["active_offer_count"] == 2  # Only ACTIVE offers counted
        assert len(data["service_offers"]) == 2

    async def test_public_profile_shows_rating_and_reviews(self, client: AsyncClient, seed_profile_data: dict):
        """Public profile exposes rating and review count."""
        biz = seed_profile_data["biz"]
        response = await client.get(f"/api/v1/public/business/{biz.slug}")
        data = response.json()
        assert data["average_rating"] == 4.8
        assert data["review_count"] == 25
        assert data["is_verified"] is True
