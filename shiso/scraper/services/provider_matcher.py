"""Provider matching for password CSV imports.

Two-phase approach:
1. Fast local match against pre-seeded known providers (exact + subdomain + fuzzy name)
2. For unmatched domains, call LLM one-by-one to classify
"""

from __future__ import annotations

import json
import structlog
import os
import re
from typing import Any

from ..agent.llm import llm_chat, load_config
from ..agent.prompts import render as render_prompt
from .accounts_db import AccountsDB, BASELINE_PROVIDERS

log = structlog.get_logger()

KNOWN_KEYWORDS = {
    "bank": "Bank",
    "checking": "Bank",
    "savings": "Bank",
    "credit union": "Bank",
    "federal": "Bank",
    "visa": "Credit Card",
    "mastercard": "Credit Card",
    "amex": "Credit Card",
    "card": "Credit Card",
    "credit card": "Credit Card",
    "electric": "Utility",
    "gas": "Utility",
    "water": "Utility",
    "energy": "Utility",
    "internet": "Utility",
    "phone": "Utility",
    "mobile": "Utility",
    "wireless": "Utility",
    "loan": "Loan",
    "student loan": "Loan",
    "mortgage": "Mortgage",
    "refinance": "Loan",
    "insurance": "Other",
    "coverage": "Other",
    "policy": "Other",
}


def _build_provider_lookup() -> dict[str, dict]:
    """Build fast domain → provider lookup from baseline + DB overrides."""
    db = AccountsDB()
    db_mappings = db.get_provider_mappings()

    lookup: dict[str, dict] = {}
    for p in BASELINE_PROVIDERS:
        lookup[p["domain_pattern"]] = p

    for m in db_mappings:
        lookup[m["domain_pattern"]] = {
            "domain_pattern": m["domain_pattern"],
            "provider_key": m["provider_key"],
            "label": m["label"],
            "account_type": m["account_type"],
        }

    return lookup


def _infer_account_type(name: str, domain: str) -> str:
    """Infer account type from site name and domain using keywords."""
    text = f"{name} {domain}".lower()
    for keyword, acct_type in KNOWN_KEYWORDS.items():
        if keyword in text:
            return acct_type
    return "Bank"


def _slugify(text: str) -> str:
    """Convert text to a provider key slug."""
    slug = re.sub(r"[^a-z0-9\s]", "", text.lower())
    slug = re.sub(r"\s+", "_", slug)
    return slug[:40]


def _learn_domain(domain: str, provider_key: str, label: str, account_type: str, confidence: float | None = None) -> None:
    """Persist a learned provider mapping to DB for future local matching."""
    try:
        db = AccountsDB()
        db.upsert_provider_mapping(
            domain_pattern=domain.lower(),
            provider_key=provider_key,
            label=label,
            account_type=account_type,
            source="learned",
            confidence=confidence,
        )
        log.info("Learned: %s -> %s (%s, conf=%.2f)", domain, provider_key, account_type, confidence or 0)
    except Exception as exc:
        log.warning("Failed to learn domain %s: %s", domain, exc)


def _looks_like_url_path(text: str) -> bool:
    """Return True if text looks like a URL path rather than a display name."""
    if not text:
        return True
    # Contains / or . in ways that suggest it's a URL path
    if "/" in text or text.startswith("login.") or text.startswith("www."):
        return True
    # All lowercase, no spaces, looks like a domain or path
    if text.islower() and "." in text and " " not in text:
        return True
    return False


def _clean_label_for_unknown(domain: str, name: str) -> tuple[str, str]:
    """Get best display label and provider_key for an unknown domain.

    Prefer the clean name, fall back to domain-derived label.
    """
    if name and not _looks_like_url_path(name):
        label = name.strip()
        provider_key = _slugify(label)
    else:
        parts = domain.lower().split(".")
        if len(parts) >= 2:
            main = parts[-2] if parts[-2] not in ("www", "login", "account", "secure", "app", "my", "web", "online", "mobile", "m") else parts[-3] if len(parts) > 2 else parts[-2]
        else:
            main = parts[0] if parts else domain
        label = main.capitalize()
        provider_key = _slugify(main)
    return label, provider_key


