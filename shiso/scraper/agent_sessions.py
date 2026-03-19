"""
HTTP client for agent sessions — used by the worker to communicate
with the dashboard's human-in-the-loop system.

The worker runs as a separate process, so it talks to the dashboard
via HTTP rather than sharing in-memory state.
"""

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

DASHBOARD_URL = os.environ.get("SHISO_DASHBOARD_URL", "http://localhost:8002")


def _request(method: str, path: str, *, data: dict | None = None, timeout: float = 5, retries: int = 3, retry_delay: float = 1.0) -> dict | None:
    """Make an HTTP request with retry logic."""
    url = f"{DASHBOARD_URL}{path}"
    body = json.dumps(data).encode() if data else None

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"} if body else None,
        method=method,
    )

    last_exc = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            logger.warning("%s %s → %s", method, path, exc.code)
            if exc.code < 500:
                return None
            last_exc = exc
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            logger.debug("%s %s attempt %d/%d failed: %s", method, path, attempt + 1, retries + 1, exc)
            last_exc = exc

        if attempt < retries:
            time.sleep(retry_delay * (attempt + 1))

    if last_exc:
        logger.warning("%s %s failed after %d attempts: %s", method, path, retries + 1, last_exc)
    return None


def _get_with_status(path: str, *, timeout: float = 5) -> tuple[int, dict | None]:
    """GET request that returns (status_code, body)."""
    url = f"{DASHBOARD_URL}{path}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except Exception as exc:
        logger.debug("GET %s failed: %s", path, exc)
        return 0, None


def check_api_health(*, timeout: float = 5) -> bool:
    """Check if the dashboard API is available."""
    try:
        result = _request("GET", "/api/health", timeout=timeout, retries=0)
        return result is not None and result.get("status") == "ok"
    except Exception:
        return False


def wait_for_api(*, timeout: float = 30, check_interval: float = 1.0) -> bool:
    """Wait for the dashboard API to become available. Returns True if healthy, False on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check_api_health(timeout=2):
            return True
        logger.debug("Waiting for dashboard API at %s...", DASHBOARD_URL)
        time.sleep(check_interval)
    logger.warning("Dashboard API not available after %.0fs", timeout)
    return False


def register_session(run_id: int, login_id: int, provider_key: str) -> None:
    """Register an agent session with the dashboard."""
    result = _request("POST", "/api/agent-sessions", data={
        "run_id": run_id,
        "login_id": login_id,
        "provider_key": provider_key,
    })
    if result:
        logger.info("Registered agent session for run %d", run_id)


def build_http_human_input_handler(run_id: int):
    """Build an async handler that prompts the user via the dashboard API.

    When the agent calls request_human_help, this handler:
    1. PUTs the prompt to the dashboard (sets session to awaiting_input)
    2. Long-polls until the user responds (dashboard blocks for up to 30s per poll)
    3. Returns the response to the agent
    """

    async def handler(prompt: str) -> str:
        loop = asyncio.get_running_loop()

        # Set awaiting_input with the prompt
        result = await loop.run_in_executor(
            None,
            lambda: _request("PUT", f"/api/agent-sessions/{run_id}/await", data={"prompt": prompt}),
        )
        if result is None:
            return "skip"

        # Long-poll for response
        while True:
            try:
                status, data = await loop.run_in_executor(
                    None,
                    lambda: _get_with_status(f"/api/agent-sessions/{run_id}/poll-response", timeout=35),
                )
                if status == 200 and data:
                    response_text = data.get("response", "")
                    if response_text:
                        return response_text
                elif status == 204:
                    continue  # no response yet
                elif status == 404:
                    return "skip"
                else:
                    await asyncio.sleep(2)
            except Exception:
                await asyncio.sleep(2)

    return handler


def complete_session_http(run_id: int, *, status: str = "completed", message: str = "") -> None:
    """Mark an agent session as finished via the dashboard API."""
    _request("PUT", f"/api/agent-sessions/{run_id}/complete", data={
        "status": status,
        "message": message,
    })
