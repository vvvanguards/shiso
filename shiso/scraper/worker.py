"""
Sync worker — polls for queued sync runs and processes them one at a time.

After each sync, runs a tuning pass (analyst + optional re-scrape) if no
other runs are queued. This way the worker improves hints between syncs
without blocking the queue.

Run as a standalone process:
    uv run python -m shiso.scraper.worker

Decoupled from the dashboard API — communicates only through the database.
"""

import asyncio
import logging
import signal
from datetime import datetime

from .agent.analyst import analyze_run, extract_run_metrics, load_provider_hints
from .agent.llm import llm_chat
from .agent.run import load_accounts
from .database import SessionLocal, init_db
from .models.accounts import ScraperLogin, ScraperLoginSyncRun
from .services.accounts_db import AccountsDB
from .services.sync import run_sync

logger = logging.getLogger(__name__)

POLL_INTERVAL = 3  # seconds
MAX_TUNE_RUNS = 2  # max additional tuning runs after a sync


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


def _has_queued_runs() -> bool:
    """Check if there are more queued runs waiting."""
    return _next_queued_run() is not None


async def execute_run(run_id: int) -> tuple[str | None, list[str]]:
    """Transition a queued run to running, execute it, finalize.

    Returns (provider_key, collected_logs) for post-run tuning.
    """
    with SessionLocal() as session:
        db_run = session.get(ScraperLoginSyncRun, run_id)
        if not db_run or db_run.status != "queued":
            return None, []
        login_id = db_run.scraper_login_id
        db_run.status = "running"
        db_run.started_at = datetime.utcnow()

        login = session.get(ScraperLogin, login_id)
        if login:
            login.last_sync_status = "running"
            login.last_sync_started_at = db_run.started_at
        session.commit()

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
        return None, []

    provider_key = next(iter(accounts))
    logins = accounts[provider_key]
    collected_logs: list[str] = []

    def _on_log(msg: str) -> None:
        collected_logs.append(msg)

    try:
        await run_sync(
            provider_key,
            logins,
            accounts_db=AccountsDB(),
            run_id=run_id,
            on_log=_on_log,
        )
    except Exception:
        logger.exception("Sync run %d failed", run_id)

    return provider_key, collected_logs


async def _should_tune(provider_key: str, run_metrics: dict, llm_chat_fn) -> bool:
    """Ask the LLM if another tuning run would help."""
    hints = load_provider_hints(provider_key)
    hint_count = sum(len(v) for v in hints.values() if isinstance(v, list)) if hints else 0

    prompt = f"""A scraper just ran for {provider_key}:
  accounts_found: {run_metrics.get('accounts_found', 0)}
  accounts_complete: {run_metrics.get('accounts_complete', 0)}
  steps_taken: {run_metrics.get('steps_taken', 0)}
  failed_actions: {run_metrics.get('failed_actions', 0)}
  crises_hit: {run_metrics.get('crises_hit', 0)}
  active_hints: {hint_count}

Would re-running improve results? Only say yes if there were failures or
incomplete accounts that better hints could fix.

Respond with ONLY JSON: {{"should_tune": true/false, "reason": "brief"}}"""

    try:
        result = await llm_chat_fn([
            {"role": "system", "content": "You decide if a scraper needs more tuning. Be conservative — only tune if there are clear fixable issues."},
            {"role": "user", "content": prompt},
        ])
        if result and isinstance(result, dict):
            should = result.get("should_tune", False)
            reason = result.get("reason", "")
            logger.info("[tune] %s: should_tune=%s — %s", provider_key, should, reason)
            return bool(should)
    except Exception:
        logger.warning("[tune] LLM decision failed for %s, skipping tune", provider_key)
    return False


async def tune_after_sync(provider_key: str, initial_logs: list[str]) -> None:
    """Run post-sync tuning: analyst + optional re-scrapes if LLM says it would help.

    Bails out immediately if new queued runs arrive.
    """
    metrics = extract_run_metrics(initial_logs)
    previous_metrics = metrics

    for i in range(MAX_TUNE_RUNS):
        # Don't tune if the queue has work waiting
        if _has_queued_runs():
            logger.info("[tune] %s: queue has pending runs, skipping tune", provider_key)
            return

        # Ask LLM if tuning would help
        if not await _should_tune(provider_key, metrics, llm_chat):
            logger.info("[tune] %s: LLM says no more tuning needed", provider_key)
            return

        logger.info("[tune] %s: running tune pass %d/%d", provider_key, i + 1, MAX_TUNE_RUNS)

        # Re-run the scraper with updated hints
        accounts = load_accounts()
        if provider_key not in accounts:
            return

        collected_logs: list[str] = []
        try:
            await run_sync(
                provider_key,
                accounts[provider_key],
                accounts_db=AccountsDB(),
                on_log=lambda msg: collected_logs.append(msg),
            )
            metrics = extract_run_metrics(collected_logs)
            logger.info(
                "[tune] %s pass %d: %d accounts (%d complete), %d failures",
                provider_key, i + 1,
                metrics.get("accounts_found", 0),
                metrics.get("accounts_complete", 0),
                metrics.get("failed_actions", 0),
            )
            previous_metrics = metrics
        except Exception:
            logger.exception("[tune] %s: tune pass %d failed", provider_key, i + 1)
            return


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
                provider_key, logs = await execute_run(run_id)

                # Tune if queue is empty and we got logs
                if provider_key and logs and not _has_queued_runs():
                    await tune_after_sync(provider_key, logs)
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
