"""Add featured_member_id to daily_questions for {member} placeholder support.

Revision ID: 013_add_featured_member
Revises: 012_add_password_reset_tokens
Create Date: 2026-02-18
"""

from alembic import op
import sqlalchemy as sa

revision = '013_add_featured_member'
down_revision = '012_add_password_reset_tokens'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('daily_questions', sa.Column('featured_member_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True))
    op.create_index('idx_daily_questions_featured_member', 'daily_questions', ['featured_member_id'])


def downgrade():
    op.drop_index('idx_daily_questions_featured_member', table_name='daily_questions')
    op.drop_column('daily_questions', 'featured_member_id')
