"""
XP multiplier calculator for equipped titles.

Calculates combined XP multipliers from a user's equipped titles.
Multipliers stack multiplicatively for powerful synergies.
"""

from sqlalchemy.orm import Session

from app.models.title import UserTitle


def applies_to_target(
    effect: dict,
    target_type: str,
    target_id: str,
) -> bool:
    """
    Check if a title effect applies to a specific target.

    Args:
        effect: Title effect dict with type, scope, target, value
        target_type: The type of target ("theme" or "skill")
        target_id: The name/identifier of the target entity

    Returns:
        True if the effect applies to this target

    Examples:
        # Specific target match
        effect = {"type": "xp_multiplier", "scope": "theme", "target": "Education", "value": 1.1}
        applies_to_target(effect, "theme", "Education")  # True
        applies_to_target(effect, "theme", "Health")     # False
        applies_to_target(effect, "skill", "Education")  # False

        # All targets within scope
        effect = {"type": "xp_multiplier", "scope": "theme", "target": "all", "value": 1.15}
        applies_to_target(effect, "theme", "Education")  # True
        applies_to_target(effect, "theme", "Health")     # True
        applies_to_target(effect, "skill", "Python")     # False

        # Global all XP
        effect = {"type": "xp_multiplier", "scope": "all", "target": "all", "value": 1.2}
        applies_to_target(effect, "theme", "Education")  # True
        applies_to_target(effect, "skill", "Python")     # True
    """
    # Only handle xp_multiplier effects
    if effect.get("type") != "xp_multiplier":
        return False

    scope = effect.get("scope", "")
    target = effect.get("target", "")

    # Global scope applies to everything
    if scope == "all":
        return True

    # Scope must match target type
    if scope != target_type:
        return False

    # "all" target within matching scope
    if target == "all":
        return True

    # Specific target match (case-insensitive)
    return target.lower() == target_id.lower()


def calculate_title_multipliers(
    db: Session,
    user_id: str,
    target_type: str,
    target_id: str,
) -> float:
    """
    Calculate combined XP multiplier from user's equipped titles.

    Queries user's equipped titles and stacks applicable multipliers
    multiplicatively.

    Args:
        db: SQLAlchemy session
        user_id: User ID to get titles for
        target_type: "theme" or "skill"
        target_id: Name/identifier of the target entity (for matching title effects)

    Returns:
        Combined multiplier (1.0 if no applicable titles)

    Example:
        Title 1: +10% Education XP (1.10)
        Title 2: +15% all themes (1.15)
        Title 3: +20% all XP (1.20)

        For Education theme: 1.10 × 1.15 × 1.20 = 1.518 (+51.8%)
    """
    # Get user's equipped titles
    user_titles = (
        db.query(UserTitle)
        .filter(
            UserTitle.user_id == user_id,
            UserTitle.is_equipped == True,  # noqa: E712
        )
        .all()
    )

    combined_multiplier = 1.0

    for user_title in user_titles:
        effect = user_title.title_template.effect

        if applies_to_target(effect, target_type, target_id):
            value = effect.get("value", 1.0)
            combined_multiplier *= value

    return combined_multiplier
