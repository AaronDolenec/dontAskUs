"""Create app_settings and email_verification_tokens tables

Revision ID: 018_create_app_settings_and_email_verification
Revises: 017_add_user_push_preference
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa

revision = '018_app_settings'
down_revision = '017_add_user_push_preference'
branch_labels = None
depends_on = None


def upgrade():
    # app_settings table
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(length=100), primary_key=True),
        sa.Column('value', sa.String(length=500), nullable=False),
    )

    # email_verification_tokens table
    op.create_table(
        'email_verification_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table('email_verification_tokens')
    op.drop_table('app_settings')
