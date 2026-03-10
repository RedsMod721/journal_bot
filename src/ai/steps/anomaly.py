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
Raw anomaly score (0.0–1.0) maps to basis-point multipliers:

    score 0.0  → troll_bp 10 000  (1.0× — normal session)
    score 0.5  → troll_bp 20 000  (2.0× — notable performance)
    score 1.0  → troll_bp 30 000  (3.0× — exceptional performance)

The cap of 30 000 bp (3.0×) is intentionally conservative for a precheck
that operates without confirmed current-session XP.  Future arc-bonus
multipliers can amplify beyond this via arc_reward_multiplier_bp.

Scoring heuristics (precheck)
-------------------------------
+0.30  High consistency: ≥3 skills active in the last 7 days.
+0.20  Multi-skill session: ≥2 distinct skills detected in current entry.
+0.20  Daily streak active: a skill with last_activity_at = yesterday/today.
+0.20  XP momentum: any skill's last session was within 48 hours.
       (capped at 1.0 total)
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
        score += 0.30
        reasons.append(f"high_consistency:{recent_week_count}_skills_7d")

    if len(detected_skills) >= 2:
        score += 0.20
        reasons.append(f"multi_skill_session:{len(detected_skills)}_skills")

    if has_momentum:
        score += 0.20
        reasons.append("xp_momentum:active_within_48h")

    score = min(1.0, round(score, 4))

    troll_multiplier, troll_bp = _troll_multiplier_from_score(score)

    return {
        "troll_bp": troll_bp,
        "troll_multiplier": troll_multiplier,
        "anomaly_score": score,
        "reasons": reasons,
    }


def _troll_multiplier_from_score(score_01: float) -> tuple[float, int]:
    """Compute troll multiplier from a normalised 0-1 anomaly score.

    Maps to the architecture formula (section 9.6 / A.6.1) which operates on a
    0-10 scale.  Because our stored score is normalised to 0-1 (DB constraint),
    the scale factor cancels and the formula simplifies to:

        m = 1.0 + (score_01 ** 1.5) * 4.0   range [1.0, 5.0]

    Precision rule (section A.6.2): computed with Decimal, quantised to 6 dp
    using ROUND_HALF_UP before conversion to float/int.

    Returns:
        (troll_multiplier, troll_bp) -- float rounded to 6 dp, int basis points.
    """
    d = Decimal(str(score_01))
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
    reasons: list[str],
    skill_xp_total: int,
    db: Session,
) -> dict[str, Any]:
    """Persist the final ``AnomalyScore`` row for the current entry.

    Runs after progression counters are updated so ``skill_xp_total`` reflects
    the actual XP awarded.  The stored score is the pre-session estimate from
    the precheck step (used to drive the troll multiplier) enriched with the
    actual XP outcome for future baseline comparisons.

    Args:
        user_id:        Owning user UUID.
        entry_id:       Journal entry UUID.
        anomaly_score:  Float 0.0–1.0 from the precheck step.
        reasons:        List of triggered heuristic strings.
        skill_xp_total: Total skill XP awarded in this session (from awards).
        db:             SQLAlchemy session (write — issues a flush).

    Returns:
        Dict with keys:
            ``anomaly_id``    — PK of the persisted row.
            ``anomaly_score`` — echo of the input score.
            ``skill_xp_total``— echo of the input XP total.
    """
    enriched_reasons = list(reasons) + [f"skill_xp_total:{skill_xp_total}"]
    row = AnomalyScore(
        user_id=user_id,
        entry_id=entry_id,
        score=anomaly_score,
        reasons_json=json.dumps(enriched_reasons),
    )
    db.add(row)
    db.flush()
    return {
        "anomaly_id": row.id,
        "anomaly_score": anomaly_score,
        "skill_xp_total": skill_xp_total,
    }
