"""Add user device tokens for push notifications

Revision ID: 007_add_device_tokens
Revises: 006_add_last_answer_date_to_streaks
Create Date: 2026-01-04

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '007_device_tokens'
down_revision = '006_streak_last_answer'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create user_device_tokens table for FCM push notifications
    op.create_table(
        'user_device_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(255), nullable=False),
        sa.Column('platform', sa.String(20), nullable=False),
        sa.Column('device_name', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'token', name='uq_user_device_token')
    )
    
    # Create indexes for efficient queries
    op.create_index('idx_device_tokens_user_id', 'user_device_tokens', ['user_id'])
    op.create_index('idx_device_tokens_active', 'user_device_tokens', ['is_active'])


def downgrade() -> None:
    op.drop_index('idx_device_tokens_active', table_name='user_device_tokens')
    op.drop_index('idx_device_tokens_user_id', table_name='user_device_tokens')
    op.drop_table('user_device_tokens')
