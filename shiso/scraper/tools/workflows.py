"""Workflow definitions — prompt + schema configs with DB-backed overrides.

A workflow tells the scraper engine what to extract and how to structure the
output. Builtin workflows still exist in code for compatibility, but the
registry can now seed and load workflow definitions from the database so tool
behavior can move toward runtime data instead of static Python only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, create_model
from sqlalchemy.exc import OperationalError

from ..database import SessionLocal
from ..models.tools import WorkflowDefinitionRecord


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
    schema_spec: list[dict[str, Any]] | None = None
    source: str = "memory"
    # Orchestration config — controls which passes run and how results persist.
    persistence_strategy: str = "generic"      # "financial" | "generic"
    enrichment_enabled: bool = False
    statement_download_enabled: bool = False
    assessment_enabled: bool = False
    dedup_enabled: bool = False


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_WORKFLOWS: dict[str, Workflow] = {}
_BUILTIN_SYNC_ATTEMPTED = False
_DYNAMIC_SCHEMA_CACHE: dict[tuple[str, str, str], type[BaseModel]] = {}


def register(w: Workflow) -> Workflow:
    """Register an in-memory workflow by its key."""
    _WORKFLOWS[w.key] = w
    return w


def get_workflow(key: str) -> Workflow | None:
    """Look up a workflow by key, preferring DB-backed definitions."""
    _ensure_builtin_workflows_seeded()
    workflow = _load_workflow_from_db(key)
    if workflow is not None:
        return workflow
    return _WORKFLOWS.get(key)


def list_workflows() -> list[Workflow]:
    """Return all known workflows, preferring DB-backed definitions by key."""
    _ensure_builtin_workflows_seeded()
    db_workflows = {w.key: w for w in _list_workflows_from_db()}
    combined = list(db_workflows.values())
    for key, workflow in _WORKFLOWS.items():
        if key not in db_workflows:
            combined.append(workflow)
    return combined


def sync_builtin_workflows_to_db() -> None:
    """Seed builtin workflows into the database without overwriting edits."""
    global _BUILTIN_SYNC_ATTEMPTED

    try:
        with SessionLocal() as session:
            existing_keys = {
                row.key
                for row in session.query(WorkflowDefinitionRecord.key).all()
            }
            changed = False
            for workflow in _WORKFLOWS.values():
                if not workflow.schema_spec or workflow.key in existing_keys:
                    continue
                session.add(
                    WorkflowDefinitionRecord(
                        key=workflow.key,
                        name=workflow.name,
                        description=workflow.description,
                        prompt_template=workflow.prompt_template,
                        result_key=workflow.result_key,
                        output_schema_json=workflow.schema_spec,
                        persistence_strategy=workflow.persistence_strategy,
                        enrichment_enabled=workflow.enrichment_enabled,
                        statement_download_enabled=workflow.statement_download_enabled,
                        assessment_enabled=workflow.assessment_enabled,
                        dedup_enabled=workflow.dedup_enabled,
                    )
                )
                changed = True

            if changed:
                session.commit()
        _BUILTIN_SYNC_ATTEMPTED = True
    except OperationalError:
        # Database may not be initialized yet; callers can still use memory fallbacks.
        return


def save_workflow_definition(
    key: str,
    *,
    name: str,
    description: str,
    prompt_template: str,
    result_key: str,
    output_schema_json: list[dict[str, Any]],
    persistence_strategy: str = "generic",
    enrichment_enabled: bool = False,
    statement_download_enabled: bool = False,
    assessment_enabled: bool = False,
    dedup_enabled: bool = False,
) -> Workflow:
    """Create or update a DB-backed workflow definition."""
    with SessionLocal() as session:
        row = (
            session.query(WorkflowDefinitionRecord)
            .filter(WorkflowDefinitionRecord.key == key)
            .first()
        )
        if row is None:
            row = WorkflowDefinitionRecord(key=key)
            session.add(row)

        row.name = name
        row.description = description
        row.prompt_template = prompt_template
        row.result_key = result_key
        row.output_schema_json = output_schema_json
        row.persistence_strategy = persistence_strategy
        row.enrichment_enabled = enrichment_enabled
        row.statement_download_enabled = statement_download_enabled
        row.assessment_enabled = assessment_enabled
        row.dedup_enabled = dedup_enabled
        session.commit()
        session.refresh(row)

    _clear_dynamic_schema_cache(key)
    workflow = _load_workflow_from_db(key)
    if workflow is None:
        raise ValueError(f"Failed to persist workflow '{key}'")
    return workflow


def delete_workflow_definition(key: str) -> bool:
    """Delete a DB-backed workflow definition.

    Builtin workflows will fall back to their in-memory definitions after delete.
    """
    deleted = False
    with SessionLocal() as session:
        row = (
            session.query(WorkflowDefinitionRecord)
            .filter(WorkflowDefinitionRecord.key == key)
            .first()
        )
        if row is not None:
            session.delete(row)
            session.commit()
            deleted = True

    _clear_dynamic_schema_cache(key)
    return deleted


def _ensure_builtin_workflows_seeded() -> None:
    global _BUILTIN_SYNC_ATTEMPTED
    if not _BUILTIN_SYNC_ATTEMPTED:
        sync_builtin_workflows_to_db()


def _load_workflow_from_db(key: str) -> Workflow | None:
    try:
        with SessionLocal() as session:
            row = (
                session.query(WorkflowDefinitionRecord)
                .filter(WorkflowDefinitionRecord.key == key)
                .first()
            )
            if row is None:
                return None
            return _workflow_from_record(row)
    except OperationalError:
        return None


def _list_workflows_from_db() -> list[Workflow]:
    try:
        with SessionLocal() as session:
            rows = (
                session.query(WorkflowDefinitionRecord)
                .order_by(WorkflowDefinitionRecord.key)
                .all()
            )
            return [_workflow_from_record(row) for row in rows]
    except OperationalError:
        return []


def _workflow_from_record(row: WorkflowDefinitionRecord) -> Workflow:
    schema_spec = row.output_schema_json or []
    output_schema = _build_output_schema(row.key, row.result_key, schema_spec)
    return Workflow(
        key=row.key,
        name=row.name,
        description=row.description,
        output_schema=output_schema,
        prompt_template=row.prompt_template,
        result_key=row.result_key,
        schema_spec=schema_spec,
        source="db",
        persistence_strategy=getattr(row, "persistence_strategy", "generic"),
        enrichment_enabled=getattr(row, "enrichment_enabled", False),
        statement_download_enabled=getattr(row, "statement_download_enabled", False),
        assessment_enabled=getattr(row, "assessment_enabled", False),
        dedup_enabled=getattr(row, "dedup_enabled", False),
    )


def _build_output_schema(
    workflow_key: str,
    result_key: str,
    schema_spec: list[dict[str, Any]],
) -> type[BaseModel]:
    cache_key = (workflow_key, result_key, json.dumps(schema_spec, sort_keys=True))
    cached = _DYNAMIC_SCHEMA_CACHE.get(cache_key)
    if cached is not None:
        return cached

    item_model_name = "".join(part.title() for part in workflow_key.split("_")) + "Item"
    item_fields: dict[str, tuple[Any, Any]] = {}
    for field_spec in schema_spec:
        field_name = str(field_spec.get("name") or "").strip()
        if not field_name:
            continue
        item_fields[field_name] = (
            _field_type_from_spec(field_spec),
            _field_default_from_spec(field_spec),
        )

    item_model = create_model(item_model_name, **item_fields)  # type: ignore[call-overload]
    output_model_name = "".join(part.title() for part in workflow_key.split("_")) + "Output"
    output_model = create_model(
        output_model_name,
        **{result_key: (list[item_model], ...)},
    )  # type: ignore[call-overload]

    _DYNAMIC_SCHEMA_CACHE[cache_key] = output_model
    return output_model


def _clear_dynamic_schema_cache(workflow_key: str) -> None:
    for cache_key in list(_DYNAMIC_SCHEMA_CACHE):
        if cache_key[0] == workflow_key:
            del _DYNAMIC_SCHEMA_CACHE[cache_key]


def _field_type_from_spec(field_spec: dict[str, Any]) -> Any:
    type_name = str(field_spec.get("type") or "str")
    base_type = {
        "str": str,
        "float": float,
        "int": int,
        "bool": bool,
    }.get(type_name, str)

    if field_spec.get("nullable", False):
        return base_type | None
    return base_type


def _field_default_from_spec(field_spec: dict[str, Any]) -> Any:
    description = str(field_spec.get("description") or "").strip() or None
    if "default" in field_spec:
        return Field(default=field_spec["default"], description=description)
    if field_spec.get("nullable", False):
        return Field(default=None, description=description)
    return Field(default=..., description=description)


def _spec(
    name: str,
    type_name: str,
    *,
    nullable: bool = False,
    default: Any = ...,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "type": type_name,
        "nullable": nullable,
    }
    if default is not ...:
        payload["default"] = default
    return payload


# ---------------------------------------------------------------------------
# Pydantic output schemas
# ---------------------------------------------------------------------------

class AccountOutput(BaseModel):
    account_name: str = ""
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
    is_paid: bool | None = None
    paid_date: str | None = None
    autopay_enabled: bool | None = None


class AccountListOutput(BaseModel):
    accounts: list[AccountOutput]
    verdict: Literal["success", "blocked_2fa", "blocked_login", "blocked_other"] | None = None
    verdict_reason: str | None = None


class BalanceUpdateItem(BaseModel):
    account_name: str = ""
    account_mask: str | None = None
    current_balance: float | None = None
    due_date: str | None = None
    minimum_payment: float | None = None
    is_paid: bool | None = None
    paid_date: str | None = None
    autopay_enabled: bool | None = None


class BalanceUpdateOutput(BaseModel):
    accounts: list[BalanceUpdateItem]
    verdict: Literal["success", "blocked_2fa", "blocked_login", "blocked_other", "needs_login"] | None = None
    verdict_reason: str | None = None


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


BALANCE_UPDATE_SCHEMA_SPEC = [
    _spec("account_name", "str", default=""),
    _spec("account_mask", "str", nullable=True),
    _spec("current_balance", "float", nullable=True),
    _spec("due_date", "str", nullable=True),
    _spec("minimum_payment", "float", nullable=True),
    _spec("is_paid", "bool", nullable=True),
    _spec("paid_date", "str", nullable=True),
    _spec("autopay_enabled", "bool", nullable=True),
]

ACCOUNT_OUTPUT_SCHEMA_SPEC = [
    _spec("account_name", "str", default=""),
    _spec("account_mask", "str", nullable=True),
    _spec("current_balance", "float", nullable=True),
    _spec("statement_balance", "float", nullable=True),
    _spec("due_date", "str", nullable=True),
    _spec("minimum_payment", "float", nullable=True),
    _spec("last_payment_amount", "float", nullable=True),
    _spec("last_payment_date", "str", nullable=True),
    _spec("credit_limit", "float", nullable=True),
    _spec("interest_rate", "float", nullable=True),
    _spec("intro_apr_rate", "float", nullable=True),
    _spec("intro_apr_end_date", "str", nullable=True),
    _spec("regular_apr", "float", nullable=True),
    _spec("promo_type", "str", nullable=True),
    _spec("account_type", "str", nullable=True),
    _spec("address", "str", nullable=True),
    _spec("is_paid", "bool", nullable=True),
    _spec("paid_date", "str", nullable=True),
    _spec("autopay_enabled", "bool", nullable=True),
]

TENANT_LEAD_SCHEMA_SPEC = [
    _spec("name", "str"),
    _spec("email", "str", nullable=True),
    _spec("phone", "str", nullable=True),
    _spec("property_address", "str", nullable=True),
    _spec("inquiry_date", "str", nullable=True),
    _spec("message", "str", nullable=True),
    _spec("status", "str", nullable=True),
]


# ---------------------------------------------------------------------------
# Workflow definitions
# ---------------------------------------------------------------------------

FINANCIAL_WORKFLOW = register(Workflow(
    key="financial_scraper",
    name="Financial Scraper",
    description="Scrapes financial accounts, balances, and billing details from provider dashboards.",
    output_schema=AccountListOutput,
    result_key="accounts",
    schema_spec=ACCOUNT_OUTPUT_SCHEMA_SPEC,
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
- account_name: Display name of the account (e.g. "360 Checking", "Sapphire Preferred", "Duke Energy")
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
- account_type: e.g. credit_card, checking, savings, utility, loan
- address: Service/billing address if shown
- is_paid: Whether the current bill has been paid or a payment is scheduled, true/false/null
- paid_date: Date the bill was paid in YYYY-MM-DD format, or null
- autopay_enabled: Whether auto-pay is enrolled on the account, true/false/null

Do NOT click into individual account detail pages — just capture what's on the overview.

Do NOT call done until you have clicked every 'view more' button and scrolled \
the full page. Missing accounts is unacceptable. Return all accounts as structured output.

IMPORTANT: Before calling done, you MUST also set:
- verdict: "success" if you successfully extracted all visible accounts, OR one of:
  - "blocked_2fa" if you encountered a 2FA/verification/code prompt that prevented access
  - "blocked_login" if you encountered a login failure (wrong credentials, account locked, etc.)
  - "blocked_other" if you encountered any other blocking issue (CAPTCHA, service error, etc.)
- verdict_reason: A brief 1-sentence explanation of why (e.g. "2FA required via SMS code", "Invalid username or password")""",
    persistence_strategy="financial",
    enrichment_enabled=True,
    statement_download_enabled=True,
    assessment_enabled=True,
    dedup_enabled=True,
))

