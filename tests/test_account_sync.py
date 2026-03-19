"""Tests for account-targeted sync queueing."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sqlalchemy.orm import sessionmaker


def test_single_login_sync_queues_account_filter(db_session, monkeypatch):
    import shiso.dashboard.main as dashboard_main
    from shiso.scraper.models.accounts import ScraperLogin, ScraperLoginSyncRun

    TestSession = sessionmaker(bind=db_session.bind)
    monkeypatch.setattr(dashboard_main.scraper, "SessionLocal", TestSession)

    with TestSession() as session:
        login = ScraperLogin(
            provider_key="amex",
            label="Primary Amex",
            username="user@example.com",
            account_type="Credit Card",
            enabled=True,
        )
        session.add(login)
        session.commit()
        session.refresh(login)
        login_id = login.id

    response = dashboard_main.sync_login(
        login_id,
        dashboard_main.SingleLoginSyncRequest(account_filter="1001"),
    )

    with TestSession() as session:
        run = session.get(ScraperLoginSyncRun, response.run_id)
        assert run is not None
        assert run.account_filter == "1001"

    assert response.status == "queued"
    assert response.account_filter == "1001"


def test_worker_execute_run_passes_account_filter(db_session, monkeypatch):
    import shiso.scraper.worker as worker
    from shiso.scraper.models.accounts import ScraperLogin, ScraperLoginSyncRun

    TestSession = sessionmaker(bind=db_session.bind)
    monkeypatch.setattr(worker, "SessionLocal", TestSession)

    with TestSession() as session:
        login = ScraperLogin(
            provider_key="amex",
            label="Primary Amex",
            username="user@example.com",
            account_type="Credit Card",
            tool_key="financial_scraper",
            enabled=True,
        )
        session.add(login)
        session.commit()
        session.refresh(login)

        run = ScraperLoginSyncRun(
            scraper_login_id=login.id,
            provider_key="amex",
            status="queued",
            account_filter="1001",
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id
        login_id = login.id

    captured: dict = {}

    monkeypatch.setattr(
        worker,
        "load_accounts",
        lambda login_ids=None: {
            "amex": [
                {
                    "id": login_id,
                    "label": "Primary Amex",
                    "username": "user@example.com",
                    "account_type": "Credit Card",
                }
            ]
        },
    )
    monkeypatch.setattr(worker, "AccountsDB", lambda: object())

    async def fake_run_sync(provider_key, logins, **kwargs):
        captured["provider_key"] = provider_key
        captured["logins"] = logins
        captured["kwargs"] = kwargs

    monkeypatch.setattr(worker, "run_sync", fake_run_sync)

    asyncio.run(worker.execute_run(run_id))

    assert captured["provider_key"] == "amex"
    assert captured["kwargs"]["account_filter"] == "1001"
    assert captured["kwargs"]["download_statements"] is True


def test_scrape_provider_applies_account_filter_without_crashing(monkeypatch):
    import shiso.scraper.agent.scraper as scraper_module
    from shiso.scraper.tools.workflows import FINANCIAL_WORKFLOW

    captured: dict = {}

    class DummyBrowserSession:
        def __init__(self, *args, **kwargs):
            pass

        async def start(self):
            return None

        async def kill(self):
            return None

    class DummyPlaybook:
        def extraction_context(self):
            return ""

        def system_message(self):
            return ""

    class DummyHistory:
        def errors(self):
            return []

        def get_structured_output(self, output_schema):
            return output_schema(
                accounts=[
                    {
                        "card_name": "Blue Business Cash",
                        "account_mask": "71005",
                        "account_type": "credit_card",
                    },
                    {
                        "card_name": "Gold Card",
                        "account_mask": "61005",
                        "account_type": "credit_card",
                    },
                ]
            )

        def final_result(self):
            return None

    class DummyAgent:
        def __init__(self, *args, **kwargs):
            self.state = SimpleNamespace(n_steps=1)
            self._login_failed = False

        async def run(self, on_step_end=None):
            return DummyHistory()

    async def fake_kill_stale_chrome(*args, **kwargs):
        return None

    async def fake_enrich_account_details(*, accounts, **kwargs):
        captured["enriched_masks"] = [acct.get("account_mask") for acct in accounts]

    monkeypatch.setattr(
        scraper_module,
        "_load_config",
        lambda: {
            "browser": {"user_data_dir": "data/test-browser-profile"},
            "agent": {
                "headless": True,
                "provider_timeout": 30,
                "enrich_details": True,
            },
            "providers": {
                "amex": {
                    "institution": "Amex",
                    "start_url": "https://example.com/login",
                    "dashboard_url": "https://example.com/dashboard",
                }
            },
            "statements": {"download_dir": "data/test-statements"},
        },
    )
    monkeypatch.setattr(scraper_module, "BrowserSession", DummyBrowserSession)
    monkeypatch.setattr(scraper_module, "_kill_stale_chrome", fake_kill_stale_chrome)
    monkeypatch.setattr(scraper_module, "_build_llm", lambda config, *, agent_cfg=None: object())
    monkeypatch.setattr(scraper_module, "_build_tools", lambda *, interactive=False: object())
    monkeypatch.setattr(scraper_module, "load_provider_playbook", lambda provider_key, account_type: DummyPlaybook())
    monkeypatch.setattr(scraper_module, "Agent", DummyAgent)
    monkeypatch.setattr(scraper_module, "_update_auth_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(scraper_module, "_enrich_account_details", fake_enrich_account_details)

    result = asyncio.run(
        scraper_module.scrape_provider(
            "amex",
            [
                {
                    "id": 12,
                    "label": "Primary Amex",
                    "username": "user@example.com",
                    "password": "secret",
                    "account_type": "Credit Card",
                }
            ],
            account_filter="71005",
            workflow=FINANCIAL_WORKFLOW,
        )
    )

    assert result.metrics.accounts_found == 1
    assert [acct.get("account_mask") for acct in result.accounts] == ["71005"]
    assert captured["enriched_masks"] == ["71005"]


def test_scrape_provider_account_filter_no_match_returns_empty(monkeypatch):
    import shiso.scraper.agent.scraper as scraper_module
    from shiso.scraper.tools.workflows import FINANCIAL_WORKFLOW

    class DummyBrowserSession:
        def __init__(self, *args, **kwargs):
            pass

        async def start(self):
            return None

        async def kill(self):
            return None

    class DummyPlaybook:
        def extraction_context(self):
            return ""

        def system_message(self):
            return ""

    class DummyHistory:
        def errors(self):
            return []

        def get_structured_output(self, output_schema):
            return output_schema(
                accounts=[
                    {
                        "card_name": "Blue Business Cash",
                        "account_mask": "71005",
                        "account_type": "credit_card",
                    },
                    {
                        "card_name": "Gold Card",
                        "account_mask": "61005",
                        "account_type": "credit_card",
                    },
                ]
            )

        def final_result(self):
            return None

    class DummyAgent:
        def __init__(self, *args, **kwargs):
            self.state = SimpleNamespace(n_steps=1)
            self._login_failed = False

        async def run(self, on_step_end=None):
            return DummyHistory()

    async def fake_kill_stale_chrome(*args, **kwargs):
        return None

    async def fake_enrich_account_details(*args, **kwargs):
        pass

    monkeypatch.setattr(
        scraper_module,
        "_load_config",
        lambda: {
            "browser": {"user_data_dir": "data/test-browser-profile"},
            "agent": {
                "headless": True,
                "provider_timeout": 30,
                "enrich_details": True,
            },
            "providers": {
                "amex": {
                    "institution": "Amex",
                    "start_url": "https://example.com/login",
                    "dashboard_url": "https://example.com/dashboard",
                }
            },
            "statements": {"download_dir": "data/test-statements"},
        },
    )
    monkeypatch.setattr(scraper_module, "BrowserSession", DummyBrowserSession)
    monkeypatch.setattr(scraper_module, "_kill_stale_chrome", fake_kill_stale_chrome)
    monkeypatch.setattr(scraper_module, "_build_llm", lambda config, *, agent_cfg=None: object())
    monkeypatch.setattr(scraper_module, "_build_tools", lambda *, interactive=False: object())
    monkeypatch.setattr(scraper_module, "load_provider_playbook", lambda provider_key, account_type: DummyPlaybook())
    monkeypatch.setattr(scraper_module, "Agent", DummyAgent)
    monkeypatch.setattr(scraper_module, "_update_auth_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(scraper_module, "_enrich_account_details", fake_enrich_account_details)

    result = asyncio.run(
        scraper_module.scrape_provider(
            "amex",
            [
                {
                    "id": 12,
                    "label": "Primary Amex",
                    "username": "user@example.com",
                    "password": "secret",
                    "account_type": "Credit Card",
                }
            ],
            account_filter="99999",
            workflow=FINANCIAL_WORKFLOW,
        )
    )

    assert result.metrics.accounts_found == 0
    assert result.metrics.accounts_before_filter == 2
    assert result.metrics.account_filter == "99999"
    assert result.accounts == []


def test_worker_process_command_invokes_module():
    import shiso.scraper.worker as worker

    command = worker._worker_process_command()

    assert command[-2:] == ["-m", "shiso.scraper.worker"]