def _match_known(domain: str, name: str, lookup: dict[str, dict]) -> dict[str, Any] | None:
    """Try to match a domain against known providers. Returns match dict or None."""
    domain_lower = domain.lower().strip()

    # 1. Exact domain match
    if domain_lower in lookup:
        p = lookup[domain_lower]
        return {
            "provider_key": p["provider_key"],
            "label": p["label"],
            "account_type": p["account_type"],
            "confidence": 0.98,
            "is_new_provider": False,
            "match_type": "exact",
        }

    # 2. Subdomain match
    parts = domain_lower.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[i:])
        if parent in lookup:
            p = lookup[parent]
            return {
                "provider_key": p["provider_key"],
                "label": p["label"],
                "account_type": p["account_type"],
                "confidence": 0.90,
                "is_new_provider": False,
                "match_type": "subdomain",
            }

    # 3. Fuzzy name match
    name_lower = name.lower()
    for d_pattern, p in lookup.items():
        label_lower = p["label"].lower()
        if label_lower and label_lower in name_lower:
            return {
                "provider_key": p["provider_key"],
                "label": p["label"],
                "account_type": p["account_type"],
                "confidence": 0.85,
                "is_new_provider": False,
                "match_type": "fuzzy_name",
            }

    return None


async def _classify_with_llm(domain: str, name: str) -> dict[str, Any]:
    """Call LLM to classify a single unmatched domain."""
    config = load_config()

    prompt = render_prompt(
        "match_providers.md",
        domain=domain,
        name=name,
        providers=BASELINE_PROVIDERS,
    )

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Classify this password entry:\nDomain: {domain}\nName: {name}"},
    ]

    preset = os.environ.get("ANALYST_LLM", "local")
    log.info("LLM classifying unmatched domain: %s (%s)", domain, preset)

    try:
        result = await llm_chat(messages, config)
    except Exception as exc:
        log.error("LLM classify failed for %s: %s", domain, exc)
        # Fallback to keyword inference
        return {
            "provider_key": _slugify(name) if name else _slugify(domain),
            "label": name if name else domain,
            "account_type": _infer_account_type(name, domain),
            "confidence": 0.40,
            "is_new_provider": True,
            "match_type": "llm_failed",
        }

    if not result or not isinstance(result, dict):
        label, provider_key = _clean_label_for_unknown(domain, name)
        return {
            "provider_key": provider_key,
            "label": label,
            "account_type": _infer_account_type(name, domain),
            "confidence": 0.40,
            "is_new_provider": True,
            "match_type": "llm_failed",
        }

    label, provider_key = _clean_label_for_unknown(domain, name)
    return {
        "provider_key": result.get("provider_key", provider_key),
        "label": result.get("label", label),
        "account_type": result.get("account_type", _infer_account_type(name, domain)),
        "confidence": result.get("confidence", 0.60),
        "is_new_provider": result.get("is_new_provider", True),
        "match_type": "llm",
    }


def _expand_domain_match(
    domain_match: dict[str, Any],
    original_row_ids: list[int],
    usernames: list[str],
) -> list[dict[str, Any]]:
    """Expand a domain-level match to all original rows sharing that domain."""
    results = []
    for row_id in original_row_ids:
        results.append({
            "row_id": row_id,
            "domain": domain_match.get("domain", ""),
            "name": domain_match.get("name", ""),
            "username": usernames[0] if usernames else "",
            "provider_key": domain_match["provider_key"],
            "label": domain_match["label"],
            "account_type": domain_match["account_type"],
            "confidence": domain_match["confidence"],
            "is_new_provider": domain_match["is_new_provider"],
            "match_type": domain_match.get("match_type", "unknown"),
        })
    return results


