"""Post-run log analyst — extracts per-provider lessons and updates playbooks."""

from __future__ import annotations

import dataclasses
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]
import tomli_w

from .playbooks import load_provider_playbook, save_provider_playbook_hints
from .scraper import ScrapeMetrics

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent.parent / "config"
CONFIG_PATH = CONFIG_DIR / "scraper.toml"
_PROMPT_PATH = CONFIG_DIR / "prompts" / "analyst.md"

_CONFIG_PATCH_INT_RANGES: dict[str, tuple[int, int]] = {
    "max_steps": (10, 120),
    "detail_max_steps": (5, 30),
    "statement_max_steps": (10, 50),
    "provider_timeout": (300, 3600),
}


@dataclass(slots=True)
class ConfigPatch:
    """Validated config overrides the analyst may apply to a provider."""
    dashboard_url: str | None = None
    start_url: str | None = None
    max_steps: int | None = None
    detail_max_steps: int | None = None
    statement_max_steps: int | None = None
    provider_timeout: int | None = None
    enrich_details: bool | None = None

    def __post_init__(self) -> None:
        for attr, (lo, hi) in _CONFIG_PATCH_INT_RANGES.items():
            val = getattr(self, attr)
            if val is None:
                continue
            try:
                setattr(self, attr, max(lo, min(hi, int(val))))
            except (TypeError, ValueError):
                setattr(self, attr, None)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ConfigPatch:
        known = {f.name for f in dataclasses.fields(cls)}
        filtered: dict[str, Any] = {}
        for k, v in raw.items():
            if k not in known or v is None:
                continue
            if k == "enrich_details":
                if isinstance(v, bool):
                    filtered[k] = v
                elif isinstance(v, str):
                    filtered[k] = v.lower() in ("true", "1", "yes")
            else:
                filtered[k] = v
        return cls(**filtered)

    def to_dict(self) -> dict[str, Any]:
        """Return only non-None fields for merging into config."""
        return {k: v for k, v in dataclasses.asdict(self).items() if v is not None}


@dataclass(slots=True)
class AnalystResult:
    """Parsed and validated output from the analyst LLM."""
    failed_actions: list[str] = field(default_factory=list)
    effective_patterns: list[str] = field(default_factory=list)
    navigation_tips: list[str] = field(default_factory=list)
    extraction_prompt: str | None = None
    config_patches: ConfigPatch | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AnalystResult:
        def _coerce_list(val: Any) -> list[str]:
            if not isinstance(val, list):
                return []
            return [str(x).strip() for x in val if str(x).strip()]

        patches_raw = raw.get("config_patches")
        config_patches = ConfigPatch.from_dict(patches_raw) if isinstance(patches_raw, dict) and patches_raw else None

        extraction_prompt = raw.get("extraction_prompt")
        if extraction_prompt is not None and not isinstance(extraction_prompt, str):
            extraction_prompt = None

        return cls(
            failed_actions=_coerce_list(raw.get("failed_actions")),
            effective_patterns=_coerce_list(raw.get("effective_patterns")),
            navigation_tips=_coerce_list(raw.get("navigation_tips")),
            extraction_prompt=extraction_prompt,
            config_patches=config_patches,
        )

    def hints_dict(self) -> dict[str, list[str]]:
        return {
            "failed_actions": self.failed_actions,
            "effective_patterns": self.effective_patterns,
            "navigation_tips": self.navigation_tips,
        }


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8").strip()


def load_provider_hints(provider_key: str) -> dict[str, Any]:
    """Backward-compatible learned-hints accessor."""
    return load_provider_playbook(provider_key).learned_hints()


def _load_provider_config(provider_key: str) -> dict[str, Any]:
    """Load the [providers.<key>] section from scraper.toml."""
    if not CONFIG_PATH.exists():
        return {}
    try:
        config = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return config.get("providers", {}).get(provider_key, {})
    except Exception:
        return {}


def _apply_config_patches(provider_key: str, patch: ConfigPatch) -> None:
    """Merge validated config patches into [providers.<key>] in scraper.toml."""
    if not CONFIG_PATH.exists():
        return
    patches = patch.to_dict()
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


