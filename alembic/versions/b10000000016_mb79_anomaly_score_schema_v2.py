"""MB79 — Anomaly score schema v2: composite PK, 0-10 scale, troll_multiplier.

Revision ID: b10000000016
Revises: b10000000015
Create Date: 2026-03-13 09:00:00.000000

Rebuilds anomaly_scores with:
  - Composite PK (user_id, entry_id) — removes standalone UUID id column
  - score on 0-10 scale  (was 0-1, CHECK updated accordingly)
  - troll_multiplier column  [1.0, 5.0]  maps score → XP/coin multiplier
  - detection_factors  (JSON text)  replaces reasons_json
  - calculated_at  (datetime)  replaces created_at

Old rows are dropped; anomaly scores will be recomputed on next pipeline run.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b10000000016"
down_revision = "b10000000015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite does not support ALTER TABLE for PK changes; drop and recreate.
    op.drop_table("anomaly_scores")

    op.create_table(
        "anomaly_scores",
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("entry_id", sa.String(36), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("troll_multiplier", sa.Float(), nullable=False),
        sa.Column("detection_factors", sa.Text(), nullable=False),  # JSON array
        sa.Column(
            "calculated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        # PK / FK
        sa.PrimaryKeyConstraint("user_id", "entry_id", name="pk_anomaly_scores"),
        sa.ForeignKeyConstraint(
            ["user_id", "entry_id"],
            ["journal_entries.user_id", "journal_entries.id"],
            ondelete="CASCADE",
            name="fk_anomaly_scores_entry",
        ),
        # Domain checks
        sa.CheckConstraint(
            "score >= 0.0 AND score <= 10.0",
            name="ck_anomaly_score_range",
        ),
        sa.CheckConstraint(
            "troll_multiplier >= 1.0 AND troll_multiplier <= 5.0",
            name="ck_troll_multiplier_range",
        ),
    )

    op.create_index("idx_anomaly_scores_user", "anomaly_scores", ["user_id"])
    op.create_index(
        "idx_anomaly_scores_score",
        "anomaly_scores",
        ["score"],
        # postgresql_ops not applied on SQLite — harmless to include
        postgresql_ops={"score": "DESC"},
    )


def downgrade() -> None:
    op.drop_index("idx_anomaly_scores_score", table_name="anomaly_scores")
    op.drop_index("idx_anomaly_scores_user", table_name="anomaly_scores")
    op.drop_table("anomaly_scores")

    # Restore original schema (v1)
    op.create_table(
        "anomaly_scores",
        sa.Column(
            "id",
            sa.String(36),
            nullable=False,
            primary_key=True,
        ),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("entry_id", sa.String(36), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("reasons_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "entry_id"],
            ["journal_entries.user_id", "journal_entries.id"],
            ondelete="CASCADE",
            name="fk_anomaly_scores_user_entry",
        ),
        sa.CheckConstraint(
            "score >= 0 AND score <= 1.0",
            name="ck_anomaly_scores_score",
        ),
    )
    op.create_index(
        "idx_anomaly_scores_user", "anomaly_scores", ["user_id"]
    )
    op.create_index(
        "idx_anomaly_scores_user_entry", "anomaly_scores", ["user_id", "entry_id"]
    )
