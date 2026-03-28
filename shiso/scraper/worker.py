"""
Sync worker — polls for queued sync runs and processes them one at a time.

Run as a standalone process:
    uv run python -m shiso.scraper.worker

Decoupled from the dashboard API — communicates only through the database.
"""

import asyncio
import signal
import time
from datetime import datetime, timedelta
import structlog

from .agent.run import load_accounts
from .database import SessionLocal, init_db
from .models.accounts import ScraperLogin, ScraperLoginSyncRun
from .models.sync_type import SyncType, SyncTypeRecord, get_sync_type_id
from .services.accounts_db import AccountsDB
from .services.sync import run_sync
from .tools import get_workflow
from ._logging import configure_logging

log = structlog.get_logger()

POLL_INTERVAL = 3  # seconds
SCHEDULE_CHECK_INTERVAL = 300  # seconds between scheduled-sync checks
FULL_SYNC_INTERVAL_HOURS = 168  # 7 days


def _worker_process_command() -> list[str]:
    """Command used to launch the non-reloading worker subprocess."""
    import sys

    return [sys.executable, "-m", "shiso.scraper.worker"]


def _cleanup_stale_runs() -> int:
    """Mark any 'running' sync runs as failed (leftover from crash/restart).
    
    Note: 'timeout' status is excluded because it's already a terminal state -
    the run completed (with timeout) and results were persisted.
    """
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


def _queue_scheduled_syncs() -> int:
    """Auto-queue full syncs for logins that are due.

    A login is due when:
    - auto_sync_enabled is True
    - enabled is True and not deleted
    - last_full_sync_at is NULL or older than FULL_SYNC_INTERVAL_HOURS
    - No existing queued/running run for this login
    """
    cutoff = datetime.utcnow() - timedelta(hours=FULL_SYNC_INTERVAL_HOURS)
    sync_type_id = get_sync_type_id("full")
    queued = 0

    with SessionLocal() as session:
        logins = (
            session.query(ScraperLogin)
            .filter(
                ScraperLogin.auto_sync_enabled.is_(True),
                ScraperLogin.enabled.is_(True),
                ScraperLogin.is_deleted.is_(False),
            )
            .filter(
                (ScraperLogin.last_full_sync_at.is_(None))
                | (ScraperLogin.last_full_sync_at < cutoff)
            )
            .all()
        )

        for login in logins:
            already = (
                session.query(ScraperLoginSyncRun)
                .filter_by(scraper_login_id=login.id)
                .filter(ScraperLoginSyncRun.status.in_(["queued", "running"]))
                .first()
            )
            if already:
                continue

            run = ScraperLoginSyncRun(
                scraper_login_id=login.id,
                provider_key=login.provider_key,
                sync_type_id=sync_type_id,
                status="queued",
                started_at=datetime.utcnow(),
            )
            login.last_sync_status = "queued"
            login.last_sync_error = None
            session.add(run)
            queued += 1

        if queued:
            session.commit()
            log.info("Scheduled %d full sync(s)", queued)

    return queued


