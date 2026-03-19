"""Shared fixtures for Shiso tests."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from shiso.scraper.database import Base


@pytest.fixture()
def db_session():
    """In-memory SQLite session with all tables created."""
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Import all models so metadata is populated
    from shiso.scraper.models.accounts import (  # noqa: F401
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
