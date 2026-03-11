"""Demo profile seed helpers for UI-facing fallback responses.

These helpers expose the curated profile data from
``data/seeds/demo/harmony_profiles_v1.json`` so the existing API endpoints can
return meaningful profile cards for the three demo users even when the current
runtime database has not been hydrated with Week 5 profile activity yet.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from src.db.models.journal_entry import JournalEntry

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED_PATH = _REPO_ROOT / "data" / "seeds" / "demo" / "harmony_profiles_v1.json"


@lru_cache(maxsize=1)
def _load_seed() -> dict[str, Any]:
    if not _SEED_PATH.exists():
        return {"reference_now_utc": None, "profiles": []}
    return json.loads(_SEED_PATH.read_text(encoding="utf-8"))


def get_demo_profile(user_id: str) -> dict[str, Any] | None:
    seed = _load_seed()
    return next((profile for profile in seed["profiles"] if profile["id"] == user_id), None)


def has_demo_profile(user_id: str) -> bool:
    return get_demo_profile(user_id) is not None


def has_live_profile_activity(db: Session, user_id: str) -> bool:
    return (
        db.query(JournalEntry.id)
        .filter(JournalEntry.user_id == user_id)
        .first()
        is not None
    )


def demo_harmony_payload(user_id: str) -> dict[str, Any] | None:
    profile = get_demo_profile(user_id)
    if profile is None:
        return None

    harmony = profile["expected_harmony"]
    reference_now = _load_seed().get("reference_now_utc")
    updated_at = (
        datetime.fromisoformat(reference_now).isoformat()
        if reference_now is not None
        else datetime.utcnow().isoformat()
    )

    return {
        "user_id": user_id,
        "dimensions": dict(harmony["dimensions"]),
        "overall_balance": harmony["overall_balance"],
        "overwork_stage": harmony["overwork_stage"],
        "overwork_consecutive_days": harmony["overwork_consecutive_days"],
        "updated_at": updated_at,
    }


def demo_variety_payload(user_id: str) -> dict[str, Any] | None:
    profile = get_demo_profile(user_id)
    if profile is None:
        return None
    return dict(profile["expected_variety"])


def demo_stats_payload(user_id: str) -> dict[str, Any] | None:
    profile = get_demo_profile(user_id)
    if profile is None:
        return None
    return {"user_id": user_id, **dict(profile["profile_stats"])}
