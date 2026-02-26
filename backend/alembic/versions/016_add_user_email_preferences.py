"""Add email notification preference columns to users table.

Revision ID: 016_add_user_email_preferences
Revises: 015_add_login_count
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa

revision = '016_add_user_email_preferences'
down_revision = '015_add_login_count'
branch_labels = None
depends_on = None


def upgrade():
    # Add columns with a server_default so existing rows are populated safely,
    # then remove the server_default (pattern used by alembic autogenerate).
    op.add_column(
        'users',
        sa.Column('email_notify_new_question', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )
    op.add_column(
        'users',
        sa.Column('email_notify_reminder', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )

    # Remove the server_default so future inserts use application defaults
    op.alter_column('users', 'email_notify_new_question', server_default=None)
    op.alter_column('users', 'email_notify_reminder', server_default=None)


def downgrade():
    op.drop_column('users', 'email_notify_reminder')
    op.drop_column('users', 'email_notify_new_question')
