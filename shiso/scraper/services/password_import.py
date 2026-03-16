"""
Parse Chrome password CSV exports and match rows to known financial providers.
"""

import csv
import io
from urllib.parse import urlparse

KNOWN_PROVIDERS = {
    "chase.com": ("chase", "Chase", "Credit Card"),
    "americanexpress.com": ("amex", "Amex", "Credit Card"),
    "citi.com": ("citi", "Citi", "Credit Card"),
    "citicards.com": ("citi", "Citi", "Credit Card"),
    "capitalone.com": ("capital_one", "Capital One", "Credit Card"),
    "discover.com": ("discover", "Discover", "Credit Card"),
    "barclays.com": ("barclays", "Barclays", "Credit Card"),
    "bfrb.bankofamerica.com": ("bofa", "Bank of America", "Credit Card"),
    "nipsco.com": ("nipsco", "NIPSCO", "Utility"),
    "amwater.com": ("american_water", "American Water", "Utility"),
    "indianaamericanwater.com": ("american_water", "American Water", "Utility"),
    "duke-energy.com": ("duke_energy", "Duke Energy", "Utility"),
    "xfinity.com": ("xfinity", "Xfinity", "Utility"),
    "comcast.com": ("xfinity", "Xfinity", "Utility"),
    "att.com": ("att", "AT&T", "Utility"),
    "verizon.com": ("verizon", "Verizon", "Utility"),
    "t-mobile.com": ("tmobile", "T-Mobile", "Utility"),
    "spectrum.com": ("spectrum", "Spectrum", "Utility"),
    "geico.com": ("geico", "GEICO", "Other"),
    "progressive.com": ("progressive", "Progressive", "Other"),
    "statefarm.com": ("state_farm", "State Farm", "Other"),
    "ally.com": ("ally", "Ally", "Bank"),
    "sofi.com": ("sofi", "SoFi", "Bank"),
    "marcus.com": ("marcus", "Marcus", "Bank"),
    "truist.com": ("truist", "Truist", "Bank"),
    "tiaabank.com": ("tiaa", "TIAA Bank", "Bank"),
    "citbank.com": ("cit_bank", "CIT Bank", "Bank"),
    "fidelity.com": ("fidelity", "Fidelity", "Bank"),
    "fidelityrewards.com": ("fidelity", "Fidelity", "Credit Card"),
    "schwab.com": ("schwab", "Schwab", "Bank"),
    "vanguard.com": ("vanguard", "Vanguard", "Bank"),
    "robinhood.com": ("robinhood", "Robinhood", "Bank"),
    "webull.com": ("webull", "Webull", "Bank"),
    "etrade.com": ("etrade", "E*TRADE", "Bank"),
    "coinbase.com": ("coinbase", "Coinbase", "Bank"),
    "venmo.com": ("venmo", "Venmo", "Bank"),
    "paypal.com": ("paypal", "PayPal", "Bank"),
    "navyfederal.org": ("navy_federal", "Navy Federal", "Bank"),
    "pnc.com": ("pnc", "PNC", "Bank"),
    "huntington.com": ("huntington", "Huntington", "Bank"),
    "regions.com": ("regions", "Regions", "Bank"),
    "wellsfargo.com": ("wells_fargo", "Wells Fargo", "Bank"),
    "bankofamerica.com": ("bofa", "Bank of America", "Bank"),
    "usaa.com": ("usaa", "USAA", "Bank"),
    "citizensbankonline.com": ("citizens", "Citizens", "Bank"),
    "loancare.com": ("loancare", "LoanCare", "Loan"),
    "myroundpoint.com": ("roundpoint", "RoundPoint", "Loan"),
    "nelnet.com": ("nelnet", "Nelnet", "Loan"),
    "navient.com": ("navient", "Navient", "Loan"),
    "mohela.com": ("mohela", "MOHELA", "Loan"),
    "salliemae.com": ("sallie_mae", "Sallie Mae", "Loan"),
}


def _match_domain(hostname: str) -> tuple[str, str, str] | None:
    for domain, info in KNOWN_PROVIDERS.items():
        if hostname.endswith(domain):
            return info
    return None


def parse_csv(content: str) -> dict:
    """Parse a Chrome passwords CSV and return matched/unmatched rows.

    Returns:
        {
            "matched": [
                {
                    "row_id": int,
                    "name": str,
                    "url": str,
                    "username": str,
                    "password": str,
                    "provider_key": str,
                    "provider_label": str,
                    "account_type": str,
                }
            ],
            "unmatched": [
                {
                    "row_id": int,
                    "name": str,
                    "url": str,
                    "username": str,
                }
            ],
            "total": int,
        }
    """
    reader = csv.DictReader(io.StringIO(content))
    matched = []
    unmatched = []
    seen = set()

    for i, row in enumerate(reader):
        name = row.get("name", "")
        url = row.get("url", "")
        username = row.get("username", "").strip()
        password = row.get("password", "")

        try:
            host = urlparse(url).hostname or ""
        except Exception:
            host = ""

        match = _match_domain(host)

        if match and username:
            pkey, label, acct_type = match
            dedup_key = (pkey, username.lower())
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            matched.append({
                "row_id": i,
                "name": name,
                "url": url,
                "username": username,
                "password": password,
                "provider_key": pkey,
                "provider_label": label,
                "account_type": acct_type,
            })
        else:
            unmatched.append({
                "row_id": i,
                "name": name,
                "url": url,
                "username": username,
            })

    return {
        "matched": matched,
        "unmatched": unmatched,
        "total": len(matched) + len(unmatched),
    }
