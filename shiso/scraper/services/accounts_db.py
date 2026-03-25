"""
Persistence helpers for scraped financial accounts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import SessionLocal, init_db
from ..models.accounts import (
    AccountSnapshot,
    AccountStatement,
    FinancialAccount,
    FinancialAccountIdentifier,
    FinancialAccountLogin,
    FinancialAccountType,
    ImportCandidate,
    ImportSession,
    PromoAprPeriod,
    ProviderMapping,
    RewardsProgram,
    RewardsBalance,
    ScraperLogin,
)

BASELINE_PROVIDERS = [
    {"domain_pattern": "chase.com", "provider_key": "chase", "label": "Chase", "account_type": "Credit Card"},
    {"domain_pattern": "americanexpress.com", "provider_key": "amex", "label": "Amex", "account_type": "Credit Card"},
    {"domain_pattern": "citi.com", "provider_key": "citi", "label": "Citi", "account_type": "Credit Card"},
    {"domain_pattern": "citicards.com", "provider_key": "citi", "label": "Citi", "account_type": "Credit Card"},
    {"domain_pattern": "capitalone.com", "provider_key": "capital_one", "label": "Capital One", "account_type": "Financial"},
    {"domain_pattern": "discover.com", "provider_key": "discover", "label": "Discover", "account_type": "Credit Card"},
    {"domain_pattern": "barclays.com", "provider_key": "barclays", "label": "Barclays", "account_type": "Credit Card"},
    {"domain_pattern": "bfrb.bankofamerica.com", "provider_key": "bofa", "label": "Bank of America", "account_type": "Credit Card"},
    {"domain_pattern": "nipsco.com", "provider_key": "nipsco", "label": "NIPSCO", "account_type": "Utility"},
    {"domain_pattern": "amwater.com", "provider_key": "american_water", "label": "American Water", "account_type": "Utility"},
    {"domain_pattern": "indianaamericanwater.com", "provider_key": "american_water", "label": "American Water", "account_type": "Utility"},
    {"domain_pattern": "duke-energy.com", "provider_key": "duke_energy", "label": "Duke Energy", "account_type": "Utility"},
    {"domain_pattern": "xfinity.com", "provider_key": "xfinity", "label": "Xfinity", "account_type": "Utility"},
    {"domain_pattern": "comcast.com", "provider_key": "xfinity", "label": "Xfinity", "account_type": "Utility"},
    {"domain_pattern": "att.com", "provider_key": "att", "label": "AT&T", "account_type": "Utility"},
    {"domain_pattern": "verizon.com", "provider_key": "verizon", "label": "Verizon", "account_type": "Utility"},
    {"domain_pattern": "t-mobile.com", "provider_key": "tmobile", "label": "T-Mobile", "account_type": "Utility"},
    {"domain_pattern": "spectrum.com", "provider_key": "spectrum", "label": "Spectrum", "account_type": "Utility"},
    {"domain_pattern": "geico.com", "provider_key": "geico", "label": "GEICO", "account_type": "Other"},
    {"domain_pattern": "progressive.com", "provider_key": "progressive", "label": "Progressive", "account_type": "Other"},
    {"domain_pattern": "statefarm.com", "provider_key": "state_farm", "label": "State Farm", "account_type": "Other"},
    {"domain_pattern": "ally.com", "provider_key": "ally", "label": "Ally", "account_type": "Bank"},
    {"domain_pattern": "sofi.com", "provider_key": "sofi", "label": "SoFi", "account_type": "Bank"},
    {"domain_pattern": "marcus.com", "provider_key": "marcus", "label": "Marcus", "account_type": "Bank"},
    {"domain_pattern": "truist.com", "provider_key": "truist", "label": "Truist", "account_type": "Bank"},
    {"domain_pattern": "tiaabank.com", "provider_key": "tiaa", "label": "TIAA Bank", "account_type": "Bank"},
    {"domain_pattern": "citbank.com", "provider_key": "cit_bank", "label": "CIT Bank", "account_type": "Bank"},
    {"domain_pattern": "fidelity.com", "provider_key": "fidelity", "label": "Fidelity", "account_type": "Bank"},
    {"domain_pattern": "fidelityrewards.com", "provider_key": "fidelity", "label": "Fidelity", "account_type": "Credit Card"},
    {"domain_pattern": "schwab.com", "provider_key": "schwab", "label": "Schwab", "account_type": "Bank"},
    {"domain_pattern": "vanguard.com", "provider_key": "vanguard", "label": "Vanguard", "account_type": "Bank"},
    {"domain_pattern": "robinhood.com", "provider_key": "robinhood", "label": "Robinhood", "account_type": "Bank"},
    {"domain_pattern": "webull.com", "provider_key": "webull", "label": "Webull", "account_type": "Bank"},
    {"domain_pattern": "etrade.com", "provider_key": "etrade", "label": "E*TRADE", "account_type": "Bank"},
    {"domain_pattern": "coinbase.com", "provider_key": "coinbase", "label": "Coinbase", "account_type": "Bank"},
    {"domain_pattern": "venmo.com", "provider_key": "venmo", "label": "Venmo", "account_type": "Bank"},
    {"domain_pattern": "paypal.com", "provider_key": "paypal", "label": "PayPal", "account_type": "Bank"},
    {"domain_pattern": "navyfederal.org", "provider_key": "navy_federal", "label": "Navy Federal", "account_type": "Bank"},
    {"domain_pattern": "pnc.com", "provider_key": "pnc", "label": "PNC", "account_type": "Bank"},
    {"domain_pattern": "huntington.com", "provider_key": "huntington", "label": "Huntington", "account_type": "Bank"},
    {"domain_pattern": "regions.com", "provider_key": "regions", "label": "Regions", "account_type": "Bank"},
    {"domain_pattern": "wellsfargo.com", "provider_key": "wells_fargo", "label": "Wells Fargo", "account_type": "Bank"},
    {"domain_pattern": "bankofamerica.com", "provider_key": "bofa", "label": "Bank of America", "account_type": "Bank"},
    {"domain_pattern": "usaa.com", "provider_key": "usaa", "label": "USAA", "account_type": "Bank"},
    {"domain_pattern": "citizensbankonline.com", "provider_key": "citizens", "label": "Citizens", "account_type": "Bank"},
    {"domain_pattern": "loancare.com", "provider_key": "loancare", "label": "LoanCare", "account_type": "Loan"},
    {"domain_pattern": "myroundpoint.com", "provider_key": "roundpoint", "label": "RoundPoint", "account_type": "Loan"},
    {"domain_pattern": "nelnet.com", "provider_key": "nelnet", "label": "Nelnet", "account_type": "Loan"},
    {"domain_pattern": "navient.com", "provider_key": "navient", "label": "Navient", "account_type": "Loan"},
    {"domain_pattern": "mohela.com", "provider_key": "mohela", "label": "MOHELA", "account_type": "Loan"},
    {"domain_pattern": "salliemae.com", "provider_key": "sallie_mae", "label": "Sallie Mae", "account_type": "Loan"},
]


@dataclass
class SnapshotView:
    id: int
    provider_key: str
    institution: str
    scraper_login_id: int | None
    display_name: str | None
    account_number: str | None
    account_mask: str | None
    address: str | None
    status: str | None
    current_balance: float | None
    statement_balance: float | None
    minimum_payment: float | None
    due_date: str | None
    last_payment_amount: float | None
    last_payment_date: str | None
    credit_limit: float | None
    interest_rate: float | None
    is_paid: bool | None
    paid_date: str | None
    autopay_enabled: bool | None
    account_subcategory: str
    account_category: str
    balance_type: str
    signed_balance: float | None
    first_seen_at: str | None
    last_seen_at: str | None
    last_snapshot_at: str | None
    updated_at: str | None
    captured_at: str


class AccountsDB:
    """Small service layer for dashboard account state."""

    def __init__(self) -> None:
        init_db()

    def session(self) -> Session:
        return SessionLocal()

    def save_scrape_results(self, provider_key: str, results: list[dict]) -> list[SnapshotView]:
        captured_at = datetime.utcnow()

        with self.session() as session:
            login_id = results[0].get("login_id") if results else None
            login = session.get(ScraperLogin, login_id) if login_id else None
            institution = (login.institution if login and login.institution
                           else provider_key.replace("_", " ").title())
            saved: list[SnapshotView] = []
            for i, row in enumerate(results):
                extracted_type = row.get("account_type")
                account_type_name = extracted_type if extracted_type else "Other"
                account_type = self._get_or_create_account_type(session, account_type_name)

                if i == 0 and login:
                    login.account_type = account_type_name

                account = self._upsert_account(
                    session=session,
                    provider_key=provider_key,
                    institution=institution,
                    account_type_id=account_type.id,
                    row=row,
                    captured_at=captured_at,
                )
                session.add(
                    AccountSnapshot(
                        financial_account_id=account.id,
                        scraper_login_id=row.get("login_id"),
                        captured_at=captured_at,
                        current_balance=row.get("current_balance"),
                        statement_balance=row.get("statement_balance"),
                        minimum_payment=row.get("minimum_payment"),
                        due_date=row.get("due_date"),
                        last_payment_amount=row.get("last_payment_amount"),
                        last_payment_date=row.get("last_payment_date"),
                        credit_limit=row.get("credit_limit"),
                        intro_apr_rate=row.get("intro_apr_rate"),
                        intro_apr_end_date=row.get("intro_apr_end_date"),
                        regular_apr=row.get("regular_apr"),
                        is_paid=row.get("is_paid"),
                        paid_date=row.get("paid_date"),
                        autopay_enabled=row.get("autopay_enabled"),
                        raw_extracted_json=row,
                    )
                )
                self._sync_account_identifiers(
                    session=session,
                    account=account,
                    provider_key=provider_key,
                    row=row,
                    captured_at=captured_at,
                )
                self._sync_account_login(
                    session=session,
                    account=account,
                    scraper_login_id=row.get("login_id"),
                    captured_at=captured_at,
                )
                self._sync_promo_period(
                    session=session,
                    account=account,
                    row=row,
                )
                saved.append(
                    _snapshot_view_from_values(
                        provider_key=provider_key,
                        institution=institution,
                        scraper_login_id=row.get("login_id"),
                        account=account,
                        row=row,
                        captured_at=captured_at,
                    )
                )

            session.commit()
            return saved

    def merge_duplicate_accounts(self, provider_key: str | None = None) -> dict[str, int]:
        with self.session() as session:
            accounts = session.query(FinancialAccount).order_by(FinancialAccount.id).all()
            grouped: dict[tuple[str, str, str], list[FinancialAccount]] = {}

            for account in accounts:
                if provider_key and account.provider_key != provider_key:
                    continue

                dedupe_key = self._account_dedupe_key(session, account)
                if dedupe_key is None:
                    continue
                grouped.setdefault(dedupe_key, []).append(account)

            merged_accounts = 0
            moved_snapshots = 0

            for duplicates in grouped.values():
                if len(duplicates) < 2:
                    continue

                primary = duplicates[0]
                for duplicate in duplicates[1:]:
                    moved = (
                        session.query(AccountSnapshot)
                        .filter(AccountSnapshot.financial_account_id == duplicate.id)
                        .update(
                            {AccountSnapshot.financial_account_id: primary.id},
                            synchronize_session=False,
                        )
                    )
                    moved_snapshots += moved

                    primary.display_name = primary.display_name or duplicate.display_name
                    primary.account_number = primary.account_number or duplicate.account_number
                    primary.account_mask = _normalize_mask(primary.account_mask) or _normalize_mask(duplicate.account_mask)
                    primary.address = primary.address or duplicate.address
                    primary.status = primary.status or duplicate.status
                    primary.active = primary.active or duplicate.active
                    if duplicate.first_seen_at and duplicate.first_seen_at < primary.first_seen_at:
                        primary.first_seen_at = duplicate.first_seen_at
                    if duplicate.last_seen_at and duplicate.last_seen_at > primary.last_seen_at:
                        primary.last_seen_at = duplicate.last_seen_at
                    if duplicate.last_snapshot_at and (
                        not primary.last_snapshot_at or duplicate.last_snapshot_at > primary.last_snapshot_at
                    ):
                        primary.last_snapshot_at = duplicate.last_snapshot_at

                    duplicate_identifiers = (
                        session.query(FinancialAccountIdentifier)
                        .filter(FinancialAccountIdentifier.financial_account_id == duplicate.id)
                        .all()
                    )
                    for identifier in duplicate_identifiers:
                        existing_identifier = (
                            session.query(FinancialAccountIdentifier)
                            .filter(
                                FinancialAccountIdentifier.financial_account_id == primary.id,
                                FinancialAccountIdentifier.provider_key == identifier.provider_key,
                                FinancialAccountIdentifier.identifier_type == identifier.identifier_type,
                                FinancialAccountIdentifier.identifier_value == identifier.identifier_value,
                            )
                            .first()
                        )
                        if existing_identifier:
                            existing_identifier.is_primary = existing_identifier.is_primary or identifier.is_primary
                            existing_identifier.source = existing_identifier.source or identifier.source
                            if identifier.last_seen_at and identifier.last_seen_at > existing_identifier.last_seen_at:
                                existing_identifier.last_seen_at = identifier.last_seen_at
                            session.delete(identifier)
                        else:
                            (
                                session.query(FinancialAccountIdentifier)
                                .filter(FinancialAccountIdentifier.id == identifier.id)
                                .update(
                                    {FinancialAccountIdentifier.financial_account_id: primary.id},
                                    synchronize_session=False,
                                )
                            )

                    duplicate_links = (
                        session.query(FinancialAccountLogin)
                        .filter(FinancialAccountLogin.financial_account_id == duplicate.id)
                        .all()
                    )
                    for link in duplicate_links:
                        existing_link = (
                            session.query(FinancialAccountLogin)
                            .filter(
                                FinancialAccountLogin.financial_account_id == primary.id,
                                FinancialAccountLogin.scraper_login_id == link.scraper_login_id,
                            )
                            .first()
                        )
                        if existing_link:
                            if link.first_seen_at and link.first_seen_at < existing_link.first_seen_at:
                                existing_link.first_seen_at = link.first_seen_at
                            if link.last_seen_at and link.last_seen_at > existing_link.last_seen_at:
                                existing_link.last_seen_at = link.last_seen_at
                            if link.last_success_at and link.last_success_at > existing_link.last_success_at:
                                existing_link.last_success_at = link.last_success_at
                            session.delete(link)
                        else:
                            (
                                session.query(FinancialAccountLogin)
                                .filter(FinancialAccountLogin.id == link.id)
                                .update(
                                    {FinancialAccountLogin.financial_account_id: primary.id},
                                    synchronize_session=False,
                                )
                            )

                    session.flush()
                    session.delete(duplicate)
                    merged_accounts += 1

            session.commit()
            return {"merged_accounts": merged_accounts, "moved_snapshots": moved_snapshots}

    def backfill_account_metadata(self, provider_key: str | None = None) -> dict[str, int]:
        with self.session() as session:
            accounts = session.query(FinancialAccount).order_by(FinancialAccount.id).all()
            updated = 0

            for account in accounts:
                if provider_key and account.provider_key != provider_key:
                    continue

                latest_snapshot = (
                    session.query(AccountSnapshot)
                    .filter(AccountSnapshot.financial_account_id == account.id)
                    .order_by(AccountSnapshot.captured_at.desc(), AccountSnapshot.id.desc())
                    .first()
                )
                if not latest_snapshot:
                    continue

                raw = latest_snapshot.raw_extracted_json or {}
                new_display_name = _infer_display_name(raw, account.institution)
                new_mask = _normalize_mask(raw.get("account_mask")) or _infer_mask(account.account_number)
                new_address = raw.get("address") or account.address
                new_status = raw.get("status") or account.status

                changed = False
                if new_display_name and new_display_name != account.display_name:
                    account.display_name = new_display_name
                    changed = True
                if new_mask != account.account_mask:
                    account.account_mask = new_mask
                    changed = True
                if new_address != account.address:
                    account.address = new_address
                    changed = True
                if new_status != account.status:
                    account.status = new_status
                    account.active = _infer_active(new_status)
                    changed = True

                if changed:
                    updated += 1

            session.commit()
            return {"updated_accounts": updated}

    def get_latest_snapshots(self) -> list[SnapshotView]:
        with self.session() as session:
            latest_snapshot_subq = (
                select(
                    AccountSnapshot.financial_account_id,
                    func.max(AccountSnapshot.captured_at).label("captured_at"),
                )
                .group_by(AccountSnapshot.financial_account_id)
                .subquery()
            )

            rows = (
                session.query(FinancialAccount, AccountSnapshot)
                .join(
                    latest_snapshot_subq,
                    FinancialAccount.id == latest_snapshot_subq.c.financial_account_id,
                )
                .join(
                    AccountSnapshot,
                    (AccountSnapshot.financial_account_id == latest_snapshot_subq.c.financial_account_id)
                    & (AccountSnapshot.captured_at == latest_snapshot_subq.c.captured_at),
                )
                .order_by(FinancialAccount.provider_key, FinancialAccount.display_name, FinancialAccount.account_number)
                .all()
            )

            return [
                _snapshot_view_from_values(
                    provider_key=account.provider_key,
                    institution=account.institution,
                    scraper_login_id=account.scraper_login_id,
                    account=account,
                    row=snapshot.raw_extracted_json,
                    captured_at=snapshot.captured_at,
                )
                for account, snapshot in rows
            ]

    def get_summary(self) -> dict:
        latest = self.get_latest_snapshots()
        by_provider: dict[str, dict] = {}
        by_category: dict[str, dict] = {}
        by_balance_type = {
            "asset": {"count": 0, "total": 0.0, "subcategories": {}},
            "liability": {"count": 0, "total": 0.0, "subcategories": {}},
        }
        asset_total = 0.0
        debt_total = 0.0

        for row in latest:
            balance = row.current_balance or 0.0
            signed = row.signed_balance or 0.0
            if row.balance_type == "asset":
                asset_total += balance
            else:
                debt_total += balance
            by_balance_type[row.balance_type]["count"] += 1
            by_balance_type[row.balance_type]["total"] += balance
            by_balance_type[row.balance_type]["subcategories"][row.account_subcategory] = (
                by_balance_type[row.balance_type]["subcategories"].get(row.account_subcategory, 0) + 1
            )

            provider = by_provider.setdefault(
                row.provider_key,
                {
                    "institution": row.institution,
                    "count": 0,
                    "asset_total": 0.0,
                    "debt_total": 0.0,
                    "net_balance": 0.0,
                    "subcategories": {},
                },
            )
            provider["count"] += 1
            provider["net_balance"] += signed
            if row.balance_type == "asset":
                provider["asset_total"] += balance
            else:
                provider["debt_total"] += balance
            provider["subcategories"][row.account_subcategory] = provider["subcategories"].get(row.account_subcategory, 0) + 1

            category = by_category.setdefault(
                row.account_subcategory,
                {"count": 0, "asset_total": 0.0, "debt_total": 0.0, "net_balance": 0.0},
            )
            category["count"] += 1
            category["net_balance"] += signed
            if row.balance_type == "asset":
                category["asset_total"] += balance
            else:
                category["debt_total"] += balance

        return {
            "accounts": len(latest),
            "asset_total": asset_total,
            "debt_total": debt_total,
            "net_balance": asset_total - debt_total,
            "by_provider": by_provider,
            "by_category": by_category,
            "by_balance_type": by_balance_type,
        }

    def upsert_statement(
        self,
        financial_account_id: int,
        statement_month: str,
        *,
        scraper_login_id: int | None = None,
        statement_date: str | None = None,
        file_path: str | None = None,
        file_size_bytes: int | None = None,
        downloaded_at: datetime | None = None,
        intro_apr_rate: float | None = None,
        intro_apr_end_date: str | None = None,
        regular_apr: float | None = None,
        credit_limit: float | None = None,
        raw_extracted_json: dict | None = None,
    ) -> AccountStatement:
        with self.session() as session:
            stmt = (
                session.query(AccountStatement)
                .filter_by(financial_account_id=financial_account_id, statement_month=statement_month)
                .first()
            )
            if not stmt:
                stmt = AccountStatement(
                    financial_account_id=financial_account_id,
                    statement_month=statement_month,
                )
                session.add(stmt)

            if scraper_login_id is not None:
                stmt.scraper_login_id = scraper_login_id
            if statement_date is not None:
                stmt.statement_date = statement_date
            if file_path is not None:
                stmt.file_path = file_path
            if file_size_bytes is not None:
                stmt.file_size_bytes = file_size_bytes
            if downloaded_at is not None:
                stmt.downloaded_at = downloaded_at
            if intro_apr_rate is not None:
                stmt.intro_apr_rate = intro_apr_rate
            if intro_apr_end_date is not None:
                stmt.intro_apr_end_date = intro_apr_end_date
            if regular_apr is not None:
                stmt.regular_apr = regular_apr
            if credit_limit is not None:
                stmt.credit_limit = credit_limit
            if raw_extracted_json is not None:
                stmt.raw_extracted_json = raw_extracted_json

            # Sync promo period from statement data
            if intro_apr_end_date:
                self._sync_promo_period(
                    session=session,
                    account=session.get(FinancialAccount, financial_account_id),
                    row={
                        "intro_apr_rate": intro_apr_rate,
                        "intro_apr_end_date": intro_apr_end_date,
                        "regular_apr": regular_apr,
                    },
                )

            session.commit()
            session.refresh(stmt)
            return stmt

    def get_statements(
        self,
        financial_account_id: int | None = None,
        limit: int = 100,
    ) -> list[AccountStatement]:
        with self.session() as session:
            query = session.query(AccountStatement)
            if financial_account_id is not None:
                query = query.filter_by(financial_account_id=financial_account_id)
            query = query.order_by(AccountStatement.statement_month.desc())
            return query.limit(limit).all()

    def get_apr_summary(self) -> list[dict]:
        with self.session() as session:
            rows = (
                session.query(AccountStatement, FinancialAccount)
                .join(FinancialAccount, AccountStatement.financial_account_id == FinancialAccount.id)
                .filter(AccountStatement.intro_apr_end_date.isnot(None))
                .order_by(AccountStatement.intro_apr_end_date)
                .all()
            )
            return [
                {
                    "account_id": account.id,
                    "provider_key": account.provider_key,
                    "display_name": account.display_name,
                    "account_mask": account.account_mask,
                    "statement_month": stmt.statement_month,
                    "intro_apr_rate": stmt.intro_apr_rate,
                    "intro_apr_end_date": stmt.intro_apr_end_date,
                    "regular_apr": stmt.regular_apr,
                    "credit_limit": stmt.credit_limit,
                }
                for stmt, account in rows
            ]

    def _get_or_create_account_type(self, session: Session, name: str) -> FinancialAccountType:
        account_type = session.query(FinancialAccountType).filter_by(name=name).first()
        if not account_type:
            balance_type = _BALANCE_TYPE_MAP.get(name, "liability")
            account_type = FinancialAccountType(name=name, balance_type=balance_type)
            session.add(account_type)
            session.flush()
        return account_type

    def _upsert_account(
        self,
        session: Session,
        provider_key: str,
        institution: str,
        account_type_id: int,
        row: dict,
        captured_at: datetime,
    ) -> FinancialAccount:
        account_number = row.get("account_number")
        account_mask = _normalize_mask(row.get("account_mask")) or _infer_mask(account_number)
        display_name = _infer_display_name(row, institution)
        address = row.get("address")
        account = None
        account_fingerprint = _account_fingerprint(provider_key, display_name, account_mask, row.get("account_type"), address)

        for identifier_type, identifier_value in [
            ("account_number", _normalize_identifier(account_number)),
            ("account_mask", _normalize_identifier(account_mask)),
            ("account_fingerprint", account_fingerprint),
        ]:
            if not identifier_value:
                continue
            account = self._find_account_by_identifier(session, provider_key, identifier_type, identifier_value)
            if account:
                break

        if not account and account_number:
            account = (
                session.query(FinancialAccount)
                .filter_by(provider_key=provider_key, account_number=account_number)
                .first()
            )

        if not account and account_mask:
            account = (
                session.query(FinancialAccount)
                .filter_by(provider_key=provider_key, account_mask=account_mask)
                .first()
            )

        # Mask suffix match: the agent may extract different-length masks across
        # runs (e.g. "690050" vs "7935690050").  If the shorter is a suffix of
        # the longer and the display_name matches, treat them as the same account.
        if not account and account_mask and display_name:
            candidates = (
                session.query(FinancialAccount)
                .filter_by(provider_key=provider_key, display_name=display_name)
                .all()
            )
            for cand in candidates:
                cand_mask = _normalize_mask(cand.account_mask) or ""
                if not cand_mask:
                    continue
                if cand_mask.endswith(account_mask) or account_mask.endswith(cand_mask):
                    account = cand
                    break

        # Display-name fallback — only when the incoming row has NO mask.
        # Providers like utilities use address as the stable identifier and
        # may not always return a mask.  When a mask IS present, we rely on
        # the suffix-match above to avoid merging distinct cards that share
        # the same display name (e.g. multiple "WELLS FARGO REWARDS").
        if not account and display_name and not account_mask:
            account = (
                session.query(FinancialAccount)
                .filter_by(provider_key=provider_key, display_name=display_name)
                .first()
            )

        if not account:
            account = FinancialAccount(
                account_type_id=account_type_id,
                provider_key=provider_key,
                institution=institution,
                account_number=account_number,
                scraper_login_id=row.get("login_id"),
                created_at=captured_at,
                updated_at=captured_at,
                first_seen_at=captured_at,
            )
            session.add(account)
            session.flush()

        account.display_name = display_name
        account.account_type_id = account_type_id
        account.account_number = account_number or account.account_number
        account.account_mask = account_mask
        account.address = address
        account.status = row.get("status")
        account.active = _infer_active(row.get("status"))
        account.last_seen_at = captured_at
        account.last_snapshot_at = captured_at
        if row.get("login_id"):
            account.scraper_login_id = row.get("login_id")
        return account

    def _find_account_by_identifier(
        self,
        session: Session,
        provider_key: str,
        identifier_type: str,
        identifier_value: str,
    ) -> FinancialAccount | None:
        identifier = (
            session.query(FinancialAccountIdentifier)
            .filter_by(
                provider_key=provider_key,
                identifier_type=identifier_type,
                identifier_value=identifier_value,
            )
            .first()
        )
        return identifier.financial_account if identifier else None

    def _sync_account_identifiers(
        self,
        session: Session,
        account: FinancialAccount,
        provider_key: str,
        row: dict,
        captured_at: datetime,
    ) -> None:
        display_name = _infer_display_name(row, account.institution)
        account_number = _normalize_identifier(row.get("account_number"))
        account_mask = _normalize_identifier(_normalize_mask(row.get("account_mask")) or _infer_mask(account.account_number))
        account_fingerprint = _account_fingerprint(
            provider_key,
            display_name,
            account_mask,
            row.get("account_type"),
            row.get("address"),
        )
        for identifier_type, identifier_value, is_primary in [
            ("account_number", account_number, True),
            ("account_mask", account_mask, account_number is None),
            ("account_fingerprint", account_fingerprint, account_number is None and account_mask is None),
        ]:
            if not identifier_value:
                continue
            identifier = (
                session.query(FinancialAccountIdentifier)
                .filter_by(
                    provider_key=provider_key,
                    identifier_type=identifier_type,
                    identifier_value=identifier_value,
                )
                .first()
            )
            if not identifier:
                session.add(
                    FinancialAccountIdentifier(
                        financial_account_id=account.id,
                        provider_key=provider_key,
                        identifier_type=identifier_type,
                        identifier_value=identifier_value,
                        is_primary=is_primary,
                        source="scrape",
                        created_at=captured_at,
                        updated_at=captured_at,
                        last_seen_at=captured_at,
                    )
                )
                continue

            identifier.financial_account_id = account.id
            identifier.is_primary = identifier.is_primary or is_primary
            identifier.last_seen_at = captured_at

    def _sync_account_login(
        self,
        session: Session,
        account: FinancialAccount,
        scraper_login_id: int | None,
        captured_at: datetime,
    ) -> None:
        if not scraper_login_id:
            return
        link = (
            session.query(FinancialAccountLogin)
            .filter_by(financial_account_id=account.id, scraper_login_id=scraper_login_id)
            .first()
        )
        if not link:
            session.add(
                FinancialAccountLogin(
                    financial_account_id=account.id,
                    scraper_login_id=scraper_login_id,
                    first_seen_at=captured_at,
                    last_seen_at=captured_at,
                    last_success_at=captured_at,
                )
            )
            return

        link.last_seen_at = captured_at
        link.last_success_at = captured_at

    def _sync_promo_period(
        self,
        session: Session,
        account: FinancialAccount | None,
        row: dict,
    ) -> None:
        """Create or update a PromoAprPeriod from scraped intro APR data."""
        if not account:
            return
        end_date = row.get("intro_apr_end_date")
        if not end_date:
            return
        apr_rate = row.get("intro_apr_rate")
        if apr_rate is None:
            return

        # Look for existing promo with same account + end_date (natural key)
        existing = (
            session.query(PromoAprPeriod)
            .filter_by(financial_account_id=account.id, end_date=end_date)
            .first()
        )
        if existing:
            # Update if data changed
            existing.apr_rate = apr_rate
            if row.get("regular_apr") is not None:
                existing.regular_apr = row["regular_apr"]
            existing.active = True
            return

        session.add(
            PromoAprPeriod(
                financial_account_id=account.id,
                promo_type=row.get("promo_type") or "purchase",
                apr_rate=apr_rate,
                regular_apr=row.get("regular_apr"),
                end_date=end_date,
                active=True,
            )
        )

    # ========================================================================
    # Rewards methods
    # ========================================================================

    def upsert_rewards_program(
        self,
        financial_account_id: int,
        program_name: str,
        *,
        program_type: str = "points",
        unit_name: str | None = None,
        cents_per_unit: float | None = None,
        display_icon_url: str | None = None,
        active: bool = True,
    ) -> RewardsProgram:
        """Create or update a rewards program for an account."""
        with self.session() as session:
            program = (
                session.query(RewardsProgram)
                .filter_by(financial_account_id=financial_account_id, program_name=program_name)
                .first()
            )
            if program:
                # Update existing
                if program_type is not None:
                    program.program_type = program_type
                if unit_name is not None:
                    program.unit_name = unit_name
                if cents_per_unit is not None:
                    program.cents_per_unit = cents_per_unit
                if display_icon_url is not None:
                    program.display_icon_url = display_icon_url
                program.active = active
            else:
                # Create new
                program = RewardsProgram(
                    financial_account_id=financial_account_id,
                    program_name=program_name,
                    program_type=program_type,
                    unit_name=unit_name,
                    cents_per_unit=cents_per_unit,
                    display_icon_url=display_icon_url,
                    active=active,
                )
                session.add(program)
            session.commit()
            session.refresh(program)
            return program

    def upsert_rewards_balance(
        self,
        rewards_program_id: int,
        balance: float,
        *,
        monetary_value: float | None = None,
        expiration_date: str | None = None,
        source_snapshot_id: int | None = None,
        raw_extracted_json: dict | None = None,
        captured_at: datetime | None = None,
    ) -> RewardsBalance:
        """Record a rewards balance snapshot."""
        if captured_at is None:
            captured_at = datetime.utcnow()
        with self.session() as session:
            rewards_balance = RewardsBalance(
                rewards_program_id=rewards_program_id,
                captured_at=captured_at,
                balance=balance,
                monetary_value=monetary_value,
                expiration_date=expiration_date,
                source_snapshot_id=source_snapshot_id,
                raw_extracted_json=raw_extracted_json,
            )
            session.add(rewards_balance)
            session.commit()
            session.refresh(rewards_balance)
            return rewards_balance

    def sync_rewards(
        self,
        financial_account_id: int,
        rewards_data: list[dict],
        *,
        source_snapshot_id: int | None = None,
        captured_at: datetime | None = None,
    ) -> list[dict]:
        """
        Sync rewards data from a scrape result.

        rewards_data should be a list of dicts with:
        - program_name: str (required)
        - balance: float (required)
        - program_type: str (optional, default "points")
        - unit_name: str (optional)
        - cents_per_unit: float (optional)
        - monetary_value: float (optional)
        - expiration_date: str (optional, YYYY-MM-DD)

        Returns list of saved rewards info.
        """
        if captured_at is None:
            captured_at = datetime.utcnow()

        results = []
        with self.session() as session:
            for rd in rewards_data:
                program_name = rd.get("program_name")
                balance = rd.get("balance")
                if not program_name or balance is None:
                    continue

                # Get or create the program
                program = (
                    session.query(RewardsProgram)
                    .filter_by(financial_account_id=financial_account_id, program_name=program_name)
                    .first()
                )
                if not program:
                    program = RewardsProgram(
                        financial_account_id=financial_account_id,
                        program_name=program_name,
                        program_type=rd.get("program_type", "points"),
                        unit_name=rd.get("unit_name"),
                        cents_per_unit=rd.get("cents_per_unit"),
                    )
                    session.add(program)
                    session.flush()
                elif program.cents_per_unit is None and rd.get("cents_per_unit") is not None:
                    program.cents_per_unit = rd["cents_per_unit"]

                # Calculate monetary value if cents_per_unit is set
                monetary_value = rd.get("monetary_value")
                if monetary_value is None and program.cents_per_unit:
                    monetary_value = balance * program.cents_per_unit / 100

                # Create the balance snapshot
                rewards_balance = RewardsBalance(
                    rewards_program_id=program.id,
                    captured_at=captured_at,
                    balance=balance,
                    monetary_value=monetary_value,
                    expiration_date=rd.get("expiration_date"),
                    source_snapshot_id=source_snapshot_id,
                    raw_extracted_json=rd,
                )
                session.add(rewards_balance)
                results.append({
                    "program_id": program.id,
                    "program_name": program_name,
                    "balance": balance,
                    "monetary_value": monetary_value,
                    "expiration_date": rd.get("expiration_date"),
                })

            session.commit()
        return results

    def get_rewards_programs(self, financial_account_id: int | None = None) -> list[dict]:
        """Get all rewards programs, optionally filtered by account."""
        with self.session() as session:
            query = session.query(RewardsProgram)
            if financial_account_id is not None:
                query = query.filter_by(financial_account_id=financial_account_id)
            programs = query.order_by(RewardsProgram.program_name).all()
            return [
                {
                    "id": p.id,
                    "financial_account_id": p.financial_account_id,
                    "program_name": p.program_name,
                    "program_type": p.program_type,
                    "unit_name": p.unit_name,
                    "cents_per_unit": p.cents_per_unit,
                    "display_icon_url": p.display_icon_url,
                    "active": p.active,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                }
                for p in programs
            ]

    def get_rewards_balances(
        self,
        rewards_program_id: int | None = None,
        financial_account_id: int | None = None,
        include_history: bool = False,
        limit: int = 100,
    ) -> list[dict]:
        """
        Get latest rewards balances.

        If include_history is False (default), returns only the most recent balance per program.
        If include_history is True, returns all balances up to limit.
        """
        with self.session() as session:
            if include_history:
                # Return all balances
                query = session.query(RewardsBalance)
                if rewards_program_id is not None:
                    query = query.filter_by(rewards_program_id=rewards_program_id)
                elif financial_account_id is not None:
                    query = query.join(RewardsProgram).filter(
                        RewardsProgram.financial_account_id == financial_account_id
                    )
                balances = query.order_by(RewardsBalance.captured_at.desc()).limit(limit).all()
            else:
                # Get latest balance per program
                if rewards_program_id is not None:
                    balances = [
                        session.query(RewardsBalance)
                        .filter_by(rewards_program_id=rewards_program_id)
                        .order_by(RewardsBalance.captured_at.desc())
                        .first()
                    ]
                    balances = [b for b in balances if b is not None]
                elif financial_account_id is not None:
                    # Subquery to get latest balance per program
                    from sqlalchemy import func
                    latest_subq = (
                        session.query(
                            RewardsBalance.rewards_program_id,
                            func.max(RewardsBalance.captured_at).label("max_captured_at"),
                        )
                        .join(RewardsProgram)
                        .filter(RewardsProgram.financial_account_id == financial_account_id)
                        .group_by(RewardsBalance.rewards_program_id)
                        .subquery()
                    )
                    balances = (
                        session.query(RewardsBalance)
                        .join(
                            latest_subq,
                            (RewardsBalance.rewards_program_id == latest_subq.c.rewards_program_id)
                            & (RewardsBalance.captured_at == latest_subq.c.max_captured_at),
                        )
                        .all()
                    )
                else:
                    # Get latest balance for all programs
                    from sqlalchemy import func
                    latest_subq = (
                        session.query(
                            RewardsBalance.rewards_program_id,
                            func.max(RewardsBalance.captured_at).label("max_captured_at"),
                        )
                        .group_by(RewardsBalance.rewards_program_id)
                        .subquery()
                    )
                    balances = (
                        session.query(RewardsBalance)
                        .join(
                            latest_subq,
                            (RewardsBalance.rewards_program_id == latest_subq.c.rewards_program_id)
                            & (RewardsBalance.captured_at == latest_subq.c.max_captured_at),
                        )
                        .limit(limit)
                        .all()
                    )

            return [
                {
                    "id": b.id,
                    "rewards_program_id": b.rewards_program_id,
                    "program_name": b.rewards_program.program_name if b.rewards_program else None,
                    "program_type": b.rewards_program.program_type if b.rewards_program else None,
                    "unit_name": b.rewards_program.unit_name if b.rewards_program else None,
                    "captured_at": b.captured_at.isoformat() if b.captured_at else None,
                    "balance": b.balance,
                    "monetary_value": b.monetary_value,
                    "expiration_date": b.expiration_date,
                }
                for b in balances
            ]

    def get_rewards_summary(self) -> dict:
        """Get summary of all rewards (total monetary value grouped by type)."""
        with self.session() as session:
            from sqlalchemy import func

            # Get latest balance per program
            latest_subq = (
                session.query(
                    RewardsBalance.rewards_program_id,
                    func.max(RewardsBalance.captured_at).label("max_captured_at"),
                )
                .join(RewardsProgram)
                .filter(RewardsProgram.active == True)
                .group_by(RewardsBalance.rewards_program_id)
                .subquery()
            )

            balances = (
                session.query(RewardsBalance, RewardsProgram, FinancialAccount, ScraperLogin)
                .join(latest_subq,
                    (RewardsBalance.rewards_program_id == latest_subq.c.rewards_program_id)
                    & (RewardsBalance.captured_at == latest_subq.c.max_captured_at))
                .join(RewardsProgram, RewardsBalance.rewards_program_id == RewardsProgram.id)
                .join(ScraperLogin, RewardsProgram.scraper_login_id == ScraperLogin.id)
                .outerjoin(FinancialAccount, RewardsProgram.financial_account_id == FinancialAccount.id)
                .all()
            )

            total_value = 0.0
            by_type: dict[str, dict] = {}
            programs: list[dict] = []

            for rb, rp, fa, sl in balances:
                value = rb.monetary_value or 0.0
                total_value += value

                type_key = rp.program_type or "other"
                type_info = by_type.setdefault(type_key, {"count": 0, "total_value": 0.0, "total_balance": 0.0})
                type_info["count"] += 1
                type_info["total_value"] += value
                type_info["total_balance"] += rb.balance or 0.0

                programs.append({
                    "program_id": rp.id,
                    "program_name": rp.program_name,
                    "program_type": rp.program_type,
                    "scraper_login_id": rp.scraper_login_id,
                    "login_label": sl.label if sl else None,
                    "account_id": fa.id if fa else None,
                    "account_display_name": fa.display_name if fa else None,
                    "account_mask": fa.account_mask if fa else None,
                    "institution": fa.institution if fa else None,
                    "membership_id": rp.membership_id,
                    "balance": rb.balance,
                    "monetary_value": rb.monetary_value,
                    "unit_name": rp.unit_name,
                    "cents_per_unit": rp.cents_per_unit,
                    "expiration_date": rb.expiration_date,
                })

            return {
                "total_monetary_value": total_value,
                "by_type": by_type,
                "programs": programs,
            }

    def _account_dedupe_key(self, session: Session, account: FinancialAccount) -> tuple[str, str, str] | None:
        mask = _normalize_mask(account.account_mask)
        if mask:
            return (account.provider_key, "mask", mask)

        if account.account_number:
            return (account.provider_key, "number", account.account_number)

        latest_snapshot = (
            session.query(AccountSnapshot)
            .filter(AccountSnapshot.financial_account_id == account.id)
            .order_by(AccountSnapshot.captured_at.desc(), AccountSnapshot.id.desc())
            .first()
        )
        raw = latest_snapshot.raw_extracted_json if latest_snapshot else {}
        name = _normalize_text(raw.get("account_name") or raw.get("card_name") or account.display_name)
        address = _normalize_text(raw.get("address") or account.address)
        if name and address:
            return (account.provider_key, "name_address", f"{name}|{address}")
        if name:
            return (account.provider_key, "name", name)
        return None

    def get_provider_mappings(self, source: str | None = None) -> list[dict]:
        """Return all provider mappings, optionally filtered by source."""
        with self.session() as session:
            query = session.query(ProviderMapping)
            if source:
                query = query.filter(ProviderMapping.source == source)
            mappings = query.order_by(ProviderMapping.domain_pattern).all()
            return [
                {
                    "id": m.id,
                    "domain_pattern": m.domain_pattern,
                    "provider_key": m.provider_key,
                    "label": m.label,
                    "account_type": m.account_type,
                    "source": m.source,
                    "confidence": m.confidence,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "updated_at": m.updated_at.isoformat() if m.updated_at else None,
                }
                for m in mappings
            ]

    def upsert_provider_mapping(
        self,
        domain_pattern: str,
        provider_key: str,
        label: str,
        account_type: str,
        source: str = "learned",
        confidence: float | None = None,
    ) -> ProviderMapping:
        """Insert or update a provider mapping."""
        with self.session() as session:
            existing = session.query(ProviderMapping).filter(
                ProviderMapping.domain_pattern == domain_pattern
            ).first()
            if existing:
                existing.provider_key = provider_key
                existing.label = label
                existing.account_type = account_type
                existing.source = source
                existing.confidence = confidence
            else:
                mapping = ProviderMapping(
                    domain_pattern=domain_pattern,
                    provider_key=provider_key,
                    label=label,
                    account_type=account_type,
                    source=source,
                    confidence=confidence,
                )
                session.add(mapping)
                existing = mapping
            session.commit()
            session.refresh(existing)
            return existing

    def delete_provider_mapping(self, domain_pattern: str) -> bool:
        """Delete a provider mapping by domain pattern. Returns True if deleted."""
        with self.session() as session:
            deleted = session.query(ProviderMapping).filter(
                ProviderMapping.domain_pattern == domain_pattern
            ).delete()
            return deleted > 0

    def seed_baseline_providers(self, providers: list[dict]) -> int:
        """Seed baseline providers from a list of {domain_pattern, provider_key, label, account_type} dicts.
        
        Only inserts if domain_pattern doesn't already exist. Returns count of inserted.
        """
        count = 0
        with self.session() as session:
            for p in providers:
                existing = session.query(ProviderMapping).filter(
                    ProviderMapping.domain_pattern == p["domain_pattern"]
                ).first()
                if not existing:
                    mapping = ProviderMapping(
                        domain_pattern=p["domain_pattern"],
                        provider_key=p["provider_key"],
                        label=p["label"],
                        account_type=p["account_type"],
                        source="baseline",
                    )
                    session.add(mapping)
                    count += 1
            session.commit()
        return count


def _snapshot_view_from_values(
    provider_key: str,
    institution: str,
    scraper_login_id: int | None,
    account: FinancialAccount,
    row: dict,
    captured_at: datetime,
) -> SnapshotView:
    category = _infer_account_category(provider_key, row)
    balance_type = _infer_balance_type(category)
    current_balance = row.get("current_balance")
    signed_balance = None if current_balance is None else current_balance * (1 if balance_type == "asset" else -1)
    return SnapshotView(
        id=account.id,
        provider_key=provider_key,
        institution=institution,
        scraper_login_id=scraper_login_id,
        display_name=row.get("account_name") or row.get("card_name") or account.display_name,
        account_number=account.account_number,
        account_mask=account.account_mask,
        address=account.address,
        status=account.status,
        current_balance=current_balance,
        statement_balance=row.get("statement_balance"),
        minimum_payment=row.get("minimum_payment"),
        due_date=row.get("due_date"),
        last_payment_amount=row.get("last_payment_amount"),
        last_payment_date=row.get("last_payment_date"),
        credit_limit=row.get("credit_limit"),
        interest_rate=row.get("interest_rate") or row.get("regular_apr"),
        is_paid=row.get("is_paid"),
        paid_date=row.get("paid_date"),
        autopay_enabled=row.get("autopay_enabled"),
        account_subcategory=category,
        account_category=category,
        balance_type=balance_type,
        signed_balance=signed_balance,
        first_seen_at=account.first_seen_at.isoformat() if account.first_seen_at else None,
        last_seen_at=account.last_seen_at.isoformat() if account.last_seen_at else None,
        last_snapshot_at=account.last_snapshot_at.isoformat() if account.last_snapshot_at else None,
        updated_at=account.updated_at.isoformat() if account.updated_at else None,
        captured_at=captured_at.isoformat(),
    )


def _infer_mask(account_number: Optional[str]) -> Optional[str]:
    if not account_number:
        return None
    digits = "".join(ch for ch in account_number if ch.isdigit())
    return digits[-4:] if digits else account_number[-4:]


def _infer_active(status: Optional[str]) -> bool:
    if not status:
        return True
    lowered = status.lower()
    return "closed" not in lowered and "inactive" not in lowered


def _infer_display_name(row: dict, institution: str) -> str:
    name = row.get("account_name") or row.get("card_name") or row.get("label") or row.get("address") or institution
    # Clean up common noise from scraped account names
    name = re.sub(r"[®™�]", "", name)
    name = re.sub(r"\(TM\)", "", name, flags=re.IGNORECASE)
    name = re.sub(r"^American Express\s+", "", name)
    name = re.sub(r"^Amex\s+", "", name, flags=re.IGNORECASE)
    name = name.strip()
    if name.lower() != "gold card":
        name = re.sub(r"\s+Card$", "", name)
    return name.strip() or institution


def _normalize_mask(mask: Optional[str]) -> Optional[str]:
    if mask is None:
        return None
    text = str(mask).strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in {"undefined", "none", "null", "n/a", "na", "unknown"}:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits or text


def _normalize_text(value: Optional[str]) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _normalize_identifier(value: Optional[str]) -> Optional[str]:
    text = _normalize_text(value)
    return text or None


def _account_fingerprint(
    provider_key: str,
    display_name: Optional[str],
    account_mask: Optional[str],
    account_type: Optional[str],
    address: Optional[str],
) -> Optional[str]:
    pieces = [
        _normalize_text(provider_key),
        _normalize_text(display_name),
        _normalize_text(account_mask),
        _normalize_text(account_type),
        _normalize_text(address),
    ]
    if not any(pieces[1:]):
        return None
    return "|".join(pieces)


def _infer_account_category(provider_key: str, row: dict) -> str:
    # Trust account_type from extraction if present
    extracted_type = (row.get("account_type") or "").lower().replace(" ", "_")
    canonical = {
        "credit_card": "Credit Card",
        "loan": "Loan",
        "mortgage": "Mortgage",
        "line_of_credit": "Line of Credit",
        "checking": "Checking",
        "savings": "Savings",
        "bank_account": "Checking",
        "utility": "Utility",
        "insurance": "Insurance",
        "investment": "Investment",
        "property": "Property",
    }
    if extracted_type in canonical:
        return canonical[extracted_type]

    if provider_key in {"nipsco", "american_water", "duke_energy"}:
        return "Utility"

    text = " ".join(
        str(value)
        for value in [row.get("account_name") or row.get("card_name"), row.get("label"), row.get("status"), row.get("address")]
        if value
    ).lower()

    if any(token in text for token in ["mortgage"]):
        return "Mortgage"
    if any(token in text for token in ["line of credit", "loc"]):
        return "Line of Credit"
    if any(token in text for token in ["loan"]):
        return "Loan"
    if any(token in text for token in ["checking"]):
        return "Checking"
    if any(token in text for token in ["savings", "money market"]):
        return "Savings"
    if any(token in text for token in ["card", "amex", "visa", "mastercard", "discover"]):
        return "Credit Card"
    return "Other"


# Balance type lookup matching ACCOUNT_TYPES in database.py
_BALANCE_TYPE_MAP = {
    "Credit Card": "liability",
    "Loan": "liability",
    "Mortgage": "liability",
    "Line of Credit": "liability",
    "Utility": "liability",
    "Insurance": "liability",
    "Checking": "asset",
    "Savings": "asset",
    "Investment": "asset",
    "Property": "asset",
    "Other": "liability",
    "Unknown": "liability",
}


def _infer_balance_type(category: str) -> str:
    return _BALANCE_TYPE_MAP.get(category, "liability")


# Import Session CRUD

def create_import_session(filename: str, rows: list[dict]) -> ImportSession:
    """Create a new import session with candidates from parsed CSV rows."""
    with SessionLocal() as session:
        session_obj = ImportSession(
            filename=filename,
            status="pending",
            total_count=len(rows),
        )
        session.add(session_obj)
        session.flush()

        candidates = []
        for i, row in enumerate(rows):
            candidates.append(ImportCandidate(
                session_id=session_obj.id,
                row_index=i,
                name=row.get("name", ""),
                url=row.get("url", ""),
                domain=row.get("domain", ""),
                username=row.get("username", ""),
                password=row.get("password", ""),
                status="pending",
            ))
        session.add_all(candidates)
        session.commit()
        session.refresh(session_obj)
        return session_obj


def get_import_session(session_id: int) -> ImportSession | None:
    """Get an import session by ID."""
    with SessionLocal() as session:
        return session.get(ImportSession, session_id)


def get_import_candidates(session_id: int) -> list[ImportCandidate]:
    """Get all candidates for an import session."""
    with SessionLocal() as session:
        return session.query(ImportCandidate).filter(
            ImportCandidate.session_id == session_id
        ).order_by(ImportCandidate.row_index).all()


def get_import_candidate(candidate_id: int) -> ImportCandidate | None:
    """Get a single import candidate."""
    with SessionLocal() as session:
        return session.get(ImportCandidate, candidate_id)


def update_import_candidate(
    candidate_id: int,
    provider_key: str | None = None,
    label: str | None = None,
    account_type: str | None = None,
    status: str | None = None,
    match_confidence: float | None = None,
    match_type: str | None = None,
    is_new_provider: bool | None = None,
) -> ImportCandidate | None:
    """Update a single candidate's match info or status."""
    with SessionLocal() as session:
        candidate = session.get(ImportCandidate, candidate_id)
        if not candidate:
            return None
        if provider_key is not None:
            candidate.provider_key = provider_key
        if label is not None:
            candidate.label = label
        if account_type is not None:
            candidate.account_type = account_type
        if status is not None:
            candidate.status = status
        if match_confidence is not None:
            candidate.match_confidence = match_confidence
        if match_type is not None:
            candidate.match_type = match_type
        if is_new_provider is not None:
            candidate.is_new_provider = is_new_provider
        session.commit()
        session.refresh(candidate)
        return candidate


