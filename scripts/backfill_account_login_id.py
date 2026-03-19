"""
Backfill scraper_login_id on FinancialAccount records.

Many accounts were scraped before we tracked the login-to-account link.
This script:
1. Adds scraper_login_id column if it doesn't exist (ALTER TABLE)
2. Fills in FinancialAccount.scraper_login_id from:
   a. FinancialAccountLogin link table (most recent successful scrape per account)
   b. Falls back to any ScraperLogin for the same provider if no link exists
"""

import sqlite3
from pathlib import Path

from shiso.scraper.database import SessionLocal
from shiso.scraper.models.accounts import FinancialAccount, FinancialAccountLogin, ScraperLogin

DB_PATH = Path("data/shiso.db")


def add_column_if_missing():
    """Add scraper_login_id column to financial_accounts if it doesn't exist."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("PRAGMA table_info(financial_accounts)")
        columns = [row[1] for row in cursor.fetchall()]
        if "scraper_login_id" not in columns:
            print("Adding scraper_login_id column to financial_accounts...")
            conn.execute("ALTER TABLE financial_accounts ADD COLUMN scraper_login_id INTEGER REFERENCES scraper_logins(id) ON DELETE SET NULL")
            conn.commit()
            print("Column added.")
        else:
            print("Column already exists.")


def backfill_scraper_login_id():
    add_column_if_missing()

    with SessionLocal() as session:
        accounts = session.query(FinancialAccount).filter(FinancialAccount.scraper_login_id.is_(None)).all()
        print(f"Found {len(accounts)} accounts without scraper_login_id")

        updated = 0
        for account in accounts:
            # Try FinancialAccountLogin link first
            link = (
                session.query(FinancialAccountLogin)
                .filter(FinancialAccountLogin.financial_account_id == account.id)
                .order_by(FinancialAccountLogin.last_success_at.desc())
                .first()
            )
            if link:
                account.scraper_login_id = link.scraper_login_id
                updated += 1
                print(f"  [{account.id}] {account.display_name or account.account_mask}: linked via FinancialAccountLogin -> login {link.scraper_login_id}")
                continue

            # Fall back to any enabled login for this provider
            login = (
                session.query(ScraperLogin)
                .filter(ScraperLogin.provider_key == account.provider_key, ScraperLogin.enabled.is_(True))
                .order_by(ScraperLogin.sort_order)
                .first()
            )
            if login:
                account.scraper_login_id = login.id
                updated += 1
                print(f"  [{account.id}] {account.display_name or account.account_mask}: linked via provider fallback -> login {login.id}")
                continue

            print(f"  [{account.id}] {account.display_name or account.account_mask}: NO LOGIN FOUND (provider={account.provider_key})")

        session.commit()
        print(f"\nUpdated {updated} accounts")


if __name__ == "__main__":
    backfill_scraper_login_id()
