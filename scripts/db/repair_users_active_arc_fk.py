"""Repair missing users.active_arc_id -> story_arcs FK on SQLite dev DB.

Safe to run multiple times. Exits 0 when already correct or repaired.
"""

from __future__ import annotations

import re

from sqlalchemy import text

from src.db.session import engine, get_database_url


def main() -> int:
    database_url = get_database_url()
    if not database_url.startswith("sqlite"):
        print(f"Skipping: non-SQLite database ({database_url})")
        return 0

    with engine.begin() as conn:
        ddl = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
        ).scalar_one_or_none()

        if not isinstance(ddl, str) or not ddl.strip():
            raise SystemExit("users table not found")

        if "FOREIGN KEY(active_arc_id)" in ddl and "REFERENCES story_arcs" in ddl:
            print("already fixed")
            return 0

        index_sql = [
            row[0]
            for row in conn.execute(
                text(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type='index' AND tbl_name='users' AND sql IS NOT NULL"
                )
            ).fetchall()
            if row and row[0]
        ]
        trigger_sql = [
            row[0]
            for row in conn.execute(
                text(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type='trigger' AND tbl_name='users' AND sql IS NOT NULL"
                )
            ).fetchall()
            if row and row[0]
        ]

        if "FOREIGN KEY(active_arc_id)" in ddl:
            ddl = re.sub(
                r"FOREIGN KEY\\(active_arc_id\\)\\s+REFERENCES\\s+[^\\(\\s]+\\s*\\(id\\)\\s*ON DELETE SET NULL",
                "FOREIGN KEY(active_arc_id) REFERENCES story_arcs (id) ON DELETE SET NULL",
                ddl,
                flags=re.IGNORECASE,
            )
        else:
            ddl = re.sub(
                r"\)\s*$",
                ", CONSTRAINT fk_users_active_arc_id FOREIGN KEY(active_arc_id) REFERENCES story_arcs (id) ON DELETE SET NULL)",
                ddl,
                flags=re.DOTALL,
            )

        ddl = re.sub(
            r"^\s*CREATE\s+TABLE\s+users",
            "CREATE TABLE users__fkfix",
            ddl,
            flags=re.IGNORECASE,
        )

        columns = [row[1] for row in conn.execute(text("PRAGMA table_info(users)")).fetchall()]
        if not columns:
            raise SystemExit("No columns found for users table")
        col_list = ", ".join(f'\"{name}\"' for name in columns)

        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.execute(text("DROP TABLE IF EXISTS users__fkfix"))
        conn.execute(text(ddl))
        conn.execute(
            text(
                f'INSERT INTO "users__fkfix" ({col_list}) '
                f'SELECT {col_list} FROM "users"'
            )
        )
        conn.execute(text('DROP TABLE "users"'))
        conn.execute(text('ALTER TABLE "users__fkfix" RENAME TO "users"'))

        for stmt in index_sql:
            conn.execute(text(stmt))
        for stmt in trigger_sql:
            conn.execute(text(stmt))

        conn.execute(text("PRAGMA foreign_keys=ON"))

    print("fixed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
