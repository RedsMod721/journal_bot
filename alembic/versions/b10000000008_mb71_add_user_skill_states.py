"""Add user_skill_states table for skill hierarchy

Revision ID: b10000000008
Revises: b10000000007
Create Date: 2026-03-11 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'b10000000008'
down_revision = 'b10000000007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_skill_states',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('skill_id', sa.String(36), nullable=False),

        # State tracking
        sa.Column('state', sa.String(30), nullable=False, server_default='locked'),
        sa.Column('user_blocked', sa.Boolean(), nullable=False, server_default=sa.false()),

        # Timestamps
        sa.Column('discovered_at', sa.DateTime(), nullable=True),
        sa.Column('unlocked_at', sa.DateTime(), nullable=True),
        sa.Column('activated_at', sa.DateTime(), nullable=True),

        # Metadata
        sa.Column('discovery_source', sa.String(255), nullable=True),
        sa.Column('unlock_parent_skill_id', sa.String(36), nullable=True),

        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='fk_user_skill_states_user'),
        sa.ForeignKeyConstraint(['skill_id'], ['global_skills.id'], ondelete='CASCADE', name='fk_user_skill_states_skill'),
        sa.UniqueConstraint('user_id', 'id', name='uq_user_skill_states_user_id'),
        sa.UniqueConstraint('user_id', 'skill_id', name='uq_user_skill_states_user_skill'),
        sa.CheckConstraint(
            "state IN ('locked','discovered','unlocked_hidden','activated')",
            name='ck_user_skill_states_state',
        ),
    )

    op.create_index('idx_user_skill_states_user', 'user_skill_states', ['user_id'])
    op.create_index('idx_user_skill_states_state', 'user_skill_states', ['state'])
    op.create_index('idx_user_skill_states_user_state', 'user_skill_states', ['user_id', 'state'])

    op.add_column(
        'users',
        sa.Column('default_blocked_preference', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('users', 'default_blocked_preference')
    op.drop_index('idx_user_skill_states_user_state', table_name='user_skill_states')
    op.drop_index('idx_user_skill_states_state', table_name='user_skill_states')
    op.drop_index('idx_user_skill_states_user', table_name='user_skill_states')
    op.drop_table('user_skill_states')
