"""Smoke tests for the Shiso dashboard UI using Playwright.

Requirements:
    pip install pytest-playwright
    playwright install chromium

Run:
    pytest tests/test_dashboard_ui.py -v

What it tests:
    - Dashboard page loads without crashing
    - No console errors (Error level)
    - Key UI sections are rendered
    - API responses are reflected in the UI
"""

from __future__ import annotations

import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Generator

import pytest
from playwright.sync_api import Browser, Page, expect


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def api_server() -> Generator[str, None, None]:
    """Start the FastAPI dashboard server in a background thread."""
    import uvicorn
    from shiso.dashboard.main import app

    shutdown = threading.Event()

    def run():
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=8299,
            log_level="warning",
        )

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    time.sleep(1.5)  # give uvicorn time to start
    yield "http://127.0.0.1:8299"
    shutdown.set()


@pytest.fixture(scope="module")
def frontend_url(api_server: str) -> Generator[str, None, None]:
    """Serve the built frontend dist and return its URL.

    The dist folder has API_BASE = '/api' hardcoded, so we intercept
    /api/* requests and route them to the FastAPI server.
    """
    dist_path = Path(__file__).parent.parent / "shiso" / "dashboard" / "frontend" / "dist"

    class ProxyingHTTPHandler(SimpleHTTPRequestHandler):
        API_TARGET = api_server.rstrip("/")

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(dist_path), **kwargs)

        def do_GET(self):
            if self.path.startswith("/api"):
                self._proxy("GET")
            else:
                super().do_GET()

        def do_POST(self):
            if self.path.startswith("/api"):
                self._proxy("POST")
            else:
                super().do_POST()

        def do_PUT(self):
            if self.path.startswith("/api"):
                self._proxy("PUT")
            else:
                super().do_PUT()

        def do_PATCH(self):
            if self.path.startswith("/api"):
                self._proxy("PATCH")
            else:
                super().do_PATCH()

        def do_DELETE(self):
            if self.path.startswith("/api"):
                self._proxy("DELETE")
            else:
                super().do_DELETE()

        def _proxy(self, method: str):
            import urllib.request
            import urllib.error

            url = f"{self.API_TARGET}{self.path}"
            body = self.rfile.read(int(self.headers.get("Content-Length", 0))) if method in ("POST", "PUT", "PATCH") else None
            req = urllib.request.Request(url, data=body, method=method)
            for key, val in self.headers.items():
                if key.lower() not in ("host", "content-length"):
                    req.add_header(key, val)

            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    self.send_response(resp.status)
                    self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
                    self.send_header("Access-Control-Allow-Headers", "*")
                    self.end_headers()
                    self.wfile.write(resp.read())
            except urllib.error.HTTPError as e:
                self.send_response(e.code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(e.read())

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.end_headers()

        def log_message(self, format, *args):
            pass  # silence request logging

    server = HTTPServer(("127.0.0.1", 8377), ProxyingHTTPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:8377"
    server.shutdown()


@pytest.fixture(scope="module")
def browser() -> Generator[Browser, None, None]:
    """Launch Chromium for all tests in this module."""
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    yield browser
    browser.close()
    pw.stop()


@pytest.fixture
def page(browser: Browser, frontend_url: str) -> Generator[Page, None, None]:
    """Open a new page per test."""
    ctx = browser.new_context()
    page = ctx.new_page()
    yield page
    ctx.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDashboardSmoke:
    def test_page_loads_without_crash(self, page: Page, frontend_url: str):
        """Navigating to the dashboard root succeeds (200)."""
        response = page.goto(frontend_url)
        assert response is not None
        assert response.status in (200, 304)

    def test_no_console_errors(self, page: Page, frontend_url: str):
        """Page emits no console errors (Error level)."""
        errors: list[str] = []

        def on_console(msg):
            if msg.type == "error":
                errors.append(msg.text)

        page.on("console", on_console)
        page.goto(frontend_url)
        page.wait_for_load_state("networkidle", timeout=15_000)

        assert errors == [], f"Console errors found: {errors}"

    def test_page_title_or_heading(self, page: Page, frontend_url: str):
        """Dashboard shows a title or heading."""
        page.goto(frontend_url)
        page.wait_for_load_state("networkidle", timeout=15_000)
        # The app uses Vue; wait for at least one section to appear
        page.wait_for_selector("[class*='section'], header, h1, h2, nav", timeout=10_000)
        content = page.content()
        assert len(content) > 100  # not an empty shell

    def test_accounts_api_populates_ui(self, page: Page, frontend_url: str):
        """The accounts section eventually renders account data from the API.

        This is an integration smoke test — we don't test specific accounts,
        just that the API data flows through to the UI.
        """
        page.goto(frontend_url)
        page.wait_for_load_state("networkidle", timeout=15_000)
        # Wait for any account-related content (table, card, list item, etc.)
        page.wait_for_function(
            """() => {
                const text = document.body.innerText;
                return text.length > 50;
            }""",
            timeout=10_000,
        )
        # The API should have returned our 54 snapshots — verify at least
        # one account-related keyword appears in the rendered text
        body_text = page.inner_text("body").lower()
        assert any(kw in body_text for kw in ["account", "balance", "card", "chase", "amex", "credit"]), \
            f"No account-related content found. Body text: {body_text[:200]}"

    def test_navigation_elements_present(self, page: Page, frontend_url: str):
        """At least one navigation or section element is visible."""
        page.goto(frontend_url)
        page.wait_for_load_state("networkidle", timeout=15_000)
        nav = page.query_selector("nav, header, [role='navigation'], aside")
        assert nav is not None, "No nav/header element found"

    def test_health_endpoint_reachable(self, page: Page, api_server: str):
        """The /api/health endpoint responds correctly."""
        response = page.request.get(f"{api_server}/api/health")
        assert response.status == 200
        data = response.json()
        assert data.get("status") == "ok"

    def test_accounts_endpoint_reachable(self, page: Page, api_server: str):
        """The /api/accounts endpoint returns our snapshot data."""
        response = page.request.get(f"{api_server}/api/accounts")
        assert response.status == 200
        data = response.json()
        assert "snapshots" in data
        assert "summary" in data
