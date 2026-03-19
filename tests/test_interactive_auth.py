"""Tests for interactive auth and 2FA response plumbing."""

from __future__ import annotations


class TestInteractiveAuthTask:
    def test_build_auth_task_mentions_human_assistance_tool(self):
        from shiso.scraper.agent.auth import _build_auth_task

        task = _build_auth_task("amex", {"institution": "American Express"}, {})

        assert "request_human_assistance" in task
        assert "SKIPPED_BY_USER" in task


class TestInteractiveAuthApi:
    def test_interactive_auth_routes_exist(self):
        from shiso.dashboard.main import app

        paths = [route.path for route in app.routes if hasattr(route, "path")]
        assert "/api/logins/{login_id}/interactive" in paths
        assert "/api/logins/{login_id}/interactive/respond" in paths

    def test_get_interactive_auth_status_defaults_to_idle(self):
        import shiso.dashboard.main as dashboard_main

        response = dashboard_main.get_interactive_auth_status(999)

        assert response.status == "idle"
        assert response.login_id == 999

    def test_respond_interactive_auth_sets_pending_response(self):
        import shiso.dashboard.main as dashboard_main

        session = dashboard_main.InteractiveAuthSessionState(
            login_id=12,
            provider_key="amex",
            status="awaiting_input",
            message="Enter the 6-digit code.",
            prompt="Enter the 6-digit code.",
        )

        dashboard_main._interactive_auth_sessions[12] = session
        try:
            response = dashboard_main.respond_interactive_auth(
                12,
                dashboard_main.InteractiveAuthRespondRequest(response="123456"),
            )
        finally:
            dashboard_main._interactive_auth_sessions.pop(12, None)

        assert response.status == "running"
        assert session.pending_response == "123456"
        assert session.response_event.is_set()

    def test_respond_interactive_auth_can_skip(self):
        import shiso.dashboard.main as dashboard_main

        session = dashboard_main.InteractiveAuthSessionState(
            login_id=21,
            provider_key="chase",
            status="awaiting_input",
            message="Enter the push confirmation or skip.",
            prompt="Enter the push confirmation or skip.",
        )

        dashboard_main._interactive_auth_sessions[21] = session
        try:
            response = dashboard_main.respond_interactive_auth(
                21,
                dashboard_main.InteractiveAuthRespondRequest(skip=True),
            )
        finally:
            dashboard_main._interactive_auth_sessions.pop(21, None)

        assert response.status == "running"
        assert session.pending_response == "skip"
        assert session.response_event.is_set()
