"""
Account and snapshot models for scraped financial data.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, MappedColumn, mapped_column, relationship

from ..database import Base


class FinancialAccountType(Base):
    __tablename__ = "financial_account_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    balance_type: Mapped[str] = mapped_column(Text, nullable=False, default="liability")  # asset | liability

    accounts: Mapped[list["FinancialAccount"]] = relationship(back_populates="account_type")


class FinancialAccount(Base):
    __tablename__ = "financial_accounts"
    __table_args__ = (
        UniqueConstraint("provider_key", "account_number", name="uq_financial_account_provider_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_type_id: Mapped[int] = mapped_column(ForeignKey("financial_account_types.id"), nullable=False)
    provider_key: Mapped[str] = mapped_column(Text, nullable=False)
    institution: Mapped[str] = mapped_column(Text, nullable=False)
    scraper_login_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scraper_logins.id", ondelete="SET NULL"))
    display_name: Mapped[Optional[str]] = mapped_column(Text)
    account_number: Mapped[Optional[str]] = mapped_column(Text)
    account_mask: Mapped[Optional[str]] = mapped_column(Text)
    address: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[Optional[str]] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_snapshot_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    scraper_login: Mapped[Optional["ScraperLogin"]] = relationship(back_populates="accounts")

    account_type: Mapped["FinancialAccountType"] = relationship(back_populates="accounts")
    snapshots: Mapped[list["AccountSnapshot"]] = relationship(back_populates="financial_account")
    statements: Mapped[list["AccountStatement"]] = relationship(back_populates="financial_account")
    promo_periods: Mapped[list["PromoAprPeriod"]] = relationship(back_populates="financial_account")
    rewards_programs: Mapped[list["RewardsProgram"]] = relationship(back_populates="financial_account")
    identifiers: Mapped[list["FinancialAccountIdentifier"]] = relationship(back_populates="financial_account")
    login_links: Mapped[list["FinancialAccountLogin"]] = relationship(back_populates="financial_account")


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    financial_account_id: Mapped[int] = mapped_column(ForeignKey("financial_accounts.id"), nullable=False)
    scraper_login_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scraper_logins.id", ondelete="SET NULL"))
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    current_balance: Mapped[Optional[float]] = mapped_column(Float)
    statement_balance: Mapped[Optional[float]] = mapped_column(Float)
    minimum_payment: Mapped[Optional[float]] = mapped_column(Float)
    due_date: Mapped[Optional[str]] = mapped_column(Text)
    last_payment_amount: Mapped[Optional[float]] = mapped_column(Float)
    last_payment_date: Mapped[Optional[str]] = mapped_column(Text)
    credit_limit: Mapped[Optional[float]] = mapped_column(Float)
    intro_apr_rate: Mapped[Optional[float]] = mapped_column(Float)
    intro_apr_end_date: Mapped[Optional[str]] = mapped_column(Text)
    regular_apr: Mapped[Optional[float]] = mapped_column(Float)
    raw_extracted_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    financial_account: Mapped["FinancialAccount"] = relationship(back_populates="snapshots")
    scraper_login: Mapped[Optional["ScraperLogin"]] = relationship(back_populates="snapshots")
    rewards_balances: Mapped[list["RewardsBalance"]] = relationship(back_populates="source_snapshot")


class FinancialAccountIdentifier(Base):
    __tablename__ = "financial_account_identifiers"
    __table_args__ = (
        UniqueConstraint("provider_key", "identifier_type", "identifier_value", name="uq_account_identifier_value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    financial_account_id: Mapped[int] = mapped_column(ForeignKey("financial_accounts.id"), nullable=False)
    provider_key: Mapped[str] = mapped_column(String, nullable=False)
    identifier_type: Mapped[str] = mapped_column(String, nullable=False)
    identifier_value: Mapped[str] = mapped_column(String, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    financial_account: Mapped["FinancialAccount"] = relationship(back_populates="identifiers")


class FinancialAccountLogin(Base):
    __tablename__ = "financial_account_logins"
    __table_args__ = (
        UniqueConstraint("financial_account_id", "scraper_login_id", name="uq_financial_account_login"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    financial_account_id: Mapped[int] = mapped_column(ForeignKey("financial_accounts.id"), nullable=False)
    scraper_login_id: Mapped[int] = mapped_column(ForeignKey("scraper_logins.id", ondelete="CASCADE"), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_success_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    financial_account: Mapped["FinancialAccount"] = relationship(back_populates="login_links")
    scraper_login: Mapped["ScraperLogin"] = relationship(back_populates="account_links", passive_deletes=True)


class ScraperLogin(Base):
    __tablename__ = "scraper_logins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_key: Mapped[str] = mapped_column(String, nullable=False)
    tool_key: Mapped[str] = mapped_column(String, nullable=False, default="financial_scraper")
    institution: Mapped[Optional[str]] = mapped_column(String)  # e.g. "Bank of America", "Chase"
    label: Mapped[str] = mapped_column(String, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String)
    password_encrypted: Mapped[Optional[str]] = mapped_column(String)
    login_url: Mapped[Optional[str]] = mapped_column(String)
    account_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    last_sync_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_sync_finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_sync_status: Mapped[Optional[str]] = mapped_column(String)
    last_sync_error: Mapped[Optional[str]] = mapped_column(Text)
    last_sync_account_count: Mapped[Optional[int]] = mapped_column(Integer)
    last_sync_snapshot_count: Mapped[Optional[int]] = mapped_column(Integer)
    last_auth_status: Mapped[Optional[str]] = mapped_column(String)  # authenticated | needs_2fa | login_failed
    last_auth_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    snapshots: Mapped[list["AccountSnapshot"]] = relationship(back_populates="scraper_login")
    account_links: Mapped[list["FinancialAccountLogin"]] = relationship(back_populates="scraper_login")
    accounts: Mapped[list["FinancialAccount"]] = relationship(back_populates="scraper_login")
    sync_runs: Mapped[list["ScraperLoginSyncRun"]] = relationship(back_populates="scraper_login")


class ScraperLoginSyncRun(Base):
    __tablename__ = "scraper_login_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scraper_login_id: Mapped[int] = mapped_column(ForeignKey("scraper_logins.id", ondelete="CASCADE"), nullable=False)
    provider_key: Mapped[str] = mapped_column(String, nullable=False)
    account_filter: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    accounts_found: Mapped[Optional[int]] = mapped_column(Integer)
    snapshots_saved: Mapped[Optional[int]] = mapped_column(Integer)
    agent_log_path: Mapped[Optional[str]] = mapped_column(Text)
    error: Mapped[Optional[str]] = mapped_column(Text)
    metrics: Mapped[Optional[dict]] = mapped_column(JSON)

    scraper_login: Mapped["ScraperLogin"] = relationship(back_populates="sync_runs", passive_deletes=True)


class ProviderMapping(Base):
    """Domain pattern → provider mapping for password import AI matching."""

    __tablename__ = "provider_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain_pattern: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    provider_key: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    account_type: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="baseline")
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class AccountStatement(Base):
    __tablename__ = "account_statements"
    __table_args__ = (
        UniqueConstraint("financial_account_id", "statement_month", name="uq_account_statement_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    financial_account_id: Mapped[int] = mapped_column(ForeignKey("financial_accounts.id"), nullable=False)
    scraper_login_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scraper_logins.id", ondelete="SET NULL"))
    statement_month: Mapped[str] = mapped_column(String, nullable=False)  # YYYY-MM
    statement_date: Mapped[Optional[str]] = mapped_column(String)
    file_path: Mapped[Optional[str]] = mapped_column(Text)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    downloaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    intro_apr_rate: Mapped[Optional[float]] = mapped_column(Float)
    intro_apr_end_date: Mapped[Optional[str]] = mapped_column(String)
    regular_apr: Mapped[Optional[float]] = mapped_column(Float)
    credit_limit: Mapped[Optional[float]] = mapped_column(Float)
    raw_extracted_json: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    financial_account: Mapped["FinancialAccount"] = relationship(back_populates="statements")


class PromoAprPeriod(Base):
    __tablename__ = "promo_apr_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    financial_account_id: Mapped[int] = mapped_column(ForeignKey("financial_accounts.id"), nullable=False)
    promo_type: Mapped[str] = mapped_column(String, nullable=False, default="purchase")  # purchase | balance_transfer | general
    apr_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    regular_apr: Mapped[Optional[float]] = mapped_column(Float)
    start_date: Mapped[Optional[str]] = mapped_column(String)  # YYYY-MM-DD
    end_date: Mapped[str] = mapped_column(String, nullable=False)  # YYYY-MM-DD
    original_amount: Mapped[Optional[float]] = mapped_column(Float)
    description: Mapped[Optional[str]] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    financial_account: Mapped["FinancialAccount"] = relationship(back_populates="promo_periods")


class RewardsProgram(Base):
    """A rewards program associated with a financial account (points, miles, cashback)."""
    __tablename__ = "rewards_programs"
    __table_args__ = (
        UniqueConstraint("financial_account_id", "program_name", name="uq_rewards_program_account_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    financial_account_id: Mapped[int] = mapped_column(ForeignKey("financial_accounts.id"), nullable=False)
    program_name: Mapped[str] = mapped_column(String, nullable=False)  # e.g., "Chase Ultimate Rewards", "Delta SkyMiles"
    program_type: Mapped[str] = mapped_column(String, nullable=False, default="points")  # points | miles | cashback | other
    unit_name: Mapped[Optional[str]] = mapped_column(String)  # e.g., "points", "miles", "%"
    cents_per_unit: Mapped[Optional[float]] = mapped_column(Float)  # Valuation: e.g., 1.5 cents per point
    display_icon_url: Mapped[Optional[str]] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    financial_account: Mapped["FinancialAccount"] = relationship(back_populates="rewards_programs")
    balances: Mapped[list["RewardsBalance"]] = relationship(back_populates="rewards_program", cascade="all, delete-orphan")


class RewardsBalance(Base):
    """A snapshot of rewards balance at a point in time."""
    __tablename__ = "rewards_balances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rewards_program_id: Mapped[int] = mapped_column(ForeignKey("rewards_programs.id", ondelete="CASCADE"), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    balance: Mapped[float] = mapped_column(Float, nullable=False)  # Raw balance in program units
    monetary_value: Mapped[Optional[float]] = mapped_column(Float)  # Calculated USD value
    expiration_date: Mapped[Optional[str]] = mapped_column(String)  # YYYY-MM-DD
    source_snapshot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("account_snapshots.id", ondelete="SET NULL"))
    raw_extracted_json: Mapped[Optional[dict]] = mapped_column(JSON)

    rewards_program: Mapped["RewardsProgram"] = relationship(back_populates="balances")
    source_snapshot: Mapped[Optional["AccountSnapshot"]] = relationship(back_populates="rewards_balances")


class ImportSession(Base):
    """An import batch — a CSV file upload with multiple candidates being reviewed."""
    __tablename__ = "import_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")  # pending | processing | done | cancelled
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    high_confidence_count: Mapped[int] = mapped_column(Integer, default=0)
    needs_review_count: Mapped[int] = mapped_column(Integer, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    candidates: Mapped[list["ImportCandidate"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class ImportCandidate(Base):
    """A single row from an imported CSV, pending review."""
    __tablename__ = "import_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("import_sessions.id", ondelete="CASCADE"), nullable=False)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)  # Original CSV row number
    name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    password: Mapped[Optional[str]] = mapped_column(Text)  # kept encrypted at rest
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")  # pending | matched | accepted | rejected | skipped
    match_confidence: Mapped[Optional[float]] = mapped_column(Float)  # 0.0-1.0
    match_type: Mapped[Optional[str]] = mapped_column(Text)  # exact | subdomain | fuzzy | keyword | llm
    provider_key: Mapped[Optional[str]] = mapped_column(Text)
    label: Mapped[Optional[str]] = mapped_column(Text)
    account_type: Mapped[Optional[str]] = mapped_column(Text)
    is_new_provider: Mapped[bool] = mapped_column(Boolean, default=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)  # duplicate of existing scraper_login
    existing_login_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scraper_logins.id", ondelete="SET NULL"))
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    session: Mapped["ImportSession"] = relationship(back_populates="candidates")
    existing_login: Mapped[Optional["ScraperLogin"]] = relationship()
