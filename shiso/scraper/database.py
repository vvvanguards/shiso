"""
Shared database configuration for Shiso.

Schema is not yet finalized — use reset_db() to drop and recreate.

TODO: Once the schema stabilizes, switch to Alembic migrations and
      stop calling init_db()/create_all on every startup.
"""

from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATABASE_PATH = PROJECT_ROOT / "data" / "shiso.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"


class Base(DeclarativeBase):
    """Base class for dashboard ORM models."""


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# Canonical account types with asset/liability classification.
ACCOUNT_TYPES = {
    "Credit Card":      "liability",
    "Loan":             "liability",
    "Mortgage":         "liability",
    "Line of Credit":   "liability",
    "Utility":          "liability",
    "Insurance":        "liability",
    "Checking":         "asset",
    "Savings":          "asset",
    "Investment":       "asset",
    "Property":         "asset",
    "Other":            "liability",
    "Unknown":          "liability",
}


def _import_models() -> None:
    """Ensure all models are imported so metadata is populated."""
    from .models.accounts import (  # noqa: F401
        AccountSnapshot,
        AccountStatement,
        FinancialAccount,
        FinancialAccountIdentifier,
        FinancialAccountLogin,
        FinancialAccountType,
        PromoAprPeriod,
        ScraperLogin,
        ScraperLoginSyncRun,
    )
    from .models.tools import (  # noqa: F401
        ProviderPlaybookRecord,
        ToolRunOutput,
        WorkflowDefinitionRecord,
        WorkflowRevisionSuggestionRecord,
    )


def init_db() -> None:
    """Create tables if they don't exist and seed reference data."""
    _import_models()
    Base.metadata.create_all(bind=engine)
    _apply_lightweight_schema_updates()
    _seed_account_types()
    _seed_builtin_workflows()


def reset_db() -> None:
    """Drop and recreate all tables. Destroys all data."""
    _import_models()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    _seed_account_types()
    _seed_builtin_workflows()


def _apply_lightweight_schema_updates() -> None:
    """Apply simple ALTER TABLE updates while the schema is still evolving."""
    with engine.begin() as conn:
        sync_run_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(scraper_login_sync_runs)")).fetchall()
        }
        if "account_filter" not in sync_run_columns:
            conn.execute(text("ALTER TABLE scraper_login_sync_runs ADD COLUMN account_filter TEXT"))
        if "agent_log_path" not in sync_run_columns:
            conn.execute(text("ALTER TABLE scraper_login_sync_runs ADD COLUMN agent_log_path TEXT"))


def _seed_account_types() -> None:
    """Ensure all canonical account types exist with correct balance_type."""
    from .models.accounts import FinancialAccountType

    with Session(engine) as session:
        for name, balance_type in ACCOUNT_TYPES.items():
            existing = session.query(FinancialAccountType).filter_by(name=name).first()
            if existing:
                if existing.balance_type != balance_type:
                    existing.balance_type = balance_type
            else:
                session.add(FinancialAccountType(name=name, balance_type=balance_type))
        session.commit()


def _seed_builtin_workflows() -> None:
    """Ensure builtin workflow definitions exist in the database."""
    from .tools.workflows import sync_builtin_workflows_to_db

    sync_builtin_workflows_to_db()
