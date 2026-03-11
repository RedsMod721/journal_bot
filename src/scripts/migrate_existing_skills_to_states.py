"""
Migrate existing user skills to user_skill_states table.

Run once after the MB71 Alembic migration:
    conda run -n myenv python -m src.scripts.migrate_existing_skills_to_states

Logic:
- Hierarchy level 1 skills (roots) → activated (they're always visible).
- Skills with xp > 0 → activated (user has already engaged with them).
- All others → locked (default hidden state).
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from src.db.session import SessionLocal
from src.db.models.global_kb import GlobalSkill
from src.db.models.skill import Skill
from src.db.models.user import User
from src.db.models.user_skill_state import UserSkillState


HIERARCHY_FILE = Path("data/seeds/kb/global_skill_hierarchy_v1.jsonl")


def load_skill_hierarchy() -> dict[str, dict]:
    """Load the global skill hierarchy from the JSONL seed file."""
    if not HIERARCHY_FILE.exists():
        print(f"ERROR: Hierarchy file not found: {HIERARCHY_FILE}", file=sys.stderr)
        sys.exit(1)

    hierarchy: dict[str, dict] = {}
    with HIERARCHY_FILE.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            skill_data = json.loads(line)
            hierarchy[skill_data["skill_id"]] = {
                "canonical_name": skill_data["canonical_name"],
                "hierarchy_level": skill_data["hierarchy_level"],
                "parent_skill_ids": skill_data.get("parent_skill_ids", []),
            }
    return hierarchy


def migrate_user_skills(db: Session, user_id: str, hierarchy: dict[str, dict]) -> int:
    """
    Create UserSkillState rows for every Skill owned by this user.
    Skips skills that already have a state row.
    Returns the number of rows inserted.
    """
    user_skills = db.query(Skill).filter(Skill.user_id == user_id).all()
    inserted = 0

    # global_skills.id (UUID) -> global_skills.source_skill_id (hierarchy key)
    global_id_to_source_id: dict[str, str] = {
        row.id: row.source_skill_id
        for row in db.query(GlobalSkill.id, GlobalSkill.source_skill_id).all()
        if row.source_skill_id
    }

    for skill in user_skills:
        # global_skill_id is the canonical link to the hierarchy
        global_id = skill.global_skill_id
        if not global_id:
            print(
                f"  SKIP skill id={skill.id!r} ({skill.canonical_name!r}): "
                "no global_skill_id — not yet linked to KB"
            )
            continue

        # Skip if state already exists (idempotent re-run)
        existing = (
            db.query(UserSkillState)
            .filter(
                UserSkillState.user_id == user_id,
                UserSkillState.skill_id == global_id,
            )
            .first()
        )
        if existing:
            continue

        source_skill_id = global_id_to_source_id.get(global_id)
        if not source_skill_id:
            print(
                f"  WARN skill id={skill.id!r} ({skill.canonical_name!r}): "
                f"global_skill_id={global_id!r} has no source_skill_id mapping"
            )
            continue

        skill_info = hierarchy.get(source_skill_id)
        if not skill_info:
            print(
                f"  WARN skill id={skill.id!r} ({skill.canonical_name!r}): "
                f"source_skill_id={source_skill_id!r} not found in hierarchy file"
            )
            continue

        # Determine initial state
        if skill_info["hierarchy_level"] == 1 or (skill.xp and skill.xp > 0):
            state = "activated"
            activated_at = skill.last_activity_at or skill.created_at
        else:
            state = "locked"
            activated_at = None

        db.add(
            UserSkillState(
                user_id=user_id,
                skill_id=global_id,
                state=state,
                user_blocked=False,
                activated_at=activated_at,
                created_at=skill.created_at,
                updated_at=datetime.now(timezone.utc),
            )
        )
        inserted += 1

    db.commit()
    return inserted


def migrate_all_users(db: Session) -> None:
    hierarchy = load_skill_hierarchy()
    print(f"Loaded {len(hierarchy)} skills from hierarchy file.")

    users = db.query(User).all()
    print(f"Migrating {len(users)} user(s)...")

    total = 0
    for user in users:
        count = migrate_user_skills(db, user.id, hierarchy)
        total += count
        print(f"  user {user.id!r}: {count} skill state(s) created")

    print(f"\nDone. {total} total UserSkillState rows inserted.")


if __name__ == "__main__":
    db: Session = SessionLocal()
    try:
        migrate_all_users(db)
    finally:
        db.close()
