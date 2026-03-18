"""
browser-use Agent-based scraper.

Uses browser-use's built-in Agent for browser automation, replacing the custom
state machine. Keeps: account merging, provider config, analyst hints, and
statement downloads as a separate Agent task.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from pydantic import BaseModel

try:
    import tomllib
except ImportError:
    import tomli as tomllib

from browser_use import Agent, ActionResult
from browser_use.browser.session import BrowserSession
from browser_use.llm import ChatOllama, ChatOpenAI, ChatOpenRouter
from browser_use.llm.browser_use.chat import ChatBrowserUse

from .analyst import load_provider_hints
from .prompts import get_extraction_prompt

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "scraper.toml"


async def _kill_stale_chrome(user_data_dir: Path, *, on_log: Callable | None = None):
    """Kill Chrome processes using our automation profile dir so the CDP port is free."""
    if sys.platform == "win32":
        # wmic gives command lines; find any chrome.exe whose args include our profile path
        needle = str(user_data_dir).lower()
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["wmic", "process", "where", "name='chrome.exe'", "get", "ProcessId,CommandLine", "/FORMAT:LIST"],
                capture_output=True, text=True, timeout=10,
            )
            pid = None
            for line in result.stdout.splitlines():
                if line.startswith("CommandLine=") and needle in line.lower():
                    pid = None  # reset — wait for matching PID line
                    continue
                if pid is None and line.startswith("CommandLine="):
                    pid = None
                if line.startswith("ProcessId=") and pid is None:
                    # previous CommandLine matched
                    pass
            # Simpler approach: just kill chrome.exe processes with our user-data-dir
            result2 = await asyncio.to_thread(
                subprocess.run,
                ["wmic", "process", "where", "name='chrome.exe'", "get", "ProcessId,CommandLine"],
                capture_output=True, text=True, timeout=10,
            )
            pids_to_kill = []
            for line in result2.stdout.splitlines():
                if needle in line.lower():
                    # Extract PID (last number on the line)
                    parts = line.strip().split()
                    if parts:
                        try:
                            pids_to_kill.append(int(parts[-1]))
                        except ValueError:
                            pass
            if pids_to_kill:
                if on_log:
                    on_log(f"Killing {len(pids_to_kill)} stale Chrome process(es)")
                for pid in pids_to_kill:
                    try:
                        await asyncio.to_thread(subprocess.run, ["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
                    except Exception:
                        pass
                await asyncio.sleep(1)
        except Exception as exc:
            logger.debug("Chrome cleanup failed (non-fatal): %s", exc)
    else:
        # Unix: pkill by matching the user-data-dir argument
        try:
            await asyncio.to_thread(
                subprocess.run,
                ["pkill", "-f", f"--user-data-dir={user_data_dir}"],
                capture_output=True, timeout=5,
            )
            await asyncio.sleep(1)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Pydantic output schema — re-exported from workflows for backward compat
# ---------------------------------------------------------------------------

from ..tools.workflows import AccountOutput, AccountListOutput  # noqa: F401
from ..tools.workflows import Workflow


from dataclasses import dataclass, field


class ProviderTimeoutError(Exception):
    """Raised when a provider scrape exceeds its wall-clock timeout."""
    pass


@dataclass
class ScrapeMetrics:
    """Structured metrics from a scraper run — no log parsing needed."""
    accounts_found: int = 0
    steps_taken: int = 0
    failed_actions: int = 0
    errors: list[str] = field(default_factory=list)
    timed_out: bool = False
    timeout_seconds: float | None = None
    elapsed_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "accounts_found": self.accounts_found,
            "steps_taken": self.steps_taken,
            "failed_actions": self.failed_actions,
            "errors": self.errors,
            "timed_out": self.timed_out,
            "timeout_seconds": self.timeout_seconds,
            "elapsed_seconds": self.elapsed_seconds,
        }


@dataclass
class ScrapeResult:
    """Return value from scrape_provider."""
    accounts: list[dict[str, Any]] = field(default_factory=list)
    metrics: ScrapeMetrics = field(default_factory=ScrapeMetrics)


@dataclass
class ScrapeContext:
    """Run-scoped configuration carried through all scraper functions."""
    provider_key: str
    interactive: bool = False
    download_statements: bool = False
    accounts_db: Any | None = None
    on_log: Callable[[str], None] | None = None

    # Populated during run
    config: dict = field(default_factory=dict)
    provider_cfg: dict = field(default_factory=dict)
    agent_cfg: dict = field(default_factory=dict)
    download_dir: Path | None = None

    def log(self, msg: str) -> None:
        if self.on_log:
            self.on_log(msg)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def _active_agent_preset() -> str:
    # Browser-use cloud is the default for the browser agent; override with AGENT_LLM.
    return os.environ.get("AGENT_LLM") or "browser_use"


def _build_llm(config: dict, *, agent_cfg: dict | None = None) -> Any:
    """Build a vision-capable LLM for browser-use Agent.

    Prefers the observer model (vision) when the active preset is not vision-capable.
    You can override the browser automation preset with AGENT_LLM.
    """
    preset = _active_agent_preset()
    presets = config.get("llm", {})
    if preset not in presets:
        raise ValueError(f"Unknown LLM preset for agent: {preset}. Available: {sorted(presets.keys())}")

    llm_cfg = presets[preset]

    # Prefer per-preset observer; otherwise use the global observer only if this preset isn't vision-capable.
    observer_cfg = llm_cfg.get("observer")
    supports_vision = bool(llm_cfg.get("supports_vision")) if "supports_vision" in llm_cfg else False
    if not observer_cfg and not supports_vision:
        observer_cfg = presets.get("observer") or {}

    cfg = observer_cfg or llm_cfg

    base_url = cfg.get("base_url", llm_cfg.get("base_url", ""))
    model = cfg.get("model", llm_cfg["model"])
    timeout = float(cfg.get("timeout", llm_cfg.get("timeout", 120.0)))

    api_key_env = cfg.get("api_key_env", "")
    api_key = os.environ.get(api_key_env, "") if api_key_env else cfg.get("api_key", "")

    # browser-use cloud (models like bu-1-0, bu-2-0, browser-use/*)
    if str(model).startswith("bu-") or str(model).startswith("browser-use/") or "browser-use.com" in str(base_url):
        llm = ChatBrowserUse(
            model=str(model),
            api_key=str(api_key) if api_key else None,
            base_url=str(base_url) if base_url else None,
            timeout=timeout,
        )
        if agent_cfg and agent_cfg.get("flash_mode") and hasattr(llm, "fast"):
            llm.fast = True
        return llm

    if "ollama" in base_url or "localhost" in base_url:
        return ChatOllama(model=model, host=base_url.replace("/v1", ""))

    # OpenRouter (OpenAI-compatible, but with its own headers/usage parsing)
    if "openrouter.ai" in str(base_url) or str(model).startswith("openrouter/"):
        return ChatOpenRouter(model=str(model), api_key=str(api_key) if api_key else None, base_url=base_url, timeout=timeout)

    # Generic OpenAI-compatible endpoint (OpenAI, vLLM, LM Studio, etc.)
    return ChatOpenAI(model=str(model), api_key=str(api_key) if api_key else None, base_url=base_url, timeout=timeout)


def _format_hints(hints: dict[str, Any]) -> str:
    """Format provider hints as text for extend_system_message."""
    if not hints:
        return ""

    parts = ["## Provider Hints (from previous runs)\n"]
    for category in ("navigation_tips", "effective_patterns", "failed_actions"):
        items = hints.get(category, [])
        if items:
            parts.append(f"### {category.replace('_', ' ').title()}")
            for item in items:
                parts.append(f"- {item}")
            parts.append("")
    return "\n".join(parts)


def _build_preamble(
    provider_key: str,
    provider_cfg: dict,
    dashboard_url: str | None,
) -> str:
    """Build the universal login/2FA/navigation preamble shared by all workflows."""
    institution = provider_cfg.get("institution", provider_key.replace("_", " ").title())

    parts = [
        f"Go to the {institution} website.",
        "If you need to log in, the username is x_username and the password is x_password.",
        "If you encounter a 2FA prompt, verification code screen, CAPTCHA, or any security "
        "challenge you cannot complete yourself, call the pause_for_human action and wait.",
    ]

    if dashboard_url:
        parts.append(f"After logging in, navigate to {dashboard_url}.")

    return "\n\n".join(parts)


def _build_task(
    provider_key: str,
    provider_cfg: dict,
    dashboard_url: str | None,
    workflow: Workflow,
    extraction_prompt: str,
) -> str:
    """Build the full Agent task: preamble + workflow prompt + extraction prompt."""
    preamble = _build_preamble(provider_key, provider_cfg, dashboard_url)

    parts = [preamble, workflow.prompt_template]
    if extraction_prompt:
        parts.append(extraction_prompt)

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Account merging (preserved from original — handles dedup across pagination)
# ---------------------------------------------------------------------------

def _normalize_mask(mask: Any) -> str | None:
    if mask is None:
        return None
    s = str(mask).strip().lstrip("*-. ").strip()
    return s if s else None


def _is_generic_account_name(name: str | None) -> bool:
    if not name:
        return True
    generic = {"account", "card", "credit card", "unknown", "n/a", ""}
    return name.strip().lower() in generic


def _account_key(account: dict[str, Any]) -> str:
    mask = _normalize_mask(account.get("account_mask"))
    name = (account.get("card_name") or "").strip()
    address = (account.get("address") or "").strip()

    if mask and name and not _is_generic_account_name(name):
        return f"mask:{mask}|name:{name}"
    if mask:
        return f"mask:{mask}"
    if name and address:
        return f"name:{name}|addr:{address}"
    if name:
        return f"name:{name}"
    return f"unknown:{id(account)}"


def _find_matching_key(collected: dict[str, dict], account: dict) -> str | None:
    """Find if account already exists under a different key."""
    mask = _normalize_mask(account.get("account_mask"))
    if not mask:
        return None
    for key, existing in collected.items():
        if _normalize_mask(existing.get("account_mask")) == mask:
            return key
    return None


def _merge_account(existing: dict, incoming: dict) -> dict:
    merged = dict(existing)
    for field in ("card_name", "account_mask", "current_balance", "statement_balance",
                  "due_date", "minimum_payment", "last_payment_amount",
                  "last_payment_date", "credit_limit", "interest_rate",
                  "account_type", "address"):
        new_val = incoming.get(field)
        old_val = merged.get(field)
        if old_val in (None, "", "Unknown Account") and new_val not in (None, ""):
            merged[field] = new_val

    # Always update billing details if incoming has them
    for field in ("current_balance", "statement_balance", "minimum_payment", "due_date",
                  "last_payment_amount", "last_payment_date", "credit_limit", "interest_rate"):
        if incoming.get(field) is not None:
            merged[field] = incoming[field]

    # Prefer longer mask
    if incoming.get("account_mask") and len(str(incoming["account_mask"])) > len(str(merged.get("account_mask") or "")):
        merged["account_mask"] = incoming["account_mask"]

    # Prefer specific names over generic
    if _is_generic_account_name(merged.get("card_name")) and not _is_generic_account_name(incoming.get("card_name")):
        merged["card_name"] = incoming.get("card_name")

    return merged


def _merge_accounts(
    collected: dict[str, dict],
    raw_accounts: list[dict],
    *,
    provider_key: str,
    label: str,
    login_id: int | None,
) -> tuple[int, int]:
    """Merge incoming accounts into collected dict. Returns (added, total)."""
    added = 0
    for account in raw_accounts:
        account.setdefault("provider", provider_key)
        account.setdefault("label", label)
        account.setdefault("login_id", login_id)

        key = _account_key(account)
        match_key = _find_matching_key(collected, account)

        if match_key:
            collected[match_key] = _merge_account(collected[match_key], account)
        elif key in collected:
            collected[key] = _merge_account(collected[key], account)
        else:
            collected[key] = account
            added += 1

    return added, len(collected)


# ---------------------------------------------------------------------------
# Step callback — emits log lines compatible with analyst metrics extraction
# ---------------------------------------------------------------------------

class _HumanPauseSkipped(Exception):
    """Raised when pause_for_human is called in auto mode to abort the agent."""


def _build_tools(*, interactive: bool = False) -> Any:
    """Build a Tools instance with a custom pause_for_human action.

    The agent calls this action when it encounters a 2FA/verification screen,
    CAPTCHA, or anything else it can't handle alone. The agent decides when
    to use it — no hardcoded keyword matching needed.

    In interactive mode, blocks for human input. In auto mode, raises
    _HumanPauseSkipped so the caller can flag the login and move on.
    """
    import asyncio
    from browser_use import Tools

    tools = Tools()

    @tools.action(
        "Pause and wait for the human to intervene. Use this when you encounter "
        "a 2FA / verification code prompt, CAPTCHA, security challenge, or any "
        "screen that requires human input you cannot provide. The browser stays "
        "open — the human will complete the action, then press Enter to resume.",
    )
    async def pause_for_human():
        if not interactive:
            logger.warning("Agent requested human intervention in auto mode — skipping")
            raise _HumanPauseSkipped("2FA/verification required")

        logger.warning("Agent requested human intervention — pausing")
        print(f"\n{'='*60}")
        print(f"  HUMAN INPUT NEEDED")
        print(f"  Complete the action in the browser window,")
        print(f"  then press Enter here to continue.")
        print(f"{'='*60}")
        # Run blocking input() in a thread so we don't block the event loop
        await asyncio.get_event_loop().run_in_executor(
            None, input, ">>> Press Enter when done... "
        )
        logger.info("Human confirmed — resuming agent")
        return ActionResult(extracted_content="Human completed the action. Continue with the task.")

    return tools


_LOGIN_FAILURE_PATTERNS = [
    "wrong user id or password",
    "wrong username or password",
    "incorrect password",
    "invalid credentials",
    "login failed",
    "unable to log in",
    "unable to sign in",
    "account locked",
    "account disabled",
]


async def _on_step(agent: Agent, on_log: Callable[[str], None] | None) -> None:
    """Called after each Agent step. Emits log lines for analyst."""
    step_num = agent.state.n_steps if hasattr(agent, "state") else 0

    actions = agent.history.action_names() if agent.history else []
    last_action = actions[-1] if actions else "unknown"

    if on_log:
        on_log(f"Step {step_num}: action={last_action}")

    errors = agent.history.errors() if agent.history else []
    if errors and errors[-1] and on_log:
        on_log(f"Step {step_num}: failed — {errors[-1]}")

    # Check agent memory for login failure — abort early instead of retrying
    if hasattr(agent, "state") and hasattr(agent.state, "memory"):
        memory = (agent.state.memory or "").lower()
        for pattern in _LOGIN_FAILURE_PATTERNS:
            if pattern in memory:
                if on_log:
                    on_log(f"Step {step_num}: login failure detected — aborting")
                agent._login_failed = True  # checked after run() returns
                agent.stop()
                return


# ---------------------------------------------------------------------------
# Statement downloads — separate Agent task per eligible account
# ---------------------------------------------------------------------------

def _build_statement_task(
    provider_key: str,
    provider_cfg: dict,
    eligible_accounts: list[dict[str, Any]],
    dashboard_url: str | None = None,
) -> str:
    """Build the Agent task for downloading statement PDFs for all eligible accounts."""
    institution = provider_cfg.get("institution", provider_key.replace("_", " ").title())

    account_lines = []
    for acct in eligible_accounts:
        name = acct.get("card_name", "unknown")
        mask = acct.get("account_mask", "")
        mask_hint = f" (ending in {mask})" if mask else ""
        account_lines.append(f"- {name}{mask_hint}")

    accounts_str = "\n".join(account_lines)
    dashboard_hint = f"You are starting on the {institution} dashboard at {dashboard_url}.\n" if dashboard_url else ""

    return f"""{dashboard_hint}You need to download the most recent BILLING STATEMENT PDF for each of these accounts:
{accounts_str}

