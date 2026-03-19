"""Tests for workflow revision suggestions generated from weak runs."""

from __future__ import annotations

import asyncio

from sqlalchemy.orm import sessionmaker

from shiso.scraper.agent import workflow_drafts
from shiso.scraper.tools.workflows import ZILLOW_LEADS_WORKFLOW


def _session_factory(db_session):
    return sessionmaker(bind=db_session.get_bind())


class TestWorkflowSuggestionTriggers:
    def test_should_suggest_for_empty_error_run(self):
        reason = workflow_drafts.should_suggest_workflow_revision(
            workflow=ZILLOW_LEADS_WORKFLOW,
            metrics={
                "steps_taken": 18,
                "failed_actions": 4,
                "errors": ["could not find lead table"],
            },
            results=[],
        )

        assert reason is not None
        assert "No items were extracted" in reason
        assert "4 failed actions" in reason

    def test_does_not_suggest_for_healthy_run(self):
        reason = workflow_drafts.should_suggest_workflow_revision(
            workflow=ZILLOW_LEADS_WORKFLOW,
            metrics={
                "steps_taken": 8,
                "failed_actions": 0,
                "errors": [],
            },
            results=[{"name": "Alice"}, {"name": "Bob"}],
        )

        assert reason is None


class TestWorkflowSuggestionPersistence:
    def test_save_list_and_update_workflow_suggestions(self, db_session, monkeypatch):
        monkeypatch.setattr(workflow_drafts, "SessionLocal", _session_factory(db_session))

        saved = workflow_drafts.save_workflow_revision_suggestion(
            "zillow_leads",
            "zillow",
            suggestion_definition={
                "key": "zillow_leads",
                "name": "Zillow Leads Refined",
                "description": "Extract lead details more reliably",
                "prompt_template": "Open the leads page and collect lead contact data.",
                "result_key": "leads",
                "output_schema_json": [{"name": "name", "type": "str", "nullable": False}],
                "rationale": "The last run missed the table.",
            },
            trigger_reason="No items were extracted; 4 failed actions",
            metrics={"failed_actions": 4},
        )

        open_items = workflow_drafts.list_workflow_revision_suggestions()
        updated = workflow_drafts.update_workflow_revision_suggestion_status(saved.id, "dismissed")
        dismissed_items = workflow_drafts.list_workflow_revision_suggestions(status="dismissed")

        assert saved is not None
        assert len(open_items) == 1
        assert open_items[0].suggested_definition["name"] == "Zillow Leads Refined"
        assert updated is not None
        assert updated.status == "dismissed"
        assert len(dismissed_items) == 1

    def test_capture_workflow_revision_suggestion_persists_draft(self, db_session, monkeypatch):
        monkeypatch.setattr(workflow_drafts, "SessionLocal", _session_factory(db_session))

        async def fake_llm(messages):
            assert "Trigger reason:" in messages[1]["content"]
            return {
                "name": "Zillow Leads Refined",
                "description": "Extract lead records from the lead inbox",
                "prompt_template": "Open the lead inbox and capture each lead row.",
                "result_key": "leads",
                "output_schema_json": [{"name": "name", "type": "str"}],
                "rationale": "The run showed repeated extraction failures.",
            }

        suggestion = asyncio.run(
            workflow_drafts.capture_workflow_revision_suggestion(
                "zillow",
                workflow=ZILLOW_LEADS_WORKFLOW,
                metrics={
                    "steps_taken": 20,
                    "failed_actions": 4,
                    "errors": ["lead table not found"],
                },
                results=[],
                log_lines=["Step 10: failed - lead table not found"],
                llm_chat_fn=fake_llm,
            )
        )

        persisted = workflow_drafts.list_workflow_revision_suggestions()

        assert suggestion is not None
        assert suggestion.trigger_reason.startswith("1 scraper error(s)")
        assert len(persisted) == 1
        assert persisted[0].suggested_definition["key"] == "zillow_leads"


