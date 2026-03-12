"""Stamp a legacy SQLite DB to the last pre-canonical revision.

Use this only for older local/dev databases that predate Alembic tracking but
already contain the legacy core tables. After running this repair, the caller
should run ``alembic upgrade head`` against the same ``DATABASE_URL``.
"""

from __future__ import annotations

from pathlib import Path
import sys

import sqlalchemy as sa
from sqlalchemy import inspect

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.db.session import get_database_url

LEGACY_BASELINE_REVISION = "4ce8e78ab15d"
REQUIRED_LEGACY_TABLES = {"users", "journal_entries", "themes", "skills"}


def main() -> None:
    database_url = get_database_url()
    engine = sa.create_engine(database_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if "alembic_version" in tables:
        with engine.connect() as conn:
            rows = conn.execute(sa.text("SELECT version_num FROM alembic_version")).fetchall()
        revisions = [row[0] for row in rows if row and row[0]]
        if revisions:
            print(
                f"alembic_version already present for {database_url}: {', '.join(revisions)}"
            )
            return

    missing_tables = sorted(REQUIRED_LEGACY_TABLES - tables)
    if missing_tables:
        raise SystemExit(
            "Legacy repair refused: database does not look like the pre-canonical "
            f"local schema. Missing tables: {', '.join(missing_tables)}"
        )

    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                CREATE TABLE IF NOT EXISTS alembic_version (
                    version_num VARCHAR(32) NOT NULL PRIMARY KEY
                )
                """
            )
        )
        conn.execute(sa.text("DELETE FROM alembic_version"))
        conn.execute(
            sa.text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": LEGACY_BASELINE_REVISION},
        )

    print(
        "Stamped legacy DB to pre-canonical baseline "
        f"{LEGACY_BASELINE_REVISION} for {database_url}"
    )
    print("Next step: python -m alembic upgrade head")


if __name__ == "__main__":
    main()
