"""Seed deterministic harmony demo profiles for the Profile screen.

This script materializes three curated demo users from
``data/seeds/demo/harmony_profiles_v1.json`` and drives harmony from the same
upstream signals the app uses in production:

- ``users`` for identity and timezone
- ``themes`` for canonical theme IDs
- ``journal_entries`` + ``journal_entries_structured`` for harmony classification
- ``forgiveness_configs`` for overwork thresholds
- ``HarmonyRefreshService`` for derived harmony rows and snapshots
- ``BalanceWindowService`` for profile-page variety data
"""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.balance_window_service import BalanceWindowService
from src.core.forgiveness_presets import get_preset_params
from src.core.harmony_refresh_service import HarmonyRefreshService
from src.core.themes import ensure_user_themes
from src.db.models.forgiveness import ForgivenessConfig
from src.db.models.harmony import HarmonyDimension, HarmonySnapshot
from src.db.models.journal_entry import JournalEntry, JournalEntryStructured
from src.db.models.strategy import StrategyTracking
from src.db.models.user import User
from src.db.session import db_session
from sqlalchemy import inspect

SEED_PATH = REPO_ROOT / "data" / "seeds" / "demo" / "harmony_profiles_v1.json"
_DIMS = ("physical", "mental", "social", "productivity", "rest", "growth", "creative")


