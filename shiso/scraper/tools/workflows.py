"""Workflow definitions — saved (prompt_template, output_schema, metadata) tuples.

A Workflow is a pure-data configuration that tells the scraper engine what to
extract and how to structure the output. The engine wraps each workflow's
prompt_template with the universal login/2FA/navigation preamble at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Workflow dataclass
# ---------------------------------------------------------------------------

@dataclass
class Workflow:
    key: str                          # "financial_scraper", "zillow_leads"
    name: str                         # "Financial Scraper"
    description: str                  # one-liner
    output_schema: type[BaseModel]    # AccountListOutput, TenantLeadList
    prompt_template: str              # domain-specific task instructions
    result_key: str = "items"         # which field in output_schema holds the list


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_WORKFLOWS: dict[str, Workflow] = {}


def register(w: Workflow) -> Workflow:
    """Register a workflow by its key. Returns the workflow for convenience."""
    _WORKFLOWS[w.key] = w
    return w


def get_workflow(key: str) -> Workflow | None:
    """Look up a workflow by key. Returns None if not found."""
    return _WORKFLOWS.get(key)


def list_workflows() -> list[Workflow]:
    """Return all registered workflows."""
    return list(_WORKFLOWS.values())


# ---------------------------------------------------------------------------
# Pydantic output schemas
# ---------------------------------------------------------------------------

class AccountOutput(BaseModel):
    card_name: str = ""
    account_mask: str | None = None
    current_balance: float | None = None
    statement_balance: float | None = None
    due_date: str | None = None
    minimum_payment: float | None = None
    last_payment_amount: float | None = None
    last_payment_date: str | None = None
    credit_limit: float | None = None
    interest_rate: float | None = None
    intro_apr_rate: float | None = None
    intro_apr_end_date: str | None = None
    regular_apr: float | None = None
    promo_type: str | None = None
    account_type: str | None = None
    address: str | None = None


class AccountListOutput(BaseModel):
    accounts: list[AccountOutput]


class TenantLead(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    property_address: str | None = None
    inquiry_date: str | None = None
    message: str | None = None
    status: str | None = None


class TenantLeadList(BaseModel):
    leads: list[TenantLead]


# ---------------------------------------------------------------------------
# Workflow definitions
# ---------------------------------------------------------------------------

FINANCIAL_WORKFLOW = register(Workflow(
    key="financial_scraper",
    name="Financial Scraper",
    description="Scrapes financial accounts, balances, and billing details from provider dashboards.",
    output_schema=AccountListOutput,
    result_key="accounts",
    prompt_template="""\
CRITICAL: You MUST find every single account. Do NOT return results until you have
exhausted all ways to reveal hidden accounts. Follow these steps IN ORDER:

1. FIRST, look for and click any of these BEFORE extracting data:
   - "View more accounts" buttons or links
   - "Show all" or "See all accounts" links
   - Expandable sections, accordions, or collapsed panels
   - Pagination controls (next page, page numbers)
   - Tabs that might contain additional accounts (e.g. "Business", "Personal")
   - Carousels with arrows to reveal more cards

2. THEN scroll down the ENTIRE page to ensure nothing is hidden below the fold.

3. ONLY AFTER expanding everything and scrolling, extract ALL accounts.

For each account, extract whatever is visible on the overview page:
- card_name: Display name of the account/card
- account_mask: Last 4-5 digits (e.g. from "****1234")
- current_balance: Current/outstanding balance amount
- statement_balance: Statement balance if shown, or null
- due_date: Payment due date in YYYY-MM-DD format
- minimum_payment: Minimum payment amount due
- last_payment_amount: Most recent payment amount, or null
- last_payment_date: Date of most recent payment in YYYY-MM-DD format, or null
- credit_limit: Credit limit or credit line amount, or null
- interest_rate: Current APR/interest rate as a percentage number (e.g. 29.99), or null
- intro_apr_rate: Promotional/introductory APR rate (e.g. 0.0 for 0% intro), or null
- intro_apr_end_date: End date of promotional APR period in YYYY-MM-DD format, or null
- regular_apr: Standard APR that applies after promo ends (e.g. 29.99), or null
- promo_type: Type of promo - "purchase", "balance_transfer", or "general", or null
- account_type: e.g. credit_card, bank_account, utility, loan
- address: Service/billing address if shown

Do NOT click into individual account detail pages — just capture what's on the overview.

Do NOT call done until you have clicked every 'view more' button and scrolled \
the full page. Missing accounts is unacceptable. Return all accounts as structured output.""",
))

ZILLOW_LEADS_WORKFLOW = register(Workflow(
    key="zillow_leads",
    name="Zillow Tenant Leads",
    description="Extracts tenant leads and inquiries from Zillow Rental Manager.",
    output_schema=TenantLeadList,
    result_key="leads",
    prompt_template="""\
Navigate to the Leads or Inquiries section. Extract ALL tenant leads/inquiries visible.

For each lead, extract:
- name: Full name of the prospective tenant
- email: Email address if shown
- phone: Phone number if shown
- property_address: Which property they inquired about
- inquiry_date: Date of the inquiry in YYYY-MM-DD format
- message: Their inquiry message if visible
- status: Lead status (e.g. new, contacted, applied, etc.)

Scroll through ALL pages of leads. Do NOT stop until you have checked for pagination \
and extracted every lead visible.

Return all leads as structured output.""",
))
