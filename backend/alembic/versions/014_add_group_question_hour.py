"""Add question_hour column to groups for per-group daily rollover time.

Each group has its own 'new day' boundary (a UTC hour, 0-23).
Existing groups are backfilled using their created_at hour + a random offset of ±3 hours.

Revision ID: 014_add_group_question_hour
Revises: 013_add_featured_member
Create Date: 2026-02-19
"""
from alembic import op
import sqlalchemy as sa
import random

revision = '014_add_group_question_hour'
down_revision = '013_add_featured_member'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('groups', sa.Column('question_hour', sa.Integer(), nullable=True))

    # Backfill existing groups: created_at hour + random offset in [-3, +3]
    conn = op.get_bind()
    groups = conn.execute(sa.text("SELECT id, created_at FROM groups")).fetchall()
    for group_id, created_at in groups:
        if created_at is not None:
            base_hour = created_at.hour
        else:
            base_hour = 0
        offset = random.randint(-3, 3)
        question_hour = (base_hour + offset) % 24
        conn.execute(
            sa.text("UPDATE groups SET question_hour = :qh WHERE id = :gid"),
            {"qh": question_hour, "gid": group_id},
        )


def downgrade():
    op.drop_column('groups', 'question_hour')
