"""Remove admin_token column from groups table

Revision ID: 010_remove_admin_token
Revises: 009_add_accounts_table
Create Date: 2026-02-17
"""

from alembic import op
import sqlalchemy as sa

revision = '010_remove_admin_token'
down_revision = '009_add_accounts'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('groups_admin_token_key', 'groups', type_='unique')
    op.drop_column('groups', 'admin_token')


def downgrade():
    op.add_column('groups', sa.Column('admin_token', sa.String(255), nullable=True))
    op.create_unique_constraint('groups_admin_token_key', 'groups', ['admin_token'])
