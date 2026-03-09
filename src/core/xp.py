"""
XP Calculation Module

Based on Appendix A.1 of the architecture (canonical reference implementation).
Section 10.6 and 10.7 define the full quest XP pipeline; this module covers
the pure numeric functions that are called from that pipeline.

Exponent schedule (target-level semantics):
  target < 60   → 1.5  (ranks F through A)
  target < 75   → 1.6  (rank S)
  target < 100  → 1.8  (rank SS)
  target >= 100 → 2.0  (rank SSS)

Reference: Architecture Appendix A.1.2–A.1.3
"""

from typing import Dict
import hashlib
import json
import math

# ---------------------------------------------------------------------------
# Precomputed cumulative XP table for levels 1–100 (generated at import time).
# Architecture note: values are generated from the reference code, not manually
# edited (Appendix A.1.4 "generation rule").
# ---------------------------------------------------------------------------


def _get_xp_exponent(target_level: int) -> float:
    """Select the exponent for advancing TO target_level (target-level semantics).

    Architecture reference: Appendix A.1.2
    """
    if target_level < 60:
        return 1.5
    elif target_level < 75:
        return 1.6
    elif target_level < 100:
        return 1.8
    else:
        return 2.0


def _required_xp(target_level: int) -> int:
    """XP required to advance from (target_level - 1) to target_level.

    Returns 0 for target_level <= 1.
    Architecture reference: Appendix A.1.3
    """
    if target_level <= 1:
        return 0
    return int(50 * (target_level ** _get_xp_exponent(target_level)))


# Build cumulative table: _CUM_XP[L] = total XP to be at the start of level L.
# Index 0 unused; index 1 = 0 XP; index 100 = 5,565,727 XP.
_MAX_LEVEL = 100
_CUM_XP: list[int] = [0] * (_MAX_LEVEL + 1)
for _t in range(2, _MAX_LEVEL + 1):
    _CUM_XP[_t] = _CUM_XP[_t - 1] + _required_xp(_t)


def _ensure_cum_table(level: int) -> None:
    """Extend the cumulative table up to *level* (inclusive) if needed."""
    if level <= _MAX_LEVEL:
        return
    start = len(_CUM_XP)
    if level < start:
        return
    _CUM_XP.extend([0] * (level - start + 1))
    for t in range(start, level + 1):
        _CUM_XP[t] = _CUM_XP[t - 1] + _required_xp(t)


def _cumulative_xp(level: int) -> int:
    """Return total XP required to be at the start of *level*."""
    if level <= 1:
        return 0
    _ensure_cum_table(level)
    return _CUM_XP[level]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def calculate_xp_for_level(level: int) -> int:
    """Return the total (cumulative) XP required to reach *level*.

    Level 1 starts at 0 XP.  The value returned is the XP a player must have
    accumulated to be *at* the given level (i.e. the "Total XP at Level Start"
    column in architecture Appendix A.1.4).

    Formula per Appendix A.1.3:
        cumulative_xp_to_reach_level(L) = Σ required_xp(t)  for t = 2..L
        where required_xp(t) = int(50 * t ** exponent(t))

    Exponent tiers (target-level semantics):
        t < 60  → 1.5   (F–A)
        t < 75  → 1.6   (S)
        t < 100 → 1.8   (SS)
        t ≥ 100 → 2.0   (SSS)

    Reference values (Architecture Appendix A.1.4):
        level  1 →          0
        level  2 →        141
        level  5 →      1,359
        level 30 →    102,669
        level 50 →    362,365
        level 100 → 5,565,727
    """
    return _cumulative_xp(level)


def calculate_level_from_xp(total_xp: int) -> int:
    """Return the current level for a player with *total_xp* accumulated XP.

    Uses exponential-bound discovery + binary search for O(log n) behavior
    with unbounded levels (no hard cap at 100).

    Architecture reference: Appendix A.1.3 get_level_from_total_xp.
    """
    if total_xp <= 0:
        return 1

    lo, hi = 1, _MAX_LEVEL
    while _cumulative_xp(hi) <= total_xp:
        lo = hi
        hi *= 2

    # Binary search: find the largest L such that cumulative_xp(L) <= total_xp.
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _cumulative_xp(mid) <= total_xp:
            lo = mid
        else:
            hi = mid - 1
    return lo


def round_half_up(x: float) -> int:
    """Runtime-independent round-half-up for non-negative values."""
    if x < 0:
        raise ValueError("round_half_up expects a non-negative value")
    return int(math.floor(x + 0.5))


def float_multiplier_to_bp(multiplier: float, *, max_bp: int = 50000) -> int:
    """Convert a legacy float multiplier to basis points (bp), round-half-up."""
    if math.isnan(multiplier) or math.isinf(multiplier):
        raise ValueError("multiplier must be a finite number")
    if multiplier < 0:
        raise ValueError("multiplier must be non-negative")
    return min(max_bp, max(0, round_half_up(multiplier * 10000.0)))


