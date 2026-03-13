"""MB80 — Personality system v2: full schema rebuild.

Revision ID: b10000000017
Revises: b10000000016
Create Date: 2026-03-13 14:00:00.000000

Rebuilds personality_states, personality_messages, and personality_memory
to match the canonical architecture (Section 3.0):

personality_states:
  - user_id as PK (was separate UUID id)
  - likability_* columns (0-100) per personality
  - settings: memory_short_term_days, switch_cooldown_seconds, max_* caps
  - selection state: last_selection_factors (JSON text), last_switched_at

personality_messages:
  - message_text (was content)
  - context_data (JSON text, replaces selector_ fields)
  - created_at (was sent_at)
  - entry_id NOT NULL
  - uq_personality_messages_exactly_once (user_id, entry_id, message_type, personality)

personality_memory:
  - key (was memory_key), value (was memory_value)
  - context (JSON text, replaces confidence)
  - tier check updated: thread | short_term | long_term
  - uq_personality_memory_idempotent (user_id, tier, key)

users table: crisis-localization columns were already added in MB00 (via
create_all); no users table changes needed here.

Old rows in all three tables are dropped; personality state will be
re-initialised on first use per user.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b10000000017"
down_revision = "b10000000016"
branch_labels = None
depends_on = None

_PERSONALITY_LIST = "('observer','therapist','coach','sassy','wargod','raphael')"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Tear down old tables (SQLite drops associated triggers implicitly)
    # ------------------------------------------------------------------
    for idx in [
        "idx_personality_memory_expires",
        "idx_personality_memory_user_tier",
        "idx_personality_memory_user",
    ]:
        op.execute(f"DROP INDEX IF EXISTS {idx}")
    op.drop_table("personality_memory")

    for idx in [
        "idx_personality_msgs_selector_seed",
        "idx_personality_msgs_personality",
        "idx_personality_msgs_user_entry_type",
        "idx_personality_msgs_user_entry",
        "idx_personality_msgs_user_sent",
        "idx_personality_msgs_user",
    ]:
        op.execute(f"DROP INDEX IF EXISTS {idx}")
    op.drop_table("personality_messages")

    op.execute("DROP INDEX IF EXISTS idx_personality_states_user")
    op.drop_table("personality_states")

    # ------------------------------------------------------------------
    # 2. personality_states  (user_id PK, likability, settings)
    # ------------------------------------------------------------------
    op.create_table(
        "personality_states",
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column(
            "active_personality",
            sa.String(50),
            nullable=False,
            server_default="observer",
        ),
        # --- Likability (0-100) ---
        sa.Column("likability_observer", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("likability_therapist", sa.Integer(), nullable=False, server_default="70"),
        sa.Column("likability_coach", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("likability_sassy", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("likability_wargod", sa.Integer(), nullable=False, server_default="40"),
        sa.Column("likability_raphael", sa.Integer(), nullable=False, server_default="60"),
        # --- Settings ---
        sa.Column("memory_short_term_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("multi_personality_annotations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("switch_cooldown_seconds", sa.Integer(), nullable=False, server_default="600"),
        sa.Column("max_messages_per_entry", sa.Integer(), nullable=True),
        sa.Column("max_message_chars", sa.Integer(), nullable=True),
        sa.Column("max_annotation_chars", sa.Integer(), nullable=True),
        # --- Selection state ---
        sa.Column(
            "last_selection_factors",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("last_switched_at", sa.DateTime(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        # Constraints
        sa.PrimaryKeyConstraint("user_id", name="pk_personality_states"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_personality_states_user",
        ),
        sa.CheckConstraint(
            f"active_personality IN {_PERSONALITY_LIST}",
            name="ck_personality_states_active_personality",
        ),
        sa.CheckConstraint(
            "multi_personality_annotations IN (0,1)",
            name="ck_personality_states_annotations",
        ),
        sa.CheckConstraint(
            "likability_observer BETWEEN 0 AND 100",
            name="ck_ps_likability_observer",
        ),
        sa.CheckConstraint(
            "likability_therapist BETWEEN 0 AND 100",
            name="ck_ps_likability_therapist",
        ),
        sa.CheckConstraint(
            "likability_coach BETWEEN 0 AND 100",
            name="ck_ps_likability_coach",
        ),
        sa.CheckConstraint(
            "likability_sassy BETWEEN 0 AND 100",
            name="ck_ps_likability_sassy",
        ),
        sa.CheckConstraint(
            "likability_wargod BETWEEN 0 AND 100",
            name="ck_ps_likability_wargod",
        ),
        sa.CheckConstraint(
            "likability_raphael BETWEEN 0 AND 100",
            name="ck_ps_likability_raphael",
        ),
        sa.CheckConstraint(
            "switch_cooldown_seconds >= 0",
            name="ck_ps_switch_cooldown",
        ),
        sa.CheckConstraint(
            "memory_short_term_days >= 1",
            name="ck_ps_memory_days",
        ),
    )

    # ------------------------------------------------------------------
    # 3. personality_messages  (exactly-once constraint)
    # ------------------------------------------------------------------
    op.create_table(
        "personality_messages",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("entry_id", sa.String(36), nullable=False),
        sa.Column("personality", sa.String(50), nullable=False),
        sa.Column("message_type", sa.String(50), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column(
            "context_data",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("quest_id", sa.String(36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        # Constraints
        sa.PrimaryKeyConstraint("id", name="pk_personality_messages"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_personality_messages_user",
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["journal_entries.id"],
            ondelete="CASCADE",
            name="fk_personality_messages_entry",
        ),
        sa.ForeignKeyConstraint(
            ["quest_id"],
            ["quests.id"],
            ondelete="SET NULL",
            name="fk_personality_messages_quest",
        ),
        sa.UniqueConstraint(
            "user_id",
            "entry_id",
            "message_type",
            "personality",
            name="uq_personality_messages_exactly_once",
        ),
        sa.CheckConstraint(
            f"personality IN {_PERSONALITY_LIST}",
            name="ck_personality_messages_personality",
        ),
    )

    op.create_index(
        "idx_personality_messages_user", "personality_messages", ["user_id"]
    )
    op.create_index(
        "idx_personality_messages_entry", "personality_messages", ["entry_id"]
    )
    op.create_index(
        "idx_personality_messages_user_entry",
        "personality_messages",
        ["user_id", "entry_id"],
    )
    op.create_index(
        "idx_personality_messages_user_entry_type",
        "personality_messages",
        ["user_id", "entry_id", "message_type"],
    )

    # ------------------------------------------------------------------
    # 4. personality_memory  (idempotent key/value/context)
    # ------------------------------------------------------------------
    op.create_table(
        "personality_memory",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "context",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        # Constraints
        sa.PrimaryKeyConstraint("id", name="pk_personality_memory"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_personality_memory_user",
        ),
        sa.UniqueConstraint(
            "user_id",
            "tier",
            "key",
            name="uq_personality_memory_idempotent",
        ),
        sa.CheckConstraint(
            "tier IN ('thread','short_term','long_term')",
            name="ck_personality_memory_tier",
        ),
    )

    op.create_index(
        "idx_personality_memory_user_tier",
        "personality_memory",
        ["user_id", "tier"],
    )
    op.create_index(
        "idx_personality_memory_expires", "personality_memory", ["expires_at"]
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # Drop v2 tables
    # ------------------------------------------------------------------
    op.execute("DROP INDEX IF EXISTS idx_personality_memory_expires")
    op.execute("DROP INDEX IF EXISTS idx_personality_memory_user_tier")
    op.drop_table("personality_memory")

    op.execute("DROP INDEX IF EXISTS idx_personality_messages_user_entry_type")
    op.execute("DROP INDEX IF EXISTS idx_personality_messages_user_entry")
    op.execute("DROP INDEX IF EXISTS idx_personality_messages_entry")
    op.execute("DROP INDEX IF EXISTS idx_personality_messages_user")
    op.drop_table("personality_messages")

    op.drop_table("personality_states")

    # ------------------------------------------------------------------
    # Restore v1 personality_states
    # ------------------------------------------------------------------
    op.create_table(
        "personality_states",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column(
            "active_personality",
            sa.String(50),
            nullable=False,
            server_default="observer",
        ),
        sa.Column("selection_factors_json", sa.Text(), nullable=True),
        sa.Column("selector_version", sa.String(50), nullable=True),
        sa.Column(
            "multi_personality_annotations",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_personality_states_user"),
        sa.CheckConstraint(
            f"active_personality IN {_PERSONALITY_LIST}",
            name="ck_personality_states_active_personality",
        ),
        sa.CheckConstraint(
            "multi_personality_annotations IN (0,1)",
            name="ck_personality_states_annotations",
        ),
    )
    op.create_index("idx_personality_states_user", "personality_states", ["user_id"])

    # ------------------------------------------------------------------
    # Restore v1 personality_messages
    # ------------------------------------------------------------------
    op.create_table(
        "personality_messages",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("entry_id", sa.String(36), nullable=True),
        sa.Column("quest_id", sa.String(36), nullable=True),
        sa.Column("personality", sa.String(50), nullable=False),
        sa.Column("message_type", sa.String(50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("selector_seed_hash", sa.String(255), nullable=True),
        sa.Column("selector_version", sa.String(50), nullable=True),
        sa.Column("logical_slot_key", sa.String(100), nullable=True),
        sa.Column(
            "sent_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["entry_id"], ["journal_entries.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["quest_id"], ["quests.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "user_id",
            "entry_id",
            "message_type",
            "logical_slot_key",
            "selector_version",
            name="uq_personality_messages_selector_slot",
        ),
        sa.CheckConstraint(
            f"personality IN {_PERSONALITY_LIST}",
            name="ck_personality_messages_personality",
        ),
    )
    op.create_index("idx_personality_msgs_user", "personality_messages", ["user_id"])
    op.create_index(
        "idx_personality_msgs_user_sent", "personality_messages", ["user_id", "sent_at"]
    )
    op.create_index(
        "idx_personality_msgs_user_entry", "personality_messages", ["user_id", "entry_id"]
    )
    op.create_index(
        "idx_personality_msgs_user_entry_type",
        "personality_messages",
        ["user_id", "entry_id", "message_type"],
    )
    op.create_index(
        "idx_personality_msgs_personality", "personality_messages", ["personality"]
    )
    op.create_index(
        "idx_personality_msgs_selector_seed",
        "personality_messages",
        ["user_id", "selector_seed_hash"],
    )

    # ------------------------------------------------------------------
    # Restore v1 personality_memory
    # ------------------------------------------------------------------
    op.create_table(
        "personality_memory",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("memory_key", sa.String(100), nullable=False),
        sa.Column("memory_value", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id", "tier", "memory_key", name="uq_personality_memory_key"
        ),
        sa.CheckConstraint(
            "tier IN ('short_term','mid_term','long_term')",
            name="ck_personality_memory_tier",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 100",
            name="ck_personality_memory_confidence",
        ),
    )
    op.create_index("idx_personality_memory_user", "personality_memory", ["user_id"])
    op.create_index(
        "idx_personality_memory_user_tier", "personality_memory", ["user_id", "tier"]
    )
    op.create_index(
        "idx_personality_memory_expires", "personality_memory", ["expires_at"]
    )
