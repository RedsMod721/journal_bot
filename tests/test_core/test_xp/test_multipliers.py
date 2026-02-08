"""
Tests for XP multiplier calculator.

Tests the applies_to_target helper and calculate_title_multipliers function
with various title effect configurations.
"""

import pytest

from app.core.xp.multipliers import applies_to_target, calculate_title_multipliers
from app.models.title import TitleTemplate, UserTitle
from app.models.user import User


class TestAppliesToTarget:
    """Tests for the applies_to_target helper function."""

    def test_specific_theme_match(self):
        """Effect targeting specific theme matches that theme."""
        effect = {
            "type": "xp_multiplier",
            "scope": "theme",
            "target": "Education",
            "value": 1.10,
        }
        assert applies_to_target(effect, "theme", "Education") is True

    def test_specific_theme_no_match_different_name(self):
        """Effect targeting specific theme doesn't match different theme."""
        effect = {
            "type": "xp_multiplier",
            "scope": "theme",
            "target": "Education",
            "value": 1.10,
        }
        assert applies_to_target(effect, "theme", "Health") is False

    def test_specific_theme_no_match_different_type(self):
        """Effect targeting theme doesn't match skill."""
        effect = {
            "type": "xp_multiplier",
            "scope": "theme",
            "target": "Education",
            "value": 1.10,
        }
        assert applies_to_target(effect, "skill", "Education") is False

    def test_all_themes_scope(self):
        """Effect targeting all themes matches any theme."""
        effect = {
            "type": "xp_multiplier",
            "scope": "theme",
            "target": "all",
            "value": 1.15,
        }
        assert applies_to_target(effect, "theme", "Education") is True
        assert applies_to_target(effect, "theme", "Health") is True
        assert applies_to_target(effect, "skill", "Python") is False

    def test_all_skills_scope(self):
        """Effect targeting all skills matches any skill."""
        effect = {
            "type": "xp_multiplier",
            "scope": "skill",
            "target": "all",
            "value": 1.15,
        }
        assert applies_to_target(effect, "skill", "Python") is True
        assert applies_to_target(effect, "skill", "Cooking") is True
        assert applies_to_target(effect, "theme", "Education") is False

    def test_global_all_scope(self):
        """Effect with scope 'all' matches everything."""
        effect = {
            "type": "xp_multiplier",
            "scope": "all",
            "target": "all",
            "value": 1.20,
        }
        assert applies_to_target(effect, "theme", "Education") is True
        assert applies_to_target(effect, "skill", "Python") is True

    def test_global_all_scope_ignores_target_value(self):
        """Global scope applies regardless of target value."""
        effect = {
            "type": "xp_multiplier",
            "scope": "all",
            "target": "Education",
            "value": 1.10,
        }
        assert applies_to_target(effect, "theme", "Education") is True
        assert applies_to_target(effect, "skill", "Python") is True

    def test_non_xp_multiplier_effect(self):
        """Non xp_multiplier effects don't apply."""
        effect = {
            "type": "damage_boost",
            "scope": "all",
            "target": "all",
            "value": 1.50,
        }
        assert applies_to_target(effect, "theme", "Education") is False

    def test_case_insensitive_target_match(self):
        """Target matching is case-insensitive."""
        effect = {
            "type": "xp_multiplier",
            "scope": "theme",
            "target": "education",
            "value": 1.10,
        }
        assert applies_to_target(effect, "theme", "Education") is True
        assert applies_to_target(effect, "theme", "EDUCATION") is True

    def test_empty_effect(self):
        """Empty effect doesn't apply."""
        assert applies_to_target({}, "theme", "Education") is False

    def test_missing_scope_or_target_does_not_apply(self):
        """Missing scope/target should not apply."""
        effect = {"type": "xp_multiplier"}
        assert applies_to_target(effect, "theme", "Education") is False