def finalize_quest_xp(
    quest_xp_total: int = 480,
    troll_bp: int = 10000,
    variety_multiplier_bp: int = 10000,
    arc_reward_multiplier_bp: int = 10000,
    diminishing_bp: int = 10000,
    penalty_xp: int = 0,
) -> Dict[str, int]:
    """Canonical Section 10 integer XP finalization pipeline.

    Stage order (architecture §5.9 / §9.8):
        base → troll → variety → arc → diminishing → penalty
    """
    base = max(0, int(quest_xp_total))
    troll_bp = max(0, int(troll_bp))
    variety_multiplier_bp = max(0, int(variety_multiplier_bp))
    arc_reward_multiplier_bp = max(0, int(arc_reward_multiplier_bp))
    diminishing_bp = max(0, int(diminishing_bp))
    penalty_xp = max(0, int(penalty_xp))

    t1 = (base * troll_bp) // 10000
    t2 = (t1 * variety_multiplier_bp) // 10000
    t3 = (t2 * arc_reward_multiplier_bp) // 10000
    t4 = (t3 * diminishing_bp) // 10000
    final_xp = max(0, t4 - penalty_xp)

    return {
        "quest_xp_total": base,
        "t1_after_troll": t1,
        "t2_after_variety": t2,
        "t3_after_arc": t3,
        "t4_after_diminishing": t4,
        "penalty_xp": penalty_xp,
        "final_xp": final_xp,
    }


def apportion_by_bp(total: int, recipients: list[tuple[str, int]]) -> dict[str, int]:
    """Deterministic sum-preserving apportionment (Section 10.1.5 / A.3)."""
    cleaned: list[tuple[str, int]] = []
    seen: set[str] = set()

    for recipient_id, bp in recipients:
        rid = str(recipient_id)
        if rid in seen:
            raise ValueError(f"duplicate recipient_id: {rid}")
        seen.add(rid)

        ibp = int(bp)
        if ibp < 0 or ibp > 10000:
            raise ValueError(f"weight_bp out of bounds for {rid}: {ibp}")
        cleaned.append((rid, ibp))

    total_int = max(0, int(total))
    if total_int == 0:
        return {rid: 0 for rid, _ in cleaned}

    sum_bp = sum(bp for _, bp in cleaned)
    if sum_bp <= 0:
        raise ValueError("sum_bp must be > 0")

    rows: list[list[int | str]] = []
    for rid, bp in cleaned:
        prod = total_int * bp
        base = prod // sum_bp
        rem = prod % sum_bp
        rows.append([rid, bp, base, rem])

    allocated = sum(int(r[2]) for r in rows)
    leftover = total_int - allocated

    order = sorted(
        range(len(rows)),
        key=lambda i: (-int(rows[i][3]), str(rows[i][0])),
    )

    out = {str(rid): int(base) for rid, _, base, _ in rows}
    for idx in order[:leftover]:
        rid = str(rows[idx][0])
        out[rid] += 1
    return out


def choose_primary_recipient_id(recipients: list[tuple[str, int]]) -> str:
    """Choose primary recipient by max bp, tie-break lexicographic id."""
    if not recipients:
        raise ValueError("recipients must not be empty")
    max_bp = max(int(bp) for _, bp in recipients)
    candidates = [str(rid) for rid, bp in recipients if int(bp) == max_bp]
    return min(candidates)


def derive_theme_awards_from_skill_award(
    source_skill_xp: int,
    source_skill_id: str,
    theme_weights_bp: list[tuple[str, int]],
) -> list[dict[str, int | str]]:
    """Deterministically derive theme awards from one persisted skill award."""
    skill_xp = int(source_skill_xp)
    if skill_xp <= 0:
        return []
    allocations = apportion_by_bp(skill_xp, theme_weights_bp)
    out: list[dict[str, int | str]] = []
    for theme_id in sorted(allocations.keys()):
        amount = int(allocations[theme_id])
        if amount <= 0:
            continue
        out.append(
            {
                "distribution_type": "theme",
                "theme_id": str(theme_id),
                "source_skill_id": str(source_skill_id),
                "source_skill_xp": skill_xp,
                "amount": amount,
            }
        )
    return out


def _identity_value(value: str | int | None) -> str:
    """Serialize identity-token values using Section 10 NULL semantics."""
    if value is None:
        return "NULL"
    return str(value)


