"""Week-long and month-long user journey simulations for integration coverage."""

from datetime import datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from freezegun import freeze_time

from app.core.config_loader import get_config
from app.core.events import EventBus
from app.core.orchestrator import JournalProcessingOrchestrator
from app.models.journal_entry import JournalEntry
from app.models.mission_quest import MissionQuestTemplate, UserMissionQuest
from app.models.skill import Skill
from app.models.theme import Theme
from app.models.title import TitleTemplate, UserTitle
from app.models.user import User
from app.models.user_stats import UserStats


def _new_user(db_session, prefix: str = "journey") -> User:
    uid = uuid4().hex[:8]
    user = User(
        username=f"{prefix}_{uid}",
        email=f"{prefix}_{uid}@example.com",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _capture_events(event_bus: EventBus, event_types: list[str]) -> list[tuple[str, dict]]:
    captured: list[tuple[str, dict]] = []

    for event_type in event_types:
        event_bus.subscribe(
            event_type,
            lambda payload, name=event_type: captured.append((name, payload)),
        )

    return captured


def _process_entry(
    db_session,
    orchestrator: JournalProcessingOrchestrator,
    *,
    user_id: str,
    content: str,
    created_at: datetime,
    categories: dict,
    entry_type: str = "text",
) -> tuple[JournalEntry, dict]:
    entry = JournalEntry(
        user_id=user_id,
        content=content,
        entry_type=entry_type,
        created_at=created_at,
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)

    with freeze_time(created_at):
        with patch.object(orchestrator, "_stub_categorize", return_value=categories):
            result = orchestrator.process_entry(db_session, entry)

    db_session.refresh(entry)
    return entry, result


def _add_xp_breakdown_source(theme: Theme, source: str, amount: float) -> None:
    metadata = dict(theme.theme_metadata or {})
    breakdown = dict(metadata.get("xp_breakdown", {}))
    breakdown[source] = breakdown.get(source, 0.0) + amount
    theme.theme_metadata = {**metadata, "xp_breakdown": breakdown}


def _apply_pending_quest_rewards_to_theme(
    db_session,
    theme: Theme,
    event_log: list[tuple[str, dict]],
    applied_quest_ids: set[str],
) -> None:
    for name, payload in event_log:
        if name != "quest.completed":
            continue

        quest_id = payload["quest_id"]
        if quest_id in applied_quest_ids:
            continue

        reward_xp = float(payload.get("reward_xp", 0))
        if reward_xp > 0:
            theme.add_xp(reward_xp)
            _add_xp_breakdown_source(theme, "quest", reward_xp)

        applied_quest_ids.add(quest_id)

    db_session.commit()
    db_session.refresh(theme)


def _add_practice_with_breakdown(skill: Skill, minutes: int) -> float:
    xp_amount = minutes * 0.5
    skill.add_practice_time(minutes)
    metadata = dict(skill.skill_metadata or {})
    breakdown = dict(metadata.get("xp_breakdown", {}))
    breakdown["practice"] = breakdown.get("practice", 0.0) + xp_amount
    skill.skill_metadata = {**metadata, "xp_breakdown": breakdown}
    return xp_amount


def test_journey_new_user_first_week(db_session):
    """Simulate a new user's first week with the app."""
    user = _new_user(db_session, "new_week")
    theme = Theme(user_id=user.id, name="Education")
    skill = Skill(user_id=user.id, theme_id=theme.id, name="Python")
    db_session.add_all([theme, skill])

    first_step = TitleTemplate(
        name="First Step",
        rank="D",
        effect={},
        unlock_condition={"type": "journal_count", "value": 1},
    )
    week_warrior = TitleTemplate(
        name="Week Warrior",
        rank="C",
        effect={},
        unlock_condition={"type": "journal_streak", "value": 7},
    )
    quest_rookie = TitleTemplate(
        name="Quest Rookie",
        rank="D",
        effect={},
        unlock_condition={"type": "quest_completion_count", "value": 1},
    )
    db_session.add_all([first_step, week_warrior, quest_rookie])

    template = MissionQuestTemplate(
        name="Journal 3 times this week",
        completion_condition={"type": "frequency", "target": 3, "period": "week"},
        reward_xp=120,
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(theme)
    db_session.refresh(skill)
    db_session.refresh(template)

    quest = UserMissionQuest(
        user_id=user.id,
        template_id=template.id,
        name=template.name,
        status="in_progress",
    )
    db_session.add(quest)
    db_session.commit()

    event_bus = EventBus()
    event_log = _capture_events(
        event_bus,
        [
            "xp.awarded",
            "quest.progress_updated",
            "quest.completed",
            "title.unlocked",
        ],
    )
    orchestrator = JournalProcessingOrchestrator(event_bus, get_config())
    categories = {
        "themes": [{"id": theme.id, "name": theme.name}],
        "skills": [{"id": skill.id, "name": skill.name}],
        "sentiment": "positive",
    }
    applied_quest_ids: set[str] = set()

    start = datetime(2026, 1, 5, 9, 0, 0)

    # Day 1
    day1_entry, _ = _process_entry(
        db_session,
        orchestrator,
        user_id=user.id,
        content="Day 1: started journaling and studied Python.",
        created_at=start,
        categories=categories,
    )
    _apply_pending_quest_rewards_to_theme(db_session, theme, event_log, applied_quest_ids)
    assert day1_entry.processing_status == "completed"
    assert db_session.query(UserTitle).filter(UserTitle.user_id == user.id).count() >= 1

    # Day 2
    _process_entry(
        db_session,
        orchestrator,
        user_id=user.id,
        content="Day 2: another solid study session.",
        created_at=start + timedelta(days=1),
        categories=categories,
    )
    _apply_pending_quest_rewards_to_theme(db_session, theme, event_log, applied_quest_ids)
    db_session.refresh(quest)
    assert quest.completion_progress in (66, 67)

    # Day 3 missed (no entry), backfilled on day 4 to keep streak data intact.

    # Day 4-6 consistent journaling (+ day 3 backfill)
    for day_offset, content in [
        (2, "Backfill for day 3: kept momentum alive."),
        (3, "Day 4: deep work and learning."),
        (4, "Day 5: more consistency."),
        (5, "Day 6: still going."),
    ]:
        _process_entry(
            db_session,
            orchestrator,
            user_id=user.id,
            content=content,
            created_at=start + timedelta(days=day_offset),
            categories=categories,
        )
        _apply_pending_quest_rewards_to_theme(
            db_session, theme, event_log, applied_quest_ids
        )

    # Day 7
    _process_entry(
        db_session,
        orchestrator,
        user_id=user.id,
        content="Day 7: final check-in for the week.",
        created_at=start + timedelta(days=6),
        categories=categories,
    )
    _apply_pending_quest_rewards_to_theme(db_session, theme, event_log, applied_quest_ids)

    db_session.refresh(theme)
    db_session.refresh(skill)
    db_session.refresh(quest)

    titles = db_session.query(UserTitle).filter(UserTitle.user_id == user.id).all()
    assert 2 <= len(titles) <= 3, f"titles={len(titles)} events={event_log}"
    assert theme.level >= 1
    assert skill.level >= 1
    assert skill.rank == "Beginner"
    assert quest.status == "completed"
    assert (
        db_session.query(UserMissionQuest)
        .filter(UserMissionQuest.user_id == user.id, UserMissionQuest.status == "completed")
        .count()
        >= 1
    )
    assert "journal" in theme.theme_metadata.get("xp_breakdown", {})
    assert "quest" in theme.theme_metadata.get("xp_breakdown", {})
    assert (
        db_session.query(JournalEntry).filter(JournalEntry.user_id == user.id).count() == 7
    )


def test_journey_power_user_month(db_session):
    """Simulate power user over 30 days."""
    user = _new_user(db_session, "power_month")
    theme = Theme(user_id=user.id, name="Career")
    skill_a = Skill(user_id=user.id, theme_id=theme.id, name="Python")
    skill_b = Skill(user_id=user.id, theme_id=theme.id, name="Systems Design")
    stats = UserStats(user_id=user.id, karma=0, karma_breakdown={})
    db_session.add_all([theme, skill_a, skill_b, stats])

    # 18 title templates with progressive journal_count conditions.
    titles = [
        TitleTemplate(
            name=f"Power Badge {i}",
            rank="D",
            effect={},
            unlock_condition={"type": "journal_count", "value": i},
        )
        for i in range(1, 19)
    ]
    db_session.add_all(titles)

    # 10 yes/no quests for week 3 grinding.
    templates = [
        MissionQuestTemplate(
            name=f"Grind Quest {i}",
            completion_condition={"type": "yes_no"},
            reward_xp=200,
        )
        for i in range(1, 11)
    ]
    db_session.add_all(templates)
    db_session.commit()
    db_session.refresh(theme)
    db_session.refresh(skill_a)
    db_session.refresh(skill_b)

    for template in templates:
        db_session.add(
            UserMissionQuest(
                user_id=user.id,
                template_id=template.id,
                name=template.name,
                status="in_progress",
            )
        )
    db_session.commit()

    event_bus = EventBus()
    event_log = _capture_events(
        event_bus, ["quest.completed", "title.unlocked", "xp.awarded"]
    )
    orchestrator = JournalProcessingOrchestrator(event_bus, get_config())
    applied_quest_ids: set[str] = set()
    start = datetime(2026, 1, 1, 8, 0, 0)

    # Week 1: 5 entries.
    for day in range(5):
        _process_entry(
            db_session,
            orchestrator,
            user_id=user.id,
            content=f"Week1 day{day + 1} progress log.",
            created_at=start + timedelta(days=day),
            categories={
                "themes": [{"id": theme.id, "name": theme.name}],
                "skills": [],
                "sentiment": "positive",
            },
        )

    # Week 2: daily entries + heavy practice logging.
    for day in range(7):
        current_day = start + timedelta(days=7 + day)
        _process_entry(
            db_session,
            orchestrator,
            user_id=user.id,
            content=f"Week2 day{day + 1}: daily deep work.",
            created_at=current_day,
            categories={
                "themes": [{"id": theme.id, "name": theme.name}],
                "skills": [{"id": skill_a.id, "name": skill_a.name}],
                "sentiment": "positive",
            },
        )

        # Practice system integration is separate from journal XP pipeline.
        _add_practice_with_breakdown(skill_a, minutes=2_500_000)
        _add_practice_with_breakdown(skill_b, minutes=2_500_000)
        stats.karma += 3
        karma_breakdown = dict(stats.karma_breakdown or {})
        karma_breakdown["lectures"] = karma_breakdown.get("lectures", 0) + 3
        stats.karma_breakdown = karma_breakdown
        db_session.commit()

    # Week 3: quest grinding (10 quests).
    for day in range(7):
        current_day = start + timedelta(days=14 + day)
        _process_entry(
            db_session,
            orchestrator,
            user_id=user.id,
            content="Week3 grind day: manually completed many objectives.",
            created_at=current_day,
            categories={
                "themes": [{"id": theme.id, "name": theme.name}],
                "skills": [],
                "sentiment": "positive",
                "manual_completion": True,
            },
        )
        _apply_pending_quest_rewards_to_theme(
            db_session, theme, event_log, applied_quest_ids
        )

    # Week 4: title collector phase, still journaling.
    for day in range(11):
        current_day = start + timedelta(days=21 + day)
        _process_entry(
            db_session,
            orchestrator,
            user_id=user.id,
            content="Week4 collecting title milestones with consistency.",
            created_at=current_day,
            categories={
                "themes": [{"id": theme.id, "name": theme.name}],
                "skills": [],
                "sentiment": "positive",
            },
        )

    db_session.refresh(theme)
    db_session.refresh(skill_a)
    db_session.refresh(skill_b)
    db_session.refresh(stats)

    unlocked_titles = (
        db_session.query(UserTitle).filter(UserTitle.user_id == user.id).count()
    )
    assert theme.level >= 10
    assert skill_a.rank in {"Expert", "Master"}
    assert skill_b.rank in {"Expert", "Master"}
    assert unlocked_titles >= 15
    assert theme.theme_metadata.get("xp_breakdown", {}).get("journal", 0) > 0
    assert theme.theme_metadata.get("xp_breakdown", {}).get("quest", 0) > 0
    assert skill_a.skill_metadata.get("xp_breakdown", {}).get("practice", 0) > 0
    assert stats.karma > 0


def test_journey_inconsistent_user(db_session):
    """User journals sporadically."""
    user = _new_user(db_session, "sporadic")
    theme = Theme(user_id=user.id, name="Wellbeing")
    db_session.add(theme)

    week_warrior = TitleTemplate(
        name="Week Warrior",
        rank="C",
        effect={},
        unlock_condition={"type": "journal_streak", "value": 7},
    )
    negative_title = TitleTemplate(
        name="Rustbound",
        rank="E",
        effect={},
        unlock_condition={
            "type": "corrosion_level",
            "theme": "Wellbeing",
            "min_level": "Rusty",
        },
    )
    db_session.add_all([week_warrior, negative_title])
    db_session.commit()
    db_session.refresh(theme)

    event_bus = EventBus()
    orchestrator = JournalProcessingOrchestrator(event_bus, get_config())
    day_offsets = [0, 2, 6, 9, 14, 24, 29]
    start = datetime(2026, 2, 1, 8, 0, 0)

    previous_day = None
    for offset in day_offsets:
        current_day = start + timedelta(days=offset)
        _process_entry(
            db_session,
            orchestrator,
            user_id=user.id,
            content=f"Sporadic check-in on day offset {offset}.",
            created_at=current_day,
            categories={
                "themes": [{"id": theme.id, "name": theme.name}],
                "skills": [],
                "sentiment": "neutral",
            },
        )

        # Explicitly simulate corrosion progression for long inactivity gaps.
        if previous_day is not None and (current_day - previous_day).days >= 7:
            if theme.corrosion_level == "Fresh":
                theme.corrosion_level = "Familiar"
            elif theme.corrosion_level == "Familiar":
                theme.corrosion_level = "Dusty"
            db_session.commit()
        previous_day = current_day

    db_session.refresh(theme)
    user_titles = db_session.query(UserTitle).filter(UserTitle.user_id == user.id).all()
    title_names = {
        db_session.get(TitleTemplate, user_title.title_template_id).name
        for user_title in user_titles
    }

    assert "Week Warrior" not in title_names
    assert theme.corrosion_level in {"Familiar", "Dusty"}
    assert "Rustbound" not in title_names
    assert theme.level >= 1 or theme.xp > 0


def test_journey_skill_progression_to_master(db_session):
    """Focus on one skill to Master rank."""
    user = _new_user(db_session, "skill_master")
    theme = Theme(user_id=user.id, name="Engineering")
    skill = Skill(user_id=user.id, theme_id=theme.id, name="Python Mastery")
    db_session.add_all([theme, skill])

    milestone_titles = [
        TitleTemplate(
            name="Amateur Spark",
            rank="D",
            effect={},
            unlock_condition={"type": "skill_rank", "rank": "Amateur"},
        ),
        TitleTemplate(
            name="Expert Forge",
            rank="B",
            effect={},
            unlock_condition={"type": "skill_rank", "rank": "Expert"},
        ),
        TitleTemplate(
            name="Master Architect",
            rank="S",
            effect={},
            unlock_condition={"type": "skill_rank", "rank": "Master"},
        ),
    ]
    db_session.add_all(milestone_titles)

    quest_templates = [
        MissionQuestTemplate(
            name="Skill Minutes",
            completion_condition={"type": "accumulation", "target": 600, "unit": "minutes"},
            reward_xp=80,
        ),
        MissionQuestTemplate(
            name="Skill Keywords",
            completion_condition={"type": "keyword_match", "keywords": ["python"]},
            reward_xp=80,
        ),
    ]
    db_session.add_all(quest_templates)
    db_session.commit()
    db_session.refresh(theme)
    db_session.refresh(skill)

    for template in quest_templates:
        db_session.add(
            UserMissionQuest(
                user_id=user.id,
                template_id=template.id,
                name=template.name,
                status="in_progress",
            )
        )
    db_session.commit()

    event_bus = EventBus()
    event_log = _capture_events(event_bus, ["quest.completed", "title.unlocked"])
    orchestrator = JournalProcessingOrchestrator(event_bus, get_config())
    applied_quest_ids: set[str] = set()
    start = datetime(2026, 3, 1, 7, 0, 0)

    for day in range(30):
        current_day = start + timedelta(days=day)

        # Practice XP dominates this journey.
        _add_practice_with_breakdown(skill, minutes=40_000_000)
        db_session.commit()

        _process_entry(
            db_session,
            orchestrator,
            user_id=user.id,
            content="Focused python practice for 120 minutes.",
            created_at=current_day,
            categories={
                "themes": [{"id": theme.id, "name": theme.name}],
                "skills": [{"id": skill.id, "name": skill.name}],
                "sentiment": "positive",
            },
        )
        _apply_pending_quest_rewards_to_theme(
            db_session, theme, event_log, applied_quest_ids
        )

    db_session.refresh(skill)
    assert skill.level >= 80
    assert skill.rank == "Master"

    owned_titles = (
        db_session.query(UserTitle).filter(UserTitle.user_id == user.id).all()
    )
    owned_title_names = {
        db_session.get(TitleTemplate, user_title.title_template_id).name
        for user_title in owned_titles
    }
    assert {"Amateur Spark", "Expert Forge", "Master Architect"}.issubset(owned_title_names)

    breakdown = skill.skill_metadata.get("xp_breakdown", {})
    assert breakdown.get("practice", 0) > breakdown.get("journal", 0)


def test_journey_quest_completionist(db_session):
    """User focuses on completing quests."""
    user = _new_user(db_session, "quester")
    theme = Theme(user_id=user.id, name="Execution")
    skill = Skill(user_id=user.id, theme_id=theme.id, name="Consistency")
    db_session.add_all([theme, skill])

    quest_master = TitleTemplate(
        name="Quest Master",
        rank="A",
        effect={},
        unlock_condition={"type": "quest_completion_count", "value": 20},
    )
    db_session.add(quest_master)
    db_session.commit()
    db_session.refresh(theme)
    db_session.refresh(skill)

    templates: list[MissionQuestTemplate] = []
    for i in range(5):
        templates.append(
            MissionQuestTemplate(
                name=f"YesNo {i}",
                completion_condition={"type": "yes_no"},
                reward_xp=50,
            )
        )
        templates.append(
            MissionQuestTemplate(
                name=f"Accum {i}",
                completion_condition={"type": "accumulation", "target": 30, "unit": "minutes"},
                reward_xp=40,
            )
        )
        templates.append(
            MissionQuestTemplate(
                name=f"Frequency {i}",
                completion_condition={"type": "frequency", "target": 3, "period": "week"},
                reward_xp=30,
            )
        )
        templates.append(
            MissionQuestTemplate(
                name=f"Keyword {i}",
                completion_condition={"type": "keyword_match", "keywords": [f"keyword{i}"]},
                reward_xp=20,
            )
        )
    db_session.add_all(templates)
    db_session.commit()

    for template in templates:
        db_session.add(
            UserMissionQuest(
                user_id=user.id,
                template_id=template.id,
                name=template.name,
                status="in_progress",
            )
        )
    db_session.commit()

    event_bus = EventBus()
    event_log = _capture_events(event_bus, ["quest.completed", "title.unlocked"])
    orchestrator = JournalProcessingOrchestrator(event_bus, get_config())
    applied_quest_ids: set[str] = set()
    start = datetime(2026, 4, 6, 10, 0, 0)

    keyword_blob = " ".join([f"keyword{i}" for i in range(5)])

    # Three entries complete yes/no, keyword, accumulation, and frequency quests.
    for day in range(3):
        _process_entry(
            db_session,
            orchestrator,
            user_id=user.id,
            content=f"Completed tasks for 10 minutes {keyword_blob}",
            created_at=start + timedelta(days=day),
            categories={
                "themes": [{"id": theme.id, "name": theme.name}],
                "skills": [{"id": skill.id, "name": skill.name}],
                "sentiment": "positive",
                "manual_completion": True,
            },
        )
        _apply_pending_quest_rewards_to_theme(
            db_session, theme, event_log, applied_quest_ids
        )

    completed_quests = (
        db_session.query(UserMissionQuest)
        .filter(UserMissionQuest.user_id == user.id, UserMissionQuest.status == "completed")
        .all()
    )
    assert len(completed_quests) == 20

    # Autoflush is disabled in tests, so run one explicit unlock check after quest commits.
    orchestrator.title_awarder.check_user_unlocks(db_session, user.id)

    title_names = {
        db_session.get(TitleTemplate, user_title.title_template_id).name
        for user_title in db_session.query(UserTitle).filter(UserTitle.user_id == user.id).all()
    }
    assert "Quest Master" in title_names

    quest_xp = theme.theme_metadata.get("xp_breakdown", {}).get("quest", 0)
    journal_xp = theme.theme_metadata.get("xp_breakdown", {}).get("journal", 0)
    assert quest_xp > journal_xp
