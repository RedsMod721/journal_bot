"""Migrate adventure skill IDs from old category-prefixed IDs to skill_adventure_* IDs.

Reads the CSV mapping file and updates:
  - global_skills.source_skill_id  (skill_id_before → skill_id_after)
  - global_skills.category         (Physical/Mental/etc. → Adventure)
  - global_skills.subcategory      (subcategory_after from CSV)

NOTE: global_skills.id is a UUID PK and is NOT changed.
      skills.global_skill_id references that UUID, so no user-skill rows need updating.

Safe to run multiple times — rows already on new source_skill_id are skipped.

Usage:
    conda run -n myenv python3 scripts/db/migrate_adventure_skill_ids.py --csv <path-to-csv>
    conda run -n myenv python3 scripts/db/migrate_adventure_skill_ids.py  # defaults to data/seeds/kb/global_skills_v1_adventure_patch_v2.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.db.session import engine, get_database_url

DEFAULT_CSV = Path(__file__).parents[2] / "data/seeds/kb/global_skills_v1_adventure_patch_v2.csv"


def load_mapping(csv_path: Path) -> list[dict]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate adventure skill IDs")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Path to the CSV mapping file")
    parser.add_argument("--dry-run", action="store_true", help="Print SQL without executing")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"ERROR: CSV not found: {args.csv}")
        return 1

    rows = load_mapping(args.csv)
    if not rows:
        print("ERROR: CSV is empty")
        return 1

    print(f"Loaded {len(rows)} mappings from {args.csv}")
    if args.dry_run:
        print("DRY RUN — no changes will be made\n")

    database_url = get_database_url()
    print(f"Database: {database_url}\n")

    global_skills_updated = 0
    global_skills_skipped = 0

    with engine.begin() as conn:
        for row in rows:
            old_source_id = row["skill_id_before"].strip()
            new_source_id = row["skill_id_after"].strip()
            new_subcategory = row["subcategory_after"].strip()

            # Check if old source_skill_id still exists (idempotent — skip if already migrated)
            exists = conn.execute(
                text("SELECT 1 FROM global_skills WHERE source_skill_id = :id"),
                {"id": old_source_id},
            ).scalar_one_or_none()

            if exists is None:
                global_skills_skipped += 1
                continue

            if args.dry_run:
                print(
                    f"  source_skill_id: {old_source_id!r} -> {new_source_id!r}"
                    f"  category: -> 'Adventure'  subcategory: -> {new_subcategory!r}"
                )
                continue

            conn.execute(
                text(
                    "UPDATE global_skills"
                    " SET source_skill_id = :new_id, category = 'Adventure', subcategory = :sub"
                    " WHERE source_skill_id = :old_id"
                ),
                {"new_id": new_source_id, "sub": new_subcategory, "old_id": old_source_id},
            )
            global_skills_updated += conn.execute(text("SELECT changes()")).scalar_one()

    if args.dry_run:
        return 0

    print(f"global_skills rows updated : {global_skills_updated}")
    print(f"global_skills rows skipped : {global_skills_skipped} (already migrated or not seeded)")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
