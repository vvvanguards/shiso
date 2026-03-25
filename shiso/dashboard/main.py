"""
Shiso dashboard API.

The API only reads/writes to the database. Sync runs are queued as DB rows
and processed by the standalone worker (shiso.scraper.worker).
"""

from datetime import datetime
from typing import Optional

import logging

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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


def _queue_sync_run(login_id: int, force: bool = False) -> tuple[int | None, str | None]:
    """Create a sync run record with status=queued.

    Returns (run_id, conflict_status) where conflict_status is None on success,
    'already_queued' if a run is queued/running and force=False,
    'running' if a run is actively executing and force=True was passed.
    """
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
            status="queued",
            started_at=datetime.utcnow(),
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        return (run.id, None)


class SnapshotResponse(BaseModel):
    provider_key: str
    institution: str
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
        generated_at=datetime.utcnow().isoformat(),
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
    account_type: str
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


@app.post("/api/logins/import/preview")
async def import_preview(file: UploadFile):
    content = (await file.read()).decode("utf-8-sig")
    result = scraper.parse_csv(content)

    # Build lookup of existing logins by (provider_key, username)
    with scraper.SessionLocal() as session:
        existing: dict[tuple[str, str], int] = {}
        for login in session.query(scraper.ScraperLogin).all():
            if login.username:
                existing[(login.provider_key, login.username.lower())] = login.id

    # Strip passwords and flag duplicates
    for row in result["matched"]:
        row["has_password"] = bool(row.pop("password", None))
        key = (row["provider_key"], row["username"].lower())
        row["is_duplicate"] = key in existing
        row["existing_login_id"] = existing.get(key)
    return result


class ImportRequest(BaseModel):
    rows: list[dict]


class LoginSyncRequest(BaseModel):
    login_ids: Optional[list[int]] = None


@app.post("/api/logins/import")
async def import_logins(file: UploadFile, selected: str = "", overwrite: str = ""):
    """Import selected rows from a Chrome passwords CSV.

    `selected` is a comma-separated list of row_ids to import.
    `overwrite` is a comma-separated list of row_ids to overwrite (update existing credentials).
    """
    content = (await file.read()).decode("utf-8-sig")
    result = scraper.parse_csv(content)

    selected_ids = {int(x) for x in selected.split(",") if x.strip()}
    overwrite_ids = {int(x) for x in overwrite.split(",") if x.strip()}
    if not selected_ids and not overwrite_ids:
        raise HTTPException(400, "No rows selected")

    all_matched = {r["row_id"]: r for r in result["matched"]}

    with scraper.SessionLocal() as session:
        # Build lookup of existing logins
        existing: dict[tuple[str, str], scraper.ScraperLogin] = {}
        for login in session.query(scraper.ScraperLogin).all():
            if login.username:
                existing[(login.provider_key, login.username.lower())] = login

        imported = 0
        updated = 0
        skipped = 0
        max_order = session.query(scraper.ScraperLogin).count()

        for row_id in selected_ids | overwrite_ids:
            row = all_matched.get(row_id)
            if not row:
                continue
            key = (row["provider_key"], row["username"].lower())
            existing_login = existing.get(key)

            if existing_login:
                if row_id in overwrite_ids:
                    # Update credentials on existing login
                    existing_login.username = row["username"]
                    if row.get("password"):
                        existing_login.password_encrypted = scraper.encrypt(row["password"])
                    if row.get("url"):
                        existing_login.login_url = row["url"]
                    updated += 1
                else:
                    skipped += 1
            else:
                login = scraper.ScraperLogin(
                    provider_key=row["provider_key"],
                    label=f'{row["provider_label"]} — {row["username"]}',
                    username=row["username"],
                    password_encrypted=scraper.encrypt(row["password"]) if row.get("password") else None,
                    login_url=row["url"],
                    account_type=row["account_type"],
                    sort_order=max_order + imported,
                )
                session.add(login)
                existing[key] = login
                imported += 1
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            _raise_login_integrity_error(exc)

    return {"imported": imported, "updated": updated, "skipped": skipped}


@app.post("/api/logins/{login_id}/sync", response_model=LoginSyncStartResponse)
def sync_login(login_id: int, force: bool = False):
    run_id, conflict = _queue_sync_run(login_id, force=force)
    if conflict:
        return LoginSyncStartResponse(run_id=0, status=conflict)
    return LoginSyncStartResponse(run_id=run_id, status="queued")


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
    # Denormalized account info for display
    display_name: Optional[str] = None
    account_mask: Optional[str] = None
    provider_key: Optional[str] = None
    institution: Optional[str] = None
    days_remaining: Optional[int] = None
    created_at: str
    updated_at: str


