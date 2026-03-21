"""
Sync type definitions — DB lookup table + Python convenience enum.

The ``sync_types`` table is the source of truth.  The :class:`SyncType`
StrEnum is a thin validation/convenience layer for type-safe Python code.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Optional

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


# ---------------------------------------------------------------------------
# DB model — source of truth
# ---------------------------------------------------------------------------

class SyncTypeRecord(Base):
    __tablename__ = "sync_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<SyncTypeRecord key={self.key!r}>"


# ---------------------------------------------------------------------------
# Python convenience enum
# ---------------------------------------------------------------------------

class SyncType(StrEnum):
    """Sync mode selector.  ``auto`` is resolved before scraping starts."""
    auto = "auto"              # sentinel — resolved at runtime, never stored
    full = "full"              # discovery + enrichment + statements + analyst
    balance = "balance"        # balance-only for known accounts
    statements = "statements"  # statement downloads only, no discovery


# Seed data: key -> (display name, description)
BUILTIN_SYNC_TYPES: dict[str, tuple[str, str]] = {
    SyncType.full: (
        "Full Sync",
        "Discovery + enrichment + statements + analyst",
    ),
    SyncType.balance: (
        "Balance Update",
        "Balance-only scrape for known accounts",
    ),
    SyncType.statements: (
        "Statements Only",
        "Download statements for known accounts",
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_sync_type_id(key: str) -> int | None:
    """Look up the ``sync_types.id`` for a given key.  Returns None if not found."""
    from ..database import SessionLocal

    with SessionLocal() as session:
        record = session.query(SyncTypeRecord).filter_by(key=key).first()
        return record.id if record else None


def resolve_sync_type(
    login_id: int,
    requested: SyncType = SyncType.auto,
) -> SyncType:
    """Determine the effective sync type for a login.

    Resolution order:
    1. If *requested* is not ``auto``, use it directly.
    2. If the login has ``needs_full_sync`` set, return ``full``.
    3. If no accounts exist for the login, return ``full``.
    4. Otherwise return ``balance``.
    """
    if requested != SyncType.auto:
        return requested

    from ..database import SessionLocal
    from .accounts import FinancialAccount, ScraperLogin

    with SessionLocal() as session:
        login = session.get(ScraperLogin, login_id)
        if not login:
            return SyncType.full

        if getattr(login, "needs_full_sync", False):
            return SyncType.full

        count = (
            session.query(FinancialAccount)
            .filter(FinancialAccount.scraper_login_id == login_id)
            .count()
        )
        return SyncType.full if count == 0 else SyncType.balance
