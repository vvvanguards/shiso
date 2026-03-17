"""
Auth status and interactive login session establishment.

Usage:
    python -m shiso.scraper.agent.auth status          # show auth status for all logins
    python -m shiso.scraper.agent.auth login            # interactive login for needs_2fa logins
    python -m shiso.scraper.agent.auth login chase amex # specific providers only
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from ..database import SessionLocal, init_db
from ..models.accounts import ScraperLogin

logger = logging.getLogger(__name__)

# Status after Agent login attempt
_STATUS_AUTHENTICATED = "authenticated"
_STATUS_NEEDS_2FA = "needs_2fa"
_STATUS_SKIPPED = "skipped"


def auth_status() -> list[dict[str, Any]]:
    """Return auth status for all enabled logins."""
    init_db()
    with SessionLocal() as session:
        logins = (
            session.query(ScraperLogin)
            .filter(ScraperLogin.enabled.is_(True))
            .order_by(ScraperLogin.provider_key, ScraperLogin.id)
            .all()
        )
        rows = []
        for login in logins:
            rows.append({
                "id": login.id,
                "provider_key": login.provider_key,
                "label": login.label,
                "username": login.username,
                "auth_status": login.last_auth_status or "unknown",
                "auth_at": login.last_auth_at.isoformat() if login.last_auth_at else None,
                "sync_status": login.last_sync_status,
                "accounts": login.last_sync_account_count or 0,
            })
        return rows


def print_auth_status() -> None:
    """Pretty-print auth status table."""
    rows = auth_status()
    if not rows:
        print("No enabled logins found.")
        return

    # Group by status
    by_status: dict[str, list] = {}
    for r in rows:
        by_status.setdefault(r["auth_status"], []).append(r)

    status_order = ["needs_2fa", "login_failed", "unknown", "authenticated"]
    for status in status_order:
        group = by_status.get(status, [])
        if not group:
            continue

        icon = {
            "authenticated": "+",
            "needs_2fa": "!",
            "login_failed": "X",
            "unknown": "?",
        }.get(status, "?")

        print(f"\n[{icon}] {status.upper()} ({len(group)})")
        for r in group:
            accts = f"  ({r['accounts']} accounts)" if r["accounts"] else ""
            when = f"  @ {r['auth_at'][:16]}" if r["auth_at"] else ""
            print(f"  {r['id']:3d}  {r['provider_key']:<20s} {r['username'] or '':<30s}{accts}{when}")

    total = len(rows)
    authed = len(by_status.get("authenticated", []))
    needs = len(by_status.get("needs_2fa", []))
    failed = len(by_status.get("login_failed", []))
    unknown = len(by_status.get("unknown", []))
    print(f"\nTotal: {total} logins — {authed} authenticated, {needs} needs 2FA, {failed} failed, {unknown} unknown")


def _build_auth_task(provider_key: str, provider_cfg: dict, entry: dict) -> str:
    """Build an Agent task for logging into a provider."""
    institution = provider_cfg.get("institution", provider_key.replace("_", " ").title())
    return (
        f"Log in to the {institution} website.\n"
        f"The username is x_username and the password is x_password.\n\n"
        f"Steps:\n"
        f"1. If there is a login form visible, fill in the username and password and submit.\n"
        f"2. If the site shows a 2FA/verification prompt (text code, email code, security question, "
        f"push notification, etc.), call the pause_for_human tool so the human can complete it.\n"
        f"3. After login is complete (you can see account info, dashboard, or a welcome message), "
        f"you are done.\n\n"
        f"Important:\n"
        f"- If the page looks like a mobile site, look for a 'Desktop site' or 'Full site' link.\n"
        f"- If you are already logged in (dashboard visible), you are done immediately.\n"
        f"- Do NOT navigate away from the site after logging in.\n"
    )


def _update_provider_auth(provider_key: str, status: str) -> int:
    """Update auth status for all enabled logins of a provider. Returns count."""
    with SessionLocal() as session:
        provider_logins = (
            session.query(ScraperLogin)
            .filter(ScraperLogin.provider_key == provider_key)
            .filter(ScraperLogin.enabled.is_(True))
            .all()
        )
        for login in provider_logins:
            login.last_auth_status = status
            if status == _STATUS_AUTHENTICATED:
                login.last_auth_at = datetime.utcnow()
        session.commit()
        return len(provider_logins)


async def auth_login(targets: list[str] | None = None) -> None:
    """Interactive login pass using browser-use Agent to auto-fill credentials.

    The Agent navigates to each site, fills username/password, then pauses
    for human 2FA completion. Only attempts logins with status needs_2fa,
    login_failed, or unknown (never tried).
    """
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    from browser_use import Agent, ActionResult, Tools
    from browser_use.browser.session import BrowserSession
    from .llm import load_config
    from .scraper import _build_llm
    from ..services.crypto import decrypt

    init_db()

    config_path = Path(__file__).parent.parent / "config" / "scraper.toml"
    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    browser_cfg = config["browser"]
    providers_cfg = config.get("providers", {})
    agent_cfg = config.get("agent", {})

    with SessionLocal() as session:
        query = (
            session.query(ScraperLogin)
            .filter(ScraperLogin.enabled.is_(True))
            .filter(
                ScraperLogin.last_auth_status.in_(["needs_2fa", "login_failed"])
                | ScraperLogin.last_auth_status.is_(None)
            )
            .order_by(ScraperLogin.provider_key, ScraperLogin.id)
        )
        if targets:
            query = query.filter(ScraperLogin.provider_key.in_(targets))

        logins = query.all()

        if not logins:
            print("No logins need authentication. All good!")
            return

        # Dedupe by provider_key — only need one login per provider to establish session
        seen_providers: set[str] = set()
        to_auth: list[dict] = []
        for login in logins:
            if login.provider_key in seen_providers:
                continue
            seen_providers.add(login.provider_key)
            entry: dict[str, Any] = {
                "id": login.id,
                "provider_key": login.provider_key,
                "label": login.label,
                "username": login.username or "",
            }
            if login.password_encrypted:
                entry["password"] = decrypt(login.password_encrypted)
            pcfg = providers_cfg.get(login.provider_key, {})
            entry["start_url"] = pcfg.get("start_url", login.login_url or "")
            to_auth.append(entry)

    print(f"\n{len(to_auth)} provider(s) need authentication:")
    for entry in to_auth:
        print(f"  {entry['provider_key']:<20s} {entry['username']}")

    # Launch browser with desktop viewport
    user_data_dir = Path(browser_cfg.get("user_data_dir", "data/browser-profile")).resolve()
    user_data_dir.mkdir(parents=True, exist_ok=True)

    from .scraper import _provider_cookie_domains
    cookie_domains = _provider_cookie_domains(config)

    browser_session = BrowserSession(
        user_data_dir=str(user_data_dir),
        headless=False,
        keep_alive=True,
        cookie_whitelist_domains=cookie_domains,
    )
    await browser_session.start()

    # Build LLM — reuse scraper's config-aware builder
    full_config = load_config()
    full_config.update(config)
    llm = _build_llm(full_config, agent_cfg=agent_cfg)

    # Build tools with pause_for_human action
    tools = Tools()

    @tools.action(
        "Pause and wait for the human to complete 2FA / verification. "
        "Use this when you see a 2FA code prompt, security question, push "
        "notification screen, CAPTCHA, or any challenge you cannot solve. "
        "The browser stays open — the human will complete the action."
    )
    async def pause_for_human():
        print(f"\n  >>> 2FA/VERIFICATION REQUIRED")
        print(f"  >>> Complete the challenge in the browser window.")
        result = await asyncio.get_event_loop().run_in_executor(
            None, input, "  >>> Press Enter when done (or 's' to skip this provider): "
        )
        if result.strip().lower() == "s":
            return ActionResult(extracted_content="SKIPPED_BY_USER")
        return ActionResult(extracted_content="Human completed verification. Continue.")

    for entry in to_auth:
        provider = entry["provider_key"]
        url = entry["start_url"]
        username = entry.get("username", "")
        password = entry.get("password", "")

        print(f"\n{'='*60}")
        print(f"  {provider.upper()}")
        print(f"  URL: {url}")
        print(f"  User: {username}")
        print(f"{'='*60}")

        if not url:
            print(f"  [{provider}] No login URL configured — skipping")
            continue

        provider_cfg = providers_cfg.get(provider, {})
        task = _build_auth_task(provider, provider_cfg, entry)

        agent = Agent(
            task=task,
            llm=llm,
            browser_session=browser_session,
            tools=tools,
            use_vision=True,
            max_steps=15,
            max_failures=3,
            max_actions_per_step=1,
            sensitive_data={"x_username": username, "x_password": password},
            directly_open_url=url,
        )

        try:
            history = await agent.run()
            final = history.final_result() or ""

            if "SKIPPED_BY_USER" in final:
                print(f"  [{provider}] Skipped by user")
            else:
                count = _update_provider_auth(provider, _STATUS_AUTHENTICATED)
                print(f"  [{provider}] Marked {count} login(s) as authenticated")

        except Exception as exc:
            logger.exception("Auth agent failed for %s", provider)
            print(f"  [{provider}] Agent error: {exc}")
            # Ask user what to do
            result = await asyncio.get_event_loop().run_in_executor(
                None, input,
                f"  >>> Mark as authenticated anyway? (y/n/s to skip): "
            )
            choice = result.strip().lower()
            if choice == "y":
                count = _update_provider_auth(provider, _STATUS_AUTHENTICATED)
                print(f"  [{provider}] Manually marked {count} login(s) as authenticated")
            else:
                print(f"  [{provider}] Left as-is")

    await browser_session.kill()
    print("\nDone! Run `just auth-status` to verify.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Auth status and login management")
    parser.add_argument("command", choices=["status", "login"], help="Command to run")
    parser.add_argument("targets", nargs="*", help="Provider keys (for login command)")
    parser.add_argument("--analyst-llm", default=None, help="LLM preset for analyst/utility tasks")
    parser.add_argument("--agent-llm", default=None, help="LLM preset for browser agent")
    args = parser.parse_args()

    if args.analyst_llm:
        os.environ["ANALYST_LLM"] = args.analyst_llm
    if args.agent_llm:
        os.environ["AGENT_LLM"] = args.agent_llm

    if args.command == "status":
        print_auth_status()
    elif args.command == "login":
        asyncio.run(auth_login(args.targets or None))
