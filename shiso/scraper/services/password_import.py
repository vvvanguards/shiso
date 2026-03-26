"""
Parse Chrome password CSV exports into raw rows for AI-powered provider matching.
"""

import csv
import io
import re
from collections import defaultdict
from enum import Enum
from urllib.parse import urlparse
from typing import Any


class FilterMode(str, Enum):
    NONE = "none"
    RULE = "rule"   # domain allowlist + skip phrases
    LLM = "llm"     # LLM classification


# ── Rule-based filter data ──────────────────────────────────────────────────

_SKIP_PHRASES = frozenset([
    "android://",
    # Social / comms
    "facebook.com", "instagram.com", "twitter.com", "x.com", "tiktok.com",
    "youtube.com", "linkedin.com", "snapchat.com", "pinterest.com", "reddit.com",
    "mail.", "outlook.com", "yahoo.com", "protonmail",
    # Shopping / retail
    "amazon.com", "ebay.com", "etsy.com", "walmart.com", "target.com", "costco.com",
    "chewy.com", "petco.com", "petsmart.com", "bestbuy.com", "homedepot.com", "lowes.com",
    "shein.com", "aliexpress.com", "wish.com",
    # Entertainment / subscriptions
    "netflix.com", "hulu.com", "disneyplus.com", "spotify.com", "apple.com",
    "audible.com", "libby", "overdrive", "kindle", "roku.com",
    "rottentomatoes.com", "metacritic.com",
    # Tech / cloud / dev
    "github.com", "gitlab.com", "bitbucket.org",
    "dropbox.com", "icloud.com", "google.com", "microsoft.com",
    "slack.com", "zoom.us", "teams.microsoft.com",
    "docker.com", "cloud.ibm.com", "portal.aws.amazon.com",
    # Education / learning
    "udemy.com", "coursera.org", "skillshare.com", "masterclass.com",
    "trial.dominodatalab", "domino-datalab",
    # Food / delivery
    "uber.com", "lyft.com", "doordash.com", "grubhub.com", "instacart.com",
    "airbnb.com", "vrbo.com", "booking.com", "expedia.com", "tripadvisor.com",
    "seamless.com", "postmates.com",
    # Real estate (consumer rental)
    "zillow.com", "trulia.com", "realtor.com", "apartments.com", "rent.com", "hotpads.com",
    # Jobs
    "indeed.com", "glassdoor.com",
    # Forums / niche
    "excelforum.com", "craigslist.com",
    # Website building / hosting
    "wordpress.com", "wix.com", "squarespace.com", "shopify.com",
    "canva.com", "figma.com", "adobe.com", "godaddy.com", "name.com", "hover.com",
    # Gaming
    "epicgames.com", "steam.com", "xbox.com", "playstation.com", "nintendo",
    # Health / fitness (non-financial)
    "fitbit.com", "strava.com", "myfitnesspal.com",
    "cvs.com", "walgreens.com", "riteaid.com",
    "valhallavitality.com", "madmushroom.com", "redcrossblood.org",
    # Misc noise
    "angel.co", "docusign.com",
    "quickbooks.com", "freshbooks.com",
    # Signup / registration pages
    "/signup", "/register", "/create-account", "/password-recovery", "/reset-password",
    "/forgot", "/recovery", "/claim",
    "signup.hulu.com", "secure.hulu.com",
])

