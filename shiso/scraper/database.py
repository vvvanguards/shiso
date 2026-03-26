"""
Shared database configuration for Shiso.
"""

from functools import lru_cache
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


# Canonical account types mapping to balance_type_id (1=asset, 2=liability).
ACCOUNT_TYPE_IDS = {
    "Credit Card":      2,
    "Loan":             2,
    "Mortgage":         2,
    "Line of Credit":   2,
    "Utility":          2,
    "Insurance":        2,
    "Checking":         1,
    "Savings":          1,
    "Investment":       1,
    "Property":         1,
    "Other":            2,
    "Unknown":          2,
}


@lru_cache(maxsize=1)
def _build_balance_type_cache() -> dict[str, int]:
    """Build account_type_name -> balance_type_id map from DB. Cached permanently."""
    from .models.accounts import FinancialAccountType

    with Session(engine) as session:
        rows = session.query(FinancialAccountType.name, FinancialAccountType.balance_type_id).all()
    return {name: balance_type_id for name, balance_type_id in rows}


def get_balance_type_id(account_type_name: str) -> int:
    """Look up balance_type_id for an account type name from the DB.

    Returns 2 (liability) as default if the account type is not found.
    Uses an LRU-cached DB query — only hits the DB once per process.
    """
    return _build_balance_type_cache().get(account_type_name, 2)


@lru_cache(maxsize=1)
def _build_balance_type_name_cache() -> dict[int, str]:
    """Build balance_type_id -> balance_type_name map from DB. Cached permanently."""
    from .models.accounts import BalanceType

    with Session(engine) as session:
        rows = session.query(BalanceType.id, BalanceType.name).all()
    return {id_: name for id_, name in rows}


def get_balance_type_name(balance_type_id: int) -> str:
    """Look up balance type name from its ID. Returns 'liability' as default."""
    return _build_balance_type_name_cache().get(balance_type_id, "liability")


def _import_models() -> None:
    """Ensure all models are imported so metadata is populated."""
    from .models.accounts import (  # noqa: F401
        AccountSnapshot,
        AccountStatement,
        FinancialAccount,
        FinancialAccountIdentifier,
        FinancialAccountLogin,
        FinancialAccountType,
        ImportCandidate,
        ImportSession,
        PromoAprPeriod,
        ProviderMapping,
        ScraperLogin,
        ScraperLoginSyncRun,
    )
    from .models.sync_type import SyncTypeRecord  # noqa: F401
    from .models.tools import (  # noqa: F401
        ProviderPlaybookRecord,
        ToolRunOutput,
        WorkflowDefinitionRecord,
        WorkflowRevisionSuggestionRecord,
    )


