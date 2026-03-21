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
    from shiso.scraper.models.sync_type import SyncTypeRecord  # noqa: F401
    from shiso.scraper.models.tools import ProviderPlaybookRecord, ToolRunOutput, WorkflowDefinitionRecord  # noqa: F401

    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.close()


SAMPLE_CSV_CONTENT = """name,url,username,password
Chase,https://chase.com,user@example.com,password123
American Express,https://americanexpress.com,user@example.com,password456
American Express,https://online.americanexpress.com,user2@example.com,password789
IndyWater,https://indianaamericanwater.com,user@example.com,password000
Unknown Service,https://someobscuresite.com,user@example.com,password111
"""


@pytest.fixture()
def sample_csv_content():
    """Real Chrome password manager CSV export format."""
    return SAMPLE_CSV_CONTENT
