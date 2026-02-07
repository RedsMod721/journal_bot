"""
CRUD operations for MissionQuestTemplate and UserMissionQuest models.

This module provides database operations for Mission/Quest management:
- MQTemplate: Create and read operations for global templates
- UserMQ: Full CRUD operations for user-specific quest instances

All functions take a SQLAlchemy Session as the first argument
and return model instances or None for not-found cases.
"""
from datetime import datetime

from sqlalchemy.orm import Session, joinedload

from app.models.mission_quest import MissionQuestTemplate, UserMissionQuest
from app.schemas.mission_quest import MQTemplateCreate, UserMQCreate, UserMQUpdate


# =============================================================================
# MISSION/QUEST TEMPLATE CRUD
# =============================================================================


def create_mq_template(db: Session, mq: MQTemplateCreate) -> MissionQuestTemplate:
    """
    Create a new MissionQuestTemplate in the database.

    Args:
        db: Database session
        mq: MQTemplateCreate schema with template data

    Returns:
        MissionQuestTemplate: The created template instance

    Example:
        template_data = MQTemplateCreate(
            name="Morning Meditation",
            description_template="Complete a meditation session",
            type="daily",
            structure="single_action",
            completion_condition={"type": "yes_no"},
            reward_xp=25
        )
        template = create_mq_template(db, template_data)
    """
    db_template = MissionQuestTemplate(
        name=mq.name,
        description_template=mq.description_template,
        type=mq.type,
        structure=mq.structure,
        completion_condition=mq.completion_condition,
        reward_xp=mq.reward_xp,
        reward_coins=mq.reward_coins,
        difficulty=mq.difficulty,
        category=mq.category,
    )
    db.add(db_template)
    db.commit()
    db.refresh(db_template)
    return db_template


def get_mq_template(db: Session, template_id: str) -> MissionQuestTemplate | None:
    """
    Retrieve a MissionQuestTemplate by its ID.

    Args:
        db: Database session
        template_id: The UUID string of the template

    Returns:
        MissionQuestTemplate: The template instance if found
        None: If no template exists with that ID
    """
    return (
        db.query(MissionQuestTemplate)
        .filter(MissionQuestTemplate.id == template_id)
        .first()
    )


def get_mq_templates_by_type(db: Session, quest_type: str) -> list[MissionQuestTemplate]:
    """
    Retrieve all MissionQuestTemplates of a specific type.

    Args:
        db: Database session
        quest_type: The type to filter by (daily, timed, periodic, etc.)

    Returns:
        list[MissionQuestTemplate]: List of templates matching the type
    """
    return (
        db.query(MissionQuestTemplate)
        .filter(MissionQuestTemplate.type == quest_type)
        .all()
    )


# =============================================================================
# USER MISSION/QUEST CRUD
# =============================================================================


def create_user_mq(db: Session, user_mq: UserMQCreate) -> UserMissionQuest:
    """
    Create a new UserMissionQuest in the database.

    Args:
        db: Database session
        user_mq: UserMQCreate schema with quest data

    Returns:
        UserMissionQuest: The created quest instance

    Example:
        quest_data = UserMQCreate(
            name="Complete morning routine",
            user_id="123e4567-...",
            template_id="987fcdeb-...",
            status="not_started"
        )
        quest = create_user_mq(db, quest_data)
    """
    db_user_mq = UserMissionQuest(
        user_id=user_mq.user_id,
        template_id=user_mq.template_id,
        parent_mq_id=user_mq.parent_mq_id,
        name=user_mq.name,
        personalized_description=user_mq.personalized_description,
        status=user_mq.status,
        completion_target=user_mq.completion_target,
        deadline=user_mq.deadline,
    )
    db.add(db_user_mq)
    db.commit()
    db.refresh(db_user_mq)
    return db_user_mq


def get_user_mq(db: Session, user_mq_id: str) -> UserMissionQuest | None:
    """
    Retrieve a UserMissionQuest by its ID.

    Args:
        db: Database session
        user_mq_id: The UUID string of the quest

    Returns:
        UserMissionQuest: The quest instance if found
        None: If no quest exists with that ID
    """
    return (
        db.query(UserMissionQuest)
        .filter(UserMissionQuest.id == user_mq_id)
        .first()
    )


