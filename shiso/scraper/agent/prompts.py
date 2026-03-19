"""Backward-compatible prompt helpers built on provider playbooks."""

from __future__ import annotations

from .playbooks import load_provider_playbook


def get_extraction_prompt(provider_key: str, account_type: str | None = None) -> str:
    """Return the static extraction context for a provider playbook."""
    return load_provider_playbook(provider_key, account_type).extraction_context()
