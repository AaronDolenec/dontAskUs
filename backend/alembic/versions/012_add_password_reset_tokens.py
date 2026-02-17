"""Add password_reset_tokens table for self-service password resets.

Revision ID: 012_add_password_reset_tokens
Revises: 011_drop_unique_group_date
Create Date: 2026-02-17
"""

from alembic import op
import sqlalchemy as sa

revision = '012_add_password_reset_tokens'
down_revision = '011_drop_unique_group_date'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'password_reset_tokens',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('account_id', sa.Integer, sa.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_password_reset_account', 'password_reset_tokens', ['account_id'])


def downgrade():
    op.drop_index('idx_password_reset_account', table_name='password_reset_tokens')
    op.drop_table('password_reset_tokens')
