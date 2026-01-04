"""Add instance admin schema: audit logs, ownership tracking, suspension fields

Revision ID: 003_instance_admin_schema
Revises: 003_answers_options
Create Date: 2025-12-16 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003_admin_schema'
down_revision = '003_answers_options'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add fields to question_sets table
    # Note: is_public already exists in initial schema, so only add new fields
    op.add_column('question_sets', sa.Column('creator_id', sa.Integer(), nullable=True))
    op.add_column('question_sets', sa.Column('created_by_group_id', sa.Integer(), nullable=True))
    op.add_column('question_sets', sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'))
    
    # Create foreign keys for question_sets
    op.create_foreign_key(
        'fk_question_sets_creator_id',
        'question_sets', 'admin_users',
        ['creator_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_question_sets_created_by_group_id',
        'question_sets', 'groups',
        ['created_by_group_id'], ['id'],
        ondelete='SET NULL'
    )

    # Add fields to groups table
    op.add_column('groups', sa.Column('instance_admin_notes', sa.Text(), nullable=True))
    op.add_column('groups', sa.Column('total_sets_created', sa.Integer(), nullable=False, server_default='0'))

    # Add fields to users table
    op.add_column('users', sa.Column('is_suspended', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('suspension_reason', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('last_known_ip', postgresql.INET(), nullable=True))
    op.add_column('users', sa.Column('user_metadata', postgresql.JSONB(), nullable=True, server_default='{}'))

    # Add fields to group_question_sets table
    op.add_column('group_question_sets', sa.Column('assigned_by_admin_id', sa.Integer(), nullable=True))
    op.add_column('group_question_sets', sa.Column('assignment_notes', sa.Text(), nullable=True))
    
    op.create_foreign_key(
        'fk_group_question_sets_assigned_by_admin_id',
        'group_question_sets', 'admin_users',
        ['assigned_by_admin_id'], ['id'],
        ondelete='SET NULL'
    )

    # Extend admin_users table
    op.add_column('admin_users', sa.Column('login_attempt_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('admin_users', sa.Column('last_login_attempt', sa.DateTime(timezone=True), nullable=True))
    op.add_column('admin_users', sa.Column('last_login_ip', postgresql.INET(), nullable=True))
    op.add_column('admin_users', sa.Column('is_locked_until', sa.DateTime(timezone=True), nullable=True))

    # Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('admin_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('target_type', sa.String(50), nullable=False),
        sa.Column('target_id', sa.String(255), nullable=False),
        sa.Column('before_state', postgresql.JSONB(), nullable=True),
        sa.Column('after_state', postgresql.JSONB(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('ip_address', postgresql.INET(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['admin_id'], ['admin_users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_audit_logs_admin_id', 'admin_id'),
        sa.Index('idx_audit_logs_action', 'action'),
        sa.Index('idx_audit_logs_timestamp', 'timestamp'),
        sa.Index('idx_audit_logs_target', 'target_type', 'target_id'),
    )

    # Create group_custom_sets table (tracks private sets created by group creators)
    op.create_table(
        'group_custom_sets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('set_id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('creator_user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['set_id'], ['question_sets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['creator_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('set_id', 'group_id', name='uq_group_custom_set'),
        sa.Index('idx_group_custom_sets_group_id', 'group_id'),
        sa.Index('idx_group_custom_sets_creator_id', 'creator_user_id'),
    )


def downgrade() -> None:
    # Drop group_custom_sets table
    op.drop_table('group_custom_sets')

    # Drop audit_logs table
    op.drop_table('audit_logs')

    # Remove fields from admin_users
    op.drop_column('admin_users', 'is_locked_until')
    op.drop_column('admin_users', 'last_login_ip')
    op.drop_column('admin_users', 'last_login_attempt')
    op.drop_column('admin_users', 'login_attempt_count')

    # Remove fields from group_question_sets
    op.drop_constraint('fk_group_question_sets_assigned_by_admin_id', 'group_question_sets', type_='foreignkey')
    op.drop_column('group_question_sets', 'assignment_notes')
    op.drop_column('group_question_sets', 'assigned_by_admin_id')

    # Remove fields from users
    op.drop_column('users', 'user_metadata')
    op.drop_column('users', 'last_known_ip')
    op.drop_column('users', 'suspension_reason')
    op.drop_column('users', 'is_suspended')

    # Remove fields from groups
    op.drop_column('groups', 'total_sets_created')
    op.drop_column('groups', 'instance_admin_notes')

    # Remove fields from question_sets
    op.drop_constraint('fk_question_sets_created_by_group_id', 'question_sets', type_='foreignkey')
    op.drop_constraint('fk_question_sets_creator_id', 'question_sets', type_='foreignkey')
    op.drop_column('question_sets', 'usage_count')
    op.drop_column('question_sets', 'created_by_group_id')
    op.drop_column('question_sets', 'creator_id')
