"""Regression tests for the workflow abstraction layer.

Covers: registry, workflow definitions, Pydantic schemas, backward compat,
ScraperLogin.tool_key, ToolRunOutput model, dashboard API models,
and scraper/sync/worker parameter plumbing.
"""

import json
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from shiso.scraper.tools import (
    Workflow,
    get_workflow,
    list_workflows,
    register,
    AccountOutput,
    AccountListOutput,
    TenantLead,
    TenantLeadList,
)
from shiso.scraper.tools.workflows import FINANCIAL_WORKFLOW, ZILLOW_LEADS_WORKFLOW


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestWorkflowRegistry:
    def test_builtin_workflows_registered(self):
        workflows = list_workflows()
        keys = {w.key for w in workflows}
        assert "financial_scraper" in keys
        assert "zillow_leads" in keys

    def test_get_workflow_found(self):
        wf = get_workflow("financial_scraper")
        assert wf is not None
        assert wf.key == "financial_scraper"

    def test_get_workflow_not_found(self):
        assert get_workflow("nonexistent_tool") is None

    def test_register_custom_workflow(self):
        custom = Workflow(
            key="_test_dummy",
            name="Test",
            description="test",
            output_schema=AccountListOutput,
            prompt_template="do stuff",
            result_key="accounts",
        )
        register(custom)
        assert get_workflow("_test_dummy") is custom

    def test_list_workflows_returns_list(self):
        result = list_workflows()
        assert isinstance(result, list)
        assert len(result) >= 2


# ---------------------------------------------------------------------------
# Workflow: Financial Scraper
# ---------------------------------------------------------------------------

class TestFinancialWorkflow:
    def test_key(self):
        assert FINANCIAL_WORKFLOW.key == "financial_scraper"

    def test_name(self):
        assert FINANCIAL_WORKFLOW.name == "Financial Scraper"

    def test_output_schema(self):
        assert FINANCIAL_WORKFLOW.output_schema is AccountListOutput

    def test_result_key(self):
        assert FINANCIAL_WORKFLOW.result_key == "accounts"

    def test_prompt_template_contains_instructions(self):
        assert "CRITICAL" in FINANCIAL_WORKFLOW.prompt_template
        assert "card_name" in FINANCIAL_WORKFLOW.prompt_template
        assert "account_mask" in FINANCIAL_WORKFLOW.prompt_template

    def test_output_schema_fields_match_original(self):
        expected_fields = {
            "card_name", "account_mask", "current_balance", "statement_balance",
            "due_date", "minimum_payment", "last_payment_amount",
            "last_payment_date", "credit_limit", "interest_rate",
            "account_type", "address",
        }
        assert set(AccountOutput.model_fields.keys()) == expected_fields

    def test_account_list_output_structure(self):
        data = AccountListOutput(accounts=[
            AccountOutput(card_name="Test Card", current_balance=100.0),
        ])
        assert len(data.accounts) == 1
        assert data.accounts[0].card_name == "Test Card"
        dumped = data.model_dump()
        assert isinstance(dumped["accounts"], list)


# ---------------------------------------------------------------------------
# Workflow: Zillow Leads
# ---------------------------------------------------------------------------

class TestZillowLeadsWorkflow:
    def test_key(self):
        assert ZILLOW_LEADS_WORKFLOW.key == "zillow_leads"

    def test_name(self):
        assert ZILLOW_LEADS_WORKFLOW.name == "Zillow Tenant Leads"

    def test_output_schema(self):
        assert ZILLOW_LEADS_WORKFLOW.output_schema is TenantLeadList

    def test_result_key(self):
        assert ZILLOW_LEADS_WORKFLOW.result_key == "leads"

    def test_prompt_template_contains_instructions(self):
        assert "leads" in ZILLOW_LEADS_WORKFLOW.prompt_template.lower()
        assert "name" in ZILLOW_LEADS_WORKFLOW.prompt_template

    def test_tenant_lead_model(self):
        lead = TenantLead(name="John Doe", email="john@example.com", phone="555-1234")
        assert lead.name == "John Doe"
        assert lead.email == "john@example.com"

    def test_tenant_lead_list_model(self):
        data = TenantLeadList(leads=[
            TenantLead(name="Alice"),
            TenantLead(name="Bob", status="new"),
        ])
        assert len(data.leads) == 2
        dumped = data.model_dump()
        assert isinstance(dumped["leads"], list)


