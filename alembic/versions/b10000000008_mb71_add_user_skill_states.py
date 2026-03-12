"""Add user_skill_states table for skill hierarchy.

Revision ID: b10000000008
Revises: b10000000007
Create Date: 2026-03-11 09:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers
revision = "b10000000008"
down_revision = "b10000000007"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    if not _table_exists("user_skill_states"):
        op.create_table(
            "user_skill_states",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("skill_id", sa.String(36), nullable=False),
            sa.Column("state", sa.String(30), nullable=False, server_default="locked"),
            sa.Column("user_blocked", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("discovered_at", sa.DateTime(), nullable=True),
            sa.Column("unlocked_at", sa.DateTime(), nullable=True),
            sa.Column("activated_at", sa.DateTime(), nullable=True),
            sa.Column("discovery_source", sa.String(255), nullable=True),
            sa.Column("unlock_parent_skill_id", sa.String(36), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["users.id"],
                ondelete="CASCADE",
                name="fk_user_skill_states_user",
            ),
            sa.ForeignKeyConstraint(
                ["skill_id"],
                ["global_skills.id"],
                ondelete="CASCADE",
                name="fk_user_skill_states_skill",
            ),
            sa.UniqueConstraint("user_id", "id", name="uq_user_skill_states_user_id"),
            sa.UniqueConstraint("user_id", "skill_id", name="uq_user_skill_states_user_skill"),
            sa.CheckConstraint(
                "state IN ('locked','discovered','unlocked_hidden','activated')",
                name="ck_user_skill_states_state",
            ),
        )

    if not _index_exists("user_skill_states", "idx_user_skill_states_user"):
        op.create_index("idx_user_skill_states_user", "user_skill_states", ["user_id"])
    if not _index_exists("user_skill_states", "idx_user_skill_states_state"):
        op.create_index("idx_user_skill_states_state", "user_skill_states", ["state"])
    if not _index_exists("user_skill_states", "idx_user_skill_states_user_state"):
        op.create_index(
            "idx_user_skill_states_user_state",
            "user_skill_states",
            ["user_id", "state"],
        )

    if not _column_exists("users", "default_blocked_preference"):
        op.add_column(
            "users",
            sa.Column(
                "default_blocked_preference",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    if _column_exists("users", "default_blocked_preference"):
        op.drop_column("users", "default_blocked_preference")

    if _table_exists("user_skill_states"):
        for index_name in (
            "idx_user_skill_states_user_state",
            "idx_user_skill_states_state",
            "idx_user_skill_states_user",
        ):
            if _index_exists("user_skill_states", index_name):
                op.drop_index(index_name, table_name="user_skill_states")
        op.drop_table("user_skill_states")
