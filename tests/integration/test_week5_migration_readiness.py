from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import create_engine, inspect, text


REPO_ROOT = Path(__file__).resolve().parents[2]
TMP_DIR = REPO_ROOT / ".pytest_tmp"
CURRENT_HEAD = "b10000000024"


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.resolve().as_posix()}"


def _run(command: list[str], *, database_url: str) -> subprocess.CompletedProcess[str]:
    env = dict(**os.environ, DATABASE_URL=database_url)
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def _degrade_story_arc_schema(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO users (
                    id,
                    email,
                    password_hash,
                    username,
                    created_at,
                    timezone,
                    language,
                    home_country
                )
                VALUES (
                    '00000000-0000-0000-0000-00000000aa01',
                    'legacy-week7@example.com',
                    'hash',
                    'legacy_week7',
                    '2026-03-01 10:00:00',
                    'UTC',
                    'en',
                    'US'
                )
                """
            )
        )

        for index_name in (
            "idx_arc_triggers_arc",
            "idx_arc_triggers_type",
            "idx_arc_triggers_user",
            "idx_story_arcs_user",
            "idx_story_arcs_status",
            "idx_story_arcs_active_unique",
        ):
            conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))

        conn.execute(text("ALTER TABLE story_arcs RENAME TO story_arcs__canonical"))
        conn.execute(
            text(
                """
                CREATE TABLE story_arcs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    arc_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    title TEXT,
                    theme_ids TEXT,
                    quest_requirement_multiplier REAL NOT NULL DEFAULT 1.0,
                    xp_reward_multiplier REAL NOT NULL DEFAULT 1.0,
                    decay_rate_multiplier REAL NOT NULL DEFAULT 1.0,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
        )
        conn.execute(text("DROP TABLE story_arcs__canonical"))

        conn.execute(text("ALTER TABLE arc_triggers RENAME TO arc_triggers__canonical"))
        conn.execute(
            text(
                """
                CREATE TABLE arc_triggers (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    arc_id TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    trigger_data TEXT,
                    triggered_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (arc_id) REFERENCES story_arcs(id) ON DELETE CASCADE
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO story_arcs (
                    id,
                    user_id,
                    arc_type,
                    status,
                    title,
                    quest_requirement_multiplier,
                    xp_reward_multiplier,
                    decay_rate_multiplier,
                    started_at,
                    ended_at,
                    created_at,
                    updated_at
                ) VALUES (
                    '00000000-0000-0000-0000-00000000aa10',
                    '00000000-0000-0000-0000-00000000aa01',
                    'event',
                    'active',
                    'exam_week',
                    1.2,
                    1.1,
                    0.8,
                    '2026-03-01T10:00:00Z',
                    NULL,
                    '2026-03-01T10:00:00Z',
                    '2026-03-01T10:00:00Z'
                )
                """
            )
        )
        conn.execute(text("DROP TABLE arc_triggers__canonical"))
        conn.execute(
            text(
                """
                INSERT INTO arc_triggers (
                    id,
                    user_id,
                    arc_id,
                    trigger_type,
                    trigger_data,
                    triggered_at
                ) VALUES (
                    '00000000-0000-0000-0000-00000000aa20',
                    '00000000-0000-0000-0000-00000000aa01',
                    '00000000-0000-0000-0000-00000000aa10',
                    'manual_event',
                    '{"source":"legacy"}',
                    '2026-03-01T10:00:00Z'
                )
                """
            )
        )


def test_fresh_db_upgrade_and_demo_seed_flow() -> None:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    db_path = TMP_DIR / "test_week7_fresh_migration.db"
    if db_path.exists():
        db_path.unlink()

    database_url = _sqlite_url(db_path)

    _run([sys.executable, "-m", "alembic", "upgrade", "head"], database_url=database_url)
    seed = _run(
        [sys.executable, "scripts/seeding/seed_harmony_profiles.py"],
        database_url=database_url,
    )

    assert "Maya Motion" in seed.stdout
    assert "Alex Builder" in seed.stdout

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert "alembic_version" in inspector.get_table_names()
    with engine.connect() as conn:
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        seeded_users = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM users
                WHERE id IN (
                    '3f0f158d-d814-43f9-b035-5f6b43edeb41',
                    '37b80e12-c72a-4c2c-979a-68b02caae381',
                    '1cf4f2e7-ccce-42d4-9f57-85ab00c6ab66'
                )
                """
            )
        ).scalar_one()

    assert revision == CURRENT_HEAD
    assert seeded_users == 3


def test_legacy_story_arc_schema_is_repaired_in_place() -> None:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    db_path = TMP_DIR / "test_week7_legacy_repair.db"
    if db_path.exists():
        db_path.unlink()

    database_url = _sqlite_url(db_path)

    _run(
        [sys.executable, "-m", "alembic", "upgrade", "b10000000023"],
        database_url=database_url,
    )
    _degrade_story_arc_schema(database_url)
    _run([sys.executable, "-m", "alembic", "upgrade", "head"], database_url=database_url)
    seed = _run(
        [sys.executable, "scripts/seeding/seed_harmony_profiles.py"],
        database_url=database_url,
    )

    assert "Leo Connector" in seed.stdout

    engine = create_engine(database_url)
    inspector = inspect(engine)
    story_columns = {col["name"] for col in inspector.get_columns("story_arcs")}
    trigger_columns = {col["name"] for col in inspector.get_columns("arc_triggers")}

    assert "event_name" in story_columns
    assert "xp_requirement_multiplier_bp" in story_columns
    assert "completed_at" in story_columns
    assert "confidence_score" in trigger_columns

    with engine.connect() as conn:
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        repaired_arc = conn.execute(
            text(
                """
                SELECT event_name, xp_requirement_multiplier_bp, xp_reward_multiplier_bp,
                       decay_rate_multiplier_bp
                FROM story_arcs
                WHERE id = '00000000-0000-0000-0000-00000000aa10'
                """
            )
        ).one()
        repaired_trigger = conn.execute(
            text(
                """
                SELECT confidence_score
                FROM arc_triggers
                WHERE id = '00000000-0000-0000-0000-00000000aa20'
                """
            )
        ).one()

    assert revision == CURRENT_HEAD
    assert repaired_arc.event_name == "exam_week"
    assert repaired_arc.xp_requirement_multiplier_bp == 12000
    assert repaired_arc.xp_reward_multiplier_bp == 11000
    assert repaired_arc.decay_rate_multiplier_bp == 8000
    assert repaired_trigger.confidence_score is None


def test_schema_drift_check_rejects_head_stamped_db_missing_story_arc_columns() -> None:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    db_path = TMP_DIR / "test_week7_schema_drift.db"
    if db_path.exists():
        db_path.unlink()

    database_url = _sqlite_url(db_path)

    _run(
        [sys.executable, "-m", "alembic", "upgrade", "b10000000023"],
        database_url=database_url,
    )
    _degrade_story_arc_schema(database_url)
    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE alembic_version SET version_num = '{CURRENT_HEAD}'"))

    check = _run(
        [
            sys.executable,
            "-c",
            (
                "from src.db.session import schema_status; "
                "status=schema_status(); "
                "print(status['ready']); "
                "print('|'.join(status['runtime_schema_integrity']['missing']))"
            ),
        ],
        database_url=database_url,
    )

    lines = [line.strip() for line in check.stdout.splitlines() if line.strip()]
    assert lines[0] == "False"
    assert "story_arcs.event_name" in lines[1]
    assert "arc_triggers.confidence_score" in lines[1]