def accept_import_candidate(candidate_id: int, provider_key: str, label: str, account_type: str) -> ImportCandidate | None:
    """Mark a candidate as accepted with the given provider info."""
    with SessionLocal() as session:
        candidate = session.get(ImportCandidate, candidate_id)
        if not candidate:
            return None
        candidate.status = "accepted"
        candidate.provider_key = provider_key
        candidate.label = label
        candidate.account_type = account_type
        session.commit()
        session.refresh(candidate)
        return candidate


def reject_import_candidate(candidate_id: int) -> ImportCandidate | None:
    """Mark a candidate as rejected."""
    with SessionLocal() as session:
        candidate = session.get(ImportCandidate, candidate_id)
        if not candidate:
            return None
        candidate.status = "rejected"
        session.commit()
        session.refresh(candidate)
        return candidate


def batch_update_candidates(
    candidate_ids: list[int],
    status: str | None = None,
    provider_key: str | None = None,
    label: str | None = None,
    account_type: str | None = None,
) -> int:
    """Batch update multiple candidates. Returns count updated."""
    if not candidate_ids:
        return 0
    with SessionLocal() as session:
        session.query(ImportCandidate).filter(
            ImportCandidate.id.in_(candidate_ids)
        ).update({
            **({} if status is None else {"status": status}),
            **({} if provider_key is None else {"provider_key": provider_key}),
            **({} if label is None else {"label": label}),
            **({} if account_type is None else {"account_type": account_type}),
        }, synchronize_session=False)
        session.commit()
        return len(candidate_ids)