def build_skill_award_identity_key(
    *,
    user_id: str,
    entry_id: str,
    quest_id: str,
    xp_reason: str,
    distribution_type: str,
    skill_id: str,
    ruleset_version: str,
) -> str:
    """Build canonical skill award identity key hash (Section 10.17.4A)."""
    canonical = (
        "kind=skill"
        f"|user_id={_identity_value(user_id)}"
        f"|entry_id={_identity_value(entry_id)}"
        f"|quest_id={_identity_value(quest_id)}"
        f"|xp_reason={_identity_value(xp_reason)}"
        f"|distribution_type={_identity_value(distribution_type)}"
        f"|skill_id={_identity_value(skill_id)}"
        f"|ruleset_version={_identity_value(ruleset_version)}"
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_theme_award_identity_key(
    *,
    user_id: str,
    entry_id: str,
    quest_id: str,
    xp_reason: str,
    distribution_type: str,
    theme_id: str,
    source_skill_id: str | None,
    source_skill_xp: int | None,
    ruleset_version: str,
) -> str:
    """Build canonical theme award identity key hash (Section 10.17.4A)."""
    canonical = (
        "kind=theme"
        f"|user_id={_identity_value(user_id)}"
        f"|entry_id={_identity_value(entry_id)}"
        f"|quest_id={_identity_value(quest_id)}"
        f"|xp_reason={_identity_value(xp_reason)}"
        f"|distribution_type={_identity_value(distribution_type)}"
        f"|theme_id={_identity_value(theme_id)}"
        f"|source_skill_id={_identity_value(source_skill_id)}"
        f"|source_skill_xp={_identity_value(source_skill_xp)}"
        f"|ruleset_version={_identity_value(ruleset_version)}"
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def sort_xp_awards_for_payload(xp_awards: list[dict]) -> list[dict]:
    """Sort XP award payload rows per Section 10.2.4 deterministic ordering."""
    return sorted(
        xp_awards,
        key=lambda a: (
            str(a.get("xp_reason", "")),
            str(a.get("distribution_type", "")),
            a.get("skill_id") is None,
            str(a.get("skill_id") or ""),
            a.get("theme_id") is None,
            str(a.get("theme_id") or ""),
            a.get("source_skill_id") is None,
            str(a.get("source_skill_id") or ""),
            -int(a.get("amount", 0)),
        ),
    )


def canonical_json_bytes(payload: dict) -> bytes:
    """Encode payload with canonical JSON settings used by replay hashing."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def calculate_session_xp(
    base_xp: int,
    minutes: int,
    quality_mult: float,
    variety_bonus: float,
    troll_multiplier: float = 1.0,
) -> Dict[str, int]:
    """Compatibility wrapper for legacy session-style XP inputs.

    Canonical production XP finalization is Section 10 integer bp math
    (`finalize_quest_xp`). This helper preserves the old input shape while
    routing multiplier stages through the canonical pipeline.
    """
    if base_xp < 0:
        raise ValueError("base_xp must be non-negative")
    if minutes <= 0:
        raise ValueError("minutes must be > 0")
    if minutes % 30 != 0:
        raise ValueError("minutes must be a multiple of 30 in compatibility mode")
    if quality_mult < 0 or math.isnan(quality_mult) or math.isinf(quality_mult):
        raise ValueError("quality_mult must be a finite non-negative number")
    if variety_bonus <= -1.0 or math.isnan(variety_bonus) or math.isinf(variety_bonus):
        raise ValueError("variety_bonus must be finite and > -1.0")
    if (
        troll_multiplier < 0
        or math.isnan(troll_multiplier)
        or math.isinf(troll_multiplier)
    ):
        raise ValueError("troll_multiplier must be a finite non-negative number")

    # Legacy pre-stage retained for backward compatibility only.
    time_mult = max(1, minutes // 30)
    pre_base = int(base_xp * time_mult * quality_mult)

    result = finalize_quest_xp(
        quest_xp_total=pre_base,
        troll_bp=float_multiplier_to_bp(troll_multiplier),
        variety_multiplier_bp=float_multiplier_to_bp(1.0 + variety_bonus),
        arc_reward_multiplier_bp=10000,
        penalty_xp=0,
    )
    skill_xp = result["final_xp"]
    theme_xp = calculate_theme_xp_from_skill(skill_xp)
    return {"skill_xp": skill_xp, "theme_xp": theme_xp}


def calculate_theme_xp_from_skill(skill_xp: int) -> int:
    """Return the theme XP derived from an awarded skill XP amount.

    Compatibility helper for legacy 0.1% propagation behavior:
        theme_xp = max(1, int(skill_xp × 0.001))

    Note:
        Canonical Section 10 production behavior derives theme awards via
        deterministic apportionment from persisted skill awards (Appendix A.4),
        not this standalone percentage helper.

    Args:
        skill_xp: The skill XP amount that was awarded.

    Returns:
        Theme XP to award (always ≥ 1).
    """
    return max(1, int(skill_xp * 0.001))
