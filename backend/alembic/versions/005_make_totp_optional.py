"""Make TOTP optional for admins - allow setup after first login

Revision ID: 005_make_totp_optional
Revises: 004_allow_multiple_member_choice
Create Date: 2025-12-18 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '005_make_totp_optional'
down_revision = '004_allow_multiple_member_choice'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make totp_secret nullable
    op.alter_column('admin_users', 'totp_secret',
               existing_type=sa.String(32),
               nullable=True)
    
    # Add totp_enabled column with default False
    op.add_column('admin_users', sa.Column('totp_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    
    # Remove server default after adding
    op.alter_column('admin_users', 'totp_enabled', server_default=None)


def downgrade() -> None:
    # Remove totp_enabled column
    op.drop_column('admin_users', 'totp_enabled')
    
    # Make totp_secret non-nullable again (will fail if NULL values exist)
    op.alter_column('admin_users', 'totp_secret',
               existing_type=sa.String(32),
               nullable=False)
