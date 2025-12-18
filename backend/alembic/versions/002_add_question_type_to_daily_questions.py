"""
Migration placeholder - question_type and question_date now created in initial schema
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '002_question_type'
down_revision = '001_token_security'
branch_labels = None
depends_on = None

def upgrade():
    # This migration is now a placeholder since question_type and question_date
    # are created as part of the initial schema (000_initial_schema.py)
    pass

def downgrade():
    # Nothing to downgrade
    pass
