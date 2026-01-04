"""Add last_answer_date column to user_group_streaks

Revision ID: 006_add_last_answer_date_to_streaks
Revises: 005_make_totp_optional
Create Date: 2025-12-18 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '006_streak_last_answer'
down_revision = '005_totp_optional'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add last_answer_date column to user_group_streaks (idempotent)
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col['name'] for col in inspector.get_columns('user_group_streaks')}
    if 'last_answer_date' not in columns:
        op.add_column('user_group_streaks', sa.Column('last_answer_date', sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Remove last_answer_date column if it exists
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col['name'] for col in inspector.get_columns('user_group_streaks')}
    if 'last_answer_date' in columns:
        op.drop_column('user_group_streaks', 'last_answer_date')
