"""Prompt loader — reads provider-specific extraction hints from config/prompts/extraction/*.md."""

from __future__ import annotations

from pathlib import Path

_EXTRACTION_DIR = Path(__file__).parent.parent / "config" / "prompts" / "extraction"

# Provider-specific extraction prompts keyed by provider slug
EXTRACTION_PROMPTS: dict[str, str] = {}
for _path in _EXTRACTION_DIR.glob("*.md"):
    EXTRACTION_PROMPTS[_path.stem] = _path.read_text(encoding="utf-8").strip()


def get_extraction_prompt(provider_key: str, account_type: str | None = None) -> str:
    """Return provider-specific extraction hints, or empty string for unknown providers."""
    return EXTRACTION_PROMPTS.get(provider_key, "")