def apply_matched_results(session_id: int, matched_mappings: list[dict]) -> int:
    """Apply match results to candidates in a session. Returns count updated.

    matched_mappings: list of {row_id, provider_key, label, account_type, confidence, match_type}
    """
    if not matched_mappings:
        return 0
    row_id_to_match: dict[int, dict] = {m["row_id"]: m for m in matched_mappings}
    with SessionLocal() as session:
        candidates = session.query(ImportCandidate).filter(
            ImportCandidate.session_id == session_id
        ).all()
        updated = 0
        for candidate in candidates:
            match = row_id_to_match.get(candidate.row_index)
            if match:
                candidate.provider_key = match.get("provider_key")
                candidate.label = match.get("label")
                candidate.account_type = match.get("account_type")
                candidate.match_confidence = match.get("confidence")
                candidate.match_type = match.get("match_type")
                candidate.status = "matched"
                updated += 1
        session.commit()
        return updated


def refresh_import_session_counts(session_id: int) -> dict:
    """Recalculate and update session counts from candidates."""
    with SessionLocal() as session:
        session_obj = session.get(ImportSession, session_id)
        if not session_obj:
            return {}
        candidates = session.query(ImportCandidate).filter(
            ImportCandidate.session_id == session_id
        ).all()
        total = len(candidates)
        processed = sum(1 for c in candidates if c.status != "pending")
        high_conf = sum(1 for c in candidates if (c.match_confidence or 0) >= 0.9 and c.status == "pending")
        needs_review = sum(1 for c in candidates if (c.match_confidence or 0) < 0.9 and c.status == "pending")
        accepted = sum(1 for c in candidates if c.status == "accepted")
        rejected = sum(1 for c in candidates if c.status in ("rejected", "skipped"))
        session_obj.total_count = total
        session_obj.processed_count = processed
        session_obj.high_confidence_count = high_conf
        session_obj.needs_review_count = needs_review
        session_obj.accepted_count = accepted
        session_obj.rejected_count = rejected
        session.commit()
        return {
            "total": total,
            "processed": processed,
            "high_confidence": high_conf,
            "needs_review": needs_review,
            "accepted": accepted,
            "rejected": rejected,
        }


def get_import_progress(session_id: int) -> dict:
    """Get current progress of an import session."""
    with SessionLocal() as session:
        session_obj = session.get(ImportSession, session_id)
        if not session_obj:
            return {}
        candidates = session.query(ImportCandidate).filter(
            ImportCandidate.session_id == session_id
        ).all()
        total = len(candidates)
        by_status = {}
        for c in candidates:
            by_status[c.status] = by_status.get(c.status, 0) + 1
        return {
            "session_id": session_id,
            "status": session_obj.status,
            "total": total,
            "processed": session_obj.processed_count,
            "high_confidence": session_obj.high_confidence_count,
            "needs_review": session_obj.needs_review_count,
            "accepted": session_obj.accepted_count,
            "rejected": session_obj.rejected_count,
            "by_status": by_status,
        }


def delete_import_session(session_id: int) -> bool:
    """Delete an import session and all its candidates."""
    with SessionLocal() as session:
        session_obj = session.get(ImportSession, session_id)
        if not session_obj:
            return False
        session.delete(session_obj)
        session.commit()
        return True
