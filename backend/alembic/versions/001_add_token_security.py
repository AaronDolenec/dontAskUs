"""Add token hashing and expiry fields

Revision ID: 001_add_token_security
Revises: 000_initial_schema
Create Date: 2025-12-13 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op  # pylint: disable=no-name-in-module
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_add_token_security'
down_revision: str = '000_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Verify session_token_expires_at column exists in users table."""
    # Check if column already exists before adding
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('users')]
    
    # Column should already exist from initial schema, but check just in case
    if 'session_token_expires_at' not in columns:
        op.add_column('users', sa.Column('session_token_expires_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Remove session_token_expires_at column from users table."""
    # Check if column exists before dropping
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('users')]
    
    if 'session_token_expires_at' in columns:
        op.drop_column('users', 'session_token_expires_at')
