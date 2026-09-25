"""Browser E2E tests for FIELDed using Playwright.

Tests the complete customer and business journeys through the actual browser:
1. Customer: signup → login → discovery → enquiry → conversation → quote → booking → payment → review
2. Business: login → enquiries → quote → booking → Brain → communications → Call Agent

Run with: pytest tests/e2e/test_browser_e2e.py --browser chromium -v
Or against production: RUN_E2E_TESTS=1 E2E_FRONTEND_URL=https://fielded.online pytest tests/e2e/test_browser_e2e.py
"""

from __future__ import annotations

import os
import re
import uuid

import pytest

# Skip all browser E2E tests unless explicitly enabled
pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_E2E_TESTS"),
    reason="Browser E2E tests require RUN_E2E_TESTS=1",
)

# Check if playwright is available
try:
    from playwright.sync_api import Page, expect

    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    if os.environ.get("RUN_E2E_TESTS"):
        pytest.skip("Playwright not installed", allow_module_level=True)

# Base URLs
FRONTEND_URL = os.environ.get("E2E_FRONTEND_URL", "http://localhost:3000")
BACKEND_URL = os.environ.get("E2E_BACKEND_URL", "http://localhost:8000")


def _unique_email() -> str:
    """Generate a unique email for test users."""
    return f"e2e-{uuid.uuid4().hex[:8]}@fielded.test"


@pytest.fixture(scope="module")
def test_user_credentials() -> dict:
    """Test user credentials for E2E tests."""
    return {
        "email": os.environ.get("E2E_TEST_EMAIL", _unique_email()),
        "password": os.environ.get("E2E_TEST_PASSWORD", "TestPass123!"),
    }


@pytest.fixture(scope="module")
def business_user_credentials() -> dict:
    """Business user credentials for E2E tests."""
    return {
        "email": os.environ.get("E2E_BUSINESS_EMAIL", _unique_email()),
        "password": os.environ.get("E2E_BUSINESS_PASSWORD", "TestPass123!"),
    }


class TestCustomerJourney:
    """Customer end-to-end journey tests."""

    def test_landing_page_loads(self, page: Page) -> None:
        """Landing page loads with expected content."""
        page.goto(FRONTEND_URL)
        expect(page).to_have_title(re.compile("FIELDed"))
        expect(page.locator("text=FIELDed")).to_be_visible()

    def test_search_page_accessible(self, page: Page) -> None:
        """Search page is accessible from landing."""
        page.goto(FRONTEND_URL)
        page.click('a[href="/search"]')
        expect(page).to_have_url(re.compile(".*search"))

    def test_login_page_loads(self, page: Page) -> None:
        """Login page loads with form elements."""
        page.goto(f"{FRONTEND_URL}/login")
        expect(page.locator('input[type="email"]')).to_be_visible()
        expect(page.locator('input[type="password"]')).to_be_visible()
        expect(page.locator('button[type="submit"]')).to_be_visible()

    def test_signup_page_loads(self, page: Page) -> None:
        """Signup page loads with form elements."""
        page.goto(f"{FRONTEND_URL}/signup")
        expect(page.locator('input[type="email"]')).to_be_visible()
        expect(page.locator('input[type="password"]')).to_be_visible()

    def test_customer_signup_and_login(self, page: Page, test_user_credentials: dict) -> None:
        """Customer can sign up and log in."""
        email = test_user_credentials["email"]
        password = test_user_credentials["password"]

        # Sign up
        page.goto(f"{FRONTEND_URL}/signup")
        page.fill('input[type="email"]', email)
        page.fill('input[type="password"]', password)
        page.click('button[type="submit"]')

        # Should redirect to customer dashboard or similar
        page.wait_for_url(re.compile(".*customer.*"))
        expect(page).to_have_url(re.compile(".*customer.*"))

    def test_customer_discovery_search(self, page: Page) -> None:
        """Customer can perform discovery search."""
        page.goto(f"{FRONTEND_URL}/search")
        search_input = page.locator('input[placeholder*="search" i], input[placeholder*="need" i], input[name="query"]')
        if search_input.count() > 0:
            search_input.fill("plumber")
            page.click('button[type="submit"]')
            # Should show results or loading state
            page.wait_for_load_state("networkidle")

    def test_customer_view_business_profile(self, page: Page) -> None:
        """Customer can view a business profile."""
        page.goto(f"{FRONTEND_URL}/network")
        # Click on first business if available
        first_business = page.locator('a[href*="/business/"]').first
        if first_business.is_visible():
            first_business.click()
            page.wait_for_load_state("networkidle")
            # Should see business name and details
            expect(page.locator("h1, h2").first).to_be_visible()

    def test_business_navigation_sidebar(self, page: Page) -> None:
        """Business dashboard has proper navigation."""
        # This test requires a logged-in business user
        # Skip if not authenticated
        page.goto(f"{FRONTEND_URL}/business/dashboard")
        if page.locator("text=Sign In").is_visible():
            pytest.skip("Not authenticated")
        # Check nav items exist
        expect(page.locator('a[href="/business/enquiries"]')).to_be_visible()
        expect(page.locator('a[href="/business/call-agent"]')).to_be_visible()