For EACH account, follow these steps:
1. Click on the account name/card on the dashboard to open it
2. Look for "Statements & Activity" link/tab and click it
3. Click "Go to PDF Statements" or "View PDF Statements"
4. Find the most recent monthly billing statement in the list
5. Click the "Download" button/icon next to that statement
6. WAIT — a "Select File Type" dialog will appear. Click the "Download" link inside that dialog to start the actual download.
   - Do NOT navigate away until you see the download complete
   - Wait a few seconds after clicking Download in the dialog
7. Go BACK to the dashboard (navigate to the overview URL) for the next account

IMPORTANT:
- Download ONE statement per account — the MOST RECENT billing statement only
- Skip "Important Notices" or "Account Agreement Changes" — those are NOT statements
- A real billing statement has a date like "Feb 26, 2026" in the statement list
- After downloading all statements, you are done"""


async def _download_statements(
    browser_session: BrowserSession,
    llm: ChatOllama | ChatOpenRouter,
    accounts: list[dict[str, Any]],
    provider_key: str,
    provider_cfg: dict,
    config: dict,
    download_dir: Path,
    dashboard_url: str | None = None,
    start_url: str | None = None,
    on_log: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Download the latest statement PDF for each eligible account using a single Agent."""
    stmt_cfg = config.get("statements", {})
    agent_cfg = config.get("agent", {})
    eligible_types = set(stmt_cfg.get("eligible_account_types", ["credit_card", "loan", "line_of_credit"]))

    eligible = [
        acct for acct in accounts
        if (acct.get("account_type") or "").lower().replace(" ", "_") in eligible_types
    ]

    if not eligible:
        if on_log:
            on_log(f"[{provider_key}] No eligible accounts for statement download")
        return []

    if on_log:
        on_log(f"[{provider_key}] Downloading statements for {len(eligible)} account(s)...")

    # Snapshot existing PDFs before download
    existing_pdfs = set(download_dir.glob("*.pdf"))

    task = _build_statement_task(provider_key, provider_cfg, eligible, dashboard_url)

    # Scale max_steps with number of accounts (~10 steps per account with single-action mode)
    max_steps = max(stmt_cfg.get("max_steps", 50), len(eligible) * 10)

    tools = _build_tools(interactive=interactive)

    agent = Agent(
        task=task,
        llm=llm,
        browser_session=browser_session,
        tools=tools,
        use_vision=True,
        max_steps=max_steps,
        max_failures=agent_cfg.get("max_failures", 3),
        max_actions_per_step=1,  # Must be 1 — download requires waiting for dialog
        directly_open_url=dashboard_url or start_url or "",
    )

    try:
        history = await agent.run(
            on_step_end=lambda a: _on_step(a, on_log),
        )
    except Exception as exc:
        logger.exception("Statement download agent failed for %s", provider_key)
        if on_log:
            on_log(f"[{provider_key}] Statement agent error: {exc}")
        return []

    # Find all newly downloaded PDFs
    new_pdfs = sorted(
        [p for p in download_dir.glob("*.pdf") if p not in existing_pdfs],
        key=lambda p: p.stat().st_mtime,
    )

    # Rename PDFs: match to accounts by text content, then rename to {mask}_{date}.pdf
    from .pdf_utils import extract_pdf_text

    downloaded: list[dict[str, Any]] = []
    for pdf_path in new_pdfs:
        size = pdf_path.stat().st_size
        matched_acct = None

        try:
            pdf_text = extract_pdf_text(pdf_path)
            # Match by account mask
            for acct in eligible:
                mask = acct.get("account_mask", "")
                if mask and mask in pdf_text:
                    matched_acct = acct
                    break
            # Fallback: match by card name
            if not matched_acct:
                for acct in eligible:
                    card = acct.get("card_name", "")
                    if card and card.lower() in pdf_text.lower():
                        matched_acct = acct
                        break
        except Exception:
            pass

        # Rename file: {product_slug}_{mask}_{original_stem}.pdf
        if matched_acct:
            card_name = matched_acct.get("card_name", "unknown")
            mask = matched_acct.get("account_mask", "")
            product_slug = re.sub(r"[^\w]+", "_", card_name).strip("_").lower()[:30]
            parts = [product_slug]
            if mask:
                parts.append(mask)
            parts.append(pdf_path.stem)
            new_name = "_".join(parts) + ".pdf"
        else:
            new_name = pdf_path.name

        new_path = download_dir / new_name
        if new_path != pdf_path and not new_path.exists():
            pdf_path.rename(new_path)
            pdf_path = new_path

        downloaded.append({
            "card_name": matched_acct.get("card_name", pdf_path.stem) if matched_acct else pdf_path.stem,
            "account_mask": matched_acct.get("account_mask") if matched_acct else None,
            "file_path": str(pdf_path),
            "file_size_bytes": size,
        })
        if on_log:
            on_log(f"[{provider_key}] Downloaded: {pdf_path.name} ({size:,} bytes)")

    if on_log:
        on_log(f"[{provider_key}] {len(downloaded)} new PDF(s) downloaded")

    return downloaded


