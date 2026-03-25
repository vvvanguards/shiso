"""add balance_types lookup table

Revision ID: 80fc688484a3
Revises: 005_rewards_login_membership
Create Date: 2026-03-24 22:39:06.052195

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '80fc688484a3'
down_revision: Union[str, None] = '005_rewards_login_membership'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create balance_types lookup table
    op.create_table(
        'balance_types',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.Text(), unique=True, nullable=False),
    )

    # Seed the two valid values
    op.execute("INSERT INTO balance_types (id, name) VALUES (1, 'asset'), (2, 'liability')")

    # Add nullable FK column for backfill
    op.add_column(
        'financial_account_types',
        sa.Column('balance_type_id', sa.Integer(), sa.ForeignKey('balance_types.id'), nullable=True),
    )

    # Backfill balance_type_id from existing balance_type text
    op.execute("""
        UPDATE financial_account_types
        SET balance_type_id = CASE
            WHEN balance_type = 'asset' THEN 1
            WHEN balance_type = 'liability' THEN 2
            ELSE 2
        END
    """)

    # Make non-nullable now that all rows are populated
    op.alter_column('financial_account_types', 'balance_type_id', nullable=False)

    # Drop the old text column
    op.drop_column('financial_account_types', 'balance_type')


def downgrade() -> None:
    # Re-add text column
    op.add_column(
        'financial_account_types',
        sa.Column('balance_type', sa.Text(), nullable=False, server_default='liability'),
    )

    # Restore text values from FK
    op.execute("""
        UPDATE financial_account_types
        SET balance_type = CASE
            WHEN balance_type_id = 1 THEN 'asset'
            ELSE 'liability'
        END
    """)

    op.alter_column('financial_account_types', 'balance_type', server_default=None)

    # Drop FK column and lookup table
    op.drop_column('financial_account_types', 'balance_type_id')
    op.drop_table('balance_types')
