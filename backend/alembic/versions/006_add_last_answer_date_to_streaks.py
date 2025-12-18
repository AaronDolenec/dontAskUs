"""Add last_answer_date column to user_group_streaks

Revision ID: 006_add_last_answer_date_to_streaks
Revises: 005_make_totp_optional
Create Date: 2025-12-18 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '006_add_last_answer_date_to_streaks'
down_revision = '005_make_totp_optional'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add last_answer_date column to user_group_streaks
    op.add_column('user_group_streaks', sa.Column('last_answer_date', sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Remove last_answer_date column
    op.drop_column('user_group_streaks', 'last_answer_date')