# Domains to keep (financial / utility / insurance / rewards / property)
_KEEP_DOMAINS = frozenset([
    # Banks / credit cards / lending
    "chase.com", "bankofamerica", "wellsfargo", "citi.com", "capitalone",
    "usbank.com", "discover.com", "americanexpress.com", "amex.com",
    "synchrony", "sync.com", "pnc.com", "bbva", "usaa", "navyfederal",
    "truist.com", "tiaabank.com", "citbank.com",
    "fidelity.com", "fidelityrewards.com", "vanguard.com", "schwab.com",
    "etrade.com", "robinhood", "wealthfront", "betterment", "acorns", "stash.com",
    "coinbase.com",
    # Insurance
    "geico.com", "progressive.com", "statefarm", "allstate", "nationwide", "farmers.com",
    "libertymutual", "kemper.com", "directauto.com", "audi.com",
    # Utilities
    "nipsco", "nisource", "americanwater", "duke-energy", "dukeenergy.com",
    "comed.com", "agl.com", "atmosenergy", "eversource", "nationalgrid.com",
    "verizon.com", "xfinity", "spectrum", "cox.com",
    # Rewards / points
    "rakuten.com", "swagbucks", "inboxdollars", "mypoints.com", "ibotta",
    "raise.com", "raise.",
    # Property / mortgage / rental
    "mrcooper", "loanstreet", "freddiemac.com", "fanniemae.com",
    "servicelinkauction", "xome.com", "doorloop", "azibo",
    "willowservicing", "loansphereservicing", "bkiconnect",
    "gilchrist.realtaxdeed",
    "account.lexus.com", "merc",
    # Tax
    "tax1099.com", "freetaxusa", "payusatax",
    # Financial services
    "paypal.com", "venmo.com", "cashapp", "zelle",
    "creditkarma", "experian", "equifax", "transunion",
    "mint.com",
    # Loans
    "avant.com", "lendingclub", "prosper.com", "sofi.com", "commonbond",
    # Medical / diagnostic
    "questdiagnostics.com",
    # Other utility
    "purevpn.com",
    "recwell.purdue.edu",
    "career8.successfactors.com",
    # Known financial logon pages
    "secure03b.chase.com", "secure02ea.chase.com", "secure01b.chase.com",
    "secure.citbank.com", "logon.vanguard.com",
    "account.progressive.com",
    "portal-login.willowservicing",
    "loansphereservicingdigital.bkiconnect",
    "account.mrcooper.com",
])


def _is_rule_junk(row: dict) -> bool:
    """Return True if row should be skipped by the rule-based filter."""
    url = row.get("url", "")
    name = row.get("name", "")
    username = row.get("username", "").strip()
    password = row.get("password", "").strip()
    url_lower = url.lower()
    name_lower = name.lower()

    if url.startswith("android://"):
        return True
    if not username or not password:
        return True
    if password.lower() in ("sharpe", "password", "test", "1234", "astrongpassword", "l0ngpassword!"):
        return True

    # Absolute skip phrases
    for skip in _SKIP_PHRASES:
        if skip in url_lower or skip in name_lower:
            return True

    # Domain must be in keep list
    domain = row.get("domain", "").lower()
    if domain:
        for keep in _KEEP_DOMAINS:
            if keep in domain:
                return False
        return True

    return False


async def filter_rows_llm(rows: list[dict]) -> list[dict]:
    """Classify rows using the LLM. Keeps financial/utility/insurance/property."""
    from ..agent.llm import llm_chat, load_config

    SYSTEM_PROMPT = """\
You are a credential organizer. Classify login credentials from a Chrome password manager export.

## KEEP — only these categories:
1. Financial: banks, credit cards, brokerages, investment, loan servicers, tax, PayPal/Venmo/Zelle, credit monitoring
2. Insurance: auto, home, life, health insurance portals
3. Utilities: electric, gas, water, internet, phone, cable
4. Property/Mortgage: servicers, HOA portals, rental management, property tax
5. Employer/Business: 401k, HSA, payroll, benefits

## JUNK — everything else:
Social media, shopping, entertainment, food delivery, travel, consumer real estate search, health/fitness apps, VPNs, developer tools, forums, signup pages.

Be conservative — when in doubt, mark JUNK.

Respond with ONLY valid JSON: {"decisions":[{"keep":true_or_false,"reason":"one sentence"}]}"""

    BATCH_SIZE = 20
    kept = []

    for batch_start in range(0, len(rows), BATCH_SIZE):
        batch = rows[batch_start : batch_start + BATCH_SIZE]
        prompt_lines = [
            f"[{i}] name={r.get('name', '')!r} | url={r.get('url', '')!r} | username={r.get('username', '')!r}"
            for i, r in enumerate(batch)
        ]
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Classify:\n" + "\n".join(prompt_lines)},
        ]
        raw = await llm_chat(messages)
        if not raw:
            continue
        decisions = raw.get("decisions", [])
        for row, decision in zip(batch, decisions):
            if decision.get("keep", False):
                kept.append(row)

    return kept


def filter_rows(rows: list[dict], mode: FilterMode) -> list[dict]:
    """Filter rows before import.

    - `none`: return all rows unchanged
    - `rule`: apply domain allowlist + skip phrases
    - `llm`: apply LLM classification (async, requires LLM config)

    Returns filtered rows with re-numbered row_ids.
    """
    if mode == FilterMode.NONE:
        return rows

    if mode == FilterMode.RULE:
        filtered = [r for r in rows if not _is_rule_junk(r)]
        # Re-number row_ids after filtering
        for i, row in enumerate(filtered):
            row["row_id"] = i
        return filtered

    # llm — handled asynchronously by filter_rows_llm; sync callers get all rows
    # (match_test uses the async path directly)
    return rows


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
