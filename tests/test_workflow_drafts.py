"""Tests for LLM-assisted workflow drafting."""

from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy.orm import sessionmaker

from shiso.scraper.agent.workflow_drafts import (
    draft_workflow_definition,
    load_recent_workflow_examples,
    normalize_workflow_draft,
)
from shiso.scraper.models.tools import ToolRunOutput
from shiso.scraper.tools.workflows import ZILLOW_LEADS_WORKFLOW


class TestWorkflowDraftNormalization:
    def test_normalize_workflow_draft_uses_examples_when_schema_missing(self):
        draft = {
            "name": "Rent Roll",
            "description": "Extract rental pricing data",
            "prompt_template": "Go to the rent roll page and extract all units.",
            "result_key": "rows",
        }
        examples = [{"unit": "1A", "rent": 1200.0, "occupied": True, "notes": None}]

        normalized = normalize_workflow_draft(
            draft,
            brief="Extract rent roll data",
            example_items=examples,
        )

        assert normalized["key"] == "rent_roll"
        assert normalized["result_key"] == "rows"
        assert {"name": "unit", "type": "str", "nullable": False} in normalized["output_schema_json"]
        assert {"name": "rent", "type": "float", "nullable": False} in normalized["output_schema_json"]
        assert {"name": "occupied", "type": "bool", "nullable": False} in normalized["output_schema_json"]
        assert {"name": "notes", "type": "str", "nullable": True} in normalized["output_schema_json"]

    def test_normalize_workflow_draft_sanitizes_schema(self):
        draft = {
            "key": "Tenant Followups",
            "name": "Tenant Followups",
            "description": "Track follow-up actions",
            "prompt_template": "Extract follow-up information.",
            "result_key": "follow_ups",
            "output_schema_json": [
                {"name": "Lead Name", "type": "STRING"},
                {"name": "retry_count", "type": "number", "default": 0},
                {"name": "active", "type": "bool", "nullable": False, "default": True},
                {"name": "Lead Name", "type": "str"},
            ],
        }

        normalized = normalize_workflow_draft(
            draft,
            brief="Track tenant follow-ups",
        )

        assert normalized["key"] == "tenant_followups"
        assert normalized["result_key"] == "follow_ups"
        assert normalized["output_schema_json"] == [
            {"name": "lead_name", "type": "str", "nullable": False},
            {"name": "retry_count", "type": "int", "nullable": False, "default": 0},
            {"name": "active", "type": "bool", "nullable": False, "default": True},
        ]


class TestWorkflowDraftGeneration:
    def test_draft_workflow_definition_normalizes_llm_output(self):
        async def fake_llm(messages):
            return {
                "name": "Zillow Leads Refined",
                "description": "Extract rental leads with contact details",
                "prompt_template": "Open the leads page and collect every lead.",
                "result_key": "leads",
                "output_schema_json": [
                    {"name": "name", "type": "str"},
                    {"name": "email", "type": "str", "nullable": True},
                ],
                "rationale": "Reuses the current key and simplifies the schema.",
            }

        draft = asyncio.run(
            draft_workflow_definition(
                "Improve the Zillow tenant lead workflow",
                existing_workflow=ZILLOW_LEADS_WORKFLOW,
                llm_chat_fn=fake_llm,
            )
        )

        assert draft is not None
        assert draft["key"] == "zillow_leads"
        assert draft["name"] == "Zillow Leads Refined"
        assert draft["rationale"] == "Reuses the current key and simplifies the schema."

    def test_load_recent_workflow_examples_reads_recent_tool_runs(self, db_session, monkeypatch):
        import shiso.scraper.agent.workflow_drafts as workflow_drafts_module

        db_session.add_all(
            [
                ToolRunOutput(
                    tool_key="zillow_leads",
                    provider_key="zillow",
                    output_json={"leads": [{"name": "Newest Lead", "email": "new@example.com"}]},
                    items_count=1,
                    created_at=datetime(2026, 3, 18, 12, 0, 0),
                ),
                ToolRunOutput(
                    tool_key="zillow_leads",
                    provider_key="zillow",
                    output_json={"leads": [{"name": "Older Lead", "email": None}]},
                    items_count=1,
                    created_at=datetime(2026, 3, 18, 11, 0, 0),
                ),
                ToolRunOutput(
                    tool_key="zillow_leads",
                    provider_key="zillow",
                    output_json={"other": "ignored"},
                    items_count=0,
                    created_at=datetime(2026, 3, 18, 10, 0, 0),
                ),
            ]
        )
        db_session.commit()

        monkeypatch.setattr(workflow_drafts_module, "SessionLocal", sessionmaker(bind=db_session.get_bind()))

        examples = load_recent_workflow_examples("zillow_leads", result_key="leads", max_items=5)

        assert examples == [
            {"name": "Newest Lead", "email": "new@example.com"},
            {"name": "Older Lead", "email": None},
        ]

    def test_draft_workflow_definition_uses_recent_examples_for_existing_workflow(self, monkeypatch):
        import shiso.scraper.agent.workflow_drafts as workflow_drafts_module

        monkeypatch.setattr(
            workflow_drafts_module,
            "load_recent_workflow_examples",
            lambda *args, **kwargs: [{"lead_name": "Alice", "active": True, "rent": 2100.0}],
        )

        async def fake_llm(messages):
            assert "Alice" in messages[1]["content"]
            return {
                "name": "Zillow Leads Refined",
                "description": "Extract leads with fit signals",
                "prompt_template": "Open the leads page and extract qualified prospects.",
                "result_key": "leads",
            }

        draft = asyncio.run(
            draft_workflow_definition(
                "Improve the Zillow lead workflow",
                existing_workflow=ZILLOW_LEADS_WORKFLOW,
                llm_chat_fn=fake_llm,
            )
        )

        assert draft is not None
        assert {"name": "lead_name", "type": "str", "nullable": False} in draft["output_schema_json"]
        assert {"name": "active", "type": "bool", "nullable": False} in draft["output_schema_json"]
        assert {"name": "rent", "type": "float", "nullable": False} in draft["output_schema_json"]
        assert draft["rationale"] == "Seeded from 1 recent item(s) from prior runs."


class TestWorkflowDraftApi:
    def test_draft_tool_endpoint_exists(self):
        from shiso.dashboard.main import app

        paths = [route.path for route in app.routes if hasattr(route, "path")]
        assert "/api/tools/draft" in paths

    def test_draft_tool_definition_maps_to_response_model(self, monkeypatch):
        import shiso.dashboard.main as dashboard_main

        async def fake_draft_workflow_definition(brief, example_items=None, existing_workflow=None):
            return {
                "key": "rent_roll",
                "name": "Rent Roll",
                "description": "Extract unit rent data",
                "prompt_template": "Collect all units and rents.",
                "result_key": "rows",
                "output_schema_json": [
                    {"name": "unit", "type": "str", "nullable": False},
                    {"name": "rent", "type": "float", "nullable": True},
                ],
                "rationale": "Good first draft.",
            }

        monkeypatch.setattr(dashboard_main.scraper, "draft_workflow_definition", fake_draft_workflow_definition)

        response = asyncio.run(
            dashboard_main.draft_tool_definition(
                dashboard_main.WorkflowDraftRequest(
                    brief="Draft a rent roll workflow",
                    example_items=[{"unit": "1A", "rent": 1200.0}],
                )
            )
        )

        assert response.key == "rent_roll"
        assert response.result_key == "rows"
        assert response.rationale == "Good first draft."
