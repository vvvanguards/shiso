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

from .playbooks import load_provider_playbook

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


from dataclasses import asdict, dataclass, field


@dataclass
class ScrapeMetrics:
    """Structured metrics from a scraper run."""
    accounts_found: int = 0
    accounts_before_filter: int = 0
    account_filter: str | None = None
    steps_taken: int = 0
    failed_actions: int = 0
    errors: list[str] = field(default_factory=list)
    timed_out: bool = False
    timeout_seconds: float | None = None
    elapsed_seconds: float | None = None
    # Log-parsed supplemental fields (populated by extract_run_metrics)
    accounts_complete: int = 0
    crises_hit: int = 0
    logins_attempted: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScrapeMetrics:
        import dataclasses as _dc
        known = {f.name for f in _dc.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


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
    """Build the full Agent task with the workflow instructions last.

    Provider playbooks add useful context, but the workflow owns the pass-level
    contract. Keeping the workflow prompt last prevents stale provider notes
    from overriding pass-specific rules like "stay on the overview page".
    """
    preamble = _build_preamble(provider_key, provider_cfg, dashboard_url)

    parts = [preamble]
    if extraction_prompt:
        parts.append(extraction_prompt)
    parts.append(workflow.prompt_template)
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


def _normalize_name(name: str | None) -> str:
    """Lowercase, collapse whitespace, strip common suffixes for comparison."""
    if not name:
        return ""
    s = " ".join(name.strip().lower().split())
    for suffix in (" card", " account"):
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    return s


def _find_matching_key(collected: dict[str, dict], account: dict) -> str | None:
    """Find if account already exists under a different key."""
    mask = _normalize_mask(account.get("account_mask"))
    name = _normalize_name(account.get("card_name"))

    for key, existing in collected.items():
        if mask and _normalize_mask(existing.get("account_mask")) == mask:
            return key
        if name and not _is_generic_account_name(account.get("card_name")):
            if _normalize_name(existing.get("card_name")) == name:
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


def _get_login_failure_patterns(playbook: "ProviderPlaybook | None" = None) -> list[str]:
    """Build login failure patterns from defaults + playbook failed_actions."""
    patterns = list(_LOGIN_FAILURE_PATTERNS)
    if not playbook:
        return patterns
    for item in playbook.failed_actions:
        lower = item.lower()
        if lower.startswith("login_pattern:"):
            patterns.append(lower.split(":", 1)[1].strip())
    return patterns


async def _on_step(agent: Agent, on_log: Callable[[str], None] | None) -> None:
    """Called after each Agent step. Emits log lines for analyst."""
    step_num = agent.state.n_steps if hasattr(agent, "state") else 0

    actions = agent.history.action_names() if agent.history else []
    last_action = actions[-1] if actions else "unknown"
    last_action_ascii = last_action.encode("ascii", errors="replace").decode("ascii")

    if on_log:
        on_log(f"Step {step_num}: action={last_action_ascii}")

    errors = agent.history.errors() if agent.history else []
    if errors and errors[-1] and on_log:
        err_msg = str(errors[-1]).encode("ascii", errors="replace").decode("ascii")
        on_log(f"Step {step_num}: failed — {err_msg}")

    # Check agent memory for login failure — abort early instead of retrying
    if hasattr(agent, "state") and hasattr(agent.state, "memory"):
        memory = (agent.state.memory or "").lower()
        patterns = getattr(agent, "_login_patterns", _LOGIN_FAILURE_PATTERNS)
        for pattern in patterns:
            if pattern in memory:
                if on_log:
                    on_log(f"Step {step_num}: login failure detected — aborting")
                agent._login_failed = True  # checked after run() returns
                agent.stop()
                return


# ---------------------------------------------------------------------------
# Account detail enrichment — navigate to each account's detail page
# ---------------------------------------------------------------------------


async def _enrich_account_details(
    browser_session: BrowserSession,
    llm: ChatOllama | ChatOpenRouter,
    accounts: list[dict[str, Any]],
    provider_key: str,
    provider_cfg: dict,
    config: dict,
    dashboard_url: str | None = None,
    start_url: str | None = None,
    on_log: Callable[[str], None] | None = None,
    playbook: "ProviderPlaybook | None" = None,
) -> None:
    """Navigate to each account's detail page and extract promo APR and other details."""
    agent_cfg = config.get("agent", {})
    detail_max_steps = provider_cfg.get("detail_max_steps", agent_cfg.get("detail_max_steps", 15))
    institution = provider_cfg.get("institution", provider_key.replace("_", " ").title())
    tools = _build_tools(interactive=False)

    # Build initial navigation action to ensure we start on the dashboard.
    # Only use dashboard_url — start_url is the login page and would break
    # the authenticated session.
    _initial_actions = (
        [{"navigate": {"url": dashboard_url, "new_tab": False}}]
        if dashboard_url else None
    )

    # Parse skip_enrichment_for from playbook navigation_tips
    skip_types: set[str] = set()
    for tip in (playbook.navigation_tips if playbook else []):
        if tip.lower().startswith("skip_enrichment_for:"):
            skip_types.update(t.strip() for t in tip.split(":", 1)[1].split(","))

    for acct in accounts:
        card_name = acct.get("card_name", "unknown")
        mask = acct.get("account_mask", "")
        mask_hint = f" ending in {mask}" if mask else ""

        # Skip enrichment for account types the playbook says are unproductive
        acct_type = (acct.get("account_type") or "").lower().replace(" ", "_")
        if acct_type and acct_type in skip_types:
            if on_log:
                on_log(f"[{provider_key}] Skipping enrichment for {card_name} (type: {acct_type})")
            continue

        if on_log:
            on_log(f"[{provider_key}] Enriching details for {card_name}{mask_hint}...")

        # Build task for this single account
        task = f"""You are on the {institution} dashboard.
Navigate to the account "{card_name}"{mask_hint} and extract detailed information.

Steps:
1. Click on the account named "{card_name}" to open its details
2. Look for promotional APR information (intro APR, promo end date, regular APR after promo)
3. Find the credit limit or spending power
4. Find the current interest rate/APR
5. Return the extracted information

Look for fields like:
- "Intro APR", "Promotional APR", "0% intro", "0% APR for X months"
- "Go-to rate", "Standard APR", "Regular APR", "APR after promo"
- "Promo end date", "Rate valid until", "Offer expires"
- "Credit limit", "Spending power", "Credit line"
- "Interest rate", "APR", "Annual percentage rate"

Return a JSON object with these fields (use null if not found):
{{
  "intro_apr_rate": <float or null>,
  "intro_apr_end_date": "<YYYY-MM-DD or null>",
  "regular_apr": <float or null>,
  "promo_type": "<purchase|balance_transfer|general|null>",
  "credit_limit": <float or null>,
  "interest_rate": <float or null>
}}

IMPORTANT:
- Stay on the account detail/summary page only — do NOT open statements, PDFs, or external pages.
- Do NOT navigate to any URL outside the dashboard.
- After extracting, navigate back to the dashboard/account summary and call done."""

        agent = Agent(
            task=task,
            llm=llm,
            browser_session=browser_session,
            tools=tools,
            use_vision=True,
            max_steps=detail_max_steps,
            max_failures=agent_cfg.get("max_failures", 2),
            max_actions_per_step=3,
            initial_actions=_initial_actions,
            use_judge=False,
            extend_system_message=playbook.system_message() if playbook else "",
        )

        try:
            history = await agent.run(on_step_end=lambda a: _on_step(a, on_log))
            result_text = history.final_result()
            if result_text:
                import json
                try:
                    # Handle JSON wrapped in markdown code blocks
                    text = result_text.strip()
                    if text.startswith("```"):
                        text = text.split("```")[1]
                        if text.startswith("json"):
                            text = text[4:]
                        text = text.strip()
                    detail = json.loads(text)
                    # Merge extracted fields into account dict
                    for field in ("intro_apr_rate", "intro_apr_end_date", "regular_apr",
                                  "promo_type", "credit_limit", "interest_rate"):
                        if detail.get(field) is not None:
                            acct[field] = detail[field]
                    if on_log:
                        enriched = [f for f in detail if detail[f] is not None]
                        if enriched:
                            on_log(f"[{provider_key}] Enriched {card_name}: {', '.join(enriched)}")
                except (json.JSONDecodeError, TypeError):
                    pass  # Keep existing values if parse fails
        except Exception as exc:
            logger.warning("[%s] Detail enrichment failed for %s: %s", provider_key, card_name, exc)
            if on_log:
                on_log(f"[{provider_key}] Detail enrichment skipped for {card_name}: {exc}")


# ---------------------------------------------------------------------------
# Statement downloads — separate Agent task per eligible account
# ---------------------------------------------------------------------------


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
    interactive: bool = False,
) -> list[dict[str, Any]]:
    """Download the latest statement PDF for each eligible account, one at a time."""
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

    institution = provider_cfg.get("institution", provider_key.replace("_", " ").title())
    downloaded: list[dict[str, Any]] = []
    tools = _build_tools(interactive=interactive)

    # Build initial navigation action to ensure we start on the dashboard.
    # Only use dashboard_url — start_url is the login page and would break
    # the authenticated session.
    _initial_actions = (
        [{"navigate": {"url": dashboard_url, "new_tab": False}}]
        if dashboard_url else None
    )

    for acct in eligible:
        card_name = acct.get("card_name", "unknown")
        mask = acct.get("account_mask", "")
        mask_hint = f" ending in {mask}" if mask else ""

        if on_log:
            on_log(f"[{provider_key}]Downloading statement for {card_name}{mask_hint}...")

        # Snapshot existing PDFs before this account's download
        before_pdfs = set(download_dir.glob("*.pdf"))

        # Build task for this single account
        task = f"""You are on the {institution} dashboard.
Open the most recent BILLING STATEMENT for this account: {card_name}{mask_hint}

Steps:
1. Click on the account named "{card_name}" to open it
2. Find "Statements & Activity" or "Statements" link/tab and click it
3. Find the most recent monthly billing statement (has a date like "Feb 26, 2026")
4. Click to view/open the statement — it may open in browser or download
5. If it opens in browser: navigate through pages to find billing details
6. If it downloads instead: note that the file was downloaded

When viewing the statement, extract these fields (use null if not found):
- due_date: Payment due date (YYYY-MM-DD)
- minimum_payment: Minimum payment due
- statement_balance: New balance / statement balance
- credit_limit: Credit line / spending limit
- intro_apr_rate: Promotional/intro APR rate (e.g. 0.0 for 0%)
- intro_apr_end_date: When intro APR ends (YYYY-MM-DD)
- regular_apr: Standard APR after promo ends
- statement_date: Statement closing date (YYYY-MM-DD)

Look for sections like:
- "Interest Charge Calculation", "Rate Information", "APR Summary"
- Payment summary showing due date, minimum payment, balance

Return a JSON object with all found fields:
{{
  "due_date": "<YYYY-MM-DD or null>",
  "minimum_payment": <float or null>,
  "statement_balance": <float or null>,
  "credit_limit": <float or null>,
  "intro_apr_rate": <float or null>,
  "intro_apr_end_date": "<YYYY-MM-DD or null>",
  "regular_apr": <float or null>,
  "statement_date": "<YYYY-MM-DD or null>",
  "file_downloaded": <true if file saved to disk, false if viewed in browser>
}}

IMPORTANT:
- Open ONE statement — the MOST RECENT billing statement only
- Skip "Important Notices" or "Account Agreement Changes" — not statements
- When done extracting, call done_action"""

        agent = Agent(
            task=task,
            llm=llm,
            browser_session=browser_session,
            tools=tools,
            use_vision=True,
            max_steps=provider_cfg.get("statement_max_steps", stmt_cfg.get("max_steps", 30)),
            max_failures=agent_cfg.get("max_failures", 3),
            max_actions_per_step=1,
            initial_actions=_initial_actions,
            use_judge=False,
        )

        agent_result = None
        try:
            history = await agent.run(on_step_end=lambda a: _on_step(a, on_log))
            result_text = history.final_result()
            if result_text:
                try:
                    agent_result = json.loads(result_text)
                    if on_log:
                        fields = [k for k, v in agent_result.items() if v is not None]
                        on_log(f"[{provider_key}] Agent extracted from statement: {', '.join(fields)}")
                except json.JSONDecodeError:
                    pass
        except Exception as exc:
            logger.warning("[%s] Statement extraction failed for %s: %s", provider_key, card_name, exc)
            if on_log:
                on_log(f"[{provider_key}] Failed to extract from statement for {card_name}: {exc}")
            continue

        # Check for downloaded PDFs (fallback)
        after_pdfs = set(download_dir.glob("*.pdf"))
        new_pdfs = after_pdfs - before_pdfs

        file_path = None
        for pdf_path in new_pdfs:
            size = pdf_path.stat().st_size

            # Rename immediately with account info
            product_slug = re.sub(r"[^\w]+", "_", card_name).strip("_").lower()[:30]
            parts = [product_slug]
            if mask:
                parts.append(mask)
            parts.append(pdf_path.stem)
            new_name = "_".join(parts) + ".pdf"
            new_path = download_dir / new_name

            if new_path != pdf_path and not new_path.exists():
                try:
                    pdf_path.rename(new_path)
                    pdf_path = new_path
                except Exception:
                    pass  # Keep original name if rename fails

            file_path = str(pdf_path)
            if on_log:
                on_log(f"[{provider_key}] Downloaded: {pdf_path.name} ({size:,} bytes)")

        downloaded.append({
            "card_name": card_name,
            "account_mask": mask,
            "file_path": file_path,
            "extracted_data": agent_result,
        })

    if on_log:
        on_log(f"[{provider_key}] {len(downloaded)} statement(s) downloaded")

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


