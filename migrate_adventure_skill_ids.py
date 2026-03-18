"""Launcher for scripts/db/migrate_adventure_skill_ids.py.

Allows running from repo root:
    conda run -n myenv python3 migrate_adventure_skill_ids.py --csv ...
"""

from scripts.db.migrate_adventure_skill_ids import main


if __name__ == "__main__":
    raise SystemExit(main())