BASELINE_PROVIDER_MAPPINGS = [
    {"domain_pattern": "chase.com", "provider_key": "chase", "label": "Chase", "account_type": "Credit Card"},
    {"domain_pattern": "americanexpress.com", "provider_key": "amex", "label": "Amex", "account_type": "Credit Card"},
    {"domain_pattern": "citi.com", "provider_key": "citi", "label": "Citi", "account_type": "Credit Card"},
    {"domain_pattern": "citicards.com", "provider_key": "citi", "label": "Citi", "account_type": "Credit Card"},
    {"domain_pattern": "capitalone.com", "provider_key": "capital_one", "label": "Capital One", "account_type": "Credit Card"},
    {"domain_pattern": "discover.com", "provider_key": "discover", "label": "Discover", "account_type": "Credit Card"},
    {"domain_pattern": "barclays.com", "provider_key": "barclays", "label": "Barclays", "account_type": "Credit Card"},
    {"domain_pattern": "bfrb.bankofamerica.com", "provider_key": "bofa", "label": "Bank of America", "account_type": "Credit Card"},
    {"domain_pattern": "nipsco.com", "provider_key": "nipsco", "label": "NIPSCO", "account_type": "Utility"},
    {"domain_pattern": "amwater.com", "provider_key": "american_water", "label": "American Water", "account_type": "Utility"},
    {"domain_pattern": "indianaamericanwater.com", "provider_key": "american_water", "label": "American Water", "account_type": "Utility"},
    {"domain_pattern": "duke-energy.com", "provider_key": "duke_energy", "label": "Duke Energy", "account_type": "Utility"},
    {"domain_pattern": "xfinity.com", "provider_key": "xfinity", "label": "Xfinity", "account_type": "Utility"},
    {"domain_pattern": "comcast.com", "provider_key": "xfinity", "label": "Xfinity", "account_type": "Utility"},
    {"domain_pattern": "att.com", "provider_key": "att", "label": "AT&T", "account_type": "Utility"},
    {"domain_pattern": "verizon.com", "provider_key": "verizon", "label": "Verizon", "account_type": "Utility"},
    {"domain_pattern": "t-mobile.com", "provider_key": "tmobile", "label": "T-Mobile", "account_type": "Utility"},
    {"domain_pattern": "spectrum.com", "provider_key": "spectrum", "label": "Spectrum", "account_type": "Utility"},
    {"domain_pattern": "geico.com", "provider_key": "geico", "label": "GEICO", "account_type": "Other"},
    {"domain_pattern": "progressive.com", "provider_key": "progressive", "label": "Progressive", "account_type": "Other"},
    {"domain_pattern": "statefarm.com", "provider_key": "state_farm", "label": "State Farm", "account_type": "Other"},
    {"domain_pattern": "ally.com", "provider_key": "ally", "label": "Ally", "account_type": "Bank"},
    {"domain_pattern": "sofi.com", "provider_key": "sofi", "label": "SoFi", "account_type": "Bank"},
    {"domain_pattern": "marcus.com", "provider_key": "marcus", "label": "Marcus", "account_type": "Bank"},
    {"domain_pattern": "truist.com", "provider_key": "truist", "label": "Truist", "account_type": "Bank"},
    {"domain_pattern": "tiaabank.com", "provider_key": "tiaa", "label": "TIAA Bank", "account_type": "Bank"},
    {"domain_pattern": "citbank.com", "provider_key": "cit_bank", "label": "CIT Bank", "account_type": "Bank"},
    {"domain_pattern": "fidelity.com", "provider_key": "fidelity", "label": "Fidelity", "account_type": "Bank"},
    {"domain_pattern": "fidelityrewards.com", "provider_key": "fidelity", "label": "Fidelity", "account_type": "Credit Card"},
    {"domain_pattern": "schwab.com", "provider_key": "schwab", "label": "Schwab", "account_type": "Bank"},
    {"domain_pattern": "vanguard.com", "provider_key": "vanguard", "label": "Vanguard", "account_type": "Bank"},
    {"domain_pattern": "robinhood.com", "provider_key": "robinhood", "label": "Robinhood", "account_type": "Bank"},
    {"domain_pattern": "webull.com", "provider_key": "webull", "label": "Webull", "account_type": "Bank"},
    {"domain_pattern": "etrade.com", "provider_key": "etrade", "label": "E*TRADE", "account_type": "Bank"},
    {"domain_pattern": "coinbase.com", "provider_key": "coinbase", "label": "Coinbase", "account_type": "Bank"},
    {"domain_pattern": "venmo.com", "provider_key": "venmo", "label": "Venmo", "account_type": "Bank"},
    {"domain_pattern": "paypal.com", "provider_key": "paypal", "label": "PayPal", "account_type": "Bank"},
    {"domain_pattern": "navyfederal.org", "provider_key": "navy_federal", "label": "Navy Federal", "account_type": "Bank"},
    {"domain_pattern": "pnc.com", "provider_key": "pnc", "label": "PNC", "account_type": "Bank"},
    {"domain_pattern": "huntington.com", "provider_key": "huntington", "label": "Huntington", "account_type": "Bank"},
    {"domain_pattern": "regions.com", "provider_key": "regions", "label": "Regions", "account_type": "Bank"},
    {"domain_pattern": "wellsfargo.com", "provider_key": "wells_fargo", "label": "Wells Fargo", "account_type": "Bank"},
    {"domain_pattern": "bankofamerica.com", "provider_key": "bofa", "label": "Bank of America", "account_type": "Bank"},
    {"domain_pattern": "usaa.com", "provider_key": "usaa", "label": "USAA", "account_type": "Bank"},
    {"domain_pattern": "citizensbankonline.com", "provider_key": "citizens", "label": "Citizens", "account_type": "Bank"},
    {"domain_pattern": "loancare.com", "provider_key": "loancare", "label": "LoanCare", "account_type": "Loan"},
    {"domain_pattern": "myroundpoint.com", "provider_key": "roundpoint", "label": "RoundPoint", "account_type": "Loan"},
    {"domain_pattern": "nelnet.com", "provider_key": "nelnet", "label": "Nelnet", "account_type": "Loan"},
    {"domain_pattern": "navient.com", "provider_key": "navient", "label": "Navient", "account_type": "Loan"},
    {"domain_pattern": "mohela.com", "provider_key": "mohela", "label": "MOHELA", "account_type": "Loan"},
    {"domain_pattern": "salliemae.com", "provider_key": "sallie_mae", "label": "Sallie Mae", "account_type": "Loan"},
]


def init_db() -> None:
    """Run alembic migrations to bring schema up to date, then seed reference data."""
    from .models.accounts import ProviderMapping

    _import_models()
    run_alembic_migrations()
    _seed_account_types()
    _seed_sync_types()
    _seed_builtin_workflows()

    with SessionLocal() as session:
        for p in BASELINE_PROVIDER_MAPPINGS:
            existing = session.query(ProviderMapping).filter(
                ProviderMapping.domain_pattern == p["domain_pattern"]
            ).first()
            if not existing:
                session.add(ProviderMapping(**p, source="baseline"))
        session.commit()


