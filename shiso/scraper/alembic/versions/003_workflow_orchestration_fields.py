"""add orchestration fields to workflow_definitions

Revision ID: 003_workflow_orchestration_fields
Revises: 002_add_is_deleted
Create Date: 2026-03-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '003_workflow_orchestration_fields'
down_revision: Union[str, None] = '002_add_is_deleted'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('workflow_definitions') as batch_op:
        batch_op.add_column(sa.Column('persistence_strategy', sa.String(), nullable=False, server_default='generic'))
        batch_op.add_column(sa.Column('enrichment_enabled', sa.Boolean(), nullable=False, server_default=sa.text('0')))
        batch_op.add_column(sa.Column('statement_download_enabled', sa.Boolean(), nullable=False, server_default=sa.text('0')))
        batch_op.add_column(sa.Column('assessment_enabled', sa.Boolean(), nullable=False, server_default=sa.text('0')))
        batch_op.add_column(sa.Column('dedup_enabled', sa.Boolean(), nullable=False, server_default=sa.text('0')))


def downgrade() -> None:
    with op.batch_alter_table('workflow_definitions') as batch_op:
        batch_op.drop_column('dedup_enabled')
        batch_op.drop_column('assessment_enabled')
        batch_op.drop_column('statement_download_enabled')
        batch_op.drop_column('enrichment_enabled')
        batch_op.drop_column('persistence_strategy')