def get_user_mqs(
    db: Session, user_id: str, status: str | None = None
) -> list[UserMissionQuest]:
    """
    Retrieve all UserMissionQuests for a user, optionally filtered by status.

    Args:
        db: Database session
        user_id: The UUID string of the user
        status: Optional status filter (not_started, in_progress, completed, failed)

    Returns:
        list[UserMissionQuest]: List of quest instances for the user
    """
    query = db.query(UserMissionQuest).filter(UserMissionQuest.user_id == user_id)

    if status is not None:
        query = query.filter(UserMissionQuest.status == status)

    return query.all()


def get_user_mq_with_children(db: Session, user_mq_id: str) -> UserMissionQuest | None:
    """
    Retrieve a UserMissionQuest with its child quests eagerly loaded.

    Uses joinedload to fetch child_mq relationship in a single query,
    avoiding N+1 query issues when accessing child quests.

    Args:
        db: Database session
        user_mq_id: The UUID string of the quest

    Returns:
        UserMissionQuest: The quest instance with child_mq loaded if found
        None: If no quest exists with that ID
    """
    return (
        db.query(UserMissionQuest)
        .options(joinedload(UserMissionQuest.child_mq))
        .filter(UserMissionQuest.id == user_mq_id)
        .first()
    )


def update_mq_progress(
    db: Session, user_mq_id: str, progress: int
) -> UserMissionQuest | None:
    """
    Update the completion progress of a UserMissionQuest.

    Sets the completion_progress to the specified value. Does not
    automatically complete the quest - use complete_user_mq for that.

    Args:
        db: Database session
        user_mq_id: The UUID string of the quest
        progress: New progress value

    Returns:
        UserMissionQuest: The updated quest instance
        None: If no quest exists with that ID

    Example:
        quest = update_mq_progress(db, quest_id, 75)
    """
    db_user_mq = (
        db.query(UserMissionQuest)
        .filter(UserMissionQuest.id == user_mq_id)
        .first()
    )
    if db_user_mq is None:
        return None

    db_user_mq.completion_progress = progress
    db.commit()
    db.refresh(db_user_mq)
    return db_user_mq


def complete_user_mq(db: Session, user_mq_id: str) -> UserMissionQuest | None:
    """
    Mark a UserMissionQuest as completed.

    Sets status to "completed" and completed_at to current time.

    Args:
        db: Database session
        user_mq_id: The UUID string of the quest

    Returns:
        UserMissionQuest: The completed quest instance
        None: If no quest exists with that ID
    """
    db_user_mq = (
        db.query(UserMissionQuest)
        .filter(UserMissionQuest.id == user_mq_id)
        .first()
    )
    if db_user_mq is None:
        return None

    db_user_mq.status = "completed"
    db_user_mq.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(db_user_mq)
    return db_user_mq


def update_user_mq(
    db: Session, user_mq_id: str, mq_update: UserMQUpdate
) -> UserMissionQuest | None:
    """
    Update a UserMissionQuest's attributes.

    Only updates fields that are explicitly set in the update schema.
    Uses exclude_unset=True to allow partial updates.

    Args:
        db: Database session
        user_mq_id: The UUID string of the quest to update
        mq_update: UserMQUpdate schema with fields to update

    Returns:
        UserMissionQuest: The updated quest instance
        None: If no quest exists with that ID

    Example:
        update = UserMQUpdate(status="in_progress", completion_progress=50)
        quest = update_user_mq(db, quest_id, update)
    """
    db_user_mq = (
        db.query(UserMissionQuest)
        .filter(UserMissionQuest.id == user_mq_id)
        .first()
    )
    if db_user_mq is None:
        return None

    update_data = mq_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_user_mq, field, value)

    db.commit()
    db.refresh(db_user_mq)
    return db_user_mq


def delete_user_mq(db: Session, user_mq_id: str) -> bool:
    """
    Delete a UserMissionQuest and its child quests.

    Due to the self-referential relationship with cascade delete,
    deleting a parent quest will also delete all child quests.

    Args:
        db: Database session
        user_mq_id: The UUID string of the quest to delete

    Returns:
        True: If the quest was successfully deleted
        False: If no quest exists with that ID
    """
    db_user_mq = (
        db.query(UserMissionQuest)
        .filter(UserMissionQuest.id == user_mq_id)
        .first()
    )
    if db_user_mq is None:
        return False

    db.delete(db_user_mq)
    db.commit()
    return True
