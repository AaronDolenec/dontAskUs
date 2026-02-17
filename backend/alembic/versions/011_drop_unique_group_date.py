"""Drop unique constraint on (group_id, question_date) to allow multiple
questions per group per day (e.g. admin renewal preserves old questions).

Revision ID: 011_drop_unique_group_date
Revises: 010_remove_admin_token
Create Date: 2026-02-17
"""

from alembic import op

revision = '011_drop_unique_group_date'
down_revision = '010_remove_admin_token'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('uq_group_date', 'daily_questions', type_='unique')


def downgrade():
    op.create_unique_constraint('uq_group_date', 'daily_questions', ['group_id', 'question_date'])
