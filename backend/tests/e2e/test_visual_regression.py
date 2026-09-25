"""Visual regression tests for FIELDed production pages.

Captures screenshots of critical pages and compares against baselines.
Run with: pytest tests/e2e/test_visual_regression.py --browser chromium -v

Baselines are stored in tests/e2e/baselines/
Update baselines with: UPDATE_BASELINES=1 pytest tests/e2e/test_visual_regression.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Skip unless explicitly enabled
pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_E2E_TESTS"),
    reason="Visual regression tests require RUN_E2E_TESTS=1",
)

try:
    from playwright.sync_api import Page

    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    if os.environ.get("RUN_E2E_TESTS"):
        pytest.skip("Playwright not installed", allow_module_level=True)

FRONTEND_URL = os.environ.get("E2E_FRONTEND_URL", "http://localhost:3000")
BASELINES_DIR = Path(__file__).parent / "baselines"
SCREENSHOTS_DIR = Path(__file__).parent / "screenshots"
UPDATE_BASELINES = os.environ.get("UPDATE_BASELINES", "0") == "1"

# Critical pages to capture
CRITICAL_PAGES = [
    ("/", "landing"),
    ("/search", "search"),
    ("/network", "network"),
    ("/login", "login"),
    ("/signup", "signup"),
]


@pytest.fixture(autouse=True)
def setup_dirs() -> None:
    """Ensure screenshot directories exist."""
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def _compare_screenshots(baseline_path: Path, current_path: Path, threshold: float = 0.15) -> bool:
    """Compare two screenshots by file-size ratio.

    Returns True if images match within threshold.
    This is a simple file-size comparison — sufficient for catching major layout
    breaks while tolerating normal dynamic-content variation (timestamps, listings).
    For pixel-perfect comparison, consider using pixelmatch or similar.
    """
    if not baseline_path.exists():
        return False

    baseline_size = baseline_path.stat().st_size
    current_size = current_path.stat().st_size

    # Allow size difference within threshold (accounts for dynamic content, rendering)
    if baseline_size == 0:
        return current_size == 0
    ratio = abs(current_size - baseline_size) / baseline_size
    return ratio < threshold


class TestVisualRegression:
    """Visual regression tests for critical pages."""

    @pytest.mark.parametrize("path,name", CRITICAL_PAGES)
    def test_page_screenshot(self, page: Page, path: str, name: str) -> None:
        """Capture and compare page screenshots."""
        # Set desktop viewport
        page.set_viewport_size({"width": 1440, "height": 900})

        # Navigate and wait for load
        page.goto(f"{FRONTEND_URL}{path}")
        page.wait_for_load_state("networkidle")
        # Extra wait for animations/rendering
        page.wait_for_timeout(500)

        # Take screenshot
        screenshot_path = SCREENSHOTS_DIR / f"{name}.png"
        page.screenshot(path=str(screenshot_path), full_page=True)

        baseline_path = BASELINES_DIR / f"{name}.png"

        if UPDATE_BASELINES:
            # Update baseline
            screenshot_path.rename(baseline_path)
            pytest.skip(f"Updated baseline for {name}")
        else:
            # Compare against baseline
            if not baseline_path.exists():
                # No baseline yet — save current as baseline
                screenshot_path.rename(baseline_path)
                pytest.skip(f"Created initial baseline for {name}")

            # Compare
            matches = _compare_screenshots(baseline_path, screenshot_path)
            assert matches, (
                f"Visual regression detected on {name} page. "
                f"Baseline: {baseline_path}, Current: {screenshot_path}. "
                f"Run with UPDATE_BASELINES=1 to update if changes are intentional."
            )


class TestMobileVisualRegression:
    """Visual regression tests for mobile viewport."""

    @pytest.mark.parametrize(
        "path,name",
        [
            ("/", "landing-mobile"),
            ("/login", "login-mobile"),
            ("/network", "network-mobile"),
        ],
    )
    def test_mobile_screenshot(self, page: Page, path: str, name: str) -> None:
        """Capture and compare mobile screenshots."""
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{FRONTEND_URL}{path}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)

        screenshot_path = SCREENSHOTS_DIR / f"{name}.png"
        page.screenshot(path=str(screenshot_path), full_page=True)

        baseline_path = BASELINES_DIR / f"{name}.png"

        if UPDATE_BASELINES:
            screenshot_path.rename(baseline_path)
            pytest.skip(f"Updated baseline for {name}")
        else:
            if not baseline_path.exists():
                screenshot_path.rename(baseline_path)
                pytest.skip(f"Created initial baseline for {name}")

            matches = _compare_screenshots(baseline_path, screenshot_path)
            assert matches, f"Mobile visual regression on {name}"


class TestBusinessDashboardVisual:
    """Visual tests for business dashboard (requires auth)."""

    def test_business_dashboard_screenshot(self, page: Page) -> None:
        """Capture business dashboard if authenticated."""
        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto(f"{FRONTEND_URL}/business/dashboard")

        # Skip if not authenticated
        if "/login" in page.url:
            pytest.skip("Not authenticated")

        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)

        screenshot_path = SCREENSHOTS_DIR / "business-dashboard.png"
        page.screenshot(path=str(screenshot_path), full_page=True)

        baseline_path = BASELINES_DIR / "business-dashboard.png"

        if UPDATE_BASELINES:
            screenshot_path.rename(baseline_path)
            pytest.skip("Updated business dashboard baseline")
        elif not baseline_path.exists():
            screenshot_path.rename(baseline_path)
            pytest.skip("Created initial business dashboard baseline")
        else:
            # Business dashboard has dynamic stats (revenue, counts) — use higher threshold
            matches = _compare_screenshots(baseline_path, screenshot_path, threshold=0.25)
            assert matches, "Business dashboard visual regression"

    def test_call_agent_screenshot(self, page: Page) -> None:
        """Capture Call Agent page if authenticated."""
        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto(f"{FRONTEND_URL}/business/call-agent")

        if "/login" in page.url:
            pytest.skip("Not authenticated")

        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)

        screenshot_path = SCREENSHOTS_DIR / "call-agent.png"
        page.screenshot(path=str(screenshot_path), full_page=True)

        baseline_path = BASELINES_DIR / "call-agent.png"

        if UPDATE_BASELINES:
            screenshot_path.rename(baseline_path)
            pytest.skip("Updated Call Agent baseline")
        elif not baseline_path.exists():
            screenshot_path.rename(baseline_path)
            pytest.skip("Created initial Call Agent baseline")
        else:
            matches = _compare_screenshots(baseline_path, screenshot_path)
            assert matches, "Call Agent visual regression"
