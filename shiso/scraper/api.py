"""
Public API for the scraper package.

The dashboard (and any other consumer) should import from here
instead of reaching into scraper internals.
"""

from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib

from .database import SessionLocal, init_db
from .models.accounts import (
    FinancialAccount,
    PromoAprPeriod,
    ScraperLogin,
    ScraperLoginSyncRun,
)
from .services.accounts_db import AccountsDB
from .services.crypto import encrypt
from .services.password_import import parse_csv
from .services.sync import run_sync, create_sync_run
from .agent.run import load_accounts, run_scrapers

# Provider keys come from the TOML config (scraper routing only).
_CONFIG_PATH = Path(__file__).parent / "config" / "scraper.toml"

def _load_provider_keys() -> set[str]:
    try:
        with open(_CONFIG_PATH, "rb") as f:
            config = tomllib.load(f)
        return set(config.get("providers", {}).keys())
    except FileNotFoundError:
        return set()

PROVIDER_KEYS = _load_provider_keys()

__all__ = [
    # DB access
    "SessionLocal",
    "init_db",
    # Models
    "FinancialAccount",
    "PromoAprPeriod",
    "ScraperLogin",
    "ScraperLoginSyncRun",
    # Services
    "AccountsDB",
    "PROVIDER_KEYS",
    "encrypt",
    "parse_csv",
    "load_accounts",
    # Scraper operations
    "run_sync",
    "create_sync_run",
    "run_scrapers",
]