# ---------------------------------------------------------------------------
# Backward Compatibility — scraper.py re-exports
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    def test_scraper_reexports_account_output(self):
        from shiso.scraper.agent.scraper import AccountOutput as ScraperAccountOutput
        assert ScraperAccountOutput is AccountOutput

    def test_scraper_reexports_account_list_output(self):
        from shiso.scraper.agent.scraper import AccountListOutput as ScraperAccountListOutput
        assert ScraperAccountListOutput is AccountListOutput

    def test_api_exports_workflow_symbols(self):
        from shiso.scraper.api import get_workflow, list_workflows, ToolRunOutput
        assert callable(get_workflow)
        assert callable(list_workflows)
        assert ToolRunOutput is not None


# ---------------------------------------------------------------------------
# ScraperLogin.tool_key
# ---------------------------------------------------------------------------

class TestScraperLoginToolKey:
    def test_tool_key_column_exists(self, db_session):
        from shiso.scraper.models.accounts import ScraperLogin
        login = ScraperLogin(
            provider_key="test",
            label="Test Login",
            account_type="Credit Card",
        )
        db_session.add(login)
        db_session.commit()
        db_session.refresh(login)
        assert login.tool_key == "financial_scraper"

    def test_tool_key_custom_value(self, db_session):
        from shiso.scraper.models.accounts import ScraperLogin
        login = ScraperLogin(
            provider_key="zillow_leads",
            label="Zillow",
            account_type="Other",
            tool_key="zillow_leads",
        )
        db_session.add(login)
        db_session.commit()
        db_session.refresh(login)
        assert login.tool_key == "zillow_leads"


# ---------------------------------------------------------------------------
# ToolRunOutput model
# ---------------------------------------------------------------------------

class TestToolRunOutput:
    def test_create_tool_run_output(self, db_session):
        from shiso.scraper.models.tools import ToolRunOutput
        from shiso.scraper.models.accounts import ScraperLogin

        login = ScraperLogin(
            provider_key="zillow_leads",
            label="Zillow",
            account_type="Other",
            tool_key="zillow_leads",
        )
        db_session.add(login)
        db_session.commit()

        output = ToolRunOutput(
            tool_key="zillow_leads",
            scraper_login_id=login.id,
            provider_key="zillow_leads",
            output_json={"leads": [{"name": "Test Lead"}]},
            items_count=1,
        )
        db_session.add(output)
        db_session.commit()
        db_session.refresh(output)

        assert output.id is not None
        assert output.tool_key == "zillow_leads"
        assert output.items_count == 1
        assert output.output_json["leads"][0]["name"] == "Test Lead"


# ---------------------------------------------------------------------------
# scrape_provider signature
# ---------------------------------------------------------------------------

class TestScrapeProviderSignature:
    def test_accepts_workflow_param(self):
        import inspect
        from shiso.scraper.agent.scraper import scrape_provider
        sig = inspect.signature(scrape_provider)
        assert "workflow" in sig.parameters

    def test_workflow_param_defaults_to_none(self):
        import inspect
        from shiso.scraper.agent.scraper import scrape_provider
        sig = inspect.signature(scrape_provider)
        assert sig.parameters["workflow"].default is None


# ---------------------------------------------------------------------------
# run_sync signature
# ---------------------------------------------------------------------------

