"""Shared LLM utilities for analyst, pdf_utils, and other non-Agent callers.

Provides a lightweight httpx-based chat function that reads config from
scraper.toml — used by modules that need raw LLM calls without browser-use.
"""

from __future__ import annotations

import json
import structlog
import os
import re
from pathlib import Path
from typing import Any

import httpx

try:
    import tomllib
except ImportError:
    import tomli as tomllib

log = structlog.get_logger()

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
        "max_tokens": 500,
    }

    log.info("LLM request: url=%s model=%s timeout=%s", url, model, timeout)
    log.debug("LLM payload messages count: %d", len(messages))
    if messages:
        log.debug("LLM system prompt (first 500 chars): %s", messages[0]["content"][:500])
        log.debug("LLM user prompt: %s", messages[-1]["content"][:200])

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            log.info("LLM sending request...")
            response = await client.post(url, json=payload, headers=headers)
            log.info("LLM response status: %s", response.status_code)
            if response.status_code != 200:
                log.error("LLM error response: %s", response.text[:500])
            else:
                log.debug("LLM response body (first 500 chars): %s", response.text[:500])
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            log.error("LLM HTTP error: %s %s", e.response.status_code, e.response.text[:500])
            return None
        except httpx.TimeoutException as e:
            log.error("LLM timeout after %ss: %s", timeout, e)
            return None
        except (httpx.ConnectError, ConnectionError) as e:
            log.error("LLM connection error: %s", e)
            return None

    if "choices" not in data or not data["choices"]:
        log.error("LLM response missing 'choices': %s", json.dumps(data)[:500])
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
        log.warning("LLM response not valid JSON: %s", content[:300])
        return None