class TestRunSyncWorkflowSuggestions:
    def test_run_sync_creates_suggestion_for_weak_nonfinancial_run(self, db_session, monkeypatch):
        import shiso.scraper.services.sync as sync_module
        from shiso.scraper.agent.scraper import ScrapeMetrics, ScrapeResult
        from shiso.scraper.models.accounts import ScraperLogin

        session_factory = _session_factory(db_session)
        monkeypatch.setattr(sync_module, "SessionLocal", session_factory)
        monkeypatch.setattr(workflow_drafts, "SessionLocal", session_factory)

        login = ScraperLogin(
            provider_key="zillow",
            label="Zillow Leads",
            account_type="Other",
            tool_key="zillow_leads",
        )
        db_session.add(login)
        db_session.commit()
        db_session.refresh(login)

        async def fake_scrape_provider(*args, **kwargs):
            on_log = kwargs.get("on_log")
            if on_log:
                on_log("[zillow] Could not find lead table")
            return ScrapeResult(
                accounts=[],
                metrics=ScrapeMetrics(
                    steps_taken=16,
                    failed_actions=4,
                    errors=["lead table missing"],
                ),
            )

        async def fake_analyze_run(*args, **kwargs):
            return {}

        async def fake_llm(messages):
            return {
                "name": "Zillow Leads Refined",
                "description": "Extract lead details more reliably",
                "prompt_template": "Open the inbox and capture every lead row before clicking details.",
                "result_key": "leads",
                "output_schema_json": [{"name": "name", "type": "str"}],
                "rationale": "Repeated lead-table failures suggest the prompt should anchor on the inbox.",
            }

        class DummyAccountsDB:
            def save_scrape_results(self, provider_key, results):
                return results

        monkeypatch.setattr(sync_module, "scrape_provider", fake_scrape_provider)
        monkeypatch.setattr(sync_module, "analyze_run", fake_analyze_run)
        monkeypatch.setattr(sync_module, "llm_chat", fake_llm)

        logs: list[str] = []
        sync = asyncio.run(
            sync_module.run_sync(
                "zillow",
                [{"id": login.id}],
                accounts_db=DummyAccountsDB(),
                workflow=ZILLOW_LEADS_WORKFLOW,
                on_log=logs.append,
            )
        )

        suggestions = workflow_drafts.list_workflow_revision_suggestions()

        assert sync.error is None
        assert len(suggestions) == 1
        assert suggestions[0].tool_key == "zillow_leads"
        assert any("workflow revision suggestion" in line for line in logs)


class TestWorkflowSuggestionApi:
    def test_workflow_suggestion_routes_exist(self):
        from shiso.dashboard.main import app

        paths = [route.path for route in app.routes if hasattr(route, "path")]
        assert "/api/tools/suggestions" in paths
        assert "/api/tools/suggestions/{suggestion_id}/status" in paths

    def test_list_tool_suggestions_maps_response_model(self, monkeypatch):
        import shiso.dashboard.main as dashboard_main

        suggestion = workflow_drafts.WorkflowRevisionSuggestion(
            id=7,
            tool_key="zillow_leads",
            provider_key="zillow",
            status="open",
            trigger_reason="No items were extracted",
            rationale="Review the extraction prompt.",
            suggested_definition={
                "key": "zillow_leads",
                "name": "Zillow Leads Refined",
                "description": "Extract lead details more reliably",
                "prompt_template": "Open the inbox and capture every lead row.",
                "result_key": "leads",
                "output_schema_json": [{"name": "name", "type": "str", "nullable": False}],
                "rationale": "Review the extraction prompt.",
            },
            metrics={"failed_actions": 4},
            created_at="2026-03-18T12:00:00",
            updated_at="2026-03-18T12:05:00",
        )

        monkeypatch.setattr(
            dashboard_main.scraper,
            "list_workflow_revision_suggestions",
            lambda status="open", tool_key=None: [suggestion],
        )

        response = dashboard_main.list_tool_suggestions()

        assert len(response) == 1
        assert response[0].tool_key == "zillow_leads"
        assert response[0].suggested_definition.key == "zillow_leads"
