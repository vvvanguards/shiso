"""Models for generic tool run outputs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow_naive() -> datetime:
    """Store UTC timestamps without tzinfo for compatibility with current schema."""
    return datetime.now(UTC).replace(tzinfo=None)


class ToolRunOutput(Base):
    __tablename__ = "tool_run_outputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tool_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    sync_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scraper_login_sync_runs.id", ondelete="SET NULL"))
    scraper_login_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scraper_logins.id", ondelete="SET NULL"))
    provider_key: Mapped[str] = mapped_column(String, nullable=False)
    output_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    items_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive, nullable=False)


class ProviderPlaybookRecord(Base):
    """Persisted provider guidance for browser automation and analyst feedback."""

    __tablename__ = "provider_playbooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_key: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    extraction_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    failed_actions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    effective_patterns: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    navigation_tips: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utcnow_naive,
        onupdate=_utcnow_naive,
        nullable=False,
    )


class WorkflowDefinitionRecord(Base):
    """Persisted workflow/tool definitions."""

    __tablename__ = "workflow_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prompt_template: Mapped[str] = mapped_column(Text, nullable=False, default="")
    result_key: Mapped[str] = mapped_column(String, nullable=False, default="items")
    output_schema_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utcnow_naive,
        onupdate=_utcnow_naive,
        nullable=False,
    )


class WorkflowRevisionSuggestionRecord(Base):
    """Persisted analyst suggestions for revising a workflow definition."""

    __tablename__ = "workflow_revision_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tool_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    provider_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    sync_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scraper_login_sync_runs.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String, nullable=False, default="open", index=True)
    trigger_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    suggested_definition_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metrics_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utcnow_naive,
        onupdate=_utcnow_naive,
        nullable=False,
    )