def _promo_to_response(promo: scraper.PromoAprPeriod, account: scraper.FinancialAccount | None = None) -> PromoResponse:
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
        return [_promo_to_response(promo, account) for promo, account in rows]


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
        {"tool_key": w.key, "display_name": w.name, "description": w.description}
        for w in scraper.list_workflows()
    ]


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

import subprocess
import sys
import threading
from pathlib import Path

# Track running interactive auth sessions (thread-safe)
_interactive_auth_sessions: dict[int, subprocess.Popen] = {}
_interactive_auth_lock = threading.Lock()


def _cleanup_old_process(login_id: int) -> None:
    """Clean up a finished process from memory."""
    if login_id in _interactive_auth_sessions:
        proc = _interactive_auth_sessions[login_id]
        if proc.poll() is not None:
            del _interactive_auth_sessions[login_id]


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


@app.post("/api/logins/{login_id}/interactive")
def start_interactive_auth(login_id: int):
    """Start an interactive auth session for a login that needs 2FA or failed.

    This spawns a browser-use agent to attempt login with human assistance for 2FA.
    Returns immediately with a status; poll GET /api/logins/{login_id}/interactive for updates.
    """
    with scraper.SessionLocal() as session:
        login = session.get(scraper.ScraperLogin, login_id)
        if not login:
            raise HTTPException(status_code=404, detail="Login not found")
        if not login.enabled:
            raise HTTPException(status_code=400, detail="Login is disabled")

        provider_key = login.provider_key

    with _interactive_auth_lock:
        # Clean up any finished process for this login
        _cleanup_old_process(login_id)

        # Check if already running
        if login_id in _interactive_auth_sessions:
            return {"status": "running", "message": f"Interactive auth already in progress for {provider_key}"}

        # Run the auth CLI as a subprocess (inherit stdout/stderr to avoid pipe deadlock)
        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "shiso.scraper.agent.auth", "login", provider_key],
                cwd=str(Path(__file__).parent.parent.parent),
            )
            _interactive_auth_sessions[login_id] = proc
            return {"status": "started", "message": f"Interactive auth started for {provider_key}. Check browser window for login prompts."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to start interactive auth: {str(e)}")


@app.get("/api/logins/{login_id}/interactive")
def get_interactive_auth_status(login_id: int):
    """Check if an interactive auth session is still running."""
    with _interactive_auth_lock:
        if login_id not in _interactive_auth_sessions:
            return {"status": "idle", "message": "No interactive auth session running"}

        proc = _interactive_auth_sessions[login_id]
        poll_result = proc.poll()

        if poll_result is None:
            return {"status": "running", "message": "Interactive auth in progress. Check browser window."}

        # Process finished - clean up
        del _interactive_auth_sessions[login_id]

        if poll_result == 0:
            return {"status": "completed", "message": "Interactive auth completed successfully. Refresh to see updated status."}
        else:
            return {"status": "failed", "message": f"Interactive auth exited with code {poll_result}"}


# ---------------------------------------------------------------------------
# Rewards Programs
# ---------------------------------------------------------------------------

class RewardsProgramBase(BaseModel):
    financial_account_id: int
    program_name: str
    program_type: str = "points"
    unit_name: Optional[str] = None
    cents_per_unit: Optional[float] = None
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
                financial_account_id=p.financial_account_id,
                program_name=p.program_name,
                program_type=p.program_type,
                unit_name=p.unit_name,
                cents_per_unit=p.cents_per_unit,
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
        account = session.get(scraper.FinancialAccount, data.financial_account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        program = scraper.RewardsProgram(
            financial_account_id=data.financial_account_id,
            program_name=data.program_name,
            program_type=data.program_type,
            unit_name=data.unit_name,
            cents_per_unit=data.cents_per_unit,
            active=data.active,
        )
        session.add(program)
        session.commit()
        session.refresh(program)
        return RewardsProgramResponse(
            id=program.id,
            financial_account_id=program.financial_account_id,
            program_name=program.program_name,
            program_type=program.program_type,
            unit_name=program.unit_name,
            cents_per_unit=program.cents_per_unit,
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
        program.financial_account_id = data.financial_account_id
        program.program_name = data.program_name
        program.program_type = data.program_type
        program.unit_name = data.unit_name
        program.cents_per_unit = data.cents_per_unit
        program.active = data.active
        session.commit()
        session.refresh(program)
        return RewardsProgramResponse(
            id=program.id,
            financial_account_id=program.financial_account_id,
            program_name=program.program_name,
            program_type=program.program_type,
            unit_name=program.unit_name,
            cents_per_unit=program.cents_per_unit,
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

    uvicorn.run("shiso.dashboard.main:app", host="0.0.0.0", port=8002, reload=True)