def reset_db() -> None:
    """Drop and recreate all tables. Destroys all data."""
    _import_models()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    _seed_account_types()
    _seed_sync_types()
    _seed_builtin_workflows()


def _add_missing_columns_to_existing_schema() -> None:
    """Add new columns to an existing pre-alembic database.

    Handles the case where the database has the old schema (before alembic
    migrations were introduced) and needs new columns added without
    recreating tables. Returns silently if columns already exist.
    """
    from sqlalchemy import text

    # Columns added by each migration that we need on the pre-alembic DB.
    # Format: (table_name, column_name, column_definition)
    new_columns = [
        # Migration 002: is_deleted on scraper_logins
        ("scraper_logins", "is_deleted", "BOOLEAN NOT NULL DEFAULT 0"),
        # Migration 004: auto_sync_enabled on scraper_logins
        ("scraper_logins", "auto_sync_enabled", "BOOLEAN NOT NULL DEFAULT 1"),
        # Migration 001: is_paid and related on account_snapshots
        ("account_snapshots", "is_paid", "BOOLEAN"),
        ("account_snapshots", "paid_date", "TEXT"),
        ("account_snapshots", "autopay_enabled", "BOOLEAN"),
        ("account_snapshots", "is_paid_override", "BOOLEAN"),
        ("account_snapshots", "is_paid_override_at", "TIMESTAMP"),
        # Migration 003: workflow_definitions orchestration fields
        ("workflow_definitions", "persistence_strategy", "TEXT"),
        ("workflow_definitions", "enrichment_enabled", "BOOLEAN"),
        ("workflow_definitions", "statement_download_enabled", "BOOLEAN"),
        ("workflow_definitions", "assessment_enabled", "BOOLEAN"),
        ("workflow_definitions", "dedup_enabled", "BOOLEAN"),
    ]

    with SessionLocal() as session:
        for table, column, definition in new_columns:
            try:
                # Check if column already exists
                session.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
                # Table exists — check if column is missing
                try:
                    session.execute(text(f"SELECT {column} FROM {table} LIMIT 1"))
                except Exception:
                    # Column missing — add it
                    session.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                    )
                    session.commit()
            except Exception:
                # Table doesn't exist at all — skip
                pass


def run_alembic_migrations() -> None:
    """Run alembic migrations to bring schema up to date."""
    from alembic.config import Config
    from alembic import command

    alembic_cfg_path = PROJECT_ROOT / "alembic.ini"
    if not alembic_cfg_path.exists():
        Base.metadata.create_all(bind=engine)
        return

    from sqlalchemy import text

    with SessionLocal() as session:
        try:
            session.execute(text("SELECT 1 FROM alembic_version"))
            is_alembic_managed = True
        except Exception:
            is_alembic_managed = False

    if not is_alembic_managed:
        # Database predates alembic. Check if it has existing tables
        # (i.e., a real existing DB, not a fresh one that needs create_all).
        with SessionLocal() as session:
            try:
                session.execute(text("SELECT 1 FROM scraper_logins LIMIT 1"))
                has_real_schema = True
            except Exception:
                has_real_schema = False

        if has_real_schema:
            # Pre-alembic DB with existing tables: add new columns directly,
            # then stamp so alembic knows we're at head for future migrations.
            _add_missing_columns_to_existing_schema()
            alembic_cfg = Config(str(alembic_cfg_path))
            command.stamp(alembic_cfg, "head")
            return

    # Normal case: fresh DB or already alembic-managed — run upgrades normally.
    alembic_cfg = Config(str(alembic_cfg_path))
    command.upgrade(alembic_cfg, "head")


def _seed_account_types() -> None:
    """Ensure all canonical account types exist with correct balance_type_id."""
    from .models.accounts import FinancialAccountType

    with Session(engine) as session:
        for name, balance_type_id in ACCOUNT_TYPE_IDS.items():
            existing = session.query(FinancialAccountType).filter_by(name=name).first()
            if existing:
                if existing.balance_type_id != balance_type_id:
                    existing.balance_type_id = balance_type_id
            else:
                session.add(FinancialAccountType(name=name, balance_type_id=balance_type_id))
        session.commit()


def _seed_sync_types() -> None:
    """Ensure all builtin sync types exist in the database."""
    from .models.sync_type import BUILTIN_SYNC_TYPES, SyncTypeRecord

    with Session(engine) as session:
        for idx, (key, (name, description)) in enumerate(BUILTIN_SYNC_TYPES.items()):
            existing = session.query(SyncTypeRecord).filter_by(key=key).first()
            if existing:
                existing.name = name
                existing.description = description
            else:
                session.add(SyncTypeRecord(
                    key=key, name=name, description=description, sort_order=idx,
                ))
        session.commit()


def _seed_builtin_workflows() -> None:
    """Ensure builtin workflow definitions exist in the database."""
    from .tools.workflows import sync_builtin_workflows_to_db

    sync_builtin_workflows_to_db()
