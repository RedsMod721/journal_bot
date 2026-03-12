from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

from sqlalchemy import create_engine, inspect, text


REPO_ROOT = Path(__file__).resolve().parents[2]
TMP_DIR = REPO_ROOT / ".pytest_tmp"
LEGACY_SOURCE_DB = REPO_ROOT / "data" / "db" / "rpg_life_tracker.db"


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


def test_fresh_db_upgrade_and_demo_seed_flow() -> None:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    db_path = TMP_DIR / "test_week5_fresh_migration.db"
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

    assert revision == "b10000000015"
    assert seeded_users == 3


def test_legacy_db_repair_upgrade_and_demo_seed_flow() -> None:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    db_path = TMP_DIR / "test_week5_legacy_repair.db"
    if db_path.exists():
        db_path.unlink()
    shutil.copyfile(LEGACY_SOURCE_DB, db_path)

    database_url = _sqlite_url(db_path)

    repair = _run(
        [sys.executable, "scripts/db/repair_legacy_alembic_state.py"],
        database_url=database_url,
    )
    _run([sys.executable, "-m", "alembic", "upgrade", "head"], database_url=database_url)
    seed = _run(
        [sys.executable, "scripts/seeding/seed_harmony_profiles.py"],
        database_url=database_url,
    )

    assert "4ce8e78ab15d" in repair.stdout
    assert "Leo Connector" in seed.stdout

    engine = create_engine(database_url)
    with engine.connect() as conn:
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert revision == "b10000000015"