async def match_providers(rows: list[dict[str, Any]], llm_limit: int | None = None) -> dict[str, Any]:
    """Match all CSV rows to providers using hybrid local + LLM approach.

    1. Aggregate rows by domain
    2. Match domains against known providers (fast, no LLM)
    3. For unmatched domains, call LLM one-by-one (up to llm_limit)
    4. Expand results back to all original rows

    Args:
        rows: List of {row_id, name, url, domain, username} from parse_csv.
        llm_limit: Max LLM calls to make (None = unlimited).

    Returns:
        {
            "mappings": [...],
            "summary": {"total", "high_confidence", "needs_review", "llm_calls"},
            "aggregated_count": int,
        }
    """
    if not rows:
        return {
            "mappings": [],
            "summary": {"total": 0, "high_confidence": 0, "needs_review": 0, "llm_calls": 0},
            "aggregated_count": 0,
        }

    # Aggregate by domain
    from .password_import import aggregate_by_domain
    aggregated = aggregate_by_domain(rows)

    lookup = _build_provider_lookup()

    matched_domains: list[dict[str, Any]] = []
    unmatched_aggregated: list[dict[str, Any]] = []
    llm_call_count = 0

    for agg in aggregated:
        domain = agg["domain"]
        name = agg["name"]

        known = _match_known(domain, name, lookup)
        if known:
            known["domain"] = domain
            known["name"] = name
            matched_domains.append(known)
        else:
            unmatched_aggregated.append(agg)

    # Classify unmatched domains one-by-one with LLM
    if unmatched_aggregated:
        domains_to_llm = unmatched_aggregated[:llm_limit] if llm_limit else unmatched_aggregated
        remaining = unmatched_aggregated[llm_limit:] if llm_limit else []
        log.info("LLM classifying %d domains (limit=%s)", len(domains_to_llm), llm_limit)
        for agg in domains_to_llm:
            llm_result = await _classify_with_llm(agg["domain"], agg["name"])
            llm_result["domain"] = agg["domain"]
            llm_result["name"] = agg["name"]
            matched_domains.append(llm_result)
            llm_call_count += 1

            # Self-learn: save high-confidence LLM results to DB for future local matching
            if llm_result.get("confidence", 0) >= 0.85 and llm_result.get("provider_key"):
                _learn_domain(
                    domain=agg["domain"],
                    provider_key=llm_result["provider_key"],
                    label=llm_result["label"],
                    account_type=llm_result["account_type"],
                    confidence=llm_result.get("confidence"),
                )

        # Remaining unmatched get keyword fallback
        for agg in remaining:
            label, provider_key = _clean_label_for_unknown(agg["domain"], agg["name"])
            matched_domains.append({
                "domain": agg["domain"],
                "name": agg["name"],
                "provider_key": provider_key,
                "label": label,
                "account_type": _infer_account_type(agg["name"], agg["domain"]),
                "confidence": 0.40,
                "is_new_provider": True,
                "match_type": "keyword_fallback",
            })

    # Expand domain matches back to all rows
    from .password_import import expand_matches
    expanded = expand_matches(matched_domains, aggregated)

    high_confidence = sum(1 for m in expanded if m.get("confidence", 0) >= 0.9)
    needs_review = sum(1 for m in expanded if m.get("confidence", 0) < 0.9)

    log.info(
        "Match complete: %d total, %d high confidence, %d needs review, %d LLM calls",
        len(expanded), high_confidence, needs_review, llm_call_count,
    )

    return {
        "mappings": expanded,
        "summary": {
            "total": len(expanded),
            "high_confidence": high_confidence,
            "needs_review": needs_review,
            "llm_calls": llm_call_count,
        },
        "aggregated_count": len(aggregated),
    }


