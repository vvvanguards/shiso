"""Models for generic tool run outputs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class ToolRunOutput(Base):
    __tablename__ = "tool_run_outputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tool_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    sync_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scraper_login_sync_runs.id", ondelete="SET NULL"))
    scraper_login_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scraper_logins.id", ondelete="SET NULL"))
    provider_key: Mapped[str] = mapped_column(String, nullable=False)
    output_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    items_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
