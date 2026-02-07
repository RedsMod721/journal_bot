"""
CRUD operations for Title models.

This module provides database operations for both Title models:

TitleTemplate (Global Bank):
- Create, read title templates
- Query by name or category

UserTitle (User Instances):
- Award titles to users
- Equip/unequip titles
- Query user's titles

All functions take a SQLAlchemy Session as the first argument
and return model instances or None for not-found cases.
"""
from sqlalchemy.orm import Session

from app.models.title import TitleTemplate, UserTitle
from app.schemas.title import TitleTemplateCreate, UserTitleCreate


# =============================================================================
# TITLE TEMPLATE CRUD (Global Bank)
# =============================================================================


def create_title_template(db: Session, title: TitleTemplateCreate) -> TitleTemplate:
    """
    Create a new title template in the database.

    Args:
        db: Database session
        title: TitleTemplateCreate schema with title definition

    Returns:
        TitleTemplate: The created title template instance

    Example:
        template_data = TitleTemplateCreate(
            name="Early Riser",
            description_template="{user_name} wakes before the sun",
            effect={"type": "xp_multiplier", "value": 1.05},
            rank="C"
        )
        template = create_title_template(db, template_data)
    """
    db_template = TitleTemplate(
        name=title.name,
        description_template=title.description_template,
        effect=title.effect,
        rank=title.rank,
        unlock_condition=title.unlock_condition,
        category=title.category,
        is_hidden=title.is_hidden,
    )
    db.add(db_template)
    db.commit()
    db.refresh(db_template)
    return db_template


def get_title_template(db: Session, template_id: str) -> TitleTemplate | None:
    """
    Retrieve a title template by its ID.

    Args:
        db: Database session
        template_id: The UUID string of the title template

    Returns:
        TitleTemplate: The title template instance if found
        None: If no template exists with that ID
    """
    return db.query(TitleTemplate).filter(TitleTemplate.id == template_id).first()


def get_title_template_by_name(db: Session, name: str) -> TitleTemplate | None:
    """
    Retrieve a title template by its name.

    Args:
        db: Database session
        name: The name of the title template

    Returns:
        TitleTemplate: The title template instance if found
        None: If no template exists with that name
    """
    return db.query(TitleTemplate).filter(TitleTemplate.name == name).first()


def get_all_title_templates(db: Session) -> list[TitleTemplate]:
    """
    Retrieve all title templates.

    Args:
        db: Database session

    Returns:
        list[TitleTemplate]: List of all title template instances
    """
    return db.query(TitleTemplate).all()


def get_title_templates_by_category(db: Session, category: str) -> list[TitleTemplate]:
    """
    Retrieve all title templates in a category.

    Args:
        db: Database session
        category: The category to filter by

    Returns:
        list[TitleTemplate]: List of title templates in the category
    """
    return db.query(TitleTemplate).filter(TitleTemplate.category == category).all()


# =============================================================================
# USER TITLE CRUD (User Instances)
# =============================================================================


def award_title_to_user(db: Session, user_title: UserTitleCreate) -> UserTitle:
    """
    Award a title to a user.

    Creates a UserTitle instance linking the user to a title template.
    The acquired_at timestamp is set automatically.

    Args:
        db: Database session
        user_title: UserTitleCreate schema with user_id and title_template_id

    Returns:
        UserTitle: The created user title instance

    Example:
        award_data = UserTitleCreate(
            user_id="987fcdeb-...",
            title_template_id="123e4567-...",
            personalized_description="Sebastian wakes before the sun"
        )
        user_title = award_title_to_user(db, award_data)
    """
    db_user_title = UserTitle(
        user_id=user_title.user_id,
        title_template_id=user_title.title_template_id,
        is_equipped=user_title.is_equipped,
        personalized_description=user_title.personalized_description,
        expires_at=user_title.expires_at,
    )
    db.add(db_user_title)
    db.commit()
    db.refresh(db_user_title)
    return db_user_title


def get_user_title(db: Session, user_title_id: str) -> UserTitle | None:
    """
    Retrieve a user title by its ID.

    Args:
        db: Database session
        user_title_id: The UUID string of the user title

    Returns:
        UserTitle: The user title instance if found
        None: If no user title exists with that ID
    """
    return db.query(UserTitle).filter(UserTitle.id == user_title_id).first()


def get_user_titles(
    db: Session, user_id: str, equipped_only: bool = False
) -> list[UserTitle]:
    """
    Retrieve all titles belonging to a user.

    Args:
        db: Database session
        user_id: The UUID string of the user
        equipped_only: If True, only return equipped titles

    Returns:
        list[UserTitle]: List of user title instances
    """
    query = db.query(UserTitle).filter(UserTitle.user_id == user_id)

    if equipped_only:
        query = query.filter(UserTitle.is_equipped == True)

    return query.all()


def equip_title(db: Session, user_title_id: str) -> UserTitle | None:
    """
    Equip a user title (activate its effects).

    Args:
        db: Database session
        user_title_id: The UUID string of the user title

    Returns:
        UserTitle: The updated user title instance
        None: If no user title exists with that ID
    """
    db_user_title = db.query(UserTitle).filter(UserTitle.id == user_title_id).first()
    if db_user_title is None:
        return None

    db_user_title.is_equipped = True
    db.commit()
    db.refresh(db_user_title)
    return db_user_title


def unequip_title(db: Session, user_title_id: str) -> UserTitle | None:
    """
    Unequip a user title (deactivate its effects).

    Args:
        db: Database session
        user_title_id: The UUID string of the user title

    Returns:
        UserTitle: The updated user title instance
        None: If no user title exists with that ID
    """
    db_user_title = db.query(UserTitle).filter(UserTitle.id == user_title_id).first()
    if db_user_title is None:
        return None

    db_user_title.is_equipped = False
    db.commit()
    db.refresh(db_user_title)
    return db_user_title


def remove_user_title(db: Session, user_title_id: str) -> bool:
    """
    Remove a title from a user.

    Args:
        db: Database session
        user_title_id: The UUID string of the user title to remove

    Returns:
        True: If the user title was successfully removed
        False: If no user title exists with that ID
    """
    db_user_title = db.query(UserTitle).filter(UserTitle.id == user_title_id).first()
    if db_user_title is None:
        return False

    db.delete(db_user_title)
    db.commit()
    return True
