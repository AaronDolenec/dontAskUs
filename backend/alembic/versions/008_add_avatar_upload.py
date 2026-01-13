"""Add avatar upload columns to users table

Revision ID: 008_avatar_upload
Revises: 007_device_tokens
Create Date: 2026-01-13

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '008_avatar_upload'
down_revision = '007_device_tokens'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add avatar_filename column for storing uploaded avatar filename
    op.add_column('users', sa.Column('avatar_filename', sa.String(255), nullable=True))
    # Add avatar_uploaded_at column for tracking when avatar was uploaded
    op.add_column('users', sa.Column('avatar_uploaded_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'avatar_uploaded_at')
    op.drop_column('users', 'avatar_filename')
