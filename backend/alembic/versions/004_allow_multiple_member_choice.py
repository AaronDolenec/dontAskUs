"""Allow multi-select member choice questions

Revision ID: 004_allow_multiple_member_choice
Revises: 003_instance_admin_schema
Create Date: 2025-12-17 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '004_multi_choice'
down_revision = '003_admin_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('question_templates', sa.Column('allow_multiple', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('daily_questions', sa.Column('allow_multiple', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    # Remove server defaults after backfilling existing rows
    op.alter_column('question_templates', 'allow_multiple', server_default=None)
    op.alter_column('daily_questions', 'allow_multiple', server_default=None)


def downgrade() -> None:
    op.drop_column('daily_questions', 'allow_multiple')
    op.drop_column('question_templates', 'allow_multiple')