def extract_run_metrics(log_lines: list[str]) -> ScrapeMetrics:
    """Extract quantitative metrics from a completed run's log lines."""
    text = "\n".join(log_lines)

    step_numbers = [int(m.group(1)) for m in re.finditer(r"Step (\d+):", text)]
    acct_match = re.search(r"Got (\d+) (?:account|item)\(s\)", text)
    complete_matches = re.findall(r"HAS billing details|OK \(\$0", text)

    return ScrapeMetrics(
        steps_taken=max(step_numbers) if step_numbers else 0,
        accounts_found=int(acct_match.group(1)) if acct_match else 0,
        accounts_complete=len(complete_matches),
        crises_hit=sum(1 for line in log_lines if "[CRISIS]" in line and "Handling anomaly" in line),
        failed_actions=sum(1 for line in log_lines if "could not find" in line or "failed" in line.lower()),
        logins_attempted=sum(1 for line in log_lines if "Login complete" in line or "Clicked submit" in line),
    )


def _has_keyword_issues(log_lines: list[str]) -> bool:
    """Check log lines for issue-indicating keywords (legacy heuristic)."""
    log_text = "\n".join(log_lines)
    return any(
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


def _should_analyze(metrics: ScrapeMetrics | None, log_lines: list[str]) -> bool:
    """Decide whether post-run analysis is warranted."""
    if not metrics:
        return _has_keyword_issues(log_lines)

    if metrics.accounts_found == 0:
        return True
    if metrics.failed_actions >= 3:
        return True
    if metrics.timed_out:
        return True
    if metrics.accounts_found > 0 and metrics.failed_actions == 0:
        return False
    return _has_keyword_issues(log_lines)


async def analyze_run(
    provider_key: str,
    log_lines: list[str],
    llm_chat_fn: Callable,
    previous_metrics: ScrapeMetrics | None = None,
    metrics: ScrapeMetrics | None = None,
) -> dict[str, Any]:
    """Analyze run logs and persist lessons as provider hints.

    Args:
        provider_key: The provider that was scraped.
        log_lines: All log lines from the run.
        llm_chat_fn: Async function(messages) -> dict | None.
        previous_metrics: Metrics from the last run for comparison.
        metrics: Structured metrics from the current run for triage.

    Returns:
        The new hints extracted (empty dict on failure).
    """
    if not log_lines:
        return {}

    if not _should_analyze(metrics, log_lines):
        logger.info("No issues detected in %s run, skipping analysis", provider_key)
        return {}

    log_text = "\n".join(log_lines)

    playbook = load_provider_playbook(provider_key)
    existing_hints = playbook.learned_hints()
    existing_hints_text = json.dumps(existing_hints, indent=2) if existing_hints else "None — this is the first analysis for this provider."
    existing_extraction_prompt = playbook.extraction_context() or "None — there is no provider-specific extraction prompt yet."

    provider_config = _load_provider_config(provider_key)
    provider_config_text = json.dumps(provider_config, indent=2) if provider_config else "No provider config found."

    prompt_template = _load_prompt()
    prompt = (
        prompt_template
        .replace("{provider_key}", provider_key)
        .replace("{logs}", log_text)
        .replace("{existing_hints}", existing_hints_text)
        .replace("{existing_extraction_prompt}", existing_extraction_prompt)
        .replace("{provider_config}", provider_config_text)
    )

    if previous_metrics:
        current_metrics = extract_run_metrics(log_lines)
        comparison = (
            f"\n\nPREVIOUS RUN METRICS: {json.dumps(previous_metrics.to_dict())}"
            f"\nCURRENT RUN METRICS: {json.dumps(current_metrics.to_dict())}"
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

    raw = await llm_chat_fn(messages)
    if not raw:
        logger.warning("Analyst returned no result for %s", provider_key)
        return {}

    result = AnalystResult.from_dict(raw)

    if result.config_patches:
        _apply_config_patches(provider_key, result.config_patches)

    playbook = save_provider_playbook_hints(
        provider_key,
        result.hints_dict(),
        extraction_prompt=result.extraction_prompt,
    )
    hints = playbook.learned_hints()

    logger.info(
        "Analyst saved hints for %s: %d failed, %d effective, %d tips",
        provider_key,
        len(hints.get("failed_actions", [])),
        len(hints.get("effective_patterns", [])),
        len(hints.get("navigation_tips", [])),
    )
    return hints
