"""Tests for the SyncType system — enum, DB model, resolution, and integration."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sqlalchemy.orm import sessionmaker

from shiso.scraper.models.sync_type import (
    BUILTIN_SYNC_TYPES,
    SyncType,
    SyncTypeRecord,
    get_sync_type_id,
    resolve_sync_type,
)


# ---------------------------------------------------------------------------
# SyncType enum
# ---------------------------------------------------------------------------

class TestSyncTypeEnum:
    def test_members(self):
        assert SyncType.auto == "auto"
        assert SyncType.full == "full"
        assert SyncType.balance == "balance"
        assert SyncType.statements == "statements"

    def test_auto_is_not_a_concrete_type(self):
        concrete = {SyncType.full, SyncType.balance, SyncType.statements}
        assert SyncType.auto not in concrete

    def test_construct_from_string(self):
        assert SyncType("full") is SyncType.full
        assert SyncType("balance") is SyncType.balance

    def test_invalid_value_raises(self):
        import pytest
        with pytest.raises(ValueError):
            SyncType("invalid")


# ---------------------------------------------------------------------------
# SyncTypeRecord DB model
# ---------------------------------------------------------------------------

class TestSyncTypeRecord:
    def test_seed_and_query(self, db_session):
        for key, (name, desc) in BUILTIN_SYNC_TYPES.items():
            db_session.add(SyncTypeRecord(key=key, name=name, description=desc))
        db_session.commit()

        records = db_session.query(SyncTypeRecord).all()
        keys = {r.key for r in records}
        assert keys == {"full", "balance", "statements"}

    def test_unique_key_constraint(self, db_session):
        from sqlalchemy.exc import IntegrityError
        import pytest

        db_session.add(SyncTypeRecord(key="full", name="Full"))
        db_session.commit()
        db_session.add(SyncTypeRecord(key="full", name="Duplicate"))
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_repr(self):
        record = SyncTypeRecord(key="full", name="Full Sync")
        assert "full" in repr(record)


# ---------------------------------------------------------------------------
# resolve_sync_type
# ---------------------------------------------------------------------------

class TestResolveSyncType:
    def test_explicit_type_returned_as_is(self, db_session, monkeypatch):
        """When an explicit type is passed, auto-resolution is skipped."""
        assert resolve_sync_type(999, requested=SyncType.full) is SyncType.full
        assert resolve_sync_type(999, requested=SyncType.balance) is SyncType.balance
        assert resolve_sync_type(999, requested=SyncType.statements) is SyncType.statements

    def test_no_login_returns_full(self, db_session, monkeypatch):
        _patch_session(monkeypatch, db_session)
        result = resolve_sync_type(9999)  # nonexistent login
        assert result is SyncType.full

    def test_no_accounts_returns_full(self, db_session, monkeypatch):
        from shiso.scraper.models.accounts import ScraperLogin
        _patch_session(monkeypatch, db_session)

        login = ScraperLogin(
            provider_key="chase", label="Chase", enabled=True,
        )
        db_session.add(login)
        db_session.commit()
        db_session.refresh(login)

        result = resolve_sync_type(login.id)
        assert result is SyncType.full

    def test_with_accounts_returns_balance(self, db_session, monkeypatch):
        from shiso.scraper.models.accounts import (
            FinancialAccount, FinancialAccountType, ScraperLogin,
        )
        _patch_session(monkeypatch, db_session)

        acct_type = FinancialAccountType(name="Credit Card", balance_type="liability")
        db_session.add(acct_type)
        db_session.flush()

        login = ScraperLogin(
            provider_key="chase", label="Chase", enabled=True,
        )
        db_session.add(login)
        db_session.flush()

        acct = FinancialAccount(
            provider_key="chase",
            institution="Chase",
            account_type_id=acct_type.id,
            scraper_login_id=login.id,
            account_number="1234",
        )
        db_session.add(acct)
        db_session.commit()

        result = resolve_sync_type(login.id)
        assert result is SyncType.balance

    def test_needs_full_sync_flag_returns_full(self, db_session, monkeypatch):
        from shiso.scraper.models.accounts import (
            FinancialAccount, FinancialAccountType, ScraperLogin,
        )
        _patch_session(monkeypatch, db_session)

        acct_type = FinancialAccountType(name="Credit Card", balance_type="liability")
        db_session.add(acct_type)
        db_session.flush()

        login = ScraperLogin(
            provider_key="chase", label="Chase", enabled=True,
            needs_full_sync=True,
        )
        db_session.add(login)
        db_session.flush()

        acct = FinancialAccount(
            provider_key="chase",
            institution="Chase",
            account_type_id=acct_type.id,
            scraper_login_id=login.id,
            account_number="1234",
        )
        db_session.add(acct)
        db_session.commit()

        # Even though accounts exist, the flag forces full
        result = resolve_sync_type(login.id)
        assert result is SyncType.full


# ---------------------------------------------------------------------------
# get_sync_type_id
# ---------------------------------------------------------------------------

class TestGetSyncTypeId:
    def test_returns_id(self, db_session, monkeypatch):
        _patch_session(monkeypatch, db_session)
        record = SyncTypeRecord(key="full", name="Full Sync")
        db_session.add(record)
        db_session.commit()
        db_session.refresh(record)

        assert get_sync_type_id("full") == record.id

    def test_returns_none_for_unknown(self, db_session, monkeypatch):
        _patch_session(monkeypatch, db_session)
        assert get_sync_type_id("nonexistent") is None


# ---------------------------------------------------------------------------
# SyncRun and finalize_sync_run per-type tracking
# ---------------------------------------------------------------------------

class TestSyncRunTracking:
    def test_create_sync_run_stores_sync_type(self, db_session, monkeypatch):
        from shiso.scraper.models.accounts import ScraperLogin, ScraperLoginSyncRun
        from shiso.scraper.services.sync import create_sync_run

        _patch_session(monkeypatch, db_session)

        # Seed sync types
        for key, (name, desc) in BUILTIN_SYNC_TYPES.items():
            db_session.add(SyncTypeRecord(key=key, name=name, description=desc))
        db_session.flush()

        login = ScraperLogin(
            provider_key="amex", label="Amex", enabled=True,
        )
        db_session.add(login)
        db_session.commit()
        db_session.refresh(login)

        sync = create_sync_run(login.id, sync_type=SyncType.balance)

        assert sync.sync_type is SyncType.balance
        db_run = db_session.get(ScraperLoginSyncRun, sync.run_id)
        assert db_run.sync_type_id is not None

        # Verify it points to the right record
        st_record = db_session.get(SyncTypeRecord, db_run.sync_type_id)
        assert st_record.key == "balance"

    def test_finalize_updates_per_type_timestamp(self, db_session, monkeypatch):
        from shiso.scraper.models.accounts import ScraperLogin, ScraperLoginSyncRun
        from shiso.scraper.services.sync import SyncRun, create_sync_run, finalize_sync_run

        _patch_session(monkeypatch, db_session)

        for key, (name, desc) in BUILTIN_SYNC_TYPES.items():
            db_session.add(SyncTypeRecord(key=key, name=name, description=desc))
        db_session.flush()

        login = ScraperLogin(
            provider_key="amex", label="Amex", enabled=True,
            needs_full_sync=True,
        )
        db_session.add(login)
        db_session.commit()
        db_session.refresh(login)

        # Create and finalize a full sync
        sync = create_sync_run(login.id, sync_type=SyncType.full)
        finalize_sync_run(sync)

        db_session.refresh(login)
        assert login.last_full_sync_at is not None
        assert login.needs_full_sync is False  # cleared by full sync

    def test_finalize_balance_sync_sets_balance_timestamp(self, db_session, monkeypatch):
        from shiso.scraper.models.accounts import ScraperLogin
        from shiso.scraper.services.sync import create_sync_run, finalize_sync_run

        _patch_session(monkeypatch, db_session)

        for key, (name, desc) in BUILTIN_SYNC_TYPES.items():
            db_session.add(SyncTypeRecord(key=key, name=name, description=desc))
        db_session.flush()

        login = ScraperLogin(
            provider_key="amex", label="Amex", enabled=True,
        )
        db_session.add(login)
        db_session.commit()
        db_session.refresh(login)

        sync = create_sync_run(login.id, sync_type=SyncType.balance)
        finalize_sync_run(sync)

        db_session.refresh(login)
        assert login.last_balance_sync_at is not None
        assert login.last_full_sync_at is None


# ---------------------------------------------------------------------------
# Worker reads sync_type from queued run
# ---------------------------------------------------------------------------

class TestWorkerSyncType:
    def test_worker_reads_sync_type_from_queued_run(self, db_session, monkeypatch):
        import shiso.scraper.worker as worker
        from shiso.scraper.models.accounts import ScraperLogin, ScraperLoginSyncRun

        TestSession = sessionmaker(bind=db_session.bind)
        monkeypatch.setattr(worker, "SessionLocal", TestSession)

        with TestSession() as session:
            # Seed sync types
            balance_st = SyncTypeRecord(key="balance", name="Balance Update")
            session.add(balance_st)
            session.flush()

            login = ScraperLogin(
                provider_key="amex", label="Amex",
                username="user@example.com",
                account_type="Credit Card",
                tool_key="financial_scraper",
                enabled=True,
            )
            session.add(login)
            session.flush()

            run = ScraperLoginSyncRun(
                scraper_login_id=login.id,
                provider_key="amex",
                status="queued",
                sync_type_id=balance_st.id,
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            run_id = run.id
            login_id = login.id

        captured: dict = {}
        monkeypatch.setattr(
            worker, "load_accounts",
            lambda login_ids=None: {
                "amex": [{"id": login_id, "label": "Amex",
                          "username": "user@example.com",
                          "account_type": "Credit Card"}]
            },
        )
        monkeypatch.setattr(worker, "AccountsDB", lambda: object())

        async def fake_run_sync(provider_key, logins, **kwargs):
            captured["sync_type"] = kwargs.get("sync_type")

        monkeypatch.setattr(worker, "run_sync", fake_run_sync)

        asyncio.run(worker.execute_run(run_id))

        assert captured["sync_type"] is SyncType.balance


# ---------------------------------------------------------------------------
# scrape_provider uses sync_type gating
# ---------------------------------------------------------------------------

class TestScrapeProviderSyncType:
    def test_balance_sync_uses_balance_workflow(self, monkeypatch):
        import shiso.scraper.agent.scraper as scraper_module

        captured: dict = {}

        class DummyBrowserSession:
            def __init__(self, *a, **kw): pass
            async def start(self): pass
            async def kill(self): pass

        class DummyPlaybook:
            def extraction_context(self): return ""
            def system_message(self): return ""
            failed_actions: list = []

        class DummyHistory:
            def errors(self): return []
            def get_structured_output(self, schema):
                return schema(accounts=[
                    {"account_name": "Gold", "account_mask": "1001",
                     "current_balance": 500.0},
                ])
            def final_result(self): return None

        class DummyAgent:
            def __init__(self, *args, **kwargs):
                captured["task"] = kwargs.get("task", "")
                captured["max_steps"] = kwargs.get("max_steps")
                self.state = SimpleNamespace(n_steps=1)
                self._login_failed = False
            async def run(self, on_step_end=None):
                return DummyHistory()

        monkeypatch.setattr(scraper_module, "_load_config", lambda: {
            "browser": {"user_data_dir": "data/test-browser-profile"},
            "agent": {"headless": True, "provider_timeout": 30},
            "providers": {
                "amex": {
                    "institution": "Amex",
                    "start_url": "https://example.com/login",
                    "dashboard_url": "https://example.com/dashboard",
                }
            },
            "statements": {"download_dir": "data/test-statements"},
        })
        monkeypatch.setattr(scraper_module, "BrowserSession", DummyBrowserSession)
        monkeypatch.setattr(scraper_module, "_kill_stale_chrome", _async_noop)
        monkeypatch.setattr(scraper_module, "_build_llm", lambda config, *, agent_cfg=None: object())
        monkeypatch.setattr(scraper_module, "_build_tools", lambda *, interactive=False, human_input_handler=None: object())
        monkeypatch.setattr(scraper_module, "load_provider_playbook", lambda pk, at: DummyPlaybook())
        monkeypatch.setattr(scraper_module, "Agent", DummyAgent)
        monkeypatch.setattr(scraper_module, "_update_auth_status", lambda *a, **kw: None)
        monkeypatch.setattr(scraper_module, "_set_needs_full_sync", lambda *a, **kw: None)
        monkeypatch.setattr(scraper_module, "_load_known_accounts_text",
                            lambda pk: "- Gold (****1001)")

        result = asyncio.run(scraper_module.scrape_provider(
            "amex",
            [{"id": 1, "label": "Amex", "username": "u", "password": "p",
              "account_type": "Credit Card"}],
            sync_type=SyncType.balance,
        ))

        # Should use reduced max_steps (default 15 for balance)
        assert captured["max_steps"] == 15
        assert result.metrics.accounts_found >= 1

    def test_full_sync_uses_standard_max_steps(self, monkeypatch):
        import shiso.scraper.agent.scraper as scraper_module
        from shiso.scraper.tools.workflows import FINANCIAL_WORKFLOW

        captured: dict = {}

        class DummyBrowserSession:
            def __init__(self, *a, **kw): pass
            async def start(self): pass
            async def kill(self): pass

        class DummyPlaybook:
            def extraction_context(self): return ""
            def system_message(self): return ""
            failed_actions: list = []

        class DummyHistory:
            def errors(self): return []
            def get_structured_output(self, schema):
                return schema(accounts=[
                    {"account_name": "Gold", "account_mask": "1001",
                     "account_type": "credit_card"},
                ])
            def final_result(self): return None

        class DummyAgent:
            def __init__(self, *args, **kwargs):
                captured["max_steps"] = kwargs.get("max_steps")
                self.state = SimpleNamespace(n_steps=1)
                self._login_failed = False
            async def run(self, on_step_end=None):
                return DummyHistory()

        async def fake_enrich(*a, **kw): pass
        async def fake_assess(*a, **kw):
            return SimpleNamespace(status="authenticated", category="success", reason="ok")

        monkeypatch.setattr(scraper_module, "_load_config", lambda: {
            "browser": {"user_data_dir": "data/test-browser-profile"},
            "agent": {"headless": True, "provider_timeout": 30, "enrich_details": False},
            "providers": {
                "amex": {
                    "institution": "Amex",
                    "start_url": "https://example.com/login",
                    "dashboard_url": "https://example.com/dashboard",
                }
            },
            "statements": {"download_dir": "data/test-statements"},
        })
        monkeypatch.setattr(scraper_module, "BrowserSession", DummyBrowserSession)
        monkeypatch.setattr(scraper_module, "_kill_stale_chrome", _async_noop)
        monkeypatch.setattr(scraper_module, "_build_llm", lambda config, *, agent_cfg=None: object())
        monkeypatch.setattr(scraper_module, "_build_tools", lambda *, interactive=False, human_input_handler=None: object())
        monkeypatch.setattr(scraper_module, "load_provider_playbook", lambda pk, at: DummyPlaybook())
        monkeypatch.setattr(scraper_module, "Agent", DummyAgent)
        monkeypatch.setattr(scraper_module, "_update_auth_status", lambda *a, **kw: None)
        monkeypatch.setattr(scraper_module, "_assess_run", fake_assess)

        result = asyncio.run(scraper_module.scrape_provider(
            "amex",
            [{"id": 1, "label": "Amex", "username": "u", "password": "p",
              "account_type": "Credit Card"}],
            sync_type=SyncType.full,
            workflow=FINANCIAL_WORKFLOW,
        ))

        # Full sync uses default max_steps (50)
        assert captured["max_steps"] == 50


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _async_noop(*args, **kwargs):
    return None


def _patch_session(monkeypatch, db_session):
    """Patch SessionLocal everywhere it's used — at the database module level
    and in service/model modules that import it at call time."""
    import shiso.scraper.database as database_mod
    import shiso.scraper.services.sync as sync_mod

    TestSession = sessionmaker(bind=db_session.bind)

    class FakeSessionLocal:
        def __init__(self):
            self._session = TestSession()

        def __enter__(self):
            return self._session

        def __exit__(self, *args):
            pass

    # Patch at the source module — lazy imports in resolve_sync_type / get_sync_type_id
    # use ``from ..database import SessionLocal`` which resolves to database_mod.SessionLocal
    monkeypatch.setattr(database_mod, "SessionLocal", FakeSessionLocal)
    monkeypatch.setattr(sync_mod, "SessionLocal", FakeSessionLocal)
