"""MB84 — Add story arcs system (Section 8).

Revision ID: b10000000021
Revises: b10000000020
Create Date: 2026-03-20 09:00:00.000000
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b10000000021"
down_revision: Union[str, Sequence[str], None] = "b10000000020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STORY_ARCS_COLUMNS = {
    "id",
    "user_id",
    "arc_type",
    "status",
    "event_name",
    "theme_ids",
    "xp_requirement_multiplier_bp",
    "xp_reward_multiplier_bp",
    "decay_rate_multiplier_bp",
    "started_at",
    "duration_days",
    "created_at",
    "updated_at",
    "completed_at",
}
_ARC_TRIGGERS_COLUMNS = {
    "id",
    "user_id",
    "arc_id",
    "trigger_type",
    "confidence_score",
    "trigger_data",
    "triggered_at",
}


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _columns(bind: sa.engine.Connection, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _ensure_story_arcs_indexes(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    existing = {idx["name"] for idx in inspector.get_indexes("story_arcs")}
    if "idx_story_arcs_user" not in existing:
        op.create_index("idx_story_arcs_user", "story_arcs", ["user_id"])
    if "idx_story_arcs_status" not in existing:
        op.create_index("idx_story_arcs_status", "story_arcs", ["status"])

    if bind.dialect.name == "sqlite":
        bind.execute(
            sa.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_story_arcs_active_unique "
                "ON story_arcs(user_id) WHERE status = 'active'"
            )
        )
    else:
        existing = {idx["name"] for idx in inspector.get_indexes("story_arcs")}
        if "idx_story_arcs_active_unique" not in existing:
            op.create_index(
                "idx_story_arcs_active_unique",
                "story_arcs",
                ["user_id"],
                unique=True,
                postgresql_where=sa.text("status = 'active'"),
            )


def _ensure_arc_triggers_indexes(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    existing = {idx["name"] for idx in inspector.get_indexes("arc_triggers")}
    if "idx_arc_triggers_arc" not in existing:
        op.create_index("idx_arc_triggers_arc", "arc_triggers", ["arc_id"])
    if "idx_arc_triggers_type" not in existing:
        op.create_index("idx_arc_triggers_type", "arc_triggers", ["trigger_type"])
    if "idx_arc_triggers_user" not in existing:
        op.create_index("idx_arc_triggers_user", "arc_triggers", ["user_id"])


def _create_story_arcs_table() -> None:
    op.create_table(
        "story_arcs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("arc_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("event_name", sa.String(200), nullable=True),
        sa.Column("theme_ids", sa.Text(), nullable=True),
        sa.Column(
            "xp_requirement_multiplier_bp",
            sa.Integer(),
            nullable=False,
            server_default="10000",
        ),
        sa.Column(
            "xp_reward_multiplier_bp",
            sa.Integer(),
            nullable=False,
            server_default="10000",
        ),
        sa.Column(
            "decay_rate_multiplier_bp",
            sa.Integer(),
            nullable=False,
            server_default="10000",
        ),
        sa.Column("started_at", sa.String(30), nullable=False),
        sa.Column("duration_days", sa.Float(), nullable=True),
        sa.Column("created_at", sa.String(30), nullable=False),
        sa.Column("updated_at", sa.String(30), nullable=False),
        sa.Column("completed_at", sa.String(30), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "arc_type IN ('tutorial', 'regression', 'redemption', 'event')",
            name="ck_story_arcs_arc_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'completed', 'abandoned')",
            name="ck_story_arcs_status",
        ),
        sa.CheckConstraint(
            "(arc_type = 'event' AND event_name IS NOT NULL)"
            " OR (arc_type != 'event' AND event_name IS NULL)",
            name="ck_story_arcs_event_name",
        ),
        sa.CheckConstraint(
            "xp_requirement_multiplier_bp > 0",
            name="ck_story_arcs_xp_req_bp",
        ),
        sa.CheckConstraint(
            "xp_reward_multiplier_bp > 0",
            name="ck_story_arcs_xp_reward_bp",
        ),
        sa.CheckConstraint(
            "decay_rate_multiplier_bp >= 0",
            name="ck_story_arcs_decay_bp",
        ),
    )


def _create_arc_triggers_table() -> None:
    op.create_table(
        "arc_triggers",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("arc_id", sa.String(36), nullable=False),
        sa.Column("trigger_type", sa.String(50), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("trigger_data", sa.Text(), nullable=True),
        sa.Column("triggered_at", sa.String(30), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["arc_id"], ["story_arcs.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0.0 AND confidence_score <= 1.0)",
            name="ck_arc_triggers_confidence",
        ),
    )


def _now_fixed_ms() -> str:
    return _normalize_timestamp(datetime.now(UTC))


def _normalize_timestamp(value: object, fallback: str | None = None) -> str | None:
    if value is None:
        return fallback

    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return fallback
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        if " " in normalized and "T" not in normalized:
            normalized = normalized.replace(" ", "T")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return fallback
    elif isinstance(value, datetime):
        parsed = value
    else:
        return fallback

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)

    return parsed.strftime("%Y-%m-%dT%H:%M:%S.%f")[:23] + "Z"


def _coerce_bp(value: object, default: int = 10000) -> int:
    if value is None:
        return default
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return max(0, int(round(numeric * 10_000)))


def _load_rows(bind: sa.engine.Connection, table_name: str) -> list[dict[str, object]]:
    return [dict(row) for row in bind.execute(sa.text(f"SELECT * FROM {table_name}")).mappings()]


def _repair_story_arc_tables_sqlite(bind: sa.engine.Connection) -> None:
    legacy_story_exists = _table_exists(bind, "story_arcs")
    legacy_trigger_exists = _table_exists(bind, "arc_triggers")
    repair_now = _now_fixed_ms()

    story_rows = _load_rows(bind, "story_arcs") if legacy_story_exists else []
    trigger_rows = _load_rows(bind, "arc_triggers") if legacy_trigger_exists else []

    bind.execute(sa.text("PRAGMA foreign_keys=OFF"))

    if legacy_trigger_exists:
        bind.execute(sa.text("ALTER TABLE arc_triggers RENAME TO arc_triggers__legacy_mb84"))
    if legacy_story_exists:
        bind.execute(sa.text("ALTER TABLE story_arcs RENAME TO story_arcs__legacy_mb84"))

    _create_story_arcs_table()

    transformed_story_rows: list[dict[str, object]] = []
    repair_trigger_rows: list[dict[str, object]] = []

    for row in story_rows:
        arc_id = str(row.get("id") or uuid.uuid4())
        user_id = str(row.get("user_id") or "")
        arc_type = str(row.get("arc_type") or "event")
        status = str(row.get("status") or "active")
        legacy_title = str(row.get("title") or "").strip()
        event_name = row.get("event_name")
        if isinstance(event_name, str):
            event_name = event_name.strip() or None
        if arc_type == "event" and event_name is None:
            event_name = legacy_title or "legacy_event"

        started_at = _normalize_timestamp(row.get("started_at"), repair_now) or repair_now
        created_at = _normalize_timestamp(row.get("created_at"), started_at) or started_at
        updated_at = (
            _normalize_timestamp(
                row.get("updated_at")
                or row.get("completed_at")
                or row.get("ended_at")
                or row.get("created_at")
                or row.get("started_at"),
                created_at,
            )
            or created_at
        )
        completed_at = _normalize_timestamp(
            row.get("completed_at") or row.get("ended_at"),
            None,
        )

        transformed_story_rows.append(
            {
                "id": arc_id,
                "user_id": user_id,
                "arc_type": arc_type,
                "status": status,
                "event_name": event_name if arc_type == "event" else None,
                "theme_ids": row.get("theme_ids"),
                "xp_requirement_multiplier_bp": row.get("xp_requirement_multiplier_bp")
                if row.get("xp_requirement_multiplier_bp") is not None
                else _coerce_bp(row.get("quest_requirement_multiplier"), 10000),
                "xp_reward_multiplier_bp": row.get("xp_reward_multiplier_bp")
                if row.get("xp_reward_multiplier_bp") is not None
                else _coerce_bp(row.get("xp_reward_multiplier"), 10000),
                "decay_rate_multiplier_bp": row.get("decay_rate_multiplier_bp")
                if row.get("decay_rate_multiplier_bp") is not None
                else _coerce_bp(row.get("decay_rate_multiplier"), 10000),
                "started_at": started_at,
                "duration_days": row.get("duration_days"),
                "created_at": created_at,
                "updated_at": updated_at,
                "completed_at": completed_at,
            }
        )

        if arc_type != "event" and legacy_title:
            repair_trigger_rows.append(
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "arc_id": arc_id,
                    "trigger_type": "legacy_schema_repair",
                    "confidence_score": None,
                    "trigger_data": json.dumps(
                        {
                            "repair": "mb84_story_arcs_legacy",
                            "legacy_title": legacy_title,
                        },
                        separators=(",", ":"),
                    ),
                    "triggered_at": updated_at,
                }
            )

    active_rows_by_user: dict[str, list[dict[str, object]]] = {}
    for row in transformed_story_rows:
        if row["status"] == "active":
            active_rows_by_user.setdefault(str(row["user_id"]), []).append(row)

    for user_id, rows in active_rows_by_user.items():
        if len(rows) <= 1:
            continue
        rows.sort(
            key=lambda row: (
                str(row["updated_at"]),
                str(row["started_at"]),
                str(row["id"]),
            ),
            reverse=True,
        )
        for duplicate in rows[1:]:
            duplicate["status"] = "abandoned"
            duplicate["completed_at"] = duplicate["updated_at"]
            repair_trigger_rows.append(
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "arc_id": str(duplicate["id"]),
                    "trigger_type": "legacy_schema_repair",
                    "confidence_score": None,
                    "trigger_data": json.dumps(
                        {
                            "repair": "mb84_multiple_active_arcs",
                            "reason": "duplicate_active_arc",
                        },
                        separators=(",", ":"),
                    ),
                    "triggered_at": str(duplicate["updated_at"]),
                }
            )

    if transformed_story_rows:
        bind.execute(
            sa.text(
                """
                INSERT INTO story_arcs (
                    id, user_id, arc_type, status, event_name, theme_ids,
                    xp_requirement_multiplier_bp, xp_reward_multiplier_bp,
                    decay_rate_multiplier_bp, started_at, duration_days,
                    created_at, updated_at, completed_at
                ) VALUES (
                    :id, :user_id, :arc_type, :status, :event_name, :theme_ids,
                    :xp_requirement_multiplier_bp, :xp_reward_multiplier_bp,
                    :decay_rate_multiplier_bp, :started_at, :duration_days,
                    :created_at, :updated_at, :completed_at
                )
                """
            ),
            transformed_story_rows,
        )

    _create_arc_triggers_table()
    valid_arc_ids = {str(row["id"]) for row in transformed_story_rows}
    transformed_trigger_rows: list[dict[str, object]] = []
    for row in trigger_rows:
        arc_id = str(row.get("arc_id") or "")
        user_id = str(row.get("user_id") or "")
        if not arc_id or arc_id not in valid_arc_ids or not user_id:
            continue
        confidence_score = row.get("confidence_score")
        if confidence_score is not None:
            try:
                confidence_float = float(confidence_score)
            except (TypeError, ValueError):
                confidence_float = None
            else:
                if confidence_float < 0.0 or confidence_float > 1.0:
                    confidence_float = None
        else:
            confidence_float = None
        transformed_trigger_rows.append(
            {
                "id": str(row.get("id") or uuid.uuid4()),
                "user_id": user_id,
                "arc_id": arc_id,
                "trigger_type": str(row.get("trigger_type") or "legacy_schema_repair"),
                "confidence_score": confidence_float,
                "trigger_data": row.get("trigger_data"),
                "triggered_at": _normalize_timestamp(row.get("triggered_at"), repair_now)
                or repair_now,
            }
        )

    transformed_trigger_rows.extend(repair_trigger_rows)
    if transformed_trigger_rows:
        bind.execute(
            sa.text(
                """
                INSERT INTO arc_triggers (
                    id, user_id, arc_id, trigger_type, confidence_score,
                    trigger_data, triggered_at
                ) VALUES (
                    :id, :user_id, :arc_id, :trigger_type, :confidence_score,
                    :trigger_data, :triggered_at
                )
                """
            ),
            transformed_trigger_rows,
        )

    if legacy_trigger_exists:
        bind.execute(sa.text("DROP TABLE arc_triggers__legacy_mb84"))
    if legacy_story_exists:
        bind.execute(sa.text("DROP TABLE story_arcs__legacy_mb84"))

    _ensure_story_arcs_indexes(bind)
    _ensure_arc_triggers_indexes(bind)
    bind.execute(sa.text("PRAGMA foreign_keys=ON"))


def upgrade() -> None:
    bind = op.get_bind()

    story_arcs_exists = _table_exists(bind, "story_arcs")
    arc_triggers_exists = _table_exists(bind, "arc_triggers")
    story_arcs_canonical = (
        story_arcs_exists and _STORY_ARCS_COLUMNS.issubset(_columns(bind, "story_arcs"))
    )
    arc_triggers_canonical = (
        arc_triggers_exists and _ARC_TRIGGERS_COLUMNS.issubset(_columns(bind, "arc_triggers"))
    )

    if bind.dialect.name == "sqlite" and (
        (story_arcs_exists and not story_arcs_canonical)
        or (arc_triggers_exists and not arc_triggers_canonical)
    ):
        _repair_story_arc_tables_sqlite(bind)
        return

    if not story_arcs_exists:
        _create_story_arcs_table()
    if not arc_triggers_exists:
        _create_arc_triggers_table()

    _ensure_story_arcs_indexes(bind)
    _ensure_arc_triggers_indexes(bind)


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index("idx_arc_triggers_user", table_name="arc_triggers")
    op.drop_index("idx_arc_triggers_type", table_name="arc_triggers")
    op.drop_index("idx_arc_triggers_arc", table_name="arc_triggers")
    op.drop_table("arc_triggers")

    op.drop_index("idx_story_arcs_status", table_name="story_arcs")
    op.drop_index("idx_story_arcs_user", table_name="story_arcs")

    if bind.dialect.name == "sqlite":
        bind.execute(sa.text("DROP INDEX IF EXISTS idx_story_arcs_active_unique"))
    else:
        op.drop_index("idx_story_arcs_active_unique", table_name="story_arcs")

    op.drop_table("story_arcs")
