"""
Run all scrapers and print results.

Usage:
    just scrape                  # run all
    just scrape amex             # run one
    just scrape nipsco amex      # run multiple

Notes:
    --analyst-llm sets ANALYST_LLM (utility LLM for analyst/PDF parsing).
    --agent-llm optionally overrides AGENT_LLM (browser agent, defaults to browser_use).
"""

import asyncio
import json
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Callable

from ..database import SessionLocal, init_db
from ..models.accounts import ScraperLogin
from ..services.accounts_db import AccountsDB
from ..services.crypto import decrypt
from ..services.sync import run_sync

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "accounts.json"


def _seed_from_json():
    """Import accounts.json into DB if scraper_logins table is empty."""
    if not CONFIG_PATH.exists():
        return
    with SessionLocal() as session:
        if session.query(ScraperLogin).count() > 0:
            return
        data = json.loads(CONFIG_PATH.read_text())
        type_map = {
            "nipsco": "Utility",
            "american_water": "Utility",
            "amex": "Credit Card",
        }
        order = 0
        for provider_key, entries in data.items():
            for entry in entries:
                login = ScraperLogin(
                    provider_key=provider_key,
                    label=entry.get("label", provider_key),
                    account_type=type_map.get(provider_key, "Other"),
                    sort_order=order,
                )
                session.add(login)
                order += 1
        session.commit()
        print(f"[seed] Imported {order} login(s) from accounts.json")


def load_accounts(login_ids: list[int] | None = None) -> dict:
    """Load scraper logins from DB, grouped by provider_key."""
    init_db()
    _seed_from_json()
    with SessionLocal() as session:
        query = session.query(ScraperLogin).order_by(ScraperLogin.sort_order)
        if login_ids:
            query = query.filter(ScraperLogin.id.in_(login_ids))
        else:
            query = query.filter(ScraperLogin.enabled.is_(True))
        logins = query.all()
        grouped = defaultdict(list)
        for login in logins:
            entry = {
                "id": login.id,
                "label": login.label,
                "login_url": login.login_url,
                "username": login.username,
                "account_type": login.account_type,
            }
            if login.password_encrypted:
                entry["password"] = decrypt(login.password_encrypted)
            grouped[login.provider_key].append(entry)
        return dict(grouped)


async def run_scrapers(
    targets: list[str] | None = None,
    login_ids: list[int] | None = None,
    download_statements: bool = False,
    interactive: bool = True,
    on_log: Callable[[str], None] | None = None,
) -> dict:
    accounts = load_accounts(login_ids=login_ids)
    if targets:
        to_run = [key for key in targets if key in accounts]
    else:
        # Run all enabled logins from the DB
        to_run = list(accounts.keys())

    if not to_run:
        if login_ids:
            raise ValueError(f"No enabled scraper logins matched ids: {login_ids}")
        raise ValueError(f"Unknown targets: {targets}. Available: {sorted(accounts.keys())}")

    accounts_db = AccountsDB()

    all_results = {}
    persisted_results = {}

    for name in to_run:
        print(f"\n=== {name.upper()} ===")
        try:
            provider_accounts = accounts.get(name, [{}])
            sync = await run_sync(
                name,
                provider_accounts,
                accounts_db=accounts_db,
                download_statements=download_statements,
                interactive=interactive,
                on_log=on_log,
            )

            all_results[name] = sync.results
            persisted_results[name] = sync.persisted

            if sync.error:
                print(f"[{name}] FAILED: {sync.error}")
            else:
                print(f"[{name}] Persisted {len(sync.persisted)} snapshot(s)")

        except Exception as e:
            import traceback
            print(f"[{name}] ERROR: {e}")
            traceback.print_exc()
            all_results[name] = []
            persisted_results[name] = []

    return {
        "results": all_results,
        "persisted": {
            name: [item.__dict__ for item in rows] if rows else []
            for name, rows in persisted_results.items()
        },
        "summary": accounts_db.get_summary(),
    }


async def main(
    targets: list[str] | None = None,
    download_statements: bool = False,
    interactive: bool = True,
):
    payload = await run_scrapers(
        targets,
        download_statements=download_statements,
        interactive=interactive,
    )

    print("\n=== RESULTS ===")
    print(json.dumps(payload["results"], indent=2))
    print("\n=== SUMMARY ===")
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run browser-use scrapers")
    parser.add_argument("targets", nargs="*", help="Provider keys to scrape (default: all)")
    parser.add_argument("--analyst-llm", default=None, help="LLM preset for analyst/utility tasks (e.g. openrouter, local)")
    parser.add_argument(
        "--agent-llm",
        default=None,
        help="LLM preset for browser agent (defaults to browser_use)",
    )
    parser.add_argument("--statements", action="store_true", help="Download latest statement PDFs")
    parser.add_argument("--auto", action="store_true", help="Auto mode: skip 2FA prompts instead of waiting")
    args = parser.parse_args()

    if args.analyst_llm:
        os.environ["ANALYST_LLM"] = args.analyst_llm
    if args.agent_llm:
        os.environ["AGENT_LLM"] = args.agent_llm

    asyncio.run(main(
        args.targets or None,
        download_statements=args.statements,
        interactive=not args.auto,
    ))
