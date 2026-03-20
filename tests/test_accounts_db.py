"""Tests for accounts_db service layer."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from shiso.scraper.database import Base
from shiso.scraper.models.accounts import (
    AccountSnapshot,
    FinancialAccount,
    FinancialAccountType,
    ScraperLogin,
)
from shiso.scraper.services.accounts_db import (
    AccountsDB,
    apply_matched_results,
    create_import_session,
    delete_import_session,
    get_import_candidates,
    get_import_session,
)
from shiso.scraper.models.accounts import ImportCandidate


@pytest.fixture()
def db_session():
    """In-memory SQLite session with all tables created."""
    engine = create_engine("sqlite:///:memory:")

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
    )
    from shiso.scraper.models.tools import ProviderPlaybookRecord, ToolRunOutput, WorkflowDefinitionRecord  # noqa: F401

    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.close()


@pytest.fixture()
def accounts_db(db_session, monkeypatch):
    """AccountsDB wired to use test db_session."""
    from shiso.scraper.services import accounts_db as adb

    TestSession = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr(adb, "SessionLocal", TestSession)

    db = AccountsDB()
    return db


class TestApplyMatchedResults:
    def test_applies_provider_key_and_label(self, accounts_db, db_session):
        session = create_import_session(
            filename="test.csv",
            rows=[
                {"row_id": 0, "name": "Chase", "url": "https://chase.com", "domain": "chase.com", "username": "user@example.com", "password": "pass123"},
                {"row_id": 1, "name": "Amex", "url": "https://americanexpress.com", "domain": "americanexpress.com", "username": "user2@example.com", "password": "pass456"},
            ],
        )

        apply_matched_results(session.id, [
            {"row_id": 0, "provider_key": "chase", "label": "Chase", "account_type": "Credit Card", "confidence": 0.98, "match_type": "exact"},
            {"row_id": 1, "provider_key": "amex", "label": "Amex", "account_type": "Credit Card", "confidence": 0.98, "match_type": "exact"},
        ])

        candidates = get_import_candidates(session.id)
        assert len(candidates) == 2

        chase = next(c for c in candidates if c.domain == "chase.com")
        assert chase.provider_key == "chase"
        assert chase.label == "Chase"
        assert chase.account_type == "Credit Card"
        assert chase.match_confidence == 0.98
        assert chase.match_type == "exact"
        assert chase.status == "matched"

        amex = next(c for c in candidates if c.domain == "americanexpress.com")
        assert amex.provider_key == "amex"

    def test_empty_mappings_does_nothing(self, accounts_db, db_session):
        session = create_import_session(
            filename="test.csv",
            rows=[
                {"row_id": 0, "name": "Chase", "url": "https://chase.com", "domain": "chase.com", "username": "user@example.com", "password": "pass123"},
            ],
        )

        apply_matched_results(session.id, [])

        candidates = get_import_candidates(session.id)
        assert candidates[0].status == "pending"
        assert candidates[0].provider_key is None


class TestSaveScrapeResults:
    def test_per_row_account_type_saved_to_financial_account(self, accounts_db, db_session):
        login = ScraperLogin(
            provider_key="amex",
            label="Amex",
            username="user@example.com",
            account_type=None,
        )
        db_session.add(login)
        db_session.commit()
        db_session.refresh(login)

        results = [
            {"login_id": login.id, "account_type": "Credit Card", "account_number": "1234", "current_balance": 1000.0, "raw": {}},
            {"login_id": login.id, "account_type": "Bank", "account_number": "5678", "current_balance": 5000.0, "raw": {}},
        ]

        accounts_db.save_scrape_results("amex", results)

        accounts = db_session.query(FinancialAccount).filter_by(provider_key="amex").all()
        assert len(accounts) == 2

        credit_card_account = next(a for a in accounts if a.account_number == "1234")
        bank_account = next(a for a in accounts if a.account_number == "5678")

        credit_card_type = db_session.get(FinancialAccountType, credit_card_account.account_type_id)
        assert credit_card_type.name == "Credit Card"

        bank_type = db_session.get(FinancialAccountType, bank_account.account_type_id)
        assert bank_type.name == "Bank"

    def test_login_account_type_set_from_first_row(self, accounts_db, db_session):
        login = ScraperLogin(
            provider_key="amex",
            label="Amex",
            username="user@example.com",
            account_type=None,
        )
        db_session.add(login)
        db_session.commit()
        db_session.refresh(login)

        results = [
            {"login_id": login.id, "account_type": "Credit Card", "account_number": "1234", "current_balance": 1000.0, "raw": {}},
            {"login_id": login.id, "account_type": "Bank", "account_number": "5678", "current_balance": 5000.0, "raw": {}},
        ]

        accounts_db.save_scrape_results("amex", results)

        db_session.refresh(login)
        assert login.account_type == "Credit Card"

    def test_existing_account_type_id_updated_on_rescrape(self, accounts_db, db_session):
        login = ScraperLogin(
            provider_key="amex",
            label="Amex",
            username="user@example.com",
            account_type=None,
        )
        db_session.add(login)
        db_session.commit()
        db_session.refresh(login)

        acct_type_credit = db_session.query(FinancialAccountType).filter_by(name="Credit Card").first()
        if not acct_type_credit:
            acct_type_credit = FinancialAccountType(name="Credit Card", balance_type="liability")
            db_session.add(acct_type_credit)
            db_session.commit()
            db_session.refresh(acct_type_credit)

        account = FinancialAccount(
            provider_key="amex",
            institution="Amex",
            account_type_id=acct_type_credit.id,
            account_number="1234",
        )
        db_session.add(account)
        db_session.commit()

        original_type_id = account.account_type_id

        results = [
            {"login_id": login.id, "account_type": "Bank", "account_number": "1234", "current_balance": 1000.0, "raw": {}},
        ]

        accounts_db.save_scrape_results("amex", results)

        db_session.refresh(account)
        bank_type = db_session.query(FinancialAccountType).filter_by(name="Bank").first()
        assert bank_type is not None
        assert account.account_type_id == bank_type.id
        assert account.account_type_id != original_type_id


class TestImportSession:
    def test_create_and_get_session(self, accounts_db, db_session):
        rows = [
            {"row_id": 0, "name": "Chase", "url": "https://chase.com", "domain": "chase.com", "username": "user@example.com", "password": "pass"},
            {"row_id": 1, "name": "Amex", "url": "https://americanexpress.com", "domain": "americanexpress.com", "username": "user2@example.com", "password": "pass2"},
        ]
        session_obj = create_import_session(filename="passwords.csv", rows=rows)

        assert session_obj.id is not None
        assert session_obj.filename == "passwords.csv"
        assert session_obj.total_count == 2
        assert session_obj.status == "pending"

        retrieved = get_import_session(session_obj.id)
        assert retrieved is not None
        assert retrieved.id == session_obj.id

    def test_get_import_candidates_returns_ordered(self, accounts_db, db_session):
        rows = [
            {"row_id": 0, "name": "Chase", "url": "https://chase.com", "domain": "chase.com", "username": "user1@example.com", "password": "pass"},
            {"row_id": 1, "name": "Amex", "url": "https://americanexpress.com", "domain": "americanexpress.com", "username": "user2@example.com", "password": "pass2"},
            {"row_id": 2, "name": "Discover", "url": "https://discover.com", "domain": "discover.com", "username": "user3@example.com", "password": "pass3"},
        ]
        session_obj = create_import_session(filename="passwords.csv", rows=rows)
        candidates = get_import_candidates(session_obj.id)

        assert len(candidates) == 3
        assert candidates[0].row_index == 0
        assert candidates[1].row_index == 1
        assert candidates[2].row_index == 2
        assert candidates[0].username == "user1@example.com"

    def test_delete_session_cascades_to_candidates(self, accounts_db, db_session):
        rows = [
            {"row_id": 0, "name": "Chase", "url": "https://chase.com", "domain": "chase.com", "username": "user@example.com", "password": "pass"},
        ]
        session_obj = create_import_session(filename="passwords.csv", rows=rows)
        session_id = session_obj.id

        candidates = get_import_candidates(session_id)
        assert len(candidates) == 1

        delete_import_session(session_id)

        assert get_import_session(session_id) is None
        remaining = db_session.query(ImportCandidate).filter_by(session_id=session_id).all()
        assert len(remaining) == 0


class TestDuplicateDetection:
    def test_existing_login_detected_as_duplicate(self, accounts_db, db_session):
        existing_login = ScraperLogin(
            provider_key="chase",
            label="Chase",
            username="user@example.com",
            account_type=None,
        )
        db_session.add(existing_login)
        db_session.commit()

        rows = [
            {"row_id": 0, "name": "Chase", "url": "https://chase.com", "domain": "chase.com", "username": "user@example.com", "password": "newpassword"},
        ]
        session_obj = create_import_session(filename="passwords.csv", rows=rows)

        apply_matched_results(session_obj.id, [
            {"row_id": 0, "provider_key": "chase", "label": "Chase", "account_type": "Credit Card", "confidence": 0.98, "match_type": "exact"},
        ])

        candidates = get_import_candidates(session_obj.id)
        assert len(candidates) == 1

        login_key = (candidates[0].provider_key or "", candidates[0].username.lower())
        existing_key = (existing_login.provider_key, existing_login.username.lower())
        assert login_key == existing_key
