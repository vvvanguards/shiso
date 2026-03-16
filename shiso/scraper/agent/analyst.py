"""Post-run log analyst — extracts per-provider lessons and persists them as hints."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]
import tomli_w

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent.parent / "config"
HINTS_PATH = CONFIG_DIR / "provider_hints.json"
CONFIG_PATH = CONFIG_DIR / "scraper.toml"
_PROMPT_PATH = CONFIG_DIR / "prompts" / "analyst.md"

def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8").strip()


def load_provider_hints(provider_key: str) -> dict[str, Any]:
    """Load hints for a specific provider. Returns empty dict if none exist."""
    if not HINTS_PATH.exists():
        return {}
    try:
        all_hints = json.loads(HINTS_PATH.read_text(encoding="utf-8"))
        return all_hints.get(provider_key, {})
    except (json.JSONDecodeError, OSError):
        return {}


def _save_hints(all_hints: dict[str, Any]) -> None:
    HINTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    HINTS_PATH.write_text(json.dumps(all_hints, indent=2), encoding="utf-8")


def _load_provider_config(provider_key: str) -> dict[str, Any]:
    """Load the [providers.<key>] section from scraper.toml."""
    if not CONFIG_PATH.exists():
        return {}
    try:
        config = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return config.get("providers", {}).get(provider_key, {})
    except Exception:
        return {}


def _apply_config_patches(provider_key: str, patches: dict[str, Any]) -> None:
    """Merge config patches into [providers.<key>] in scraper.toml."""
    if not patches or not CONFIG_PATH.exists():
        return
    # Allowlist of keys the analyst may change
    allowed_keys = {"dashboard_url", "start_url"}
    patches = {k: v for k, v in patches.items() if k in allowed_keys and v}
    if not patches:
        return

    config = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    providers = config.setdefault("providers", {})
    provider_cfg = providers.setdefault(provider_key, {})

    changed = []
    for key, value in patches.items():
        old = provider_cfg.get(key)
        if old != value:
            provider_cfg[key] = value
            changed.append(f"{key}: {old!r} → {value!r}")

    if changed:
        CONFIG_PATH.write_bytes(tomli_w.dumps(config).encode("utf-8"))
        for c in changed:
            logger.info("Analyst patched config for %s: %s", provider_key, c)


def extract_run_metrics(log_lines: list[str]) -> dict[str, Any]:
    """Extract quantitative metrics from a completed run's log lines."""
    text = "\n".join(log_lines)
    lines = log_lines

    # Count steps (highest step number seen)
    step_numbers = [int(m.group(1)) for m in re.finditer(r"Step (\d+):", text)]
    steps_taken = max(step_numbers) if step_numbers else 0

    # Count accounts found
    acct_match = re.search(r"Got (\d+) account\(s\)", text)
    accounts_found = int(acct_match.group(1)) if acct_match else 0

    # Count crises
    crises = sum(1 for l in lines if "[CRISIS]" in l and "Handling anomaly" in l)

    # Count failed actions
    failed = sum(1 for l in lines if "could not find" in l or "failed" in l.lower())

    # Count logins (successful re-logins)
    logins = sum(1 for l in lines if "Login complete" in l or "Clicked submit" in l)

    # Accounts with due dates (from merge lines or final count)
    complete_matches = re.findall(r"HAS billing details|OK \(\$0", text)
    accounts_complete = len(complete_matches)

    return {
        "steps_taken": steps_taken,
        "accounts_found": accounts_found,
        "accounts_complete": accounts_complete,
        "crises_hit": crises,
        "failed_actions": failed,
        "logins_attempted": logins,
    }


async def analyze_run(
    provider_key: str,
    log_lines: list[str],
    llm_chat_fn: Callable,
    previous_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyze run logs and persist lessons as provider hints.

    Args:
        provider_key: The provider that was scraped.
        log_lines: All log lines from the run.
        llm_chat_fn: Async function(messages) -> dict | None.
        previous_metrics: Metrics from the last run for comparison.

    Returns:
        The new hints extracted (empty dict on failure).
    """
    if not log_lines:
        return {}

    # Only analyze if there were issues (failures, crises, or max steps hit)
    log_text = "\n".join(log_lines)
    has_issues = any(
        indicator in log_text
        for indicator in [
            "could not find",
            "CRISIS",
            "failed",
            "ERROR",
            "no progress",
            "LOOP DETECTED",
            "stopping",
        ]
    )
    if not has_issues:
        logger.info("No issues detected in %s run, skipping analysis", provider_key)
        return {}

    existing_hints = load_provider_hints(provider_key)
    existing_hints_text = json.dumps(existing_hints, indent=2) if existing_hints else "None — this is the first analysis for this provider."

    provider_config = _load_provider_config(provider_key)
    provider_config_text = json.dumps(provider_config, indent=2) if provider_config else "No provider config found."

    prompt_template = _load_prompt()
    prompt = (
        prompt_template
        .replace("{provider_key}", provider_key)
        .replace("{logs}", log_text)
        .replace("{existing_hints}", existing_hints_text)
        .replace("{provider_config}", provider_config_text)
    )

    # Include previous run comparison if available
    if previous_metrics:
        current_metrics = extract_run_metrics(log_lines)
        comparison = (
            f"\n\nPREVIOUS RUN METRICS: {json.dumps(previous_metrics)}"
            f"\nCURRENT RUN METRICS: {json.dumps(current_metrics)}"
            f"\nCompare these to assess whether existing hints are helping. "
            f"If the same failures repeat, rewrite the relevant hint more forcefully. "
            f"If metrics improved, note what worked."
        )
        prompt += comparison

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "Analyze these logs and return the JSON lessons."},
    ]

    logger.info("Running post-run analyst for %s (%d log lines)", provider_key, len(log_lines))

    result = await llm_chat_fn(messages)
    if not result:
        logger.warning("Analyst returned no result for %s", provider_key)
        return {}

    # Validate structure
    for key in ("failed_actions", "effective_patterns", "navigation_tips"):
        if key not in result:
            result[key] = []
        if not isinstance(result[key], list):
            result[key] = []

    # Apply config patches if the analyst suggested any
    config_patches = result.pop("config_patches", None)
    if isinstance(config_patches, dict) and config_patches:
        _apply_config_patches(provider_key, config_patches)

    # Replace hints for this provider (analyst returns the complete curated set)
    try:
        all_hints = json.loads(HINTS_PATH.read_text(encoding="utf-8")) if HINTS_PATH.exists() else {}
    except (json.JSONDecodeError, OSError):
        all_hints = {}

    result["updated_at"] = datetime.utcnow().isoformat()
    all_hints[provider_key] = result
    _save_hints(all_hints)

    logger.info(
        "Analyst saved hints for %s: %d failed, %d effective, %d tips",
        provider_key,
        len(result.get("failed_actions", [])),
        len(result.get("effective_patterns", [])),
        len(result.get("navigation_tips", [])),
    )
    return result
