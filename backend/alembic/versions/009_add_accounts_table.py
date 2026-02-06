"""Add accounts table and link users to accounts

Revision ID: 009_add_accounts
Revises: 008_avatar_upload
Create Date: 2025-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy import inspect as sa_inspect

# revision identifiers, used by Alembic.
revision = '009_add_accounts'
down_revision = '008_avatar_upload'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa_inspect(conn)
    existing_tables = inspector.get_table_names()

    # 1. Create accounts table
    if 'accounts' not in existing_tables:
        op.create_table(
            'accounts',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('account_id', sa.String(36), unique=True, nullable=False),
            sa.Column('email', sa.String(255), unique=True, nullable=False),
            sa.Column('password_hash', sa.String(255), nullable=False),
            sa.Column('display_name', sa.String(50), nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
            sa.Column('is_verified', sa.Boolean(), server_default='false', nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column('last_login', sa.DateTime(), nullable=True),
            sa.Column('last_login_ip', INET, nullable=True),
            sa.Column('login_attempt_count', sa.Integer(), server_default='0', nullable=False),
            sa.Column('last_login_attempt', sa.DateTime(), nullable=True),
            sa.Column('is_locked_until', sa.DateTime(), nullable=True),
        )
        op.create_index('idx_accounts_email', 'accounts', ['email'], unique=True)

    # 2. Add account_id column to users table (nullable for migration period)
    existing_columns = [c['name'] for c in inspector.get_columns('users')]
    if 'account_id' not in existing_columns:
        op.add_column('users', sa.Column('account_id', sa.Integer(), nullable=True))
        op.create_foreign_key(
            'fk_users_account_id',
            'users', 'accounts',
            ['account_id'], ['id'],
            ondelete='SET NULL'
        )
        op.create_index('idx_user_account', 'users', ['account_id'])

    # 3. Make session_token nullable (new users won't need it)
    # This is safe because existing users already have session tokens
    op.alter_column('users', 'session_token', nullable=True)

    # 4. Add unique constraint for account_id + group_id (one membership per group per account)
    # Only add if it doesn't exist
    existing_constraints = [c['name'] for c in inspector.get_unique_constraints('users')]
    if 'uq_account_group' not in existing_constraints:
        # Use a partial unique constraint - only enforce when account_id is not null
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_account_group "
            "ON users (account_id, group_id) WHERE account_id IS NOT NULL"
        )


def downgrade():
    conn = op.get_bind()
    inspector = sa_inspect(conn)

    # Remove the partial unique index
    op.execute("DROP INDEX IF EXISTS uq_account_group")

    # Remove account_id from users
    existing_columns = [c['name'] for c in inspector.get_columns('users')]
    if 'account_id' in existing_columns:
        op.drop_constraint('fk_users_account_id', 'users', type_='foreignkey')
        op.drop_index('idx_user_account', table_name='users')
        op.drop_column('users', 'account_id')

    # Make session_token non-nullable again
    op.alter_column('users', 'session_token', nullable=False)

    # Drop accounts table
    if 'accounts' in inspector.get_table_names():
        op.drop_index('idx_accounts_email', table_name='accounts')
        op.drop_table('accounts')
