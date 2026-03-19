"""Tests for dashboard account responses."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_dashboard_accounts_include_linked_login_id(monkeypatch):
    import shiso.dashboard.main as dashboard_main
    from shiso.scraper.services.accounts_db import SnapshotView

    sample_snapshot = SnapshotView(
        provider_key="amex",
        institution="American Express",
        scraper_login_id=17,
        display_name="Blue Cash Preferred",
        account_number=None,
        account_mask="1001",
        address=None,
        status="open",
        current_balance=0.0,
        statement_balance=0.0,
        minimum_payment=None,
        due_date=None,
        last_payment_amount=None,
        last_payment_date=None,
        credit_limit=10000.0,
        interest_rate=None,
        account_subcategory="Credit Card",
        account_category="Credit Card",
        balance_type="liability",
        signed_balance=0.0,
        first_seen_at=None,
        last_seen_at=None,
        last_snapshot_at=None,
        updated_at=None,
        captured_at="2026-03-18T00:00:00",
    )

    monkeypatch.setattr(dashboard_main.db, "get_latest_snapshots", lambda: [sample_snapshot])
    monkeypatch.setattr(dashboard_main.db, "get_summary", lambda: {"accounts": 1})
    monkeypatch.setattr(dashboard_main.scraper, "PROVIDER_KEYS", {"amex"})

    client = TestClient(dashboard_main.app)
    response = client.get("/api/accounts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshots"][0]["scraper_login_id"] == 17