ZILLOW_LEADS_WORKFLOW = register(Workflow(
    key="zillow_leads",
    name="Zillow Tenant Leads",
    description="Extracts tenant leads and inquiries from Zillow Rental Manager.",
    output_schema=TenantLeadList,
    result_key="leads",
    schema_spec=TENANT_LEAD_SCHEMA_SPEC,
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

BALANCE_UPDATE_WORKFLOW = register(Workflow(
    key="balance_update",
    name="Balance Update (Fast Sync)",
    description="Quick balance/payment scrape for already-known accounts — skips discovery and detail enrichment.",
    output_schema=BalanceUpdateOutput,
    result_key="accounts",
    schema_spec=BALANCE_UPDATE_SCHEMA_SPEC,
    prompt_template="""\
You are on the account dashboard page. Your ONLY job is to read the current \
balance, due date, and minimum payment for the accounts listed below. \
Do NOT navigate to other pages, do NOT discover new accounts, do NOT click \
into account detail pages.

If you are NOT on the dashboard (e.g. you see a login page, security challenge, \
or redirect), set verdict to "needs_login" and stop immediately.

For each known account below, extract:
- account_name: Display name of the account
- account_mask: Last 4-5 digits (match to the known accounts)
- current_balance: Current/outstanding balance amount
- due_date: Payment due date in YYYY-MM-DD format
- minimum_payment: Minimum payment amount due
- is_paid: Whether the current bill has been paid or a payment is scheduled, true/false/null
- paid_date: Date the bill was paid in YYYY-MM-DD format, or null
- autopay_enabled: Whether auto-pay is enrolled on the account, true/false/null

Known accounts to look for:
{{ known_accounts }}

Return all matched accounts as structured output.

IMPORTANT: Before calling done, set:
- verdict: "success" if you extracted balances, OR
  - "needs_login" if you landed on a login/auth page instead of the dashboard
  - "blocked_2fa" if a 2FA/verification prompt appeared
  - "blocked_login" if credentials failed
  - "blocked_other" for any other issue
- verdict_reason: Brief explanation""",
    persistence_strategy="financial",
    dedup_enabled=True,
))
