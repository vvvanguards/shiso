"""Tests for import API endpoints."""

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from shiso.scraper.database import Base
from shiso.scraper.services.accounts_db import BASELINE_PROVIDERS


@pytest.fixture()
def test_engine():
    """File-based SQLite engine for testing (shared across modules)."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    from shiso.scraper.models.accounts import (
        AccountSnapshot, AccountStatement, FinancialAccount,
        FinancialAccountIdentifier, FinancialAccountLogin,
        FinancialAccountType, PromoAprPeriod, ScraperLogin,
        ScraperLoginSyncRun,
        ImportCandidate, ImportSession, ProviderMapping,
    )
    from shiso.scraper.models.tools import ProviderPlaybookRecord, ToolRunOutput, WorkflowDefinitionRecord  # noqa: F401
    from shiso.scraper.models.sync_type import SyncTypeRecord  # noqa: F401

    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture()
def test_session(test_engine):
    """Session bound to the test engine."""
    TestSession = sessionmaker(bind=test_engine)
    session = TestSession()
    yield session
    session.close()


@pytest.fixture()
def client(test_engine):
    """TestClient with all SessionLocal references patched to use test engine."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    import shiso.dashboard.main as dashboard_main
    from shiso.scraper import database
    from shiso.scraper.services import accounts_db
    from shiso.scraper import api as scraper_api
    from shiso.scraper.services import provider_matcher

    TestSession = sessionmaker(bind=test_engine)

    def fake_build_lookup():
        lookup = {}
        for p in BASELINE_PROVIDERS:
            lookup[p["domain_pattern"]] = p
        return lookup

    with patch.object(database, "SessionLocal", TestSession), \
         patch.object(accounts_db, "SessionLocal", TestSession), \
         patch.object(scraper_api, "SessionLocal", TestSession), \
         patch.object(provider_matcher, "_build_provider_lookup", fake_build_lookup):
        yield TestClient(dashboard_main.app)


SAMPLE_CSV = b"""name,url,username,password
Chase,https://chase.com,user@example.com,password123
American Express,https://americanexpress.com,user@example.com,password456
"""


class TestImportStartEndpoint:
    def test_parses_csv_and_returns_session_with_candidates(self, client):
        response = client.post(
            "/api/logins/import/start",
            files={"file": ("passwords.csv", SAMPLE_CSV, "text/csv")},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["session_id"] is not None
        assert len(data["candidates"]) == 2
        assert data["summary"]["total"] == 2

        chase = next(c for c in data["candidates"] if "chase" in c["domain"])
        assert chase["provider_key"] == "chase"
        assert chase["label"] == "Chase"
        assert chase["username"] == "user@example.com"

    def test_candidates_have_matching_fields(self, client):
        response = client.post(
            "/api/logins/import/start",
            files={"file": ("passwords.csv", SAMPLE_CSV, "text/csv")},
        )

        assert response.status_code == 200
        data = response.json()

        for c in data["candidates"]:
            assert "id" in c
            assert "domain" in c
            assert "username" in c
            assert "provider_key" in c
            assert "label" in c
            assert "is_duplicate" in c

    def test_empty_csv_returns_empty(self, client):
        empty_csv = b"name,url,username,password\n"
        response = client.post(
            "/api/logins/import/start",
            files={"file": ("empty.csv", empty_csv, "text/csv")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] is None
        assert data["candidates"] == []


class TestImportConfirmEndpoint:
    def test_creates_scraper_login_for_new(self, client):
        start_response = client.post(
            "/api/logins/import/start",
            files={"file": ("passwords.csv", SAMPLE_CSV, "text/csv")},
        )
        session_id = start_response.json()["session_id"]
        candidates = start_response.json()["candidates"]
        chase_id = next(c["id"] for c in candidates if "chase" in c["domain"])

        confirm_response = client.post(
            f"/api/logins/import/{session_id}/confirm",
            json=[chase_id],
        )

        assert confirm_response.status_code == 200
        result = confirm_response.json()
        assert result["imported"] == 1
        assert result["updated"] == 0

        get_response = client.get(f"/api/logins/import/{session_id}")
        assert get_response.status_code == 404

    def test_updates_existing_login_password(self, client, test_session):
        from shiso.scraper.models.accounts import ScraperLogin
        from shiso.scraper.services.crypto import encrypt

        existing = ScraperLogin(
            provider_key="chase",
            label="Chase",
            username="user@example.com",
            password_encrypted=encrypt("oldpassword"),
            account_type=None,
        )
        test_session.add(existing)
        test_session.commit()

        start_response = client.post(
            "/api/logins/import/start",
            files={"file": ("passwords.csv", SAMPLE_CSV, "text/csv")},
        )
        session_id = start_response.json()["session_id"]
        candidates = start_response.json()["candidates"]
        chase_id = next(c["id"] for c in candidates if "chase" in c["domain"])

        confirm_response = client.post(
            f"/api/logins/import/{session_id}/confirm",
            json=[chase_id],
        )

        assert confirm_response.status_code == 200
        result = confirm_response.json()
        assert result["imported"] == 0
        assert result["updated"] == 1

    def test_sets_account_type_to_none_on_new_login(self, client, test_session):
        from shiso.scraper.models.accounts import ScraperLogin

        start_response = client.post(
            "/api/logins/import/start",
            files={"file": ("passwords.csv", SAMPLE_CSV, "text/csv")},
        )
        session_id = start_response.json()["session_id"]
        candidates = start_response.json()["candidates"]
        amex_id = next(c["id"] for c in candidates if "americanexpress" in c["domain"])

        client.post(
            f"/api/logins/import/{session_id}/confirm",
            json=[amex_id],
        )

        test_session.expire_all()
        login = test_session.query(ScraperLogin).filter_by(provider_key="amex").first()
        assert login is not None
        assert login.account_type is None


class TestImportDeleteEndpoint:
    def test_deletes_session_and_candidates(self, client):
        start_response = client.post(
            "/api/logins/import/start",
            files={"file": ("passwords.csv", SAMPLE_CSV, "text/csv")},
        )
        session_id = start_response.json()["session_id"]

        get_response = client.get(f"/api/logins/import/{session_id}")
        assert get_response.status_code == 200

        delete_response = client.delete(f"/api/logins/import/{session_id}")
        assert delete_response.status_code == 200
        assert delete_response.json()["deleted"] is True

        get_response_after = client.get(f"/api/logins/import/{session_id}")
        assert get_response_after.status_code == 404

    def test_delete_nonexistent_returns_404(self, client):
        response = client.delete("/api/logins/import/99999")
        assert response.status_code == 404