class TestCalculateTitleMultipliers:
    """Tests for calculate_title_multipliers function."""

    def test_no_equipped_titles(self, db_session, sample_user):
        """User with no titles gets base multiplier of 1.0."""
        result = calculate_title_multipliers(
            db_session, sample_user.id, "theme", "Education"
        )
        assert result == 1.0

    def test_titles_for_other_users_are_ignored(self, db_session, sample_user, fake):
        """Only titles for the specified user should be considered."""
        other_user = User(username=fake.user_name(), email=fake.email())
        db_session.add(other_user)
        db_session.commit()

        template = TitleTemplate(
            name="OtherUserTitle",
            effect={
                "type": "xp_multiplier",
                "scope": "theme",
                "target": "Education",
                "value": 2.0,
            },
            rank="B",
        )
        db_session.add(template)
        db_session.commit()

        other_title = UserTitle(
            user_id=other_user.id,
            title_template_id=template.id,
            is_equipped=True,
        )
        db_session.add(other_title)
        db_session.commit()

        result = calculate_title_multipliers(
            db_session, sample_user.id, "theme", "Education"
        )
        assert result == 1.0

    def test_single_matching_title(self, db_session, sample_user):
        """Single matching title applies its multiplier."""
        template = TitleTemplate(
            name="Scholar",
            effect={
                "type": "xp_multiplier",
                "scope": "theme",
                "target": "Education",
                "value": 1.10,
            },
            rank="C",
        )
        db_session.add(template)
        db_session.commit()

        user_title = UserTitle(
            user_id=sample_user.id,
            title_template_id=template.id,
            is_equipped=True,
        )
        db_session.add(user_title)
        db_session.commit()

        result = calculate_title_multipliers(
            db_session, sample_user.id, "theme", "Education"
        )
        assert result == pytest.approx(1.10)

    def test_case_insensitive_matching_in_calculator(self, db_session, sample_user):
        """Calculator should match targets case-insensitively."""
        template = TitleTemplate(
            name="Scholar",
            effect={
                "type": "xp_multiplier",
                "scope": "theme",
                "target": "education",
                "value": 1.25,
            },
            rank="C",
        )
        db_session.add(template)
        db_session.commit()

        user_title = UserTitle(
            user_id=sample_user.id,
            title_template_id=template.id,
            is_equipped=True,
        )
        db_session.add(user_title)
        db_session.commit()

        result = calculate_title_multipliers(
            db_session, sample_user.id, "theme", "Education"
        )
        assert result == pytest.approx(1.25)

    def test_unequipped_title_not_applied(self, db_session, sample_user):
        """Unequipped titles don't contribute to multiplier."""
        template = TitleTemplate(
            name="Scholar",
            effect={
                "type": "xp_multiplier",
                "scope": "theme",
                "target": "Education",
                "value": 1.50,
            },
            rank="C",
        )
        db_session.add(template)
        db_session.commit()

        user_title = UserTitle(
            user_id=sample_user.id,
            title_template_id=template.id,
            is_equipped=False,
        )
        db_session.add(user_title)
        db_session.commit()

        result = calculate_title_multipliers(
            db_session, sample_user.id, "theme", "Education"
        )
        assert result == 1.0

    def test_non_xp_multiplier_effects_are_ignored(self, db_session, sample_user):
        """Effects with non-xp_multiplier type should not apply."""
        template = TitleTemplate(
            name="DamageBoost",
            effect={
                "type": "damage_boost",
                "scope": "theme",
                "target": "Education",
                "value": 9.0,
            },
            rank="C",
        )
        db_session.add(template)
        db_session.commit()

        user_title = UserTitle(
            user_id=sample_user.id,
            title_template_id=template.id,
            is_equipped=True,
        )
        db_session.add(user_title)
        db_session.commit()

        result = calculate_title_multipliers(
            db_session, sample_user.id, "theme", "Education"
        )
        assert result == 1.0

    def test_effect_missing_value_defaults_to_one(self, db_session, sample_user):
        """Missing value should default to multiplier of 1.0."""
        template = TitleTemplate(
            name="NoValue",
            effect={
                "type": "xp_multiplier",
                "scope": "theme",
                "target": "Education",
            },
            rank="C",
        )
        db_session.add(template)
        db_session.commit()

        user_title = UserTitle(
            user_id=sample_user.id,
            title_template_id=template.id,
            is_equipped=True,
        )
        db_session.add(user_title)
        db_session.commit()

        result = calculate_title_multipliers(
            db_session, sample_user.id, "theme", "Education"
        )
        assert result == 1.0

    def test_non_matching_title_not_applied(self, db_session, sample_user):
        """Titles targeting different targets don't apply."""
        template = TitleTemplate(
            name="Athlete",
            effect={
                "type": "xp_multiplier",
                "scope": "theme",
                "target": "Health",
                "value": 1.25,
            },
            rank="C",
        )
        db_session.add(template)
        db_session.commit()

        user_title = UserTitle(
            user_id=sample_user.id,
            title_template_id=template.id,
            is_equipped=True,
        )
        db_session.add(user_title)
        db_session.commit()

        result = calculate_title_multipliers(
            db_session, sample_user.id, "theme", "Education"
        )
        assert result == 1.0

    def test_multiplicative_stacking(self, db_session, sample_user):
        """Multiple matching titles stack multiplicatively."""
        # Title 1: +10% Education XP (1.10)
        template1 = TitleTemplate(
            name="Scholar",
            effect={
                "type": "xp_multiplier",
                "scope": "theme",
                "target": "Education",
                "value": 1.10,
            },
            rank="C",
        )
        # Title 2: +15% all themes (1.15)
        template2 = TitleTemplate(
            name="Lifelong Learner",
            effect={
                "type": "xp_multiplier",
                "scope": "theme",
                "target": "all",
                "value": 1.15,
            },
            rank="B",
        )
        # Title 3: +20% all XP (1.20)
        template3 = TitleTemplate(
            name="Overachiever",
            effect={
                "type": "xp_multiplier",
                "scope": "all",
                "target": "all",
                "value": 1.20,
            },
            rank="A",
        )
        db_session.add_all([template1, template2, template3])
        db_session.commit()

        for template in [template1, template2, template3]:
            user_title = UserTitle(
                user_id=sample_user.id,
                title_template_id=template.id,
                is_equipped=True,
            )
            db_session.add(user_title)
        db_session.commit()

        # Expected: 1.10 × 1.15 × 1.20 = 1.518
        result = calculate_title_multipliers(
            db_session, sample_user.id, "theme", "Education"
        )
        assert result == pytest.approx(1.518)

    def test_mixed_matching_and_non_matching(self, db_session, sample_user):
        """Only matching titles contribute to multiplier."""
        # Matching: +10% Education
        template1 = TitleTemplate(
            name="Scholar",
            effect={
                "type": "xp_multiplier",
                "scope": "theme",
                "target": "Education",
                "value": 1.10,
            },
            rank="C",
        )
        # Non-matching: +25% Health
        template2 = TitleTemplate(
            name="Athlete",
            effect={
                "type": "xp_multiplier",
                "scope": "theme",
                "target": "Health",
                "value": 1.25,
            },
            rank="C",
        )
        # Matching: +20% all XP
        template3 = TitleTemplate(
            name="Overachiever",
            effect={
                "type": "xp_multiplier",
                "scope": "all",
                "target": "all",
                "value": 1.20,
            },
            rank="A",
        )
        db_session.add_all([template1, template2, template3])
        db_session.commit()

        for template in [template1, template2, template3]:
            user_title = UserTitle(
                user_id=sample_user.id,
                title_template_id=template.id,
                is_equipped=True,
            )
            db_session.add(user_title)
        db_session.commit()

        # Expected: 1.10 × 1.20 = 1.32 (Health bonus not applied)
        result = calculate_title_multipliers(
            db_session, sample_user.id, "theme", "Education"
        )
        assert result == pytest.approx(1.32)

    def test_skill_multipliers(self, db_session, sample_user):
        """Skill-specific multipliers work correctly."""
        template = TitleTemplate(
            name="Pythonista",
            effect={
                "type": "xp_multiplier",
                "scope": "skill",
                "target": "Python",
                "value": 1.30,
            },
            rank="B",
        )
        db_session.add(template)
        db_session.commit()

        user_title = UserTitle(
            user_id=sample_user.id,
            title_template_id=template.id,
            is_equipped=True,
        )
        db_session.add(user_title)
        db_session.commit()

        result = calculate_title_multipliers(
            db_session, sample_user.id, "skill", "Python"
        )
        assert result == pytest.approx(1.30)

        # Doesn't apply to other skills
        result_other = calculate_title_multipliers(
            db_session, sample_user.id, "skill", "Cooking"
        )
        assert result_other == 1.0

    def test_mixed_equipped_and_unequipped_titles(self, db_session, sample_user):
        """Only equipped titles should contribute to multiplier."""
        template1 = TitleTemplate(
            name="Equipped",
            effect={
                "type": "xp_multiplier",
                "scope": "theme",
                "target": "Education",
                "value": 1.10,
            },
            rank="C",
        )
        template2 = TitleTemplate(
            name="Unequipped",
            effect={
                "type": "xp_multiplier",
                "scope": "theme",
                "target": "Education",
                "value": 1.50,
            },
            rank="B",
        )
        db_session.add_all([template1, template2])
        db_session.commit()

        db_session.add(
            UserTitle(
                user_id=sample_user.id,
                title_template_id=template1.id,
                is_equipped=True,
            )
        )
        db_session.add(
            UserTitle(
                user_id=sample_user.id,
                title_template_id=template2.id,
                is_equipped=False,
            )
        )
        db_session.commit()

        result = calculate_title_multipliers(
            db_session, sample_user.id, "theme", "Education"
        )
        assert result == pytest.approx(1.10)
