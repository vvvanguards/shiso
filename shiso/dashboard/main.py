"""
Shiso dashboard API.

The API only reads/writes to the database. Sync runs are queued as DB rows
and processed by the standalone worker (shiso.scraper.worker).
"""

import asyncio
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

import shiso.scraper.api as scraper

logger = logging.getLogger(__name__)

app = FastAPI(title="Finance Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = scraper.AccountsDB()


@app.get("/api/health")
def health():
    """Health check endpoint for worker and monitoring."""
    return {"status": "ok", "service": "dashboard", "timestamp": datetime.now(timezone.utc).isoformat()}


def _queue_sync_run(login_id: int, *, account_filter: str | None = None, force: bool = False) -> tuple[int | None, str | None]:
    """Create a sync run record with status=queued.

    Returns (run_id, conflict_status) where conflict_status is None on success,
    'already_queued' if a run is queued/running and force=False,
    'running' if a run is actively executing and force=True was passed.
    """
    normalized_filter = str(account_filter or "").strip() or None
    with scraper.SessionLocal() as session:
        login = session.get(scraper.ScraperLogin, login_id)
        if not login:
            raise HTTPException(status_code=404, detail="Login not found")
        if not login.enabled:
            raise HTTPException(status_code=400, detail="Login is disabled")

        existing = (
            session.query(scraper.ScraperLoginSyncRun)
            .filter_by(scraper_login_id=login_id)
            .filter(scraper.ScraperLoginSyncRun.status.in_(["queued", "running"]))
            .first()
        )

        if existing:
            if existing.status == "running":
                return (None, "running")
            if not force:
                return (None, "already_queued")
            # force=True and queued — cancel the old run and create a new one
            existing.status = "cancelled"
            existing.finished_at = datetime.utcnow()

        login.last_sync_status = "queued"
        login.last_sync_error = None

        run = scraper.ScraperLoginSyncRun(
            scraper_login_id=login.id,
            provider_key=login.provider_key,
            account_filter=normalized_filter,
            status="queued",
            started_at=datetime.utcnow(),
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        return (run.id, None)


class SnapshotResponse(BaseModel):
    id: int
    provider_key: str
    institution: str
    scraper_login_id: Optional[int] = None
    display_name: Optional[str] = None
    account_number: Optional[str] = None
    account_mask: Optional[str] = None
    address: Optional[str] = None
    status: Optional[str] = None
    current_balance: Optional[float] = None
    statement_balance: Optional[float] = None
    minimum_payment: Optional[float] = None
    due_date: Optional[str] = None
    last_payment_amount: Optional[float] = None
    last_payment_date: Optional[str] = None
    credit_limit: Optional[float] = None
    interest_rate: Optional[float] = None
    account_subcategory: str
    account_category: str
    balance_type: str
    signed_balance: Optional[float] = None
    first_seen_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    last_snapshot_at: Optional[str] = None
    updated_at: Optional[str] = None
    captured_at: str


class DashboardResponse(BaseModel):
    snapshots: list[SnapshotResponse]
    summary: dict
    available_scrapers: list[str]
    generated_at: str


@app.get("/api/accounts", response_model=DashboardResponse)
def get_accounts() -> DashboardResponse:
    snapshots = db.get_latest_snapshots()
    return DashboardResponse(
        snapshots=[SnapshotResponse(**row.__dict__) for row in snapshots],
        summary=db.get_summary(),
        available_scrapers=sorted(scraper.PROVIDER_KEYS),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/api/accounts/summary")
def get_accounts_summary() -> dict:
    return db.get_summary()


class LoginBase(BaseModel):
    provider_key: str
    institution: Optional[str] = None
    label: str
    username: Optional[str] = None
    password: Optional[str] = None
    login_url: Optional[str] = None
    account_type: str
    tool_key: str = "financial_scraper"
    enabled: bool = True
    sort_order: int = 0


class LoginResponse(BaseModel):
    id: int
    provider_key: str
    institution: Optional[str] = None
    label: str
    username: Optional[str] = None
    has_password: bool = False
    login_url: Optional[str] = None
    account_type: Optional[str] = None
    tool_key: str = "financial_scraper"
    enabled: bool = True
    sort_order: int = 0
    last_sync_started_at: Optional[str] = None
    last_sync_finished_at: Optional[str] = None
    last_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None
    last_sync_account_count: Optional[int] = None
    last_sync_snapshot_count: Optional[int] = None
    last_auth_status: Optional[str] = None
    last_auth_at: Optional[str] = None
    created_at: str
    updated_at: str


class LoginSyncRunResponse(BaseModel):
    id: int
    scraper_login_id: int
    provider_key: str
    account_filter: Optional[str] = None
    status: str
    started_at: str
    finished_at: Optional[str] = None
    accounts_found: Optional[int] = None
    snapshots_saved: Optional[int] = None
    error: Optional[str] = None
    metrics: Optional[dict] = None


class LoginSyncStartResponse(BaseModel):
    run_id: int
    status: str
    account_filter: Optional[str] = None


def _login_to_response(login: scraper.ScraperLogin) -> LoginResponse:
    return LoginResponse(
        id=login.id,
        provider_key=login.provider_key,
        institution=login.institution or login.provider_key.replace("_", " ").title(),
        label=login.label,
        username=login.username,
        has_password=bool(login.password_encrypted),
        login_url=login.login_url,
        account_type=login.account_type,
        tool_key=login.tool_key or "financial_scraper",
        enabled=login.enabled,
        sort_order=login.sort_order,
        last_sync_started_at=login.last_sync_started_at.isoformat() if login.last_sync_started_at else None,
        last_sync_finished_at=login.last_sync_finished_at.isoformat() if login.last_sync_finished_at else None,
        last_sync_status=login.last_sync_status,
        last_sync_error=login.last_sync_error,
        last_sync_account_count=login.last_sync_account_count,
        last_sync_snapshot_count=login.last_sync_snapshot_count,
        last_auth_status=login.last_auth_status,
        last_auth_at=login.last_auth_at.isoformat() if login.last_auth_at else None,
        created_at=login.created_at.isoformat(),
        updated_at=login.updated_at.isoformat(),
    )


def _sync_run_to_response(run: scraper.ScraperLoginSyncRun) -> LoginSyncRunResponse:
    return LoginSyncRunResponse(
        id=run.id,
        scraper_login_id=run.scraper_login_id,
        provider_key=run.provider_key,
        account_filter=run.account_filter,
        status=run.status,
        started_at=run.started_at.isoformat(),
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        accounts_found=run.accounts_found,
        snapshots_saved=run.snapshots_saved,
        error=run.error,
        metrics=run.metrics,
    )


@app.get("/api/logins", response_model=list[LoginResponse])
def list_logins():
    with scraper.SessionLocal() as session:
        logins = session.query(scraper.ScraperLogin).order_by(scraper.ScraperLogin.sort_order, scraper.ScraperLogin.provider_key).all()
        return [_login_to_response(l) for l in logins]


@app.get("/api/logins/{login_id}/runs", response_model=list[LoginSyncRunResponse])
def list_login_runs(login_id: int, limit: int = 20):
    with scraper.SessionLocal() as session:
        login = session.get(scraper.ScraperLogin, login_id)
        if not login:
            raise HTTPException(status_code=404, detail="Login not found")
        runs = (
            session.query(scraper.ScraperLoginSyncRun)
            .filter(scraper.ScraperLoginSyncRun.scraper_login_id == login_id)
            .order_by(scraper.ScraperLoginSyncRun.started_at.desc(), scraper.ScraperLoginSyncRun.id.desc())
            .limit(max(1, min(limit, 100)))
            .all()
        )
        return [_sync_run_to_response(run) for run in runs]


def _apply_login_data(login: scraper.ScraperLogin, data: LoginBase):
    login.provider_key = data.provider_key
    login.institution = data.institution
    login.label = data.label
    login.username = data.username.strip() if data.username else None
    login.login_url = data.login_url
    login.account_type = data.account_type
    login.tool_key = data.tool_key or "financial_scraper"
    login.enabled = data.enabled
    login.sort_order = data.sort_order
    if data.password is not None:
        login.password_encrypted = scraper.encrypt(data.password) if data.password else None


def _raise_login_integrity_error(exc: IntegrityError) -> None:
    message = str(getattr(exc, "orig", exc))
    if "uq_scraper_logins_provider_username_nocase" in message or "index 'uq_scraper_logins_provider_username_nocase'" in message:
        raise HTTPException(
            status_code=409,
            detail="A login for this provider and username already exists.",
        )
    raise exc


@app.post("/api/logins", response_model=LoginResponse, status_code=201)
def create_login(data: LoginBase):
    with scraper.SessionLocal() as session:
        login = scraper.ScraperLogin()
        _apply_login_data(login, data)
        session.add(login)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            _raise_login_integrity_error(exc)
        session.refresh(login)
        return _login_to_response(login)


@app.put("/api/logins/{login_id}", response_model=LoginResponse)
def update_login(login_id: int, data: LoginBase):
    with scraper.SessionLocal() as session:
        login = session.get(scraper.ScraperLogin, login_id)
        if not login:
            raise HTTPException(status_code=404, detail="Login not found")
        _apply_login_data(login, data)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            _raise_login_integrity_error(exc)
        session.refresh(login)
        return _login_to_response(login)


@app.delete("/api/logins/{login_id}")
def delete_login(login_id: int):
    from shiso.scraper.models.accounts import AccountSnapshot, AccountStatement, FinancialAccountLogin, ScraperLoginSyncRun
    with scraper.SessionLocal() as session:
        login = session.get(scraper.ScraperLogin, login_id)
        if not login:
            raise HTTPException(status_code=404, detail="Login not found")
        # Manual cascade — SQLite won't enforce ON DELETE until tables are recreated
        session.query(AccountSnapshot).filter_by(scraper_login_id=login_id).update({"scraper_login_id": None})
        session.query(AccountStatement).filter_by(scraper_login_id=login_id).update({"scraper_login_id": None})
        session.query(FinancialAccountLogin).filter_by(scraper_login_id=login_id).delete()
        session.query(ScraperLoginSyncRun).filter_by(scraper_login_id=login_id).delete()
        session.delete(login)
        session.commit()
        return {"ok": True}


@app.get("/api/logins/providers")
def list_providers():
    return sorted(scraper.PROVIDER_KEYS)


@app.get("/api/logins/provider-mappings")
def list_provider_mappings():
    """Return all user-defined provider mappings from DB."""
    return db.get_provider_mappings()


@app.delete("/api/logins/provider-mappings/{domain}")
def delete_provider_mapping(domain: str):
    """Delete a user-defined provider mapping."""
    deleted = db.delete_provider_mapping(domain)
    if not deleted:
        raise HTTPException(status_code=404, detail="Provider mapping not found")
    return {"ok": True}


class LoginSyncRequest(BaseModel):
    login_ids: Optional[list[int]] = None


class SingleLoginSyncRequest(BaseModel):
    account_filter: Optional[str] = None
    force: bool = False


@app.post("/api/logins/import/start")
async def import_start(file: UploadFile):
    """Parse CSV, match providers locally, detect duplicates. Returns session immediately."""
    content = (await file.read()).decode("utf-8-sig")
    raw_rows = scraper.parse_csv(content)

    if not raw_rows:
        return {"session_id": None, "candidates": [], "summary": {"total": 0, "duplicates": 0}}

    matched = scraper.match_providers_sync(raw_rows)

    session = scraper.create_import_session(
        filename=getattr(file, "filename", "upload.csv"),
        rows=raw_rows,
    )

    scraper.apply_matched_results(session.id, matched.get("mappings", []))

    existing: dict[tuple[str, str], scraper.ScraperLogin] = {}
    with scraper.SessionLocal() as db_session:
        for login in db_session.query(scraper.ScraperLogin).all():
            if login.username:
                existing[(login.provider_key, login.username.lower())] = login

    duplicates = 0
    for mapping in matched.get("mappings", []):
        key = (mapping.get("provider_key", ""), mapping.get("username", "").lower())
        login = existing.get(key)
        if login:
            duplicates += 1

    scraper.refresh_import_session_counts(session.id)
    candidates = scraper.get_import_candidates(session.id)

    return {
        "session_id": session.id,
        "candidates": [_candidate_to_dict(c, existing.get((c.provider_key or "", c.username.lower()))) for c in candidates],
        "summary": {
            "total": len(candidates),
            "duplicates": duplicates,
        },
    }


@app.get("/api/logins/import/{session_id}")
async def get_import_session(session_id: int):
    """Get an import session with its candidates."""
    session = scraper.get_import_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Import session not found")

    candidates = scraper.get_import_candidates(session_id)

    existing: dict[tuple[str, str], scraper.ScraperLogin] = {}
    with scraper.SessionLocal() as db_session:
        for login in db_session.query(scraper.ScraperLogin).all():
            if login.username:
                existing[(login.provider_key, login.username.lower())] = login

    return {
        "session": {
            "id": session.id,
            "filename": session.filename,
            "status": session.status,
            "total_count": session.total_count,
            "processed_count": session.processed_count,
            "created_at": session.created_at.isoformat() if session.created_at else None,
        },
        "candidates": [_candidate_to_dict(c, existing.get((c.provider_key or "", c.username.lower()))) for c in candidates],
    }


@app.post("/api/logins/import/{session_id}/confirm")
async def import_confirm(session_id: int, selected_ids: list[int]):
    """Create/update ScraperLogin from selected candidates, then delete session."""
    session = scraper.get_import_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Import session not found")

    candidates = {c.id: c for c in scraper.get_import_candidates(session_id)}
    selected = [candidates[cid] for cid in selected_ids if cid in candidates]

    imported = 0
    updated = 0

    with scraper.SessionLocal() as db_session:
        existing: dict[tuple[str, str], scraper.ScraperLogin] = {}
        for login in db_session.query(scraper.ScraperLogin).all():
            if login.username:
                existing[(login.provider_key, login.username.lower())] = login

        max_order = db_session.query(scraper.ScraperLogin).count()

        for candidate in selected:
            if not candidate.provider_key or not candidate.username:
                continue
            key = (candidate.provider_key, candidate.username.lower())
            existing_login = existing.get(key)

            if existing_login:
                existing_login.username = candidate.username
                if candidate.password:
                    existing_login.password_encrypted = scraper.encrypt(candidate.password)
                if candidate.url:
                    existing_login.login_url = candidate.url
                updated += 1
            else:
                label = candidate.label or f"{candidate.name} — {candidate.username}"
                login = scraper.ScraperLogin(
                    provider_key=candidate.provider_key,
                    label=label,
                    username=candidate.username,
                    password_encrypted=scraper.encrypt(candidate.password) if candidate.password else None,
                    login_url=candidate.url,
                    account_type=None,
                    sort_order=max_order + imported,
                )
                db_session.add(login)
                existing[key] = login
                imported += 1

        try:
            db_session.commit()
        except IntegrityError as exc:
            db_session.rollback()
            _raise_login_integrity_error(exc)

    scraper.delete_import_session(session_id)
    return {"imported": imported, "updated": updated}


@app.delete("/api/logins/import/{session_id}")
async def import_delete(session_id: int):
    """Delete an import session and all its candidates."""
    deleted = scraper.delete_import_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Import session not found")
    return {"deleted": True}


def _candidate_to_dict(candidate, existing_login) -> dict:
    return {
        "id": candidate.id,
        "row_index": candidate.row_index,
        "name": candidate.name,
        "url": candidate.url,
        "domain": candidate.domain,
        "username": candidate.username,
        "status": candidate.status,
        "provider_key": candidate.provider_key,
        "label": candidate.label,
        "account_type": candidate.account_type,
        "is_duplicate": existing_login is not None,
        "existing_login_id": existing_login.id if existing_login else None,
        "match_confidence": candidate.match_confidence,
        "match_type": candidate.match_type,
    }


@app.post("/api/logins/{login_id}/sync", response_model=LoginSyncStartResponse)
def sync_login(login_id: int, req: SingleLoginSyncRequest | None = None):
    account_filter = req.account_filter if req else None
    force = req.force if req else False
    run_id, conflict = _queue_sync_run(login_id, account_filter=account_filter, force=force)
    if conflict:
        return LoginSyncStartResponse(run_id=0, status=conflict, account_filter=account_filter)
    return LoginSyncStartResponse(run_id=run_id, status="queued", account_filter=account_filter)


@app.post("/api/logins/sync")
def sync_logins(req: LoginSyncRequest = LoginSyncRequest()):
    with scraper.SessionLocal() as session:
        query = session.query(scraper.ScraperLogin).filter(scraper.ScraperLogin.enabled.is_(True))
        if req.login_ids:
            query = query.filter(scraper.ScraperLogin.id.in_(req.login_ids))
        logins = query.order_by(scraper.ScraperLogin.sort_order, scraper.ScraperLogin.provider_key).all()
        login_ids = [login.id for login in logins]

    if not login_ids:
        raise HTTPException(status_code=400, detail="No enabled logins selected")

    runs = []
    for lid in login_ids:
        run_id = _queue_sync_run(lid)
        if run_id is not None:
            runs.append({"login_id": lid, "run_id": run_id, "status": "queued"})

    return {"runs": runs, "logins_queued": len(runs)}


@app.get("/api/sync-runs/{run_id}", response_model=LoginSyncRunResponse)
def get_sync_run(run_id: int):
    with scraper.SessionLocal() as session:
        run = session.get(scraper.ScraperLoginSyncRun, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Sync run not found")
        return _sync_run_to_response(run)



class StatementResponse(BaseModel):
    id: int
    financial_account_id: int
    statement_month: str
    statement_date: Optional[str] = None
    file_path: Optional[str] = None
    file_size_bytes: Optional[int] = None
    downloaded_at: Optional[str] = None
    intro_apr_rate: Optional[float] = None
    intro_apr_end_date: Optional[str] = None
    regular_apr: Optional[float] = None
    credit_limit: Optional[float] = None


def _statement_to_response(stmt) -> StatementResponse:
    return StatementResponse(
        id=stmt.id,
        financial_account_id=stmt.financial_account_id,
        statement_month=stmt.statement_month,
        statement_date=stmt.statement_date,
        file_path=stmt.file_path,
        file_size_bytes=stmt.file_size_bytes,
        downloaded_at=stmt.downloaded_at.isoformat() if stmt.downloaded_at else None,
        intro_apr_rate=stmt.intro_apr_rate,
        intro_apr_end_date=stmt.intro_apr_end_date,
        regular_apr=stmt.regular_apr,
        credit_limit=stmt.credit_limit,
    )


@app.get("/api/accounts/{account_id}/statements", response_model=list[StatementResponse])
def get_account_statements(account_id: int):
    statements = db.get_statements(financial_account_id=account_id)
    return [_statement_to_response(s) for s in statements]


@app.get("/api/statements/apr-summary")
def get_apr_summary():
    return db.get_apr_summary()


# ---------------------------------------------------------------------------
# Promo APR Periods
# ---------------------------------------------------------------------------

class PromoBase(BaseModel):
    financial_account_id: int
    promo_type: str = "purchase"
    apr_rate: float = 0.0
    regular_apr: Optional[float] = None
    start_date: Optional[str] = None
    end_date: str
    original_amount: Optional[float] = None
    description: Optional[str] = None
    active: bool = True


class PromoResponse(PromoBase):
    id: int
    display_name: Optional[str] = None
    account_mask: Optional[str] = None
    provider_key: Optional[str] = None
    institution: Optional[str] = None
    outstanding_balance: Optional[float] = None
    days_remaining: Optional[int] = None
    created_at: str
    updated_at: str


def _promo_to_response(promo: scraper.PromoAprPeriod, account: scraper.FinancialAccount | None = None, outstanding_balance: float | None = None) -> PromoResponse:
    from datetime import date
    days = None
    try:
        end = date.fromisoformat(promo.end_date)
        days = (end - date.today()).days
    except (ValueError, TypeError):
        pass

    return PromoResponse(
        id=promo.id,
        financial_account_id=promo.financial_account_id,
        promo_type=promo.promo_type,
        apr_rate=promo.apr_rate,
        regular_apr=promo.regular_apr,
        start_date=promo.start_date,
        end_date=promo.end_date,
        original_amount=promo.original_amount,
        description=promo.description,
        active=promo.active,
        display_name=account.display_name if account else None,
        account_mask=account.account_mask if account else None,
        provider_key=account.provider_key if account else None,
        institution=account.institution if account else None,
        outstanding_balance=outstanding_balance,
        days_remaining=days,
        created_at=promo.created_at.isoformat(),
        updated_at=promo.updated_at.isoformat(),
    )


@app.get("/api/promos", response_model=list[PromoResponse])
def list_promos(active_only: bool = False):
    with scraper.SessionLocal() as session:
        query = (
            session.query(scraper.PromoAprPeriod, scraper.FinancialAccount)
            .join(scraper.FinancialAccount, scraper.PromoAprPeriod.financial_account_id == scraper.FinancialAccount.id)
        )
        if active_only:
            query = query.filter(scraper.PromoAprPeriod.active.is_(True))
        query = query.order_by(scraper.PromoAprPeriod.end_date)
        rows = query.all()
        
        results = []
        for promo, account in rows:
            snapshot = (
                session.query(scraper.AccountSnapshot)
                .filter(scraper.AccountSnapshot.financial_account_id == account.id)
                .order_by(scraper.AccountSnapshot.captured_at.desc())
                .first()
            )
            outstanding_balance = snapshot.current_balance if snapshot else None
            results.append(_promo_to_response(promo, account, outstanding_balance))
        return results


@app.post("/api/promos", response_model=PromoResponse, status_code=201)
def create_promo(data: PromoBase):
    with scraper.SessionLocal() as session:
        account = session.get(scraper.FinancialAccount, data.financial_account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        promo = scraper.PromoAprPeriod(
            financial_account_id=data.financial_account_id,
            promo_type=data.promo_type,
            apr_rate=data.apr_rate,
            regular_apr=data.regular_apr,
            start_date=data.start_date,
            end_date=data.end_date,
            original_amount=data.original_amount,
            description=data.description,
            active=data.active,
        )
        session.add(promo)
        session.commit()
        session.refresh(promo)
        return _promo_to_response(promo, account)


@app.put("/api/promos/{promo_id}", response_model=PromoResponse)
def update_promo(promo_id: int, data: PromoBase):
    with scraper.SessionLocal() as session:
        promo = session.get(scraper.PromoAprPeriod, promo_id)
        if not promo:
            raise HTTPException(status_code=404, detail="Promo not found")
        promo.financial_account_id = data.financial_account_id
        promo.promo_type = data.promo_type
        promo.apr_rate = data.apr_rate
        promo.regular_apr = data.regular_apr
        promo.start_date = data.start_date
        promo.end_date = data.end_date
        promo.original_amount = data.original_amount
        promo.description = data.description
        promo.active = data.active
        session.commit()
        session.refresh(promo)
        account = session.get(scraper.FinancialAccount, promo.financial_account_id)
        return _promo_to_response(promo, account)


@app.delete("/api/promos/{promo_id}")
def delete_promo(promo_id: int):
    with scraper.SessionLocal() as session:
        promo = session.get(scraper.PromoAprPeriod, promo_id)
        if not promo:
            raise HTTPException(status_code=404, detail="Promo not found")
        session.delete(promo)
        session.commit()
        return {"ok": True}


@app.get("/api/account-types")
def list_account_types():
    """Account types from the DB for dropdowns."""
    from shiso.scraper.models.accounts import FinancialAccountType
    with scraper.SessionLocal() as session:
        types = session.query(FinancialAccountType).order_by(FinancialAccountType.name).all()
        return [{"id": t.id, "name": t.name, "balance_type": t.balance_type} for t in types]


@app.get("/api/accounts/list")
def list_accounts_simple():
    """Minimal account list for dropdowns."""
    with scraper.SessionLocal() as session:
        accounts = session.query(scraper.FinancialAccount).order_by(scraper.FinancialAccount.provider_key, scraper.FinancialAccount.display_name).all()
        return [
            {"id": a.id, "display_name": a.display_name, "account_mask": a.account_mask, "provider_key": a.provider_key, "institution": a.institution}
            for a in accounts
        ]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@app.get("/api/tools")
def list_registered_tools():
    """List all registered workflows (exposed as tools for API compatibility)."""
    return [
        {
            "tool_key": w.key,
            "display_name": w.name,
            "description": w.description,
            "result_key": w.result_key,
            "source": getattr(w, "source", "memory"),
        }
        for w in scraper.list_workflows()
    ]


class WorkflowFieldSpec(BaseModel):
    name: str
    type: str
    nullable: bool = False
    default: Any | None = None


class WorkflowDefinitionBase(BaseModel):
    name: str
    description: str = ""
    prompt_template: str
    result_key: str = "items"
    output_schema_json: list[WorkflowFieldSpec]


class WorkflowDefinitionResponse(WorkflowDefinitionBase):
    key: str
    source: str = "db"


class WorkflowDraftRequest(BaseModel):
    brief: str
    example_items: list[dict[str, Any]] = Field(default_factory=list)
    existing_key: Optional[str] = None


class WorkflowDraftResponse(WorkflowDefinitionResponse):
    rationale: Optional[str] = None


class WorkflowSuggestionResponse(BaseModel):
    id: int
    tool_key: str
    provider_key: str
    sync_run_id: Optional[int] = None
    status: str
    trigger_reason: str
    rationale: Optional[str] = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    suggested_definition: WorkflowDraftResponse
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class WorkflowSuggestionStatusRequest(BaseModel):
    status: str


def _workflow_to_response(workflow) -> WorkflowDefinitionResponse:
    return WorkflowDefinitionResponse(
        key=workflow.key,
        name=workflow.name,
        description=workflow.description,
        prompt_template=workflow.prompt_template,
        result_key=workflow.result_key,
        output_schema_json=[WorkflowFieldSpec(**field) for field in (workflow.schema_spec or [])],
        source=getattr(workflow, "source", "memory"),
    )


def _draft_to_response(draft: dict[str, Any]) -> WorkflowDraftResponse:
    return WorkflowDraftResponse(
        key=draft["key"],
        name=draft["name"],
        description=draft["description"],
        prompt_template=draft["prompt_template"],
        result_key=draft["result_key"],
        output_schema_json=[WorkflowFieldSpec(**field) for field in draft["output_schema_json"]],
        source="draft",
        rationale=draft.get("rationale"),
    )


def _workflow_suggestion_to_response(suggestion) -> WorkflowSuggestionResponse:
    return WorkflowSuggestionResponse(
        id=suggestion.id,
        tool_key=suggestion.tool_key,
        provider_key=suggestion.provider_key,
        sync_run_id=suggestion.sync_run_id,
        status=suggestion.status,
        trigger_reason=suggestion.trigger_reason,
        rationale=suggestion.rationale,
        metrics=suggestion.metrics or {},
        suggested_definition=_draft_to_response(suggestion.suggested_definition),
        created_at=suggestion.created_at,
        updated_at=suggestion.updated_at,
    )


@app.get("/api/tools/suggestions", response_model=list[WorkflowSuggestionResponse])
def list_tool_suggestions(status: Optional[str] = "open", tool_key: Optional[str] = None):
    suggestions = scraper.list_workflow_revision_suggestions(status=status, tool_key=tool_key)
    return [_workflow_suggestion_to_response(suggestion) for suggestion in suggestions]


@app.post("/api/tools/suggestions/{suggestion_id}/status", response_model=WorkflowSuggestionResponse)
def update_tool_suggestion_status(suggestion_id: int, req: WorkflowSuggestionStatusRequest):
    try:
        suggestion = scraper.update_workflow_revision_suggestion_status(suggestion_id, req.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not suggestion:
        raise HTTPException(status_code=404, detail="Workflow suggestion not found")
    return _workflow_suggestion_to_response(suggestion)


@app.get("/api/tools/{tool_key}", response_model=WorkflowDefinitionResponse)
def get_tool_definition(tool_key: str):
    workflow = scraper.get_workflow(tool_key)
    if not workflow:
        raise HTTPException(status_code=404, detail="Tool not found")
    return _workflow_to_response(workflow)


@app.post("/api/tools/draft", response_model=WorkflowDraftResponse)
async def draft_tool_definition(req: WorkflowDraftRequest):
    existing_workflow = scraper.get_workflow(req.existing_key) if req.existing_key else None
    draft = await scraper.draft_workflow_definition(
        req.brief,
        example_items=req.example_items,
        existing_workflow=existing_workflow,
    )
    if not draft:
        raise HTTPException(status_code=502, detail="Failed to draft tool definition")
    return _draft_to_response(draft)


@app.put("/api/tools/{tool_key}", response_model=WorkflowDefinitionResponse)
def save_tool_definition(tool_key: str, data: WorkflowDefinitionBase):
    workflow = scraper.save_workflow_definition(
        tool_key,
        name=data.name,
        description=data.description,
        prompt_template=data.prompt_template,
        result_key=data.result_key,
        output_schema_json=[field.model_dump(exclude_none=False) for field in data.output_schema_json],
    )
    return _workflow_to_response(workflow)


@app.delete("/api/tools/{tool_key}")
def delete_tool_definition(tool_key: str):
    deleted = scraper.delete_workflow_definition(tool_key)
    return {"ok": deleted}


@app.get("/api/tools/{tool_key}/runs")
def list_tool_runs(tool_key: str, limit: int = 20):
    """Recent ToolRunOutput rows for a specific tool."""
    with scraper.SessionLocal() as session:
        runs = (
            session.query(scraper.ToolRunOutput)
            .filter(scraper.ToolRunOutput.tool_key == tool_key)
            .order_by(scraper.ToolRunOutput.created_at.desc())
            .limit(max(1, min(limit, 100)))
            .all()
        )
        return [
            {
                "id": r.id,
                "tool_key": r.tool_key,
                "sync_run_id": r.sync_run_id,
                "scraper_login_id": r.scraper_login_id,
                "provider_key": r.provider_key,
                "output_json": r.output_json,
                "items_count": r.items_count,
                "created_at": r.created_at.isoformat(),
            }
            for r in runs
        ]


# ---------------------------------------------------------------------------
# Interactive Auth
# ---------------------------------------------------------------------------

@dataclass
class InteractiveAuthSessionState:
    login_id: int
    provider_key: str
    status: str = "idle"
    message: str = ""
    prompt: str | None = None
    pending_response: str | None = None
    response_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class InteractiveAuthStatusResponse(BaseModel):
    login_id: int
    provider_key: Optional[str] = None
    status: str
    message: str
    prompt: Optional[str] = None
    updated_at: Optional[str] = None


class InteractiveAuthRespondRequest(BaseModel):
    response: Optional[str] = None
    skip: bool = False


_interactive_auth_sessions: dict[int, InteractiveAuthSessionState] = {}
_interactive_auth_lock = threading.Lock()
_INTERACTIVE_AUTH_TERMINAL_STATUSES = {"completed", "failed", "skipped"}


def _interactive_auth_response(session: InteractiveAuthSessionState) -> InteractiveAuthStatusResponse:
    return InteractiveAuthStatusResponse(
        login_id=session.login_id,
        provider_key=session.provider_key,
        status=session.status,
        message=session.message,
        prompt=session.prompt,
        updated_at=session.updated_at,
    )


def _set_interactive_auth_state(
    session: InteractiveAuthSessionState,
    *,
    status: str | None = None,
    message: str | None = None,
    prompt: str | None = None,
) -> None:
    if status is not None:
        session.status = status
    if message is not None:
        session.message = message
    session.prompt = prompt
    session.updated_at = datetime.now(timezone.utc).isoformat()


def _run_interactive_auth_session(login_id: int) -> None:
    from shiso.scraper.agent import auth as auth_module

    async def _wait_for_human_response(prompt: str) -> str:
        while True:
            with _interactive_auth_lock:
                session = _interactive_auth_sessions.get(login_id)
                if session is None:
                    return "skip"
                _set_interactive_auth_state(
                    session,
                    status="awaiting_input",
                    message="The agent needs your help to continue authentication.",
                    prompt=prompt,
                )
                session.pending_response = None
                session.response_event.clear()
                wait_event = session.response_event

            await asyncio.get_running_loop().run_in_executor(None, wait_event.wait)

            with _interactive_auth_lock:
                session = _interactive_auth_sessions.get(login_id)
                if session is None:
                    return "skip"
                response = session.pending_response
                session.pending_response = None
                session.response_event.clear()
                if response is None:
                    continue
                return response

    def _status_callback(status: str, message: str) -> None:
        with _interactive_auth_lock:
            session = _interactive_auth_sessions.get(login_id)
            if session is None:
                return
            prompt = session.prompt if status == "awaiting_input" else None
            _set_interactive_auth_state(session, status=status, message=message, prompt=prompt)

    try:
        result = asyncio.run(
            auth_module.interactive_auth_login(
                login_id,
                human_input_handler=_wait_for_human_response,
                status_callback=_status_callback,
            )
        )
    except Exception as exc:
        logger.exception("Interactive auth session crashed for login %s", login_id)
        result = {"status": "failed", "message": str(exc), "provider_key": None}

    with _interactive_auth_lock:
        session = _interactive_auth_sessions.get(login_id)
        if session is None:
            return
        _set_interactive_auth_state(
            session,
            status=str(result.get("status") or "failed"),
            message=str(result.get("message") or "Interactive auth finished."),
            prompt=None,
        )


@app.get("/api/logins/problems")
def get_problem_logins():
    """Get logins that need attention (needs_2fa or login_failed)."""
    with scraper.SessionLocal() as session:
        logins = (
            session.query(scraper.ScraperLogin)
            .filter(scraper.ScraperLogin.last_auth_status.in_(["needs_2fa", "login_failed"]))
            .order_by(scraper.ScraperLogin.provider_key)
            .all()
        )
        return [_login_to_response(l) for l in logins]


@app.post("/api/logins/{login_id}/interactive", response_model=InteractiveAuthStatusResponse)
def start_interactive_auth(login_id: int):
    """Start or resume an interactive auth session for one login."""
    with scraper.SessionLocal() as session:
        login = session.get(scraper.ScraperLogin, login_id)
        if not login:
            raise HTTPException(status_code=404, detail="Login not found")
        if not login.enabled:
            raise HTTPException(status_code=400, detail="Login is disabled")

        provider_key = login.provider_key

    with _interactive_auth_lock:
        existing = _interactive_auth_sessions.get(login_id)
        if existing and existing.status not in _INTERACTIVE_AUTH_TERMINAL_STATUSES:
            return _interactive_auth_response(existing)

        interactive_session = InteractiveAuthSessionState(
            login_id=login_id,
            provider_key=provider_key,
            status="starting",
            message=f"Starting interactive auth for {provider_key}. Check the browser window.",
        )
        thread = threading.Thread(
            target=_run_interactive_auth_session,
            args=(login_id,),
            daemon=True,
            name=f"interactive-auth-{login_id}",
        )
        interactive_session.thread = thread
        _interactive_auth_sessions[login_id] = interactive_session
        thread.start()
        return _interactive_auth_response(interactive_session)


@app.get("/api/logins/{login_id}/interactive", response_model=InteractiveAuthStatusResponse)
def get_interactive_auth_status(login_id: int):
    """Check if an interactive auth session is still running."""
    with _interactive_auth_lock:
        session = _interactive_auth_sessions.get(login_id)
        if not session:
            return InteractiveAuthStatusResponse(
                login_id=login_id,
                status="idle",
                message="No interactive auth session running.",
            )
        return _interactive_auth_response(session)


@app.post("/api/logins/{login_id}/interactive/respond", response_model=InteractiveAuthStatusResponse)
def respond_interactive_auth(login_id: int, req: InteractiveAuthRespondRequest):
    """Relay a 2FA code, answer, or skip decision back to the interactive auth agent."""
    with _interactive_auth_lock:
        session = _interactive_auth_sessions.get(login_id)
        if not session:
            raise HTTPException(status_code=404, detail="No interactive auth session found")
        if session.status != "awaiting_input":
            raise HTTPException(status_code=409, detail=f"Interactive auth is not waiting for input (status: {session.status})")

        response_text = "skip" if req.skip else str(req.response or "").strip()
        if not response_text:
            raise HTTPException(status_code=400, detail="A response is required unless you choose skip")

        session.pending_response = response_text
        _set_interactive_auth_state(
            session,
            status="running",
            message="Response received. Continuing in the browser.",
            prompt=None,
        )
        session.response_event.set()
        return _interactive_auth_response(session)


# ---------------------------------------------------------------------------
# Agent Sessions — generalized human-in-the-loop for any running agent
# ---------------------------------------------------------------------------

@dataclass
class AgentSessionState:
    """Tracks a human-in-the-loop channel for a running sync/agent task."""
    run_id: int
    login_id: int
    provider_key: str
    status: str = "idle"  # idle | running | awaiting_input | completed | failed
    message: str = ""
    prompt: str | None = None
    pending_response: str | None = None
    response_event: threading.Event = field(default_factory=threading.Event)
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AgentSessionResponse(BaseModel):
    run_id: int
    login_id: int
    provider_key: Optional[str] = None
    status: str
    message: str
    prompt: Optional[str] = None
    updated_at: Optional[str] = None


class AgentSessionRespondRequest(BaseModel):
    response: Optional[str] = None
    skip: bool = False


_agent_sessions: dict[int, AgentSessionState] = {}  # keyed by run_id
_agent_sessions_lock = threading.Lock()


def _agent_session_response(session: AgentSessionState) -> AgentSessionResponse:
    return AgentSessionResponse(
        run_id=session.run_id,
        login_id=session.login_id,
        provider_key=session.provider_key,
        status=session.status,
        message=session.message,
        prompt=session.prompt,
        updated_at=session.updated_at,
    )


def create_agent_session(run_id: int, login_id: int, provider_key: str) -> AgentSessionState:
    """Create or retrieve an agent session for a sync run.

    Called by the worker when starting a run so the dashboard can communicate
    with the agent in real time.
    """
    with _agent_sessions_lock:
        existing = _agent_sessions.get(run_id)
        if existing:
            return existing
        session = AgentSessionState(
            run_id=run_id,
            login_id=login_id,
            provider_key=provider_key,
            status="running",
            message=f"Sync running for {provider_key}.",
        )
        _agent_sessions[run_id] = session
        return session


def build_human_input_handler(run_id: int) -> Any:
    """Build an async handler the scraper agent can call to request user help.

    Returns an async callable that:
    1. Sets the session status to awaiting_input with the agent's prompt
    2. Waits for the user to respond via the API
    3. Returns the user's response to the agent
    """
    import asyncio

    async def handler(prompt: str) -> str:
        while True:
            with _agent_sessions_lock:
                session = _agent_sessions.get(run_id)
                if session is None:
                    return "skip"
                session.status = "awaiting_input"
                session.message = "The agent needs your help to continue."
                session.prompt = prompt
                session.pending_response = None
                session.response_event.clear()
                session.updated_at = datetime.now(timezone.utc).isoformat()
                wait_event = session.response_event

            await asyncio.get_running_loop().run_in_executor(None, wait_event.wait)

            with _agent_sessions_lock:
                session = _agent_sessions.get(run_id)
                if session is None:
                    return "skip"
                response = session.pending_response
                session.pending_response = None
                session.response_event.clear()
                if response is None:
                    continue
                session.status = "running"
                session.message = "Response received. Continuing."
                session.prompt = None
                session.updated_at = datetime.now(timezone.utc).isoformat()
                return response

    return handler


def complete_agent_session(run_id: int, *, status: str = "completed", message: str = "") -> None:
    """Mark an agent session as finished (called by the worker when a run ends)."""
    with _agent_sessions_lock:
        session = _agent_sessions.get(run_id)
        if session:
            session.status = status
            session.message = message or f"Run {status}."
            session.prompt = None
            session.updated_at = datetime.now(timezone.utc).isoformat()


@app.get("/api/agent-sessions", response_model=list[AgentSessionResponse])
def list_agent_sessions():
    """List all active (non-terminal) agent sessions."""
    with _agent_sessions_lock:
        return [
            _agent_session_response(s)
            for s in _agent_sessions.values()
            if s.status not in ("completed", "failed", "idle")
        ]


@app.get("/api/agent-sessions/{run_id}", response_model=AgentSessionResponse)
def get_agent_session(run_id: int):
    """Get the status of an agent session by run_id."""
    with _agent_sessions_lock:
        session = _agent_sessions.get(run_id)
        if not session:
            return AgentSessionResponse(
                run_id=run_id,
                login_id=0,
                status="idle",
                message="No agent session for this run.",
            )
        return _agent_session_response(session)


@app.post("/api/agent-sessions/{run_id}/respond", response_model=AgentSessionResponse)
def respond_agent_session(run_id: int, req: AgentSessionRespondRequest):
    """Send a response (or skip) to a waiting agent."""
    with _agent_sessions_lock:
        session = _agent_sessions.get(run_id)
        if not session:
            raise HTTPException(status_code=404, detail="No agent session found")
        if session.status != "awaiting_input":
            raise HTTPException(
                status_code=409,
                detail=f"Agent is not waiting for input (status: {session.status})",
            )

        response_text = "skip" if req.skip else str(req.response or "").strip()
        if not response_text:
            raise HTTPException(status_code=400, detail="A response is required unless you choose skip")

        session.pending_response = response_text
        session.status = "running"
        session.message = "Response received. Continuing."
        session.prompt = None
        session.updated_at = datetime.now(timezone.utc).isoformat()
        session.response_event.set()
        return _agent_session_response(session)


# --- Worker-facing endpoints (called by the worker process via HTTP) ---


class AgentSessionCreateRequest(BaseModel):
    run_id: int
    login_id: int
    provider_key: str


class AgentSessionAwaitRequest(BaseModel):
    prompt: str


class AgentSessionCompleteRequest(BaseModel):
    status: str = "completed"
    message: str = ""


class AgentSessionPollResponse(BaseModel):
    response: str


@app.post("/api/agent-sessions", response_model=AgentSessionResponse, status_code=201)
def create_agent_session_endpoint(req: AgentSessionCreateRequest):
    """Register a new agent session (called by the worker at run start)."""
    session = create_agent_session(req.run_id, req.login_id, req.provider_key)
    return _agent_session_response(session)


@app.put("/api/agent-sessions/{run_id}/await", response_model=AgentSessionResponse)
def set_agent_session_awaiting(run_id: int, req: AgentSessionAwaitRequest):
    """Set a session to awaiting_input with a prompt (called by the worker)."""
    with _agent_sessions_lock:
        session = _agent_sessions.get(run_id)
        if not session:
            raise HTTPException(status_code=404, detail="No agent session found")
        session.status = "awaiting_input"
        session.message = "The agent needs your help to continue."
        session.prompt = req.prompt
        session.pending_response = None
        session.response_event.clear()
        session.updated_at = datetime.now(timezone.utc).isoformat()
        return _agent_session_response(session)


@app.get("/api/agent-sessions/{run_id}/poll-response")
def poll_agent_session_response(run_id: int):
    """Long-poll for a user response (called by the worker).

    Blocks for up to 30 seconds. Returns 200 with response text when
    the user responds, or 204 if no response yet.
    """
    with _agent_sessions_lock:
        session = _agent_sessions.get(run_id)
        if not session:
            raise HTTPException(status_code=404, detail="No agent session found")
        wait_event = session.response_event

    # Block up to 30s waiting for user response
    got_response = wait_event.wait(timeout=30)

    if not got_response:
        return Response(status_code=204)

    with _agent_sessions_lock:
        session = _agent_sessions.get(run_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session gone")
        response = session.pending_response
        session.pending_response = None
        session.response_event.clear()
        if response is None:
            return Response(status_code=204)
        return JSONResponse({"response": response})


@app.put("/api/agent-sessions/{run_id}/complete", response_model=AgentSessionResponse)
def complete_agent_session_endpoint(run_id: int, req: AgentSessionCompleteRequest):
    """Mark a session as completed/failed (called by the worker)."""
    complete_agent_session(run_id, status=req.status, message=req.message)
    with _agent_sessions_lock:
        session = _agent_sessions.get(run_id)
        if session:
            return _agent_session_response(session)
    return AgentSessionResponse(
        run_id=run_id,
        login_id=0,
        status=req.status,
        message=req.message,
    )


# ---------------------------------------------------------------------------
# Rewards Programs
# ---------------------------------------------------------------------------

class RewardsProgramBase(BaseModel):
    scraper_login_id: int
    financial_account_id: Optional[int] = None
    program_name: str
    program_type: str = "points"
    membership_id: Optional[str] = None
    unit_name: Optional[str] = None
    cents_per_unit: Optional[float] = None
    current_balance: Optional[float] = None
    active: bool = True


class RewardsProgramResponse(RewardsProgramBase):
    id: int
    display_icon_url: Optional[str] = None
    created_at: str
    updated_at: str


@app.get("/api/rewards", response_model=list[RewardsProgramResponse])
def list_rewards_programs():
    """List all rewards programs."""
    with scraper.SessionLocal() as session:
        programs = session.query(scraper.RewardsProgram).order_by(scraper.RewardsProgram.program_name).all()
        return [
            RewardsProgramResponse(
                id=p.id,
                scraper_login_id=p.scraper_login_id,
                financial_account_id=p.financial_account_id,
                program_name=p.program_name,
                program_type=p.program_type,
                membership_id=p.membership_id,
                unit_name=p.unit_name,
                cents_per_unit=p.cents_per_unit,
                current_balance=p.current_balance,
                display_icon_url=p.display_icon_url,
                active=p.active,
                created_at=p.created_at.isoformat(),
                updated_at=p.updated_at.isoformat(),
            )
            for p in programs
        ]


@app.post("/api/rewards", response_model=RewardsProgramResponse, status_code=201)
def create_rewards_program(data: RewardsProgramBase):
    """Create a new rewards program."""
    with scraper.SessionLocal() as session:
        login = session.get(scraper.ScraperLogin, data.scraper_login_id)
        if not login:
            raise HTTPException(status_code=404, detail="Scraper login not found")
        if data.financial_account_id is not None:
            account = session.get(scraper.FinancialAccount, data.financial_account_id)
            if not account:
                raise HTTPException(status_code=404, detail="Financial account not found")
        program = scraper.RewardsProgram(
            scraper_login_id=data.scraper_login_id,
            financial_account_id=data.financial_account_id,
            program_name=data.program_name,
            program_type=data.program_type,
            membership_id=data.membership_id,
            unit_name=data.unit_name,
            cents_per_unit=data.cents_per_unit,
            current_balance=data.current_balance,
            active=data.active,
        )
        session.add(program)
        session.commit()
        session.refresh(program)
        return RewardsProgramResponse(
            id=program.id,
            scraper_login_id=program.scraper_login_id,
            financial_account_id=program.financial_account_id,
            program_name=program.program_name,
            program_type=program.program_type,
            membership_id=program.membership_id,
            unit_name=program.unit_name,
            cents_per_unit=program.cents_per_unit,
            current_balance=program.current_balance,
            display_icon_url=program.display_icon_url,
            active=program.active,
            created_at=program.created_at.isoformat(),
            updated_at=program.updated_at.isoformat(),
        )


@app.put("/api/rewards/{program_id}", response_model=RewardsProgramResponse)
def update_rewards_program(program_id: int, data: RewardsProgramBase):
    """Update a rewards program."""
    with scraper.SessionLocal() as session:
        program = session.get(scraper.RewardsProgram, program_id)
        if not program:
            raise HTTPException(status_code=404, detail="Rewards program not found")
        login = session.get(scraper.ScraperLogin, data.scraper_login_id)
        if not login:
            raise HTTPException(status_code=404, detail="Scraper login not found")
        if data.financial_account_id is not None:
            account = session.get(scraper.FinancialAccount, data.financial_account_id)
            if not account:
                raise HTTPException(status_code=404, detail="Financial account not found")
        program.scraper_login_id = data.scraper_login_id
        program.financial_account_id = data.financial_account_id
        program.program_name = data.program_name
        program.program_type = data.program_type
        program.membership_id = data.membership_id
        program.unit_name = data.unit_name
        program.cents_per_unit = data.cents_per_unit
        program.current_balance = data.current_balance
        program.active = data.active
        session.commit()
        session.refresh(program)
        return RewardsProgramResponse(
            id=program.id,
            scraper_login_id=program.scraper_login_id,
            financial_account_id=program.financial_account_id,
            program_name=program.program_name,
            program_type=program.program_type,
            membership_id=program.membership_id,
            unit_name=program.unit_name,
            cents_per_unit=program.cents_per_unit,
            current_balance=program.current_balance,
            display_icon_url=program.display_icon_url,
            active=program.active,
            created_at=program.created_at.isoformat(),
            updated_at=program.updated_at.isoformat(),
        )


@app.delete("/api/rewards/{program_id}")
def delete_rewards_program(program_id: int):
    """Delete a rewards program."""
    with scraper.SessionLocal() as session:
        program = session.get(scraper.RewardsProgram, program_id)
        if not program:
            raise HTTPException(status_code=404, detail="Rewards program not found")
        session.delete(program)
        session.commit()
        return {"ok": True}


@app.get("/api/rewards/summary")
def get_rewards_summary():
    """Get summary of all rewards programs with latest balances."""
    return db.get_rewards_summary()


scraper.init_db()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "shiso.dashboard.main:app",
        host="0.0.0.0",
        port=8002,
        reload=True,
        reload_dirs=["shiso"],
        reload_excludes=[
            "tests/*",
            "data/*",
            ".venv/*",
            "shiso/dashboard/frontend/node_modules/*",
            "shiso/dashboard/frontend/dist/*",
        ],
    )
