"""
Sync worker — polls for queued sync runs and processes them one at a time.

Run as a standalone process:
    uv run python -m shiso.scraper.worker

Decoupled from the dashboard API — communicates only through the database.
"""

import asyncio
import logging
import signal
from datetime import datetime

from .agent.run import load_accounts
from .database import SessionLocal, init_db
from .models.accounts import ScraperLogin, ScraperLoginSyncRun
from .services.accounts_db import AccountsDB
from .services.sync import run_sync
from .tools import get_workflow

logger = logging.getLogger(__name__)

POLL_INTERVAL = 3  # seconds


def _cleanup_stale_runs() -> int:
    """Mark any 'running' sync runs as failed (leftover from crash/restart)."""
    now = datetime.utcnow()
    count = 0
    with SessionLocal() as session:
        for run in session.query(ScraperLoginSyncRun).filter_by(status="running").all():
            run.status = "failed"
            run.error = "Interrupted by worker restart"
            run.finished_at = now
            count += 1
        for login in session.query(ScraperLogin).filter_by(last_sync_status="running").all():
            login.last_sync_status = "failed"
            login.last_sync_error = "Interrupted by worker restart"
            login.last_sync_finished_at = now
        if count:
            session.commit()
    return count


def _next_queued_run() -> tuple[int, str] | None:
    """Return (run_id, provider_key) for the oldest queued run, or None."""
    with SessionLocal() as session:
        run = (
            session.query(ScraperLoginSyncRun)
            .filter_by(status="queued")
            .order_by(ScraperLoginSyncRun.started_at)
            .first()
        )
        if run:
            return run.id, run.provider_key
    return None


async def execute_run(run_id: int) -> None:
    """Transition a queued run to running, execute it, finalize."""
    with SessionLocal() as session:
        db_run = session.get(ScraperLoginSyncRun, run_id)
        if not db_run or db_run.status != "queued":
            return
        login_id = db_run.scraper_login_id
        db_run.status = "running"
        db_run.started_at = datetime.utcnow()

        login = session.get(ScraperLogin, login_id)
        if login:
            login.last_sync_status = "running"
            login.last_sync_started_at = db_run.started_at
        session.commit()

    # Resolve workflow from login's tool_key
    with SessionLocal() as session:
        login_obj = session.get(ScraperLogin, login_id)
        tool_key = login_obj.tool_key if login_obj else "financial_scraper"

    workflow = None
    if tool_key and tool_key != "financial_scraper":
        workflow = get_workflow(tool_key)
        if not workflow:
            logger.warning("Unknown tool_key '%s' for login %d, falling back to default", tool_key, login_id)

    accounts = load_accounts(login_ids=[login_id])
    if not accounts:
        with SessionLocal() as session:
            db_run = session.get(ScraperLoginSyncRun, run_id)
            db_run.status = "failed"
            db_run.error = "No account data found for login"
            db_run.finished_at = datetime.utcnow()
            login = session.get(ScraperLogin, login_id)
            if login:
                login.last_sync_status = "failed"
                login.last_sync_error = db_run.error
                login.last_sync_finished_at = db_run.finished_at
            session.commit()
        return

    provider_key = next(iter(accounts))
    logins = accounts[provider_key]

    try:
        await run_sync(
            provider_key,
            logins,
            accounts_db=AccountsDB(),
            run_id=run_id,
            workflow=workflow,
        )
    except Exception:
        logger.exception("Sync run %d failed", run_id)


async def run_worker() -> None:
    """Main worker loop."""
    init_db()
    stale = _cleanup_stale_runs()
    if stale:
        logger.info("Cleaned up %d stale run(s)", stale)

    logger.info("Sync worker started — polling every %ds", POLL_INTERVAL)
    stop = asyncio.Event()

    def _signal_handler():
        logger.info("Shutting down...")
        stop.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            signal.signal(sig, lambda s, f: _signal_handler())

    while not stop.is_set():
        try:
            queued = _next_queued_run()
            if queued:
                run_id, provider_key = queued
                logger.info("Picking up run %d (%s)", run_id, provider_key)
                await execute_run(run_id)
            else:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=POLL_INTERVAL)
                except asyncio.TimeoutError:
                    pass
        except Exception:
            logger.exception("Worker error")
            try:
                await asyncio.wait_for(stop.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass

    logger.info("Sync worker stopped")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    asyncio.run(run_worker())