class TestRunSyncSignature:
    def test_accepts_workflow_param(self):
        import inspect
        from shiso.scraper.services.sync import run_sync
        sig = inspect.signature(run_sync)
        assert "workflow" in sig.parameters

    def test_workflow_param_defaults_to_none(self):
        import inspect
        from shiso.scraper.services.sync import run_sync
        sig = inspect.signature(run_sync)
        assert sig.parameters["workflow"].default is None


# ---------------------------------------------------------------------------
# Dashboard API models
# ---------------------------------------------------------------------------

class TestDashboardModels:
    def test_login_base_has_tool_key(self):
        from shiso.dashboard.main import LoginBase
        data = LoginBase(
            provider_key="test",
            label="Test",
            account_type="Credit Card",
            tool_key="zillow_leads",
        )
        assert data.tool_key == "zillow_leads"

    def test_login_base_tool_key_defaults(self):
        from shiso.dashboard.main import LoginBase
        data = LoginBase(
            provider_key="test",
            label="Test",
            account_type="Credit Card",
        )
        assert data.tool_key == "financial_scraper"

    def test_login_response_has_tool_key(self):
        from shiso.dashboard.main import LoginResponse
        fields = LoginResponse.model_fields
        assert "tool_key" in fields


# ---------------------------------------------------------------------------
# Dashboard API endpoints exist
# ---------------------------------------------------------------------------

class TestDashboardRoutes:
    def test_tools_endpoint_exists(self):
        from shiso.dashboard.main import app
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/api/tools" in paths

    def test_tool_runs_endpoint_exists(self):
        from shiso.dashboard.main import app
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/api/tools/{tool_key}/runs" in paths


# ---------------------------------------------------------------------------
# Config: zillow_leads provider exists
# ---------------------------------------------------------------------------

class TestConfig:
    def test_zillow_leads_in_provider_keys(self):
        from shiso.scraper.api import PROVIDER_KEYS
        assert "zillow_leads" in PROVIDER_KEYS


# ---------------------------------------------------------------------------
# Generic output extraction (result_key)
# ---------------------------------------------------------------------------

class TestGenericOutputExtraction:
    def test_financial_output_result_key(self):
        data = AccountListOutput(accounts=[
            AccountOutput(card_name="Card A"),
            AccountOutput(card_name="Card B"),
        ])
        dumped = data.model_dump()
        items = dumped.get(FINANCIAL_WORKFLOW.result_key, [])
        assert len(items) == 2

    def test_zillow_output_result_key(self):
        data = TenantLeadList(leads=[
            TenantLead(name="Alice"),
            TenantLead(name="Bob"),
        ])
        dumped = data.model_dump()
        items = dumped.get(ZILLOW_LEADS_WORKFLOW.result_key, [])
        assert len(items) == 2


# ---------------------------------------------------------------------------
# _build_preamble + _build_task
# ---------------------------------------------------------------------------

class TestBuildTask:
    def test_preamble_contains_login_instructions(self):
        from shiso.scraper.agent.scraper import _build_preamble
        preamble = _build_preamble("chase", {"institution": "Chase"}, None)
        assert "Chase" in preamble
        assert "x_username" in preamble
        assert "x_password" in preamble

    def test_preamble_includes_dashboard_url(self):
        from shiso.scraper.agent.scraper import _build_preamble
        preamble = _build_preamble("amex", {"institution": "Amex"}, "https://example.com/dashboard")
        assert "https://example.com/dashboard" in preamble

    def test_build_task_combines_preamble_and_workflow(self):
        from shiso.scraper.agent.scraper import _build_task
        task = _build_task(
            "chase",
            {"institution": "Chase"},
            None,
            FINANCIAL_WORKFLOW,
            "Extra extraction prompt.",
        )
        # Has preamble
        assert "Chase" in task
        assert "x_username" in task
        # Has workflow prompt
        assert "CRITICAL" in task
        # Has extraction prompt
        assert "Extra extraction prompt." in task