def _learn_dashboard_url(
    provider_key: str,
    history: Any,
    start_url: str,
    on_log: Callable[[str], None] | None = None,
) -> str | None:
    """Learn the dashboard URL from a successful Pass 1 agent run.

    After the agent logs in and discovers accounts, the URL it landed on is the
    authenticated dashboard.  We extract it from the agent history and persist
    it to scraper.toml so enrichment / statement agents can navigate back.

    Returns the learned dashboard URL, or None.
    """
    try:
        urls = history.urls() if history else []
    except Exception:
        return None

    if not urls:
        return None

    # Walk backwards through history URLs to find the last authenticated page.
    # Skip blank/None entries and the start_url (login page).
    start_host = urlparse(start_url).hostname if start_url else None
    login_keywords = {"login", "signin", "sign-in", "sign_in", "auth/login", "signon"}

    candidate: str | None = None
    for url in reversed(urls):
        if not url:
            continue
        parsed = urlparse(url)
        path_lower = (parsed.path or "").lower()
        # Skip login pages
        if any(kw in path_lower for kw in login_keywords):
            continue
        # Skip about:blank, chrome:// etc.
        if parsed.scheme not in ("http", "https"):
            continue
        # Skip PDF viewer URLs or document retrieval URLs
        if "/documents/" in path_lower or path_lower.endswith(".pdf"):
            continue
        candidate = url
        break

    if not candidate:
        return None

    # Strip query params and fragments to get a clean, stable URL
    parsed = urlparse(candidate)
    clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    # Some dashboards need specific query params (e.g. ?p1=yes) — keep them
    # if the path alone looks like a generic route
    if parsed.query:
        clean_url = f"{clean_url}?{parsed.query}"
    # Strip trailing fragment
    clean_url = clean_url.split("#")[0]

    # Persist to scraper.toml
    from .analyst import ConfigPatch, _apply_config_patches
    _apply_config_patches(provider_key, ConfigPatch(dashboard_url=clean_url))

    if on_log:
        on_log(f"[{provider_key}] Learned dashboard URL: {clean_url}")

    return clean_url


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
    account_filter: str | None = None,
    on_log: Callable[[str], None] | None = None,
    workflow: Workflow | None = None,
) -> ScrapeResult:
    """Scrape one provider using browser-use Agent.

    Pass 1: discover accounts from overview page.
    Pass 1.5: enrich account details (promo APR, credit limit).
    Pass 2 (if download_statements): download statement PDFs and extract billing fields.

    If account_filter is provided, only process matching accounts (by card_name or account_mask).
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
        nonlocal all_accounts
        # Track URLs across logins so enrichment/statement passes can navigate back.
        start_url: str = ""
        dashboard_url: str | None = str(provider_cfg.get("dashboard_url") or "").strip() or None

        for login_idx, login in enumerate(logins):
            login_id = login.get("id")
            label = login.get("label", provider_key)
            username = login.get("username", "")
            password = login.get("password", "")

            if not username:
                if on_log:
                    on_log(f"[{provider_key}] Skipping {label}: no username")
                continue

            # Clear cookies between logins so the site sees a fresh session
            if login_idx > 0:
                try:
                    await browser_session.clear_cookies()
                    if on_log:
                        on_log(f"[{provider_key}] Cleared cookies for fresh login")
                except Exception as exc:
                    logger.warning("Failed to clear cookies for %s: %s", provider_key, exc)

            start_url = provider_cfg.get("start_url", login.get("login_url", ""))
            # Preserve a previously learned dashboard_url; only override from
            # config if we don't have one yet.
            if not dashboard_url:
                dashboard_url = str(provider_cfg.get("dashboard_url") or "").strip() or None
            account_type = login.get("account_type")
            playbook = load_provider_playbook(provider_key, account_type)

            if on_log:
                on_log(f"[{provider_key}] Scraping as {label}...")

            # Resolve workflow — default to financial_scraper
            from ..tools.workflows import get_workflow as _get_wf, FINANCIAL_WORKFLOW
            active_wf = workflow or _get_wf("financial_scraper") or FINANCIAL_WORKFLOW
            output_schema = active_wf.output_schema
            task = _build_task(
                provider_key,
                provider_cfg,
                dashboard_url,
                active_wf,
                playbook.extraction_context(),
            )

            tools = _build_tools(interactive=interactive)

            agent = Agent(
                task=task,
                llm=llm,
                browser_session=browser_session,
                tools=tools,
                use_vision=True,
                max_steps=provider_cfg.get("max_steps", agent_cfg.get("max_steps", 50)),
                max_failures=agent_cfg.get("max_failures", 3),
                max_actions_per_step=agent_cfg.get("max_actions_per_step", 3),
                extend_system_message=playbook.system_message(),
                output_model_schema=output_schema,
                sensitive_data={"x_username": username, "x_password": password},
                directly_open_url=start_url,
            )

            agent._login_patterns = _get_login_failure_patterns(playbook)

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

                    # Learn dashboard URL from the agent's navigation history
                    # so enrichment / statement agents can navigate back reliably.
                    if not dashboard_url:
                        learned = _learn_dashboard_url(
                            provider_key, history, start_url, on_log=on_log,
                        )
                        if learned:
                            dashboard_url = learned

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

# --- Deduplicate accounts across all logins ---
        if len(all_accounts) > 1:
            deduped: dict[str, dict] = {}
            for acct in all_accounts:
                key = _account_key(acct)
                match_key = _find_matching_key(deduped, acct)
                if match_key:
                    deduped[match_key] = _merge_account(deduped[match_key], acct)
                elif key in deduped:
                    deduped[key] = _merge_account(deduped[key], acct)
                else:
                    deduped[key] = acct
            if len(deduped) < len(all_accounts):
                if on_log:
                    on_log(f"[{provider_key}] Deduplicated {len(all_accounts)} accounts to {len(deduped)}")
                all_accounts[:] = list(deduped.values())

        # --- Apply account filter if specified ---
        metrics.accounts_before_filter = len(all_accounts)
        metrics.account_filter = account_filter
        if account_filter and all_accounts:
            filter_lower = account_filter.lower()
            filtered = []
            for acct in all_accounts:
                card_name = (acct.get("card_name") or "").lower()
                mask = (acct.get("account_mask") or "").lower()
                if filter_lower in card_name or filter_lower == mask:
                    filtered.append(acct)
            if filtered:
                if on_log:
                    on_log(f"[{provider_key}] Filtered to {len(filtered)} account(s) matching '{account_filter}'")
                all_accounts[:] = filtered
            else:
                if on_log:
                    on_log(f"[{provider_key}] No accounts match filter '{account_filter}', returning empty result")
                all_accounts.clear()

        # --- Pass 1.5: enrich account details (promo APR, credit limit) ---
        if all_accounts:
            enrich_details = provider_cfg.get("enrich_details", agent_cfg.get("enrich_details", True))
            if enrich_details:
                if on_log:
                    on_log(f"[{provider_key}] Enriching account details...")
                await _enrich_account_details(
                    browser_session=browser_session,
                    llm=llm,
                    accounts=all_accounts,
                    provider_key=provider_key,
                    provider_cfg=provider_cfg,
                    config=config,
                    dashboard_url=dashboard_url,
                    start_url=start_url,
                    on_log=on_log,
                    playbook=playbook,
                )

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
                dashboard_url=dashboard_url,
                start_url=start_url,
                on_log=on_log,
                interactive=interactive,
            )

            # Process statement results: use agent-extracted data; fall back to PDF parsing only if needed
            for dl in statement_results:
                stmt_data = dl.get("extracted_data")
                file_path = dl.get("file_path")

                # Skip if we don't have data from anywhere
                if not stmt_data and not file_path:
                    continue

                if not stmt_data and file_path:
                    # No agent extraction, parse downloaded PDF
                    from .pdf_utils import extract_statement_data
                    from .llm import llm_chat
                    stmt_data = await extract_statement_data(file_path, llm_chat)
                    if on_log:
                        card_name = dl.get("card_name", "unknown")
                        on_log(f"[{provider_key}] PDF parsed for {card_name}")

                if not stmt_data:
                    continue

                # Find the matching account
                card_name = dl.get("card_name", "")
                mask = dl.get("account_mask", "")
                matched_acct = None
                for acct in all_accounts:
                    if mask and acct.get("account_mask") == mask:
                        matched_acct = acct
                        break
                if not matched_acct and card_name:
                    for acct in all_accounts:
                        if acct.get("card_name") == card_name:
                            matched_acct = acct
                            break

                if matched_acct:
                    # Enrich the scraped account dict with extracted fields
                    for field in ("due_date", "minimum_payment", "statement_balance",
                                  "last_payment_amount", "last_payment_date",
                                  "credit_limit"):
                        val = stmt_data.get(field)
                        if val is not None:
                            matched_acct[field] = val
                    for field in ("intro_apr_rate", "intro_apr_end_date", "regular_apr"):
                        val = stmt_data.get(field)
                        if val is not None:
                            matched_acct[field] = val

                    # Persist to AccountStatement table
                    if accounts_db:
                        dl["statement_data"] = stmt_data
                        _persist_statement(
                            accounts_db, provider_key, matched_acct, dl, stmt_data, on_log,
                        )

                    if on_log:
                        filled = [k for k, v in stmt_data.items() if v is not None]
                        on_log(f"[{provider_key}] Statement enriched {card_name}: {', '.join(filled)}")
                elif on_log:
                    on_log(f"[{provider_key}] Statement for {card_name} — no matching account found")

            if on_log:
                on_log(f"[{provider_key}] Processed {len(statement_results)} statement(s)")

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
