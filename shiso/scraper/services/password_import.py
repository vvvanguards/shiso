"""
Parse Chrome password CSV exports into raw rows for AI-powered provider matching.
"""

import csv
import io
from collections import defaultdict
from urllib.parse import urlparse


def parse_csv(content: str) -> list[dict]:
    """Parse a Chrome passwords CSV and return raw rows for AI matching.

    No provider matching is done here — that's handled by the AI provider_matcher.
    Within-file deduplication is still applied by (url, username).

    Returns:
        [
            {
                "row_id": int,
                "name": str,
                "url": str,
                "domain": str,
                "username": str,
                "password": str,
            }
        ]
    """
    reader = csv.DictReader(io.StringIO(content))
    seen: set[tuple[str, str]] = set()
    rows = []

    for i, row in enumerate(reader):
        name = row.get("name", "")
        url = row.get("url", "")
        username = row.get("username", "").strip()
        password = row.get("password", "")

        try:
            host = urlparse(url).hostname or ""
        except Exception:
            host = ""

        dedup_key = (url.lower(), username.lower())
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        rows.append({
            "row_id": i,
            "name": name,
            "url": url,
            "domain": host,
            "username": username,
            "password": password,
        })

    return rows


def aggregate_by_domain(rows: list[dict]) -> list[dict]:
    """Group rows by domain, counting usernames per domain.

    This dramatically reduces rows sent to LLM while preserving enough context
    for provider matching. Each aggregated entry represents one unique domain.

    Returns:
        [
            {
                "domain": str,
                "name": str,  # most common name for this domain
                "username_count": int,
                "usernames": list[str],
                "passwords": list[str],  # first password only (for hinting)
                "original_row_ids": list[int],
            }
        ]
    """
    by_domain: dict[str, dict] = defaultdict(lambda: {
        "names": [],
        "usernames": [],
        "passwords": [],
        "row_ids": [],
    })

    for row in rows:
        domain = row.get("domain", "")
        if not domain:
            continue

        d = by_domain[domain]
        d["names"].append(row.get("name", ""))
        if row.get("username"):
            d["usernames"].append(row["username"])
        if row.get("password"):
            d["passwords"].append(row["password"])
        d["row_ids"].append(row["row_id"])

    aggregated = []
    for domain, d in by_domain.items():
        # Pick the most common/non-empty name
        names = [n for n in d["names"] if n]
        name = names[0] if names else domain

        aggregated.append({
            "domain": domain,
            "name": name,
            "username_count": len(d["usernames"]),
            "usernames": d["usernames"],
            "password": d["passwords"][0] if d["passwords"] else "",
            "original_row_ids": d["row_ids"],
        })

    return aggregated


def expand_matches(
    aggregated_matches: list[dict],
    aggregated_domains: list[dict],
) -> list[dict]:
    """Expand aggregated matches back to original row structure.

    Each aggregated match is applied to all original rows that share that domain.
    """
    # Build domain → match lookup
    domain_match: dict[str, dict] = {m["domain"]: m for m in aggregated_matches}

    # Build row_id → original row lookup
    row_lookup: dict[int, dict] = {}
    for ad in aggregated_domains:
        for row_id in ad["original_row_ids"]:
            row_lookup[row_id] = {
                "domain": ad["domain"],
                "name": ad["name"],
                "username": ad["usernames"][0] if ad["usernames"] else "",
            }

    # Expand
    expanded = []
    for ad in aggregated_domains:
        match = domain_match.get(ad["domain"], {})
        if not match:
            for row_id in ad["original_row_ids"]:
                row = row_lookup[row_id]
                expanded.append({
                    "row_id": row_id,
                    "domain": row["domain"],
                    "name": row["name"],
                    "username": row["username"],
                    "provider_key": "",
                    "label": "",
                    "account_type": "",
                    "confidence": 0.0,
                    "is_new_provider": False,
                    "match_type": "unknown",
                })
            continue
        for row_id in ad["original_row_ids"]:
            row = row_lookup[row_id]
            expanded.append({
                "row_id": row_id,
                "domain": row["domain"],
                "name": row["name"],
                "username": row["username"],
                "provider_key": match.get("provider_key", ""),
                "label": match.get("label", ""),
                "account_type": match.get("account_type", ""),
                "confidence": match.get("confidence", 0.0),
                "is_new_provider": match.get("is_new_provider", False),
                "match_type": match.get("match_type", "unknown"),
            })

    return expanded
