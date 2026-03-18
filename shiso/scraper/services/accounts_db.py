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
    PromoAprPeriod,
    RewardsProgram,
    RewardsBalance,
    ScraperLogin,
)


@dataclass
class SnapshotView:
    provider_key: str
    institution: str
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
            # Resolve institution and account_type from the ScraperLogin record
            login_id = results[0].get("login_id") if results else None
            login = session.get(ScraperLogin, login_id) if login_id else None
            institution = (login.institution if login and login.institution
                           else provider_key.replace("_", " ").title())
            acct_type_name = login.account_type if login else "Other"
            account_type = self._get_or_create_account_type(session, acct_type_name)
            saved: list[SnapshotView] = []
            for row in results:
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

        if not account:
            account = FinancialAccount(
                account_type_id=account_type_id,
                provider_key=provider_key,
                institution=institution,
                account_number=account_number,
                created_at=captured_at,
                updated_at=captured_at,
                first_seen_at=captured_at,
            )
            session.add(account)
            session.flush()

        account.display_name = display_name
        account.account_number = account_number or account.account_number
        account.account_mask = account_mask
        account.address = address
        account.status = row.get("status")
        account.active = _infer_active(row.get("status"))
        account.last_seen_at = captured_at
        account.last_snapshot_at = captured_at
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
                promo_type="purchase",  # default; can be refined later
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
                session.query(RewardsBalance, RewardsProgram, FinancialAccount)
                .join(latest_subq,
                    (RewardsBalance.rewards_program_id == latest_subq.c.rewards_program_id)
                    & (RewardsBalance.captured_at == latest_subq.c.max_captured_at))
                .join(RewardsProgram, RewardsBalance.rewards_program_id == RewardsProgram.id)
                .join(FinancialAccount, RewardsProgram.financial_account_id == FinancialAccount.id)
                .all()
            )

            total_value = 0.0
            by_type: dict[str, dict] = {}
            programs: list[dict] = []

            for rb, rp, fa in balances:
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
                    "account_id": fa.id,
                    "account_display_name": fa.display_name,
                    "account_mask": fa.account_mask,
                    "institution": fa.institution,
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
        name = _normalize_text(raw.get("card_name") or account.display_name)
        address = _normalize_text(raw.get("address") or account.address)
        if name and address:
            return (account.provider_key, "name_address", f"{name}|{address}")
        if name:
            return (account.provider_key, "name", name)
        return None


def _snapshot_view_from_values(
    provider_key: str,
    institution: str,
    account: FinancialAccount,
    row: dict,
    captured_at: datetime,
) -> SnapshotView:
    category = _infer_account_category(provider_key, row)
    balance_type = _infer_balance_type(category)
    current_balance = row.get("current_balance")
    signed_balance = None if current_balance is None else current_balance * (1 if balance_type == "asset" else -1)
    return SnapshotView(
        provider_key=provider_key,
        institution=institution,
        display_name=row.get("card_name") or account.display_name,
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
    name = row.get("card_name") or row.get("label") or row.get("address") or institution
    # Clean up common noise from scraped card names
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
        for value in [row.get("card_name"), row.get("label"), row.get("status"), row.get("address")]
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
