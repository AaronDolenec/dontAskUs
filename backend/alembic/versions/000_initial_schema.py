"""Initial schema creation with all tables and columns

Revision ID: 000_initial_schema
Revises: 
Create Date: 2025-12-13 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op  # pylint: disable=no-name-in-module
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '000_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial schema with all tables."""
    # Create question_templates table
    op.create_table(
        'question_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.String(36), nullable=False),
        sa.Column('category', sa.String(50), nullable=True),
        sa.Column('question_text', sa.String(255), nullable=True),
        sa.Column('option_a_template', sa.String(100), nullable=True),
        sa.Column('option_b_template', sa.String(100), nullable=True),
        sa.Column('question_type', sa.Enum('BINARY_VOTE', 'SINGLE_CHOICE', 'FREE_TEXT', name='questiontypeenum'), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('template_id')
    )
    
    # Create groups table
    op.create_table(
        'groups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.String(36), nullable=False),
        sa.Column('name', sa.String(100), nullable=True),
        sa.Column('invite_code', sa.String(8), nullable=False),
        sa.Column('qr_data', sa.Text(), nullable=True),
        sa.Column('admin_token', sa.String(255), nullable=True),
        sa.Column('creator_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('group_id'),
        sa.UniqueConstraint('invite_code'),
        sa.UniqueConstraint('admin_token')
    )
    op.create_index('idx_group_code', 'groups', ['invite_code'])
    op.create_index('ix_groups_name', 'groups', ['name'])
    
    # Create users table with session_token_expires_at
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=True),
        sa.Column('display_name', sa.String(50), nullable=True),
        sa.Column('session_token', sa.String(255), nullable=True),
        sa.Column('session_token_expires_at', sa.DateTime(), nullable=True),
        sa.Column('color_avatar', sa.String(7), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('answer_streak', sa.Integer(), nullable=True),
        sa.Column('longest_answer_streak', sa.Integer(), nullable=True),
        sa.Column('last_answer_date', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
        sa.UniqueConstraint('session_token'),
        sa.UniqueConstraint('group_id', 'session_token', name='uq_group_session'),
        sa.UniqueConstraint('group_id', 'display_name', name='uq_group_display_name')
    )
    op.create_index('idx_user_session', 'users', ['session_token'])
    op.create_index('ix_users_user_id', 'users', ['user_id'])
    
    # Add foreign key for creator_id in groups
    op.create_foreign_key('fk_groups_creator_id', 'groups', 'users', ['creator_id'], ['id'])
    
    # Create group_analytics table
    op.create_table(
        'group_analytics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=True),
        sa.Column('total_members', sa.Integer(), nullable=True),
        sa.Column('total_questions_created', sa.Integer(), nullable=True),
        sa.Column('total_votes_cast', sa.Integer(), nullable=True),
        sa.Column('average_participation_rate', sa.Float(), nullable=True),
        sa.Column('last_updated', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id']),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create daily_questions table
    op.create_table(
        'daily_questions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.String(36), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=True),
        sa.Column('template_id', sa.Integer(), nullable=True),
        sa.Column('question_text', sa.String(255), nullable=True),
        sa.Column('option_a', sa.String(100), nullable=True),
        sa.Column('option_b', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id']),
        sa.ForeignKeyConstraint(['template_id'], ['question_templates.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('question_id')
    )
    op.create_index('ix_daily_questions_question_id', 'daily_questions', ['question_id'])
    
    # Create votes table
    op.create_table(
        'votes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vote_id', sa.String(36), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('vote', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['question_id'], ['daily_questions.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('vote_id'),
        sa.UniqueConstraint('question_id', 'user_id', name='uq_user_question')
    )
    op.create_index('ix_votes_vote_id', 'votes', ['vote_id'])
    
    # Create question_sets table
    op.create_table(
        'question_sets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('set_id', sa.String(36), nullable=False),
        sa.Column('name', sa.String(150), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('set_id')
    )
    op.create_index('ix_question_sets_set_id', 'question_sets', ['set_id'])
    op.create_index('ix_question_sets_name', 'question_sets', ['name'])
    
    # Create question_set_templates table (matches models.QuestionSetTemplate)
    op.create_table(
        'question_set_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('question_set_id', sa.Integer(), nullable=True),
        sa.Column('template_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['question_set_id'], ['question_sets.id']),
        sa.ForeignKeyConstraint(['template_id'], ['question_templates.id']),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create group_question_sets table (matches models.GroupQuestionSet)
    op.create_table(
        'group_question_sets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=True),
        sa.Column('question_set_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('selected_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id']),
        sa.ForeignKeyConstraint(['question_set_id'], ['question_sets.id']),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create user_group_streaks table
    op.create_table(
        'user_group_streaks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('group_id', sa.Integer(), nullable=True),
        sa.Column('current_streak', sa.Integer(), nullable=True),
        sa.Column('longest_streak', sa.Integer(), nullable=True),
        sa.Column('last_activity', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table('user_group_streaks')
    op.drop_table('group_question_sets')
    op.drop_table('question_set_templates')
    op.drop_table('question_sets')
    op.drop_table('votes')
    op.drop_table('daily_questions')
    op.drop_table('group_analytics')
    op.drop_table('users')
    op.drop_table('groups')
    op.drop_table('question_templates')
