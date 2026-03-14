"""
Theme XP derivation from skill awards.

Implements Section 10.7.3 (Derivation algorithm) from architecture.

Algorithm (per skill award row with amount S):
    1. Look up skill.canonical_name → theme mappings in the JSON artifact.
    2. Apportion S across mapped themes using Huntington-Hill (same algorithm
       as Section 10.6.4, keyed by theme_name instead of skill_id).
    3. Write one xp_awards row per theme with amount > 0:
           distribution_type = 'theme'
           skill_id          = NULL
           theme_id          = <resolved from Theme.name>
           source_skill_id   = <originating skill's id>
           source_skill_xp   = S
    4. Idempotency: award_identity_key = SHA-256 of the canonical field set
       (guarded by uq_xp_awards_identity unique constraint + savepoint).

Source of truth:
    Theme awards are derived from persisted XpAward rows with
    distribution_type IN ('primary', 'secondary') — never directly from
    raw entry weights — to guarantee replay determinism (Section 10.7.1).
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.quest_theme_mapping import ThemeMapping
from src.core.quest_xp_distribution import QuestXPDistributionService
from src.db.models.global_kb import GlobalSkill
from src.db.models.skill import Skill, Theme
from src.db.models.xp import XpAward

logger = logging.getLogger(__name__)

# distribution_type values for skill awards (source rows)
_SKILL_DISTRIBUTION_TYPES = frozenset({"primary", "secondary"})


class ThemeXPDerivationService:
    """
    Derive theme XP from persisted skill award rows (Section 10.7.3).

    One instance per DB session; cheap to construct.
    """

    def __init__(self, db: Session, theme_mapping: ThemeMapping) -> None:
        self.db = db
        self.theme_mapping = theme_mapping
        self._xp_dist = QuestXPDistributionService(db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def derive_theme_awards(
        self,
        user_id: str,
        entry_id: str,
        quest_id: str,
        skill_awards: List[XpAward],
        xp_reason: str,
        processing_run_id: str,
        quest_matcher_version: int,
    ) -> List[XpAward]:
        """
        Derive and persist theme awards from a list of skill XpAward rows.

        Skips:
            - rows already tagged distribution_type='theme' (avoid re-deriving)
            - skills with no theme mappings in the artifact
            - theme amounts == 0 after apportionment (Section 10.7.3)
            - theme names that don't exist for this user (tenant isolation)

        Args:
            user_id:               User receiving XP.
            entry_id:              Source journal entry ID.
            quest_id:              Completed quest ID.
            skill_awards:          Persisted XpAward rows to derive from.
            xp_reason:             Stable reason key forwarded to theme rows.
            processing_run_id:     Pipeline run identifier.
            quest_matcher_version: Quest matcher schema version (audit).

        Returns:
            List of XpAward objects (newly created or pre-existing duplicates).
        """
        theme_awards: List[XpAward] = []

        # Cache theme rows for this user to avoid repeated queries
        themes_by_name = self._load_user_themes(user_id)

        for skill_award in skill_awards:
            if skill_award.distribution_type not in _SKILL_DISTRIBUTION_TYPES:
                continue  # Only derive from skill rows (Section 10.7.1)

            skill = (
                self.db.query(Skill)
                .filter(
                    Skill.user_id == user_id,
                    Skill.id == skill_award.skill_id,
                )
                .first()
            )
            if not skill:
                logger.warning(
                    "theme_derivation: skill_id=%s not found for user_id=%s — skipping",
                    skill_award.skill_id,
                    user_id,
                )
                continue

            source_skill_id: str | None = None
            if skill.global_skill_id:
                source_skill_id = (
                    self.db.query(GlobalSkill.source_skill_id)
                    .filter(GlobalSkill.id == skill.global_skill_id)
                    .scalar()
                )

            theme_entries = self.theme_mapping.get_themes_for_skill(
                *self.theme_mapping.candidate_keys_for_skill(
                    canonical_name=skill.canonical_name,
                    source_skill_id=source_skill_id,
                )
            )
            if not theme_entries:
                continue  # No theme mappings for this skill

            skill_xp = skill_award.amount

            # Build {theme_name: weight_bp} for apportionment
            weights_bp = {
                entry["theme_name"]: entry["theme_weight_bp"]
                for entry in theme_entries
            }

            # Huntington-Hill apportionment of skill_xp across themes
            amounts_by_theme = self._xp_dist.apportion_xp(skill_xp, weights_bp)

            for theme_name, amount in amounts_by_theme.items():
                if amount <= 0:
                    continue  # Section 10.7.3: never write zero-amount rows

                theme_row = themes_by_name.get(theme_name)
                if theme_row is None:
                    logger.warning(
                        "theme_derivation: theme '%s' not found for user_id=%s — skipping",
                        theme_name,
                        user_id,
                    )
                    continue

                award = self._persist_theme_award(
                    user_id=user_id,
                    entry_id=entry_id,
                    quest_id=quest_id,
                    theme_id=theme_row.id,
                    amount=amount,
                    source_skill_id=skill_award.skill_id,
                    source_skill_xp=skill_xp,
                    xp_reason=xp_reason,
                    processing_run_id=processing_run_id,
                    quest_matcher_version=quest_matcher_version,
                )
                if award is not None:
                    theme_awards.append(award)

        return theme_awards

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_user_themes(self, user_id: str) -> dict[str, Theme]:
        """Return {theme_name: Theme} for the user (single query)."""
        rows: list[Theme] = (
            self.db.query(Theme)
            .filter(Theme.user_id == user_id)
            .all()
        )
        return {row.name: row for row in rows}

    def _persist_theme_award(
        self,
        *,
        user_id: str,
        entry_id: str,
        quest_id: str,
        theme_id: str,
        amount: int,
        source_skill_id: str,
        source_skill_xp: int,
        xp_reason: str,
        processing_run_id: str,
        quest_matcher_version: int,
    ) -> XpAward | None:
        """
        Write one theme XpAward row (idempotent).

        Uses a savepoint so that a duplicate identity key rolls back only this
        row without aborting the outer transaction.

        Identity key covers: user_id, entry_id, quest_id, xp_reason,
        'theme', theme_id, source_skill_id — sufficient to uniquely identify
        one theme award derivation within a pipeline run.
        """
        identity_key = _theme_identity_key(
            user_id, entry_id, quest_id, xp_reason, theme_id, source_skill_id
        )
        now = datetime.now(timezone.utc)
        now_ms = int(now.timestamp() * 1000)

        award = XpAward(
            id=str(uuid.uuid4()),
            user_id=user_id,
            entry_id=entry_id,
            quest_id=quest_id,
            xp_reason=xp_reason,
            distribution_type="theme",
            amount=amount,
            skill_id=None,          # Theme awards: skill_id must be NULL
            theme_id=theme_id,
            source_skill_id=source_skill_id,
            source_skill_xp=source_skill_xp,
            skill_weight=None,
            skill_weight_bp=None,
            processing_run_id=processing_run_id,
            quest_matcher_version=quest_matcher_version,
            awarded_at=now,
            awarded_at_utc_ms=now_ms,
            award_identity_key=identity_key,
        )

        sp = self.db.begin_nested()
        try:
            self.db.add(award)
            self.db.flush()
            sp.commit()
            return award
        except IntegrityError:
            sp.rollback()
            existing = (
                self.db.query(XpAward)
                .filter(XpAward.award_identity_key == identity_key)
                .first()
            )
            if existing:
                return existing
            logger.error(
                "theme_derivation: IntegrityError but no existing row found "
                "for identity_key=%s — award skipped",
                identity_key,
            )
            return None


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _theme_identity_key(
    user_id: str,
    entry_id: str,
    quest_id: str,
    xp_reason: str,
    theme_id: str,
    source_skill_id: str,
) -> str:
    """
    Deterministic identity hash for a theme XP award.

    Canonical form:
        SHA-256(user_id:entry_id:quest_id:xp_reason:theme:theme_id:source_skill_id)

    The literal string 'theme' in position 5 prevents any collision with the
    skill-award identity key defined in Section 10.6.5.
    """
    raw = ":".join(
        [user_id, entry_id, quest_id, xp_reason, "theme", theme_id, source_skill_id]
    )
    return hashlib.sha256(raw.encode()).hexdigest()