def _update_auth_status(login_id: int | None, status: str) -> None:
    """Update the last_auth_status on a ScraperLogin."""
    if not login_id:
        return
    try:
        from datetime import datetime
        from ..database import SessionLocal
        from ..models.accounts import ScraperLogin
        with SessionLocal() as session:
            login = session.get(ScraperLogin, login_id)
            if login:
                login.last_auth_status = status
                login.last_auth_at = datetime.utcnow()
                session.commit()
    except Exception:
        logger.debug("Could not update auth status for login %s", login_id, exc_info=True)


def _persist_statement(
    accounts_db: Any,
    provider_key: str,
    matched_acct: dict,
    dl: dict,
    stmt_data: dict,
    on_log: Callable[[str], None] | None = None,
) -> None:
    """Match a downloaded statement to a FinancialAccount and upsert an AccountStatement."""
    from ..database import SessionLocal
    from ..models.accounts import FinancialAccount

    mask = matched_acct.get("account_mask", "")
    card_name = matched_acct.get("card_name", "")

    # Find the FinancialAccount by mask or display_name
    with SessionLocal() as session:
        db_account = None
        if mask:
            db_account = (
                session.query(FinancialAccount)
                .filter_by(provider_key=provider_key, account_mask=mask)
                .first()
            )
        if not db_account and card_name:
            db_account = (
                session.query(FinancialAccount)
                .filter_by(provider_key=provider_key, display_name=card_name)
                .first()
            )

    if not db_account:
        if on_log:
            on_log(f"[{provider_key}] No DB account for {card_name} ({mask}) — skipping statement persist")
        return

    # Derive statement_month from statement_date or filename
    statement_date = stmt_data.get("statement_date")
    if statement_date and len(statement_date) >= 7:
        statement_month = statement_date[:7]  # YYYY-MM
    else:
        # Try to parse from filename
        stem = Path(dl["file_path"]).stem
        month_match = re.search(r"(\d{4})[_-](\d{2})", stem)
        if month_match:
            statement_month = f"{month_match.group(1)}-{month_match.group(2)}"
        else:
            from datetime import datetime
            statement_month = datetime.utcnow().strftime("%Y-%m")

    from datetime import datetime
    accounts_db.upsert_statement(
        financial_account_id=db_account.id,
        statement_month=statement_month,
        scraper_login_id=matched_acct.get("login_id"),
        statement_date=statement_date,
        file_path=dl["file_path"],
        file_size_bytes=dl.get("file_size_bytes"),
        downloaded_at=datetime.utcnow(),
        intro_apr_rate=stmt_data.get("intro_apr_rate"),
        intro_apr_end_date=stmt_data.get("intro_apr_end_date"),
        regular_apr=stmt_data.get("regular_apr"),
        credit_limit=stmt_data.get("credit_limit"),
        raw_extracted_json=stmt_data,
    )

    if on_log:
        on_log(f"[{provider_key}] Saved statement for {card_name} ({statement_month})")


