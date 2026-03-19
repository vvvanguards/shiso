"""Tests for the provider playbook abstraction."""

from __future__ import annotations

import asyncio
import json

from sqlalchemy.orm import sessionmaker

from shiso.scraper.agent import analyst, playbooks
from shiso.scraper.agent.prompts import get_extraction_prompt
from shiso.scraper.models.tools import ProviderPlaybookRecord


def _session_factory(db_session):
    return sessionmaker(bind=db_session.get_bind())


class TestProviderPlaybooks:
    def test_load_provider_playbook_bootstraps_file_guidance_into_db(self, tmp_path, monkeypatch, db_session):
        extraction_dir = tmp_path / "prompts" / "extraction"
        extraction_dir.mkdir(parents=True)
        hints_path = tmp_path / "provider_hints.json"

        (extraction_dir / "amex.md").write_text("Static extraction note.", encoding="utf-8")
        hints_path.write_text(
            json.dumps(
                {
                    "amex": {
                        "navigation_tips": ["Go directly to /overview."],
                        "effective_patterns": ["Expand hidden account groups first."],
                        "failed_actions": ["Avoid account detail pages."],
                        "updated_at": "2026-03-18T12:00:00",
                    }
                }
            ),
            encoding="utf-8",
        )

        monkeypatch.setattr(playbooks, "EXTRACTION_DIR", extraction_dir)
        monkeypatch.setattr(playbooks, "HINTS_PATH", hints_path)
        monkeypatch.setattr(playbooks, "SessionLocal", _session_factory(db_session))

        playbook = playbooks.load_provider_playbook("amex")
        row = db_session.query(ProviderPlaybookRecord).filter_by(provider_key="amex").first()

        assert playbook.extraction_context() == "Static extraction note."
        assert playbook.navigation_tips == ["Go directly to /overview."]
        assert playbook.effective_patterns == ["Expand hidden account groups first."]
        assert playbook.failed_actions == ["Avoid account detail pages."]
        assert row is not None
        assert row.extraction_prompt == "Static extraction note."
        assert row.navigation_tips == ["Go directly to /overview."]
        assert "Navigation Tips" in playbook.system_message()
        assert "- Go directly to /overview." in playbook.system_message()

    def test_save_provider_playbook_hints_keeps_static_prompt_and_updates_db(self, tmp_path, monkeypatch, db_session):
        extraction_dir = tmp_path / "prompts" / "extraction"
        extraction_dir.mkdir(parents=True)

        (extraction_dir / "chase.md").write_text("Static chase note.", encoding="utf-8")
        monkeypatch.setattr(playbooks, "EXTRACTION_DIR", extraction_dir)
        monkeypatch.setattr(playbooks, "HINTS_PATH", tmp_path / "provider_hints.json")
        monkeypatch.setattr(playbooks, "SessionLocal", _session_factory(db_session))

        saved = playbooks.save_provider_playbook_hints(
            "chase",
            {
                "navigation_tips": ["Start from the auth landing page."],
                "effective_patterns": ["Wait for cards to finish loading."],
                "failed_actions": ["Do not retry stale click targets."],
            },
        )

        reloaded = playbooks.load_provider_playbook("chase")
        persisted = db_session.query(ProviderPlaybookRecord).filter_by(provider_key="chase").first()

        assert saved.extraction_context() == "Static chase note."
        assert reloaded.extraction_context() == "Static chase note."
        assert persisted is not None
        assert persisted.navigation_tips == ["Start from the auth landing page."]
        assert persisted.updated_at is not None

    def test_save_provider_playbook_hints_can_replace_extraction_prompt(self, tmp_path, monkeypatch, db_session):
        extraction_dir = tmp_path / "prompts" / "extraction"
        extraction_dir.mkdir(parents=True)
        (extraction_dir / "discover.md").write_text("Original prompt.", encoding="utf-8")

        monkeypatch.setattr(playbooks, "EXTRACTION_DIR", extraction_dir)
        monkeypatch.setattr(playbooks, "HINTS_PATH", tmp_path / "provider_hints.json")
        monkeypatch.setattr(playbooks, "SessionLocal", _session_factory(db_session))

        updated = playbooks.save_provider_playbook_hints(
            "discover",
            {"navigation_tips": ["Stay on the summary page."]},
            extraction_prompt="Revised prompt from analyst.",
        )

        persisted = db_session.query(ProviderPlaybookRecord).filter_by(provider_key="discover").first()

        assert updated.extraction_context() == "Revised prompt from analyst."
        assert persisted is not None
        assert persisted.extraction_prompt == "Revised prompt from analyst."

    def test_get_extraction_prompt_reads_from_db_playbook(self, tmp_path, monkeypatch, db_session):
        monkeypatch.setattr(playbooks, "EXTRACTION_DIR", tmp_path / "prompts" / "extraction")
        monkeypatch.setattr(playbooks, "HINTS_PATH", tmp_path / "provider_hints.json")
        monkeypatch.setattr(playbooks, "SessionLocal", _session_factory(db_session))

        db_session.add(
            ProviderPlaybookRecord(
                provider_key="nipsco",
                extraction_prompt="Utility prompt from DB.",
                navigation_tips=["Open the billing summary first."],
            )
        )
        db_session.commit()

        assert get_extraction_prompt("nipsco") == "Utility prompt from DB."

    def test_analyze_run_can_update_extraction_prompt(self, tmp_path, monkeypatch, db_session):
        extraction_dir = tmp_path / "prompts" / "extraction"
        extraction_dir.mkdir(parents=True)
        (extraction_dir / "citi.md").write_text("Old prompt.", encoding="utf-8")

        monkeypatch.setattr(playbooks, "EXTRACTION_DIR", extraction_dir)
        monkeypatch.setattr(playbooks, "HINTS_PATH", tmp_path / "provider_hints.json")
        monkeypatch.setattr(playbooks, "SessionLocal", _session_factory(db_session))
        monkeypatch.setattr(
            analyst,
            "_load_prompt",
            lambda: (
                "Provider: {provider_key}\n"
                "Logs: {logs}\n"
                "Hints: {existing_hints}\n"
                "Prompt: {existing_extraction_prompt}\n"
                "Config: {provider_config}"
            ),
        )
        monkeypatch.setattr(analyst, "_load_provider_config", lambda provider_key: {})

        async def fake_llm(messages):
            return {
                "failed_actions": ["Avoid expired sessions."],
                "effective_patterns": ["Use the summary screen."],
                "navigation_tips": ["Do not click account details first."],
                "extraction_prompt": "New provider prompt.",
                "config_patches": {},
            }

        result = asyncio.run(
            analyst.analyze_run(
                "citi",
                ["ERROR: loop detected"],
                fake_llm,
            )
        )

        persisted = db_session.query(ProviderPlaybookRecord).filter_by(provider_key="citi").first()

        assert result["navigation_tips"] == ["Do not click account details first."]
        assert persisted is not None
        assert persisted.extraction_prompt == "New provider prompt."