async def execute_run(run_id: int) -> None:
    """Transition a queued run to running, execute it, finalize."""
    structlog.contextvars.bind_contextvars(run_id=run_id)
    try:
        with SessionLocal() as session:
            db_run = session.get(ScraperLoginSyncRun, run_id)
            if not db_run or db_run.status != "queued":
                return
            login_id = db_run.scraper_login_id
            account_filter = db_run.account_filter
            db_run.status = "running"
            db_run.started_at = datetime.utcnow()

            login = session.get(ScraperLogin, login_id)
            if login:
                login.last_sync_status = "running"
                login.last_sync_started_at = db_run.started_at
                provider_key_for_session = login.provider_key
            else:
                provider_key_for_session = db_run.provider_key
            session.commit()

        # Create agent session for human-in-the-loop via dashboard API
        human_input_handler = None
        complete_session = None
        try:
            from .agent_sessions import register_session, build_http_human_input_handler, complete_session_http, wait_for_api

            if wait_for_api(timeout=15):
                register_session(run_id, login_id, provider_key_for_session)
                human_input_handler = build_http_human_input_handler(run_id)
                complete_session = lambda status, message: complete_session_http(run_id, status=status, message=message)
                log.info("Dashboard API connected for run %d", run_id)
            else:
                log.warning("Dashboard API not available, running without human-in-the-loop")
        except Exception:
            log.debug("Agent sessions not available, running without human-in-the-loop", exc_info=True)

        # Resolve sync type from the queued run (dashboard may have set it)
        queued_sync_type = SyncType.auto
        with SessionLocal() as session:
            db_run_check = session.get(ScraperLoginSyncRun, run_id)
            if db_run_check and db_run_check.sync_type_id:
                st_record = session.get(SyncTypeRecord, db_run_check.sync_type_id)
                if st_record and st_record.key in SyncType.__members__:
                    queued_sync_type = SyncType(st_record.key)

        # Resolve workflow from login's tool_key
        with SessionLocal() as session:
            login_obj = session.get(ScraperLogin, login_id)
            tool_key = login_obj.tool_key if login_obj else "financial_scraper"

        workflow = None
        download_statements = True
        if tool_key and tool_key != "financial_scraper":
            workflow = get_workflow(tool_key)
            if not workflow:
                log.warning("Unknown tool_key '%s' for login %d, falling back to default", tool_key, login_id)
            else:
                download_statements = False

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
            if complete_session:
                try:
                    complete_session("failed", "No account data found")
                except Exception:
                    pass
            return

        provider_key = next(iter(accounts))
        logins = accounts[provider_key]

        try:
            await run_sync(
                provider_key,
                logins,
                accounts_db=AccountsDB(),
                download_statements=download_statements,
                run_id=run_id,
                account_filter=account_filter,
                workflow=workflow,
                human_input_handler=human_input_handler,
                sync_type=queued_sync_type,
            )
            if complete_session:
                try:
                    complete_session("completed", f"Sync completed for {provider_key}.")
                except Exception:
                    pass
        except Exception:
            log.exception("Sync run %d failed", run_id)
            if complete_session:
                try:
                    complete_session("failed", f"Sync run {run_id} failed.")
                except Exception:
                    pass
    finally:
        structlog.contextvars.clear_contextvars()


async def run_worker() -> None:
    """Main worker loop."""
    init_db()
    stale = _cleanup_stale_runs()
    if stale:
        log.info("Cleaned up %d stale run(s)", stale)

    log.info("Sync worker started — polling every %ds", POLL_INTERVAL)
    stop = asyncio.Event()
    last_schedule_check = 0.0

    def _signal_handler():
        log.info("Shutting down...")
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
                log.info("Picking up run %d (%s)", run_id, provider_key)
                await execute_run(run_id)
            else:
                # Periodically check if any logins need a scheduled full sync
                now = time.time()
                if now - last_schedule_check >= SCHEDULE_CHECK_INTERVAL:
                    _queue_scheduled_syncs()
                    last_schedule_check = now

                try:
                    await asyncio.wait_for(stop.wait(), timeout=POLL_INTERVAL)
                except asyncio.TimeoutError:
                    pass
        except Exception:
            log.exception("Worker error")
            try:
                await asyncio.wait_for(stop.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass

    log.info("Sync worker stopped")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Sync worker for processing queued runs")
    parser.add_argument("--reload", action="store_true", help="Restart on code changes (dev mode)")
    args = parser.parse_args()

    configure_logging()

    if args.reload:
        try:
            from watchfiles import watch
        except ImportError:
            log.error("--reload requires watchfiles: pip install watchfiles")
            raise SystemExit(1)

        import os
        import subprocess
        import sys

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        watch_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ignore_dirs = {
            os.path.join(project_root, "tests"),
            os.path.join(project_root, "data"),
            os.path.join(project_root, ".git"),
            os.path.join(project_root, ".venv"),
            os.path.join(project_root, "shiso", "dashboard", "frontend", "node_modules"),
            os.path.join(project_root, "shiso", "dashboard", "frontend", "dist"),
        }
        log.info("Watching %s for changes...", watch_dir)
        log.info("Worker running in reload mode — will restart on file changes")
        worker_proc = subprocess.Popen(_worker_process_command())
        try:
            for changes in watch(watch_dir):
                changed_paths = [str(change[1]) for change in changes]
                if changed_paths and all(
                    any(path.startswith(ignore_dir) for ignore_dir in ignore_dirs)
                    for path in changed_paths
                ):
                    log.info("Ignoring reload for non-worker changes")
                    continue
                log.info("Code changed, restarting worker...")
                worker_proc.terminate()
                worker_proc.wait(timeout=10)
                worker_proc = subprocess.Popen(_worker_process_command())
        except KeyboardInterrupt:
            log.info("Stopping reload worker...")
        finally:
            if worker_proc.poll() is None:
                worker_proc.terminate()
                try:
                    worker_proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    worker_proc.kill()
    else:
        asyncio.run(run_worker())
