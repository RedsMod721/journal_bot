"""Steps 08b + 14c — Anomaly/troll detection and score persistence.

``precheck``  (step 08b) — Runs *before* quest-reward computation.
              Uses DB history to estimate a troll_bp multiplier for the
              current session without needing to know the final XP total.
              Allowed to degrade: falls back to neutral (10 000 bp, 1.0×).

``record``    (step 14c) — Runs *after* progression counters are updated.
              Persists the final ``AnomalyScore`` row so the score is
              visible to analytics dashboards and future pipeline runs.
              Allowed to degrade: a missing row is not pipeline-critical.

Troll multiplier schedule
--------------------------
Raw anomaly score (0.0–10.0, Section 9.0.1) maps to multipliers via:

    m = 1.0 + ((score/10) ** 1.5) * 4.0   range [1.0, 5.0]

    score  0.0 → m 1.000  (10 000 bp — normal session)
    score  5.0 → m 2.414  (24 142 bp — notable performance)
    score 10.0 → m 5.000  (50 000 bp — exceptional performance)

score is stored on the 0–10 canonical scale in the DB (ck_anomaly_score_range).

Scoring heuristics (precheck)
-------------------------------
+3.0  High consistency: ≥3 skills active in the last 7 days.
+2.0  Multi-skill session: ≥2 distinct skills detected in current entry.
+2.0  Daily streak active: a skill with last_activity_at = yesterday/today.
+2.0  XP momentum: any skill's last session was within 48 hours.
      (capped at 10.0 total)
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.orm import Session

from src.db.models.anomaly import AnomalyScore
from src.db.models.skill import Skill


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Step 08b — Precheck (before quest reward calculation)
# ---------------------------------------------------------------------------


def precheck(
    *,
    user_id: str,
    detected_skills: list[str],
    db: Session,
) -> dict[str, Any]:
    """Estimate the troll_bp multiplier from historical DB signals.

    Runs before the XP reward steps so the result feeds into
    ``finalize_quest_xp(troll_bp=...)``.  Uses only historical data
    (skill recency) so no knowledge of the current session's XP is needed.

    Args:
        user_id:          Owning user UUID.
        detected_skills:  Skill names detected in the current entry (step 07).
        db:               SQLAlchemy session (read-only within this step).

    Returns:
        Dict with keys:
            ``troll_bp``        — int, 10 000–30 000.
            ``troll_multiplier``— float, 1.0–3.0.
            ``anomaly_score``   — float 0.0–1.0 (pre-session estimate).
            ``reasons``         — list[str] of triggered heuristics.
    """
    now = _now_utc()
    week_cutoff = now - timedelta(days=7)
    day_cutoff = now - timedelta(days=2)  # "within 48 h"

    # ── Consistency: how many skills are active this week ─────────────────
    recent_week_count: int = (
        db.query(Skill)
        .filter(
            Skill.user_id == user_id,
            Skill.last_activity_at >= week_cutoff,
        )
        .count()
    )

    # ── XP momentum: any skill active within 48 h ────────────────────────
    has_momentum: bool = (
        db.query(Skill)
        .filter(
            Skill.user_id == user_id,
            Skill.last_activity_at >= day_cutoff,
        )
        .count()
    ) > 0

    score = 0.0
    reasons: list[str] = []

    if recent_week_count >= 3:
        score += 3.0
        reasons.append(f"high_consistency:{recent_week_count}_skills_7d")

    if len(detected_skills) >= 2:
        score += 2.0
        reasons.append(f"multi_skill_session:{len(detected_skills)}_skills")

    if has_momentum:
        score += 2.0
        reasons.append("xp_momentum:active_within_48h")

    score = min(10.0, round(score, 4))

    troll_multiplier, troll_bp = _troll_multiplier_from_score(score)

    return {
        "troll_bp": troll_bp,
        "troll_multiplier": troll_multiplier,
        "anomaly_score": score,
        "reasons": reasons,
    }


def _troll_multiplier_from_score(score_010: float) -> tuple[float, int]:
    """Compute troll multiplier from a 0-10 anomaly score (Section 9.6 / A.6.1).

        m = 1.0 + ((score / 10) ** 1.5) * 4.0   range [1.0, 5.0]

    Precision rule (section A.6.2): computed with Decimal, quantised to 6 dp
    using ROUND_HALF_UP before conversion to float/int.

    Returns:
        (troll_multiplier, troll_bp) -- float rounded to 6 dp, int basis points.
    """
    d = Decimal(str(score_010)) / Decimal("10")
    # x^1.5 = x * sqrt(x)  (avoids fractional-exponent drift per arch spec)
    sqrt_d = d.sqrt()
    x_power = d * sqrt_d
    m = Decimal("1.0") + x_power * Decimal("4.0")
    m = m.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    troll_bp = int(m * Decimal("10000"))
    return float(m), troll_bp


# ---------------------------------------------------------------------------
# Step 14c — Record final anomaly score
# ---------------------------------------------------------------------------


def record(
    *,
    user_id: str,
    entry_id: str,
    anomaly_score: float,
    troll_multiplier: float,
    reasons: list[str],
    skill_xp_total: int,
    db: Session,
) -> dict[str, Any]:
    """Project the authoritative anomaly row already persisted in step 08b.

    The canonical write happens in ``AnomalyOrchestrator.ensure_anomaly_score``.
    This helper remains as a compatibility shim for downstream summary code,
    but it must not create or overwrite anomaly rows.
    """
    del anomaly_score, troll_multiplier, reasons

    existing = (
        db.query(AnomalyScore)
        .filter(
            AnomalyScore.user_id == user_id,
            AnomalyScore.entry_id == entry_id,
        )
        .first()
    )
    if existing:
        return {
            "anomaly_id": entry_id,
            "anomaly_score": existing.score,
            "skill_xp_total": skill_xp_total,
        }

    return {
        "anomaly_id": None,
        "anomaly_score": 0.0,
        "skill_xp_total": skill_xp_total,
    }