def match_providers_sync(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Synchronous version — matches against known providers only, no LLM.

    Use this when LLM is unavailable or for testing.
    """
    if not rows:
        return {
            "mappings": [],
            "summary": {"total": 0, "high_confidence": 0, "needs_review": 0, "llm_calls": 0},
            "aggregated_count": 0,
        }

    from .password_import import aggregate_by_domain
    aggregated = aggregate_by_domain(rows)

    lookup = _build_provider_lookup()

    matched_domains: list[dict[str, Any]] = []

    for agg in aggregated:
        domain = agg["domain"]
        name = agg["name"]

        known = _match_known(domain, name, lookup)
        if known:
            known["domain"] = domain
            known["name"] = name
            matched_domains.append(known)
        else:
            # Fallback to keyword inference
            label, provider_key = _clean_label_for_unknown(domain, name)
            matched_domains.append({
                "domain": domain,
                "name": name,
                "provider_key": provider_key,
                "label": label,
                "account_type": _infer_account_type(name, domain),
                "confidence": 0.40,
                "is_new_provider": True,
                "match_type": "keyword_fallback",
            })

    from .password_import import expand_matches
    expanded = expand_matches(matched_domains, aggregated)

    high_confidence = sum(1 for m in expanded if m.get("confidence", 0) >= 0.9)
    needs_review = sum(1 for m in expanded if m.get("confidence", 0) < 0.9)

    return {
        "mappings": expanded,
        "summary": {
            "total": len(expanded),
            "high_confidence": high_confidence,
            "needs_review": needs_review,
            "llm_calls": 0,
        },
        "aggregated_count": len(aggregated),
    }


async def enrich_domain_metadata(domain: str) -> dict[str, Any] | None:
    """Fetch a domain's login page and extract Open Graph metadata.

    Returns dict with keys: domain, login_url, favicon_url, is_financial, label, category.
    Returns None on failure (non-critical — log and continue).
    """
    import asyncio
    import re
    from urllib.parse import urlparse

    # Try to find a login URL for the domain
    login_url = f"https://{domain}"
    favicon_url = f"https://{domain}/favicon.ico"
    is_financial = None
    label = domain.split('.')[0].capitalize()
    category = "Other"

    try:
        import httpx
        async with asyncio.timeout(8):
            try:
                resp = await httpx.AsyncClient(follow_redirects=True).get(login_url, timeout=8.0)
                html = resp.text

                # Extract og:title for label
                og_title_match = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
                if not og_title_match:
                    og_title_match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']', html, re.I)
                if og_title_match:
                    label = og_title_match.group(1).split('|')[0].split('-')[0].strip()

                # Extract og:description for category hints
                og_desc = ""
                desc_match = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
                if desc_match:
                    og_desc = desc_match.group(1).lower()

                # Try to find a login URL from common patterns
                login_patterns = [
                    r'href=["\']([^"\']*login[^"\']*)["\']',
                    r'href=["\']([^"\']*signin[^"\']*)["\']',
                    r'action=["\']([^"\']*login[^"\']*)["\']',
                ]
                for pattern in login_patterns:
                    m = re.search(pattern, html, re.I)
                    if m:
                        href = m.group(1)
                        if href.startswith('/'):
                            parsed = urlparse(login_url)
                            login_url = f"{parsed.scheme}://{parsed.netloc}{href}"
                        elif href.startswith('http'):
                            login_url = href
                        break

                # Heuristic: detect financial institution
                financial_keywords = ['bank', 'credit', 'loan', 'investment', 'insurance', 'mortgage', 'wealth', 'capital', 'fidelity', 'vanguard', 'schwab', 'chase', 'citi', 'amex', 'discover', 'wells fargo', 'bank of america']
                is_financial = any(kw in og_desc or kw in label.lower() for kw in financial_keywords)

                # Try to infer category from page content
                if any(k in og_desc for k in ['bank', 'credit union', 'lending']):
                    category = "Bank"
                elif any(k in og_desc for k in ['credit card', 'rewards', 'miles']):
                    category = "Credit Card"
                elif any(k in og_desc for k in ['insurance', 'coverage', 'quote']):
                    category = "Insurance"
                elif any(k in og_desc for k in ['electric', 'gas', 'water', 'utility', 'energy']):
                    category = "Utility"

                return {
                    "domain": domain,
                    "login_url": login_url,
                    "favicon_url": favicon_url,
                    "is_financial": is_financial,
                    "label": label,
                    "category": category,
                }
            except Exception:
                # Fallback: preserve login_url/favicon_url, use domain as label
                log.warning("Enrichment parse failed for domain=%s, using fallback", domain)
                return {
                    "domain": domain,
                    "login_url": login_url,
                    "favicon_url": favicon_url,
                    "is_financial": None,
                    "label": domain.split('.')[0].capitalize(),
                    "category": "Other",
                }
    except asyncio.TimeoutError:
        log.warning("Enrichment timeout for domain: %s", domain)
        return None
    except Exception as exc:
        log.warning("Enrichment failed for domain %s: %s", domain, exc)
        return None
