"""Add login_count column to accounts table.

Tracks total number of successful logins per account.

Revision ID: 015_add_login_count
Revises: 014_add_group_question_hour
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa

revision = '015_add_login_count'
down_revision = '014_add_group_question_hour'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('accounts', sa.Column('login_count', sa.Integer(), server_default='0', nullable=False))


def downgrade():
    op.drop_column('accounts', 'login_count')
