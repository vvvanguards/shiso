"""add scraper_login_id, membership_id, current_balance to rewards_programs

Revision ID: 005_rewards_login_membership
Revises: 004_auto_sync_enabled
Create Date: 2026-03-24

- scraper_login_id: required FK to scraper_logins (where you manage the program)
- financial_account_id: made nullable (was required)
- membership_id: string for loyalty/membership number
- current_balance: latest known balance (fast access)
- Update UniqueConstraint from (financial_account_id, program_name) to (scraper_login_id, program_name)

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '005_rewards_login_membership'
down_revision: Union[str, None] = '004_auto_sync_enabled'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('rewards_programs') as batch_op:
        # Add new columns
        batch_op.add_column(sa.Column('scraper_login_id', sa.Integer(), sa.ForeignKey('scraper_logins.id', ondelete='SET NULL'), nullable=False, server_default=sa.text('0')))
        batch_op.add_column(sa.Column('membership_id', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('current_balance', sa.Float(), nullable=True))
        # Drop old unique constraint (on financial_account_id, program_name)
        batch_op.drop_constraint('uq_rewards_program_account_name', type_='unique')
        # Add new unique constraint (on scraper_login_id, program_name)
        batch_op.create_unique_constraint('uq_rewards_program_login_name', ['scraper_login_id', 'program_name'])
        # Make financial_account_id nullable
        batch_op.alter_column('financial_account_id', existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('rewards_programs') as batch_op:
        batch_op.alter_column('financial_account_id', existing_type=sa.Integer(), nullable=False)
        batch_op.drop_constraint('uq_rewards_program_login_name', type_='unique')
        batch_op.create_unique_constraint('uq_rewards_program_account_name', ['financial_account_id', 'program_name'])
        batch_op.drop_column('current_balance')
        batch_op.drop_column('membership_id')
        batch_op.drop_column('scraper_login_id')
