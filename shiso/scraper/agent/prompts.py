"""Prompt template loader and helpers for scraper agents."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .playbooks import load_provider_playbook

_PROMPTS_DIR = Path(__file__).parent.parent / "config" / "prompts"

_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    keep_trailing_newline=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render(template_name: str, **kwargs: object) -> str:
    """Render a prompt template with the given variables."""
    return _env.get_template(template_name).render(**kwargs).strip()


def get_extraction_prompt(provider_key: str, account_type: str | None = None) -> str:
    """Return the static extraction context for a provider playbook."""
    return load_provider_playbook(provider_key, account_type).extraction_context()
