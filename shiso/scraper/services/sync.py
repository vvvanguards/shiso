"""
Sync service — shared lifecycle for scraper runs.

Used by both the CLI (run.py) and the dashboard API to create, track,
and finalize sync runs with consistent logging and metrics.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable

from ..database import SessionLocal
from ..models.accounts import ScraperLogin, ScraperLoginSyncRun
from ..models.tools import ToolRunOutput
from ..services.accounts_db import AccountsDB
from ..agent.analyst import analyze_run
from ..agent.llm import llm_chat
from ..agent.scraper import ScrapeMetrics, scrape_provider
from ..agent.workflow_drafts import capture_workflow_revision_suggestion

logger = logging.getLogger(__name__)


class SyncRun:
    """Tracks a single provider sync run with logging and DB persistence."""

    def __init__(self, login_id: int, provider_key: str, run_id: int):
        self.login_id = login_id
        self.provider_key = provider_key
        self.run_id = run_id
        self.logs: list[str] = []
        self.results: list[dict] = []
        self.persisted: list[Any] = []
        self.metrics: ScrapeMetrics = ScrapeMetrics()
        self.error: str | None = None
        self.timed_out: bool = False

    def on_log(self, msg: str) -> None:
        self.logs.append(msg)


def create_sync_run(login_id: int) -> SyncRun:
    """Create a ScraperLoginSyncRun record and return a SyncRun tracker."""
    with SessionLocal() as session:
        login = session.get(ScraperLogin, login_id)
        if not login:
            raise ValueError(f"Login {login_id} not found")

        started_at = datetime.utcnow()
        login.last_sync_started_at = started_at
        login.last_sync_status = "running"
        login.last_sync_error = None

        run = ScraperLoginSyncRun(
            scraper_login_id=login.id,
            provider_key=login.provider_key,
            status="running",
            started_at=started_at,
        )
        session.add(run)
        session.commit()
        session.refresh(run)

        return SyncRun(
            login_id=login.id,
            provider_key=login.provider_key,
            run_id=run.id,
        )


def finalize_sync_run(sync: SyncRun) -> None:
    """Update the ScraperLoginSyncRun and ScraperLogin with final results.
    
    Status values:
    - "running": in progress
    - "succeeded": completed without errors
    - "failed": error during execution
    - "timeout": exceeded provider_timeout limit (may have partial results)
    """
    finished_at = datetime.utcnow()

    with SessionLocal() as session:
        db_run = session.get(ScraperLoginSyncRun, sync.run_id)
        login = session.get(ScraperLogin, sync.login_id)

        if sync.timed_out:
            db_run.status = "timeout"
            db_run.error = sync.error or "Provider timeout"
            login.last_sync_status = "timeout"
            login.last_sync_error = sync.error
            # Record partial results for timeout
            db_run.accounts_found = len(sync.results)
            db_run.snapshots_saved = len(sync.persisted)
        elif sync.error:
            db_run.status = "failed"
            db_run.error = sync.error
            login.last_sync_status = "failed"
            login.last_sync_error = sync.error
        else:
            db_run.status = "succeeded"
            db_run.accounts_found = len(sync.results)
            db_run.snapshots_saved = len(sync.persisted)
            login.last_sync_status = "succeeded"
            login.last_sync_error = None
            login.last_sync_account_count = len(sync.results)
            login.last_sync_snapshot_count = len(sync.persisted)

        db_run.finished_at = finished_at
        db_run.metrics = sync.metrics.to_dict()
        login.last_sync_finished_at = finished_at
        session.commit()


async def run_sync(
    provider_key: str,
    logins: list[dict[str, Any]],
    *,
    accounts_db: AccountsDB,
    download_statements: bool = False,
    interactive: bool = False,
    account_filter: str | None = None,
    on_log: Callable[[str], None] | None = None,
    run_id: int | None = None,
    workflow: Any | None = None,
    human_input_handler: Callable | None = None,
) -> SyncRun:
    """Run a full sync for one provider: scrape, persist, analyze.

    Creates the sync run record (or reuses an existing one via run_id),
    runs the scraper, persists results, runs post-run analysis, and
    finalizes the run record.
    """
    # Find the login_id — use first login's id for the sync run record
    login_id = logins[0].get("id") if logins else None
    if not login_id:
        raise ValueError(f"No login ID found for {provider_key}")

    if run_id:
        sync = SyncRun(login_id=login_id, provider_key=provider_key, run_id=run_id)
    else:
        sync = create_sync_run(login_id)

    def _log(msg: str) -> None:
        sync.on_log(msg)
        if on_log:
            on_log(msg)

    try:
        scrape_result = await scrape_provider(
            provider_key,
            logins,
            download_statements=download_statements,
            accounts_db=accounts_db,
            interactive=interactive,
            account_filter=account_filter,
            on_log=_log,
            workflow=workflow,
            run_id=sync.run_id,
            human_input_handler=human_input_handler,
        )
        results = scrape_result.accounts
        sync.results = results
        sync.metrics = scrape_result.metrics

        # Handle timeout status
        if scrape_result.metrics.timed_out:
            sync.timed_out = True
            sync.error = scrape_result.metrics.errors[-1] if scrape_result.metrics.errors else "Provider timeout"

        # Route persistence: non-financial workflows → ToolRunOutput; financial → AccountsDB
        if workflow and workflow.key != "financial_scraper":
            login_id = logins[0].get("id") if logins else None
            output = ToolRunOutput(
                tool_key=workflow.key,
                sync_run_id=sync.run_id,
                scraper_login_id=login_id,
                provider_key=provider_key,
                output_json={workflow.result_key: [r for r in results]},
                items_count=len(results),
            )
            with SessionLocal() as session:
                session.add(output)
                session.commit()
            sync.persisted = results
        else:
            sync.persisted = accounts_db.save_scrape_results(provider_key, results)

    except Exception as exc:
        logger.exception("Sync failed for %s", provider_key)
        sync.error = str(exc)

    # Post-run analysis (even on failure — partial logs are useful)
    if sync.logs:
        try:
            prev_metrics = _get_previous_metrics(provider_key)
            prev = ScrapeMetrics.from_dict(prev_metrics) if prev_metrics else None
            hints = await analyze_run(
                provider_key, sync.logs, llm_chat,
                previous_metrics=prev,
                metrics=sync.metrics,
            )
            if hints and on_log:
                n = sum(len(v) for v in hints.values() if isinstance(v, list))
                on_log(f"[{provider_key}] Analyst saved {n} hint(s)")
        except Exception as exc:
            logger.warning("Analyst failed for %s: %s", provider_key, exc)

    if workflow:
        try:
            suggestion = await capture_workflow_revision_suggestion(
                provider_key,
                workflow=workflow,
                sync_run_id=sync.run_id,
                metrics=sync.metrics.to_dict(),
                results=sync.results,
                error=sync.error,
                log_lines=sync.logs,
                llm_chat_fn=llm_chat,
            )
            if suggestion and on_log:
                on_log(f"[{provider_key}] Analyst drafted workflow revision suggestion for {workflow.key}")
        except Exception as exc:
            logger.warning("Workflow analyst failed for %s/%s: %s", provider_key, getattr(workflow, "key", "?"), exc)

    finalize_sync_run(sync)

    # Update agent log path if we have it
    if scrape_result.agent_log_path:
        with SessionLocal() as session:
            db_run = session.get(ScraperLoginSyncRun, sync.run_id)
            db_run.agent_log_path = scrape_result.agent_log_path
            session.commit()

    return sync


def _get_previous_metrics(provider_key: str) -> dict | None:
    """Get metrics from the most recent run with metrics data."""
    with SessionLocal() as session:
        prev_run = (
            session.query(ScraperLoginSyncRun)
            .filter(ScraperLoginSyncRun.provider_key == provider_key)
            .filter(ScraperLoginSyncRun.metrics.isnot(None))
            .order_by(ScraperLoginSyncRun.started_at.desc())
            .first()
        )
        if prev_run and prev_run.metrics:
            return prev_run.metrics
    return None


