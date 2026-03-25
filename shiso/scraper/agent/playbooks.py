"""Provider playbooks unify static prompts and learned hints.

The scraper previously pulled provider knowledge from multiple places:
- static extraction markdown files
- learned hints in provider_hints.json

This module provides a single abstraction over both sources so the rest of the
runtime can treat provider guidance as one playbook, regardless of storage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.exc import OperationalError

from ..database import SessionLocal
from ..models.tools import ProviderPlaybookRecord

CONFIG_DIR = Path(__file__).parent.parent / "config"
HINTS_PATH = CONFIG_DIR / "provider_hints.json"
EXTRACTION_DIR = CONFIG_DIR / "prompts" / "extraction"

_PLAYBOOK_HINT_KEYS = ("failed_actions", "effective_patterns", "navigation_tips")


@dataclass(slots=True)
class ProviderPlaybook:
    """Provider-specific guidance used by the browser agent and analyst."""

    provider_key: str
    extraction_prompt: str = ""
    failed_actions: list[str] = field(default_factory=list)
    effective_patterns: list[str] = field(default_factory=list)
    navigation_tips: list[str] = field(default_factory=list)
    updated_at: str | None = None

    def learned_hints(self) -> dict[str, Any]:
        """Return the persisted, analyst-managed portion of the playbook."""
        data = {
            key: list(getattr(self, key))
            for key in _PLAYBOOK_HINT_KEYS
            if getattr(self, key)
        }
        if self.updated_at:
            data["updated_at"] = self.updated_at
        return data

    def extraction_context(self) -> str:
        """Static task addendum appended to the workflow prompt."""
        return self.extraction_prompt.strip()

    def system_message(self) -> str:
        """Learned provider context appended to the agent system prompt."""
        sections: list[str] = []
        labels = {
            "navigation_tips": "Navigation Tips",
            "effective_patterns": "Effective Patterns",
            "failed_actions": "Avoid These Actions",
        }

        for key in ("navigation_tips", "effective_patterns", "failed_actions"):
            items = getattr(self, key)
            if not items:
                continue
            sections.append(f"## {labels[key]}")
            sections.extend(f"- {item}" for item in items)
            sections.append("")

        return "\n".join(sections).strip()


def _load_all_hints() -> dict[str, Any]:
    if not HINTS_PATH.exists():
        return {}
    try:
        return json.loads(HINTS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_all_hints(all_hints: dict[str, Any]) -> None:
    HINTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    HINTS_PATH.write_text(json.dumps(all_hints, indent=2), encoding="utf-8")


def load_provider_playbook(provider_key: str, account_type: str | None = None) -> ProviderPlaybook:
    """Load a provider playbook from the current storage layout.

    `account_type` is reserved for future playbook variants and kept for API
    compatibility with older extraction prompt loaders.
    """
    del account_type  # Future: allow playbooks to branch by account type.

    db_playbook = _load_db_playbook(provider_key)
    if db_playbook is not None:
        return db_playbook

    file_playbook = _load_file_playbook(provider_key)
    if file_playbook.extraction_prompt or file_playbook.learned_hints():
        _save_db_playbook(file_playbook)
    return file_playbook


def save_provider_playbook_hints(
    provider_key: str,
    hints: dict[str, Any],
    *,
    extraction_prompt: str | None = None,
) -> ProviderPlaybook:
    """Persist the mutable portion of a provider playbook."""
    playbook = load_provider_playbook(provider_key)
    if extraction_prompt is not None:
        playbook.extraction_prompt = str(extraction_prompt).strip()
    for key in _PLAYBOOK_HINT_KEYS:
        setattr(playbook, key, _coerce_hint_list(hints.get(key)))
    playbook.updated_at = datetime.now(UTC).isoformat()
    if not _save_db_playbook(playbook):
        all_hints = _load_all_hints()
        all_hints[provider_key] = playbook.learned_hints()
        _save_all_hints(all_hints)
    return playbook


def _load_file_playbook(provider_key: str) -> ProviderPlaybook:
    extraction_path = EXTRACTION_DIR / f"{provider_key}.md"
    extraction_prompt = (
        extraction_path.read_text(encoding="utf-8").strip()
        if extraction_path.exists()
        else ""
    )
    raw_hints = _load_all_hints().get(provider_key, {})
    return ProviderPlaybook(
        provider_key=provider_key,
        extraction_prompt=extraction_prompt,
        failed_actions=_coerce_hint_list(raw_hints.get("failed_actions")),
        effective_patterns=_coerce_hint_list(raw_hints.get("effective_patterns")),
        navigation_tips=_coerce_hint_list(raw_hints.get("navigation_tips")),
        updated_at=_coerce_updated_at(raw_hints.get("updated_at")),
    )


def _load_db_playbook(provider_key: str) -> ProviderPlaybook | None:
    try:
        with SessionLocal() as session:
            row = (
                session.query(ProviderPlaybookRecord)
                .filter(ProviderPlaybookRecord.provider_key == provider_key)
                .first()
            )
            if not row:
                return None
            return _playbook_from_record(row)
    except (OperationalError, AttributeError):
        return None


def _save_db_playbook(playbook: ProviderPlaybook) -> bool:
    try:
        with SessionLocal() as session:
            row = (
                session.query(ProviderPlaybookRecord)
                .filter(ProviderPlaybookRecord.provider_key == playbook.provider_key)
                .first()
            )
            if not row:
                row = ProviderPlaybookRecord(provider_key=playbook.provider_key)
                session.add(row)

            row.extraction_prompt = playbook.extraction_context()
            row.failed_actions = list(playbook.failed_actions)
            row.effective_patterns = list(playbook.effective_patterns)
            row.navigation_tips = list(playbook.navigation_tips)
            session.commit()
            session.refresh(row)
            playbook.updated_at = row.updated_at.isoformat() if row.updated_at else playbook.updated_at
            return True
    except (OperationalError, AttributeError):
        return False


def _playbook_from_record(row: ProviderPlaybookRecord) -> ProviderPlaybook:
    return ProviderPlaybook(
        provider_key=row.provider_key,
        extraction_prompt=row.extraction_prompt or "",
        failed_actions=_coerce_hint_list(row.failed_actions),
        effective_patterns=_coerce_hint_list(row.effective_patterns),
        navigation_tips=_coerce_hint_list(row.navigation_tips),
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )


def _coerce_hint_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _coerce_updated_at(value: Any) -> str | None:
    if not value:
        return None
    return str(value)