def _load_seed(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_datetime(raw: str) -> datetime:
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _entry_created_at(reference_now: datetime, entry_spec: dict[str, Any]) -> datetime:
    day = (reference_now - timedelta(days=int(entry_spec["days_ago"]))).date()
    hour = int(entry_spec.get("hour_utc", 12))
    minute = int(entry_spec.get("minute_utc", 0))
    return datetime.combine(day, time(hour=hour, minute=minute, tzinfo=timezone.utc))


def _refresh_now(reference_now: datetime, days_ago: int) -> datetime:
    target_day = (reference_now - timedelta(days=days_ago)).date()
    return datetime.combine(
        target_day,
        time(
            hour=reference_now.hour,
            minute=reference_now.minute,
            second=reference_now.second,
            tzinfo=timezone.utc,
        ),
    )


def _upsert_user(db, profile_spec: dict[str, Any]) -> User:
    user = db.query(User).filter(User.id == profile_spec["id"]).one_or_none()
    if user is None:
        user = User(
            id=profile_spec["id"],
            email=profile_spec["email"],
            password_hash="seeded_password_hash",
        )
        db.add(user)
        db.flush()

    user.email = profile_spec["email"]
    user.username = profile_spec["username"]
    user.display_name = profile_spec["display_name"]
    user.timezone = profile_spec["timezone"]
    user.home_country = str(profile_spec.get("home_country", "FR")).upper()
    user.password_hash = user.password_hash or "seeded_password_hash"
    return user


def _assert_week5_schema(db) -> None:
    inspector = inspect(db.get_bind())

    if inspector.has_table("harmony_dimensions"):
        harmony_columns = {
            column["name"] for column in inspector.get_columns("harmony_dimensions")
        }
        required = {"user_id", "physical", "mental", "social", "productivity", "rest", "growth", "creative"}
        if not required.issubset(harmony_columns):
            raise RuntimeError(
                "Legacy harmony schema detected. "
                "The current DATABASE_URL points at a database with the old "
                "row-per-dimension harmony table. Seed these profiles against a "
                "Week 5 schema database first."
            )

    if inspector.has_table("strategy_tracking"):
        strategy_columns = {
            column["name"] for column in inspector.get_columns("strategy_tracking")
        }
        required = {
            "user_id",
            "social_risk_count",
            "study_burst_count",
            "mundane_focus_count",
            "troll_exploits_count",
            "daily_grind_count",
            "harmony_balance_count",
        }
        if not required.issubset(strategy_columns):
            raise RuntimeError(
                "Legacy strategy schema detected. "
                "The current DATABASE_URL points at a database with the old "
                "row-per-strategy tracking table. Seed these profiles against a "
                "Week 5 schema database first."
            )


def _ensure_forgiveness_config(db, user: User, preset: str) -> ForgivenessConfig:
    config = (
        db.query(ForgivenessConfig)
        .filter(ForgivenessConfig.user_id == user.id)
        .one_or_none()
    )
    if config is None:
        config = ForgivenessConfig(user_id=user.id)
        db.add(config)
        db.flush()

    params = get_preset_params(preset)
    config.preset = preset
    config.skill_decay_rate = params.skill_decay_rate
    config.skill_grace_period_days = params.skill_grace_days
    config.insight_decay_rate = params.insight_decay_rate
    config.insight_grace_period_days = params.insight_grace_days
    config.critical_staleness_threshold = params.critical_threshold
    user.forgiveness_config_id = config.id
    return config


def _clear_profile_runtime_state(db, user_id: str) -> None:
    db.query(HarmonySnapshot).filter(HarmonySnapshot.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(StrategyTracking).filter(StrategyTracking.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(HarmonyDimension).filter(HarmonyDimension.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(JournalEntryStructured).filter(
        JournalEntryStructured.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(JournalEntry).filter(JournalEntry.user_id == user_id).delete(
        synchronize_session=False
    )
    db.flush()


def _theme_id_map(db, user_id: str) -> dict[str, str]:
    themes = ensure_user_themes(db, user_id)
    return {name: theme.id for name, theme in themes.items()}


def _seed_entries(
    db,
    user_id: str,
    reference_now: datetime,
    theme_ids: dict[str, str],
    profile_spec: dict[str, Any],
) -> None:
    for entry_spec in profile_spec["journal_entries"]:
        created_at = _entry_created_at(reference_now, entry_spec)
        entry = JournalEntry(
            user_id=user_id,
            content=entry_spec["content"],
            entry_type="text",
            status="completed",
            created_at=created_at,
            processed_at=created_at,
        )
        db.add(entry)
        db.flush()

        involved = [
            {"kind": "theme", "id": theme_ids[theme_name]}
            for theme_name in entry_spec["themes"]
        ]
        db.add(
            JournalEntryStructured(
                user_id=user_id,
                entry_id=entry.id,
                canonical_text=entry_spec["content"],
                energy_level=entry_spec.get("energy_level"),
                skills_themes_involved=json.dumps(involved, separators=(",", ":")),
            )
        )
    db.flush()


def _refresh_profile_harmony(
    db,
    user_id: str,
    reference_now: datetime,
    profile_spec: dict[str, Any],
) -> None:
    harmony_service = HarmonyRefreshService(db)
    refresh_spec = profile_spec["refresh"]
    advance = refresh_spec["mode"] == "advance"

    for days_ago in refresh_spec["days_ago_sequence"]:
        run_at = _refresh_now(reference_now, int(days_ago))
        result = harmony_service.refresh_harmony(
            user_id,
            run_at,
            advance_overwork_state=advance,
        )
        harmony_service.create_snapshot(user_id, result.snapshot_date_local)


def _assert_expected_harmony(db, user_id: str, reference_now: datetime, profile_spec: dict[str, Any]) -> dict[str, Any]:
    harmony_service = HarmonyRefreshService(db)
    result = harmony_service.refresh_harmony(
        user_id,
        reference_now,
        advance_overwork_state=False,
    )
    expected = profile_spec["expected_harmony"]
    actual = {
        "dimensions": {
            dim: round(float(getattr(result.harmony, dim)), 5)
            for dim in _DIMS
        },
        "overall_balance": round(float(result.harmony.overall_balance), 5),
        "overwork_stage": int(result.overwork.stage),
        "overwork_consecutive_days": int(result.overwork.consecutive_days),
    }

    for dim in _DIMS:
        expected_value = round(float(expected["dimensions"][dim]), 5)
        if actual["dimensions"][dim] != expected_value:
            raise ValueError(
                f"{profile_spec['scenario']} {dim} mismatch: "
                f"expected {expected_value}, got {actual['dimensions'][dim]}"
            )
    expected_overall = round(float(expected["overall_balance"]), 5)
    if actual["overall_balance"] != expected_overall:
        raise ValueError(
            f"{profile_spec['scenario']} overall mismatch: "
            f"expected {expected_overall}, got {actual['overall_balance']}"
        )
    if actual["overwork_stage"] != int(expected["overwork_stage"]):
        raise ValueError(
            f"{profile_spec['scenario']} stage mismatch: "
            f"expected {expected['overwork_stage']}, got {actual['overwork_stage']}"
        )
    if actual["overwork_consecutive_days"] != int(expected["overwork_consecutive_days"]):
        raise ValueError(
            f"{profile_spec['scenario']} consecutive day mismatch: expected "
            f"{expected['overwork_consecutive_days']}, got {actual['overwork_consecutive_days']}"
        )
    return actual


def main() -> None:
    seed_spec = _load_seed(SEED_PATH)
    reference_now = _parse_datetime(seed_spec["reference_now_utc"])

    summaries: list[dict[str, Any]] = []
    with db_session() as db:
        _assert_week5_schema(db)
        for profile_spec in seed_spec["profiles"]:
            user = _upsert_user(db, profile_spec)
            _ensure_forgiveness_config(db, user, profile_spec["forgiveness_preset"])
            _clear_profile_runtime_state(db, user.id)
            theme_ids = _theme_id_map(db, user.id)
            _seed_entries(db, user.id, reference_now, theme_ids, profile_spec)
            _refresh_profile_harmony(db, user.id, reference_now, profile_spec)
            BalanceWindowService(db).refresh_window(user.id, reference_now)
            actual = _assert_expected_harmony(db, user.id, reference_now, profile_spec)
            summaries.append(
                {
                    "user_id": user.id,
                    "display_name": user.display_name,
                    "scenario": profile_spec["scenario"],
                    **actual,
                }
            )

    print(json.dumps({"seed_path": str(SEED_PATH), "profiles": summaries}, indent=2))


if __name__ == "__main__":
    main()