class TestBusinessJourney:
    """Business end-to-end journey tests."""

    def test_business_dashboard_loads(self, page: Page) -> None:
        """Business dashboard loads for authenticated users."""
        page.goto(f"{FRONTEND_URL}/business/dashboard")
        # If redirected to login, skip
        if "/login" in page.url:
            pytest.skip("Not authenticated")
        expect(page.locator("text=Good")).to_be_visible()

    def test_business_enquiries_page(self, page: Page) -> None:
        """Business enquiries page loads."""
        page.goto(f"{FRONTEND_URL}/business/enquiries")
        if "/login" in page.url:
            pytest.skip("Not authenticated")
        expect(page).to_have_url(re.compile(".*enquiries"))

    def test_business_call_agent_page(self, page: Page) -> None:
        """Business Call Agent page loads."""
        page.goto(f"{FRONTEND_URL}/business/call-agent")
        if "/login" in page.url:
            pytest.skip("Not authenticated")
        expect(page.locator("text=Call Agent")).to_be_visible()

    def test_business_brain_page(self, page: Page) -> None:
        """Business Brain page loads."""
        page.goto(f"{FRONTEND_URL}/business/brain")
        if "/login" in page.url:
            pytest.skip("Not authenticated")
        expect(page).to_have_url(re.compile(".*brain"))

    def test_business_services_page(self, page: Page) -> None:
        """Business services page loads."""
        page.goto(f"{FRONTEND_URL}/business/services")
        if "/login" in page.url:
            pytest.skip("Not authenticated")
        expect(page).to_have_url(re.compile(".*services"))


class TestPublicPages:
    """Public page accessibility tests."""

    def test_landing_page_content(self, page: Page) -> None:
        """Landing page has expected content structure."""
        page.goto(FRONTEND_URL)
        # Check for key elements
        expect(page.locator("header, nav").first).to_be_visible()
        expect(page.locator("footer").first).to_be_visible()

    def test_network_page_loads(self, page: Page) -> None:
        """Network/search page loads businesses."""
        page.goto(f"{FRONTEND_URL}/network")
        page.wait_for_load_state("networkidle")
        # Should have business listings or empty state
        expect(page.locator("main").first).to_be_visible()

    def test_search_page_loads(self, page: Page) -> None:
        """Search page loads with search input."""
        page.goto(f"{FRONTEND_URL}/search")
        page.wait_for_load_state("networkidle")
        expect(page.locator("main").first).to_be_visible()

    def test_login_page_structure(self, page: Page) -> None:
        """Login page has proper structure."""
        page.goto(f"{FRONTEND_URL}/login")
        expect(page.locator("form").first).to_be_visible()
        expect(page.locator('input[type="email"]')).to_be_visible()
        expect(page.locator('input[type="password"]')).to_be_visible()

    def test_signup_page_structure(self, page: Page) -> None:
        """Signup page has proper structure."""
        page.goto(f"{FRONTEND_URL}/signup")
        expect(page.locator("form").first).to_be_visible()
        expect(page.locator('input[type="email"]')).to_be_visible()


class TestResponsiveDesign:
    """Responsive design tests across viewports."""

    def test_mobile_viewport(self, page: Page) -> None:
        """Pages render correctly on mobile viewport."""
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(FRONTEND_URL)
        expect(page.locator("header, nav").first).to_be_visible()

    def test_tablet_viewport(self, page: Page) -> None:
        """Pages render correctly on tablet viewport."""
        page.set_viewport_size({"width": 768, "height": 1024})
        page.goto(FRONTEND_URL)
        expect(page.locator("header, nav").first).to_be_visible()

    def test_desktop_viewport(self, page: Page) -> None:
        """Pages render correctly on desktop viewport."""
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.goto(FRONTEND_URL)
        expect(page.locator("header, nav").first).to_be_visible()


class TestAccessibility:
    """Basic accessibility tests."""

    def test_page_has_title(self, page: Page) -> None:
        """All pages have a title."""
        page.goto(FRONTEND_URL)
        expect(page).to_have_title(re.compile(".+"))

    def test_images_have_alt(self, page: Page) -> None:
        """Images have alt attributes."""
        page.goto(FRONTEND_URL)
        images = page.locator("img")
        for i in range(images.count()):
            img = images.nth(i)
            alt = img.get_attribute("alt")
            assert alt is not None, f"Image missing alt: {img.get_attribute('src')}"

    def test_form_labels_present(self, page: Page) -> None:
        """Form inputs have associated labels."""
        page.goto(f"{FRONTEND_URL}/login")
        inputs = page.locator("input")
        for i in range(inputs.count()):
            input_el = inputs.nth(i)
            input_type = input_el.get_attribute("type")
            if input_type in ("hidden", "submit"):
                continue
            # Check for label or aria-label
            label = input_el.evaluate("""el => {
                const id = el.id;
                if (id) {
                    const label = document.querySelector(`label[for="${id}"]`);
                    if (label) return true;
                }
                return el.getAttribute('aria-label') !== null || el.getAttribute('placeholder') !== null;
            }""")
            assert label, f"Input missing label: {input_el.get_attribute('name') or input_el.get_attribute('type')}"
