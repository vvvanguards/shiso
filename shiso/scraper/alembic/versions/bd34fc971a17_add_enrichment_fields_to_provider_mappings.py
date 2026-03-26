"""add enrichment fields to provider_mappings

Revision ID: bd34fc971a17
Revises: 80fc688484a3
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '80fc688484a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

def upgrade() -> None:
    op.add_column('provider_mappings', sa.Column('login_url', sa.Text, nullable=True))
    op.add_column('provider_mappings', sa.Column('favicon_url', sa.Text, nullable=True))
    op.add_column('provider_mappings', sa.Column('is_financial', sa.Boolean, nullable=True))

def downgrade() -> None:
    op.drop_column('provider_mappings', 'is_financial')
    op.drop_column('provider_mappings', 'favicon_url')
    op.drop_column('provider_mappings', 'login_url')
