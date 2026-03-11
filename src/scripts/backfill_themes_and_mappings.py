"""
Backfill canonical user themes and skill-theme mappings.

Run:
    python -m src.scripts.backfill_themes_and_mappings

Behavior (idempotent):
- Ensures every user has all 12 canonical theme rows.
- Ensures skill_theme_mappings exist for every user skill linked to a global
  skill (derived from GlobalSkill.related_themes_json).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.core.themes import CANONICAL_THEME_NAMES, ensure_skill_theme_mappings, ensure_user_themes
from src.db.models.skill import Skill, Theme
from src.db.models.user import User
from src.db.session import SessionLocal


@dataclass(slots=True)
class UserBackfillResult:
    user_id: str
    themes_created: int
    mappings_created: int
    skill_count: int


def _iter_user_ids(db: Session) -> Iterable[str]:
    for (user_id,) in db.query(User.id).order_by(User.id.asc()).all():
        yield str(user_id)


def backfill_user(db: Session, user_id: str) -> UserBackfillResult:
    existing_theme_count = (
        db.query(Theme)
        .filter(Theme.user_id == user_id, Theme.name.in_(CANONICAL_THEME_NAMES))
        .count()
    )

    ensure_user_themes(db, user_id)

    skill_ids = [
        str(skill_id)
        for (skill_id,) in (
            db.query(Skill.id)
            .filter(Skill.user_id == user_id, Skill.global_skill_id.isnot(None))
            .all()
        )
    ]
    mappings_created = ensure_skill_theme_mappings(db, user_id, skill_ids)

    themes_after = (
        db.query(Theme)
        .filter(Theme.user_id == user_id, Theme.name.in_(CANONICAL_THEME_NAMES))
        .count()
    )
    themes_created = max(0, themes_after - existing_theme_count)

    return UserBackfillResult(
        user_id=user_id,
        themes_created=themes_created,
        mappings_created=mappings_created,
        skill_count=len(skill_ids),
    )


def backfill_all_users(db: Session) -> list[UserBackfillResult]:
    results: list[UserBackfillResult] = []

    for user_id in _iter_user_ids(db):
        result = backfill_user(db, user_id)
        db.commit()
        results.append(result)

    return results


def main() -> int:
    db = SessionLocal()
    try:
        results = backfill_all_users(db)
    finally:
        db.close()

    total_users = len(results)
    total_themes = sum(item.themes_created for item in results)
    total_mappings = sum(item.mappings_created for item in results)

    print(f"Processed users: {total_users}")
    print(f"Canonical themes created: {total_themes}")
    print(f"Skill-theme mappings created: {total_mappings}")
    for item in results:
        print(
            f"- user={item.user_id} skills={item.skill_count} "
            f"themes_created={item.themes_created} mappings_created={item.mappings_created}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