def _provider_cookie_domains(config: dict[str, Any]) -> list[str]:
    """Extract wildcard domains from provider URLs for cookie whitelisting."""
    domains: set[str] = set()
    for pcfg in config.get("providers", {}).values():
        for key in ("start_url", "dashboard_url"):
            url = pcfg.get(key, "")
            if not url:
                continue
            host = urlparse(url).hostname
            if host:
                parts = host.split(".")
                root = ".".join(parts[-2:]) if len(parts) > 2 else host
                domains.add(f"*.{root}")
    return sorted(domains)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def scrape_provider(
    provider_key: str,
    logins: list[dict[str, Any]],
    *,
    download_statements: bool = False,
    accounts_db: Any | None = None,
    interactive: bool = False,
    on_log: Callable[[str], None] | None = None,
    workflow: Workflow | None = None,
) -> ScrapeResult:
    """Scrape one provider using browser-use Agent.

    Pass 1: discover accounts from overview page.
    Pass 2 (if download_statements): download statement PDFs and extract billing fields.
    """
    config = _load_config()
    browser_cfg = config["browser"]
    agent_cfg = config.get("agent", {})
    provider_cfg = config.get("providers", {}).get(provider_key, {})
    stmt_cfg = config.get("statements", {})

    # Get timeout config (default 30 minutes), allow per-provider override
    provider_timeout = provider_cfg.get("timeout", agent_cfg.get("provider_timeout", 1800))

    ctx = ScrapeContext(
        provider_key=provider_key,
        interactive=interactive,
        download_statements=download_statements,
        accounts_db=accounts_db,
        on_log=on_log,
        config=config,
        provider_cfg=provider_cfg,
        agent_cfg=agent_cfg,
    )

    # Set up download directory for statement PDFs (must be absolute for CDP)
    download_dir = (Path(stmt_cfg.get("download_dir", "data/statements")) / provider_key).resolve()
    download_dir.mkdir(parents=True, exist_ok=True)

    # Dedicated automation profile — sessions and cookies persist across runs.
    # First run: human logs in manually. Subsequent runs: already authenticated.
    user_data_dir = Path(browser_cfg.get("user_data_dir", "data/browser-profile")).resolve()
    user_data_dir.mkdir(parents=True, exist_ok=True)

    # Whitelist provider domains so the "I still don't care about cookies"
    # extension doesn't dismiss consent banners on financial sites (which can
    # reject session cookies needed for login persistence).
    cookie_domains = _provider_cookie_domains(config)

    browser_session = BrowserSession(
        user_data_dir=str(user_data_dir),
        headless=agent_cfg.get("headless", False),
        keep_alive=True,
        downloads_path=str(download_dir),
        accept_downloads=True,
        cookie_whitelist_domains=cookie_domains,
    )

    # Kill any leftover Chrome processes using our profile dir before launching
    await _kill_stale_chrome(user_data_dir, on_log=on_log)

    await browser_session.start()

    llm = _build_llm(config, agent_cfg=agent_cfg)
    all_accounts: list[dict[str, Any]] = []
    metrics = ScrapeMetrics()
    metrics.timeout_seconds = provider_timeout

    async def _run_scrape_with_timeout():
        """Inner function that does the actual scraping, wrapped by timeout."""
        for login in logins:
            login_id = login.get("id")
            label = login.get("label", provider_key)
            username = login.get("username", "")
            password = login.get("password", "")

            if not username:
                if on_log:
                    on_log(f"[{provider_key}] Skipping {label}: no username")
                continue

            start_url = provider_cfg.get("start_url", login.get("login_url", ""))
            dashboard_url = str(provider_cfg.get("dashboard_url") or "").strip() or None
            account_type = login.get("account_type")
            extraction_prompt = get_extraction_prompt(provider_key, account_type)
            hints = load_provider_hints(provider_key)

            if on_log:
                on_log(f"[{provider_key}] Scraping as {label}...")

            # Resolve workflow — default to financial_scraper
            from ..tools.workflows import get_workflow as _get_wf, FINANCIAL_WORKFLOW
            active_wf = workflow or _get_wf("financial_scraper") or FINANCIAL_WORKFLOW
            output_schema = active_wf.output_schema
            task = _build_task(provider_key, provider_cfg, dashboard_url, active_wf, extraction_prompt)

            tools = _build_tools(interactive=interactive)

            agent = Agent(
                task=task,
                llm=llm,
                browser_session=browser_session,
                tools=tools,
                use_vision=True,
                max_steps=agent_cfg.get("max_steps", 50),
                max_failures=agent_cfg.get("max_failures", 3),
                max_actions_per_step=agent_cfg.get("max_actions_per_step", 3),
                extend_system_message=_format_hints(hints),
                output_model_schema=output_schema,
                sensitive_data={"x_username": username, "x_password": password},
                directly_open_url=start_url,
            )

            try:
                history = await agent.run(
                    on_step_end=lambda a: _on_step(a, on_log),
                )

                # Collect metrics from agent history
                metrics.steps_taken += agent.state.n_steps if hasattr(agent, "state") else 0
                errors = history.errors() if history else []
                metrics.failed_actions += sum(1 for e in errors if e)

                # Early exit if login failure was detected in step callback
                if getattr(agent, "_login_failed", False):
                    _update_auth_status(login_id, "login_failed")
                    metrics.errors.append(f"{label}: login failed — bad credentials")
                    if on_log:
                        on_log(f"[{provider_key}] {label}: login failed — check credentials")
                    continue

                # --- Pass 1: extract accounts from overview ---
                result = history.get_structured_output(output_schema)
                login_accounts: list[dict] = []
                if result:
                    result_dict = result.model_dump()
                    # Use the workflow's result_key to extract the list
                    login_accounts = result_dict.get(active_wf.result_key, [])
                    if not login_accounts:
                        # Fallback: find first list field
                        login_accounts = next((v for v in result_dict.values() if isinstance(v, list)), []) or []
                if not login_accounts:
                    # Fallback: try parsing final_result as JSON
                    raw_text = history.final_result()
                    if raw_text:
                        try:
                            parsed = json.loads(raw_text)
                            if isinstance(parsed, dict):
                                # Find the first list value in the dict
                                list_val = next((v for v in parsed.values() if isinstance(v, list)), None)
                                if list_val is not None:
                                    parsed = list_val
                            if isinstance(parsed, list):
                                login_accounts = parsed
                        except (json.JSONDecodeError, TypeError):
                            pass

                if not login_accounts:
                    if on_log:
                        on_log(f"[{provider_key}] No accounts found for {label}")
                else:
                    if on_log:
                        on_log(f"[{provider_key}] Pass 1: found {len(login_accounts)} item(s)")

                    if active_wf.key != "financial_scraper":
                        # Non-financial workflows: store raw results directly
                        for item in login_accounts:
                            item.setdefault("provider", provider_key)
                            item.setdefault("login_id", login_id)
                        all_accounts.extend(login_accounts)
                    else:
                        # Financial scraper: merge/dedup accounts
                        collected: dict[str, dict] = {}
                        added, total = _merge_accounts(
                            collected, login_accounts,
                            provider_key=provider_key,
                            label=label,
                            login_id=login_id,
                        )
                        all_accounts.extend(collected.values())

                    if on_log:
                        on_log(f"[{provider_key}] Got {len(all_accounts)} item(s) from {label}")

                # Mark login as authenticated
                _update_auth_status(login_id, "authenticated")

            except _HumanPauseSkipped:
                _update_auth_status(login_id, "needs_2fa")
                if on_log:
                    on_log(f"[{provider_key}] {label}: 2FA required — skipping (auto mode)")

            except Exception as exc:
                logger.exception("Agent failed for %s/%s", provider_key, label)
                _update_auth_status(login_id, "login_failed")
                metrics.errors.append(f"{label}: {exc}")
                if on_log:
                    on_log(f"[{provider_key}] Error for {label}: {exc}")

        # --- Pass 2: download statement PDFs and extract billing data ---
        # Persist accounts first so statement matching can find them in the DB
        if download_statements and all_accounts and accounts_db:
            accounts_db.save_scrape_results(provider_key, all_accounts)
            if on_log:
                on_log(f"[{provider_key}] Pass 2: downloading statements...")

            statement_results = await _download_statements(
                browser_session=browser_session,
                llm=llm,
                accounts=all_accounts,
                provider_key=provider_key,
                provider_cfg=provider_cfg,
                config=config,
                download_dir=download_dir,
                dashboard_url=provider_cfg.get("dashboard_url"),
                start_url=provider_cfg.get("start_url"),
                on_log=on_log,
            )

            # Parse downloaded PDFs, match to DB accounts, persist statements
            if statement_results:
                from .pdf_utils import extract_statement_data, extract_pdf_text
                from .llm import llm_chat

                for dl in statement_results:
                    try:
                        # Match PDF to scraped account by mask or card name in text
                        pdf_text = extract_pdf_text(dl["file_path"])
                        matched_acct = None
                        for acct in all_accounts:
                            mask = acct.get("account_mask", "")
                            if mask and mask in pdf_text:
                                matched_acct = acct
                                break
                        if not matched_acct:
                            for acct in all_accounts:
                                card = acct.get("card_name", "")
                                if card and card.lower() in pdf_text.lower():
                                    matched_acct = acct
                                    break

                        stmt_data = await extract_statement_data(dl["file_path"], llm_chat)
                        if stmt_data:
                            dl["statement_data"] = stmt_data
                            if matched_acct:
                                dl["card_name"] = matched_acct.get("card_name", dl["card_name"])
                                dl["account_mask"] = matched_acct.get("account_mask")
                                # Enrich the scraped account dict with PDF-extracted fields
                                for field in ("due_date", "minimum_payment", "statement_balance",
                                              "last_payment_amount", "last_payment_date",
                                              "credit_limit"):
                                    pdf_val = stmt_data.get(field)
                                    if pdf_val is not None:
                                        matched_acct[field] = pdf_val
                                for field in ("intro_apr_rate", "intro_apr_end_date", "regular_apr"):
                                    pdf_val = stmt_data.get(field)
                                    if pdf_val is not None:
                                        matched_acct[field] = pdf_val

                                # Persist to AccountStatement table via accounts_db
                                if accounts_db:
                                    _persist_statement(
                                        accounts_db, provider_key, matched_acct, dl, stmt_data, on_log,
                                    )

                                if on_log:
                                    filled = [f for f in stmt_data if stmt_data[f] is not None]
                                    on_log(f"[{provider_key}] PDF enriched {matched_acct.get('card_name')}: {', '.join(filled)}")
                            else:
                                if on_log:
                                    on_log(f"[{provider_key}] PDF {dl['file_path']} — no account match found")
                    except Exception as exc:
                        logger.exception("Statement parsing failed for %s", dl["file_path"])
                        if on_log:
                            on_log(f"[{provider_key}] PDF parse error: {exc}")

            if on_log:
                on_log(f"[{provider_key}] Downloaded {len(statement_results)} statement(s)")

    # Run with timeout
    start_time = time.monotonic()
    try:
        await asyncio.wait_for(_run_scrape_with_timeout(), timeout=provider_timeout)
        metrics.elapsed_seconds = time.monotonic() - start_time
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - start_time
        metrics.elapsed_seconds = elapsed
        metrics.timed_out = True
        metrics.errors.append(f"Provider timeout after {elapsed:.1f}s (limit: {provider_timeout}s)")
        if on_log:
            on_log(f"[{provider_key}] TIMEOUT: exceeded {provider_timeout}s limit after {elapsed:.1f}s")
        logger.warning("%s timed out after %.1fs (limit: %ds)", provider_key, elapsed, provider_timeout)
    finally:
        # Always kill the browser session
        await browser_session.kill()

    metrics.accounts_found = len(all_accounts)
    if on_log:
        on_log(f"[{provider_key}] {len(all_accounts)} account(s) across {len(logins)} login(s)")

    return ScrapeResult(accounts=all_accounts, metrics=metrics)
