"""Add push notification preference column to users table.

Revision ID: 017_add_user_push_preference
Revises: 016_add_user_email_preferences
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa

revision = '017_add_user_push_preference'
down_revision = '016_add_user_email_preferences'
branch_labels = None
depends_on = None


def upgrade():
    # Add column with a server_default so existing rows are populated safely,
    # then remove the server_default (pattern used by alembic autogenerate).
    op.add_column(
        'users',
        sa.Column('push_notify_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )

    # Remove the server_default so future inserts use application defaults
    op.alter_column('users', 'push_notify_enabled', server_default=None)


def downgrade():
    op.drop_column('users', 'push_notify_enabled')
