"""
Expand answer options and question types
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003_answers_options'
down_revision = '002_question_type'
branch_labels = None
depends_on = None

old_question_enum = postgresql.ENUM(
    'BINARY_VOTE', 'SINGLE_CHOICE', 'FREE_TEXT',
    name='questiontypeenum_old'
)

new_question_enum = postgresql.ENUM(
    'BINARY_VOTE', 'SINGLE_CHOICE', 'FREE_TEXT', 'MEMBER_CHOICE', 'DUO_CHOICE',
    name='questiontypeenum_new'
)


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1) Add options column to daily_questions if missing (idempotent)
    op.execute('ALTER TABLE daily_questions ADD COLUMN IF NOT EXISTS options TEXT')

    # 2) Widen votes.answer to Text if not already
    vote_cols = inspector.get_columns('votes')
    answer_col = next((c for c in vote_cols if c['name'] == 'answer'), None)
    if answer_col and not isinstance(answer_col['type'], sa.Text):
        op.alter_column('votes', 'answer',
            existing_type=answer_col['type'],
            type_=sa.Text(),
            existing_nullable=True
        )

    # 3) Expand questiontypeenum with new values if needed
    existing_enum = sa.Enum(name='questiontypeenum').create(bind=bind, checkfirst=True)
    # The above ensures the type exists; now check labels
    enum_labels = bind.execute(sa.text("SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON e.enumtypid = t.oid WHERE t.typname = 'questiontypeenum'"))
    labels = {row[0] for row in enum_labels}
    if 'DUO_CHOICE' not in labels or 'MEMBER_CHOICE' not in labels:
        new_question_enum.create(bind, checkfirst=True)
        op.execute("ALTER TABLE question_templates ALTER COLUMN question_type TYPE questiontypeenum_new USING question_type::text::questiontypeenum_new")
        op.execute("ALTER TABLE daily_questions ALTER COLUMN question_type TYPE questiontypeenum_new USING question_type::text::questiontypeenum_new")
        op.execute('DROP TYPE questiontypeenum')
        op.execute('ALTER TYPE questiontypeenum_new RENAME TO questiontypeenum')
    else:
        # Already expanded; nothing to do
        pass


def downgrade():
    bind = op.get_bind()

    # recreate old enum under temp name
    old_question_enum.create(bind, checkfirst=False)
    op.execute("ALTER TABLE question_templates ALTER COLUMN question_type TYPE questiontypeenum_old USING question_type::text::questiontypeenum_old")
    op.execute("ALTER TABLE daily_questions ALTER COLUMN question_type TYPE questiontypeenum_old USING question_type::text::questiontypeenum_old")
    op.execute('DROP TYPE questiontypeenum')
    op.execute('ALTER TYPE questiontypeenum_old RENAME TO questiontypeenum')

    # narrow votes.answer back to length 1
    op.alter_column('votes', 'answer',
        existing_type=sa.Text(),
        type_=sa.String(length=1),
        existing_nullable=True
    )

    # drop options column
    op.drop_column('daily_questions', 'options')