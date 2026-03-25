"""add is_deleted to scraper_logins

Revision ID: 002_add_is_deleted
Revises: 001_initial
Create Date: 2026-03-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '002_add_is_deleted'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('scraper_logins') as batch_op:
        batch_op.add_column(sa.Column('is_deleted', sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('scraper_logins') as batch_op:
        batch_op.drop_column('is_deleted')
