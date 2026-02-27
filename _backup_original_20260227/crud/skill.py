"""
CRUD operations for Skill model.

This module provides database operations for Skill management:
- Create: Create new skills with parent skill and theme support
- Read: Get skills by ID, user, theme, or with child skills
- Update: Modify skill attributes, add practice time, and add XP
- Delete: Remove skills (cascades to child skills)

All functions take a SQLAlchemy Session as the first argument
and return Skill model instances or None for not-found cases.
"""
from sqlalchemy.orm import Session, joinedload

from app.models.skill import Skill
from app.schemas.skill import SkillCreate, SkillUpdate


def create_skill(db: Session, skill: SkillCreate) -> Skill:
    """
    Create a new skill in the database.

    Args:
        db: Database session
        skill: SkillCreate schema with name, user_id, and optional fields

    Returns:
        Skill: The created skill instance

    Example:
        skill_data = SkillCreate(
            name="Python Programming",
            user_id="123e4567-...",
            theme_id="987fcdeb-...",
            difficulty="Hard"
        )
        skill = create_skill(db, skill_data)
    """
    db_skill = Skill(
        user_id=skill.user_id,
        theme_id=skill.theme_id,
        name=skill.name,
        description=skill.description,
        difficulty=skill.difficulty,
        parent_skill_id=skill.parent_skill_id,
    )
    db.add(db_skill)
    db.commit()
    db.refresh(db_skill)
    return db_skill


def get_skill(db: Session, skill_id: str) -> Skill | None:
    """
    Retrieve a skill by its ID.

    Args:
        db: Database session
        skill_id: The UUID string of the skill

    Returns:
        Skill: The skill instance if found
        None: If no skill exists with that ID
    """
    return db.query(Skill).filter(Skill.id == skill_id).first()


def get_user_skills(db: Session, user_id: str) -> list[Skill]:
    """
    Retrieve all skills belonging to a user.

    Args:
        db: Database session
        user_id: The UUID string of the user

    Returns:
        list[Skill]: List of skill instances owned by the user
    """
    return db.query(Skill).filter(Skill.user_id == user_id).all()


def get_theme_skills(db: Session, theme_id: str) -> list[Skill]:
    """
    Retrieve all skills belonging to a theme.

    Args:
        db: Database session
        theme_id: The UUID string of the theme

    Returns:
        list[Skill]: List of skill instances in the theme
    """
    return db.query(Skill).filter(Skill.theme_id == theme_id).all()


def get_skill_with_children(db: Session, skill_id: str) -> Skill | None:
    """
    Retrieve a skill with its child skills eagerly loaded.

    Uses joinedload to fetch child_skills relationship in a single query,
    avoiding N+1 query issues when accessing child skills.

    Args:
        db: Database session
        skill_id: The UUID string of the skill

    Returns:
        Skill: The skill instance with child_skills loaded if found
        None: If no skill exists with that ID
    """
    return (
        db.query(Skill)
        .options(joinedload(Skill.child_skills))
        .filter(Skill.id == skill_id)
        .first()
    )


def add_practice_time(
    db: Session, skill_id: str, minutes: int, multiplier: float = 1.0
) -> Skill | None:
    """
    Add practice time to a skill and award XP.

    Calls the skill's add_practice_time() method which:
    - Increments total practice time
    - Awards XP based on: minutes * 0.5 * multiplier
    - Handles automatic level-ups

    Args:
        db: Database session
        skill_id: The UUID string of the skill
        minutes: Number of minutes practiced (must be non-negative)
        multiplier: Optional XP multiplier (default 1.0)

    Returns:
        Skill: The updated skill instance
        None: If no skill exists with that ID

    Example:
        skill = add_practice_time(db, skill_id, 30, multiplier=2.0)
        # Adds 30 minutes and awards 30 XP (30 * 0.5 * 2.0)
    """
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if skill is None:
        return None

    skill.add_practice_time(minutes, multiplier)
    db.commit()
    db.refresh(skill)
    return skill


def add_xp_to_skill(db: Session, skill_id: str, xp_amount: float) -> Skill | None:
    """
    Add XP to a skill and handle level-ups.

    Calls the skill's add_xp() method which handles:
    - XP accumulation
    - Automatic level-up when threshold is reached
    - Exponential scaling of next level requirements
    - Rank updates based on level

    Args:
        db: Database session
        skill_id: The UUID string of the skill
        xp_amount: Amount of XP to add (must be non-negative)

    Returns:
        Skill: The updated skill instance
        None: If no skill exists with that ID

    Example:
        skill = add_xp_to_skill(db, skill_id, 100.0)
        # skill.level may have increased if XP threshold was crossed
    """
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if skill is None:
        return None

    skill.add_xp(xp_amount)
    db.commit()
    db.refresh(skill)
    return skill


def update_skill(db: Session, skill_id: str, skill_update: SkillUpdate) -> Skill | None:
    """
    Update a skill's attributes.

    Only updates fields that are explicitly set in the update schema.
    Uses exclude_unset=True to allow partial updates.

    Args:
        db: Database session
        skill_id: The UUID string of the skill to update
        skill_update: SkillUpdate schema with fields to update

    Returns:
        Skill: The updated skill instance
        None: If no skill exists with that ID

    Example:
        update = SkillUpdate(name="Advanced Python", difficulty="Expert")
        skill = update_skill(db, skill_id, update)
    """
    db_skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if db_skill is None:
        return None

    update_data = skill_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_skill, field, value)

    db.commit()
    db.refresh(db_skill)
    return db_skill


def delete_skill(db: Session, skill_id: str) -> bool:
    """
    Delete a skill and its child skills.

    Due to the self-referential relationship with cascade delete,
    deleting a parent skill will also delete all child skills.

    Args:
        db: Database session
        skill_id: The UUID string of the skill to delete

    Returns:
        True: If the skill was successfully deleted
        False: If no skill exists with that ID
    """
    db_skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if db_skill is None:
        return False

    db.delete(db_skill)
    db.commit()
    return True
