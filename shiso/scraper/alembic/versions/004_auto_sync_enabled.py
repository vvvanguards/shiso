"""add auto_sync_enabled to scraper_logins

Revision ID: 004_auto_sync_enabled
Revises: 003_workflow_orchestration_fields
Create Date: 2026-03-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '004_auto_sync_enabled'
down_revision: Union[str, None] = '003_workflow_orchestration_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('scraper_logins') as batch_op:
        batch_op.add_column(sa.Column('auto_sync_enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')))


def downgrade() -> None:
    with op.batch_alter_table('scraper_logins') as batch_op:
        batch_op.drop_column('auto_sync_enabled')
