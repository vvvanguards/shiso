"""Shared LLM utilities for analyst, pdf_utils, and other non-Agent callers.

Provides a lightweight httpx-based chat function that reads config from
scraper.toml — used by modules that need raw LLM calls without browser-use.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx

try:
    import tomllib
except ImportError:
    import tomli as tomllib

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "scraper.toml"


def load_config() -> dict:
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def get_llm_endpoint(config: dict) -> tuple[str, str, str, float]:
    """Return (base_url, api_key, model, timeout) for the active LLM preset."""
    preset = os.environ.get("ANALYST_LLM", "local")
    llm_cfg = config["llm"][preset]

    base_url = llm_cfg["base_url"]
    model = llm_cfg["model"]
    timeout = float(llm_cfg.get("timeout", 120))

    api_key_env = llm_cfg.get("api_key_env", "")
    api_key = os.environ.get(api_key_env, "") if api_key_env else llm_cfg.get("api_key", "")

    return base_url, api_key, model, timeout


async def llm_chat(messages: list[dict[str, Any]], config: dict | None = None) -> dict | None:
    """Send a chat completion request and return the parsed JSON response.

    Returns the parsed dict from the LLM response content, or None on failure.
    """
    if config is None:
        config = load_config()

    base_url, api_key, model, timeout = get_llm_endpoint(config)
    url = f"{base_url.rstrip('/')}/chat/completions"

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error("LLM HTTP error: %s %s", e.response.status_code, e.response.text[:300])
            return None
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            logger.error("LLM connection error: %s", e)
            return None

    if "choices" not in data or not data["choices"]:
        logger.error("LLM response missing 'choices': %s", json.dumps(data)[:500])
        return None

    content = data["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "\n".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )

    # Strip markdown fences
    content = content.strip()
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.warning("LLM response not valid JSON: %s", content[:300])
        return None
