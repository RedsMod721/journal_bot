"""Tests for quest matcher orchestration."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.quests.matcher import QuestMatcher
from app.models.journal_entry import JournalEntry
from app.models.mission_quest import MissionQuestTemplate, UserMissionQuest


def _make_event_bus():
    return SimpleNamespace(emit=MagicMock())


def _create_template(
    db_session,
    completion_condition: dict,
    autostart: bool = False,
    autostart_condition: dict | None = None,
) -> MissionQuestTemplate:
    template = MissionQuestTemplate(
        name="Template",
        completion_condition=completion_condition,
        autostart=autostart,
        autostart_condition=autostart_condition,
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)
    return template


def _create_user_quest(
    db_session,
    user_id: str,
    template: MissionQuestTemplate,
    progress: int = 0,
    status: str = "in_progress",
    autostart: bool = False,
) -> UserMissionQuest:
    quest = UserMissionQuest(
        user_id=user_id,
        template_id=template.id,
        name="Quest",
        completion_progress=progress,
        status=status,
        autostart=autostart,
    )
    db_session.add(quest)
    db_session.commit()
    db_session.refresh(quest)
    return quest


def _create_entry(
    db_session,
    user_id: str,
    content: str,
    ai_categories: dict | None = None,
) -> JournalEntry:
    entry = JournalEntry(
        user_id=user_id,
        content=content,
        ai_categories=ai_categories or {},
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)
    return entry


def test_quest_matcher_processes_active_quests(db_session, sample_user) -> None:
    event_bus = _make_event_bus()
    matcher = QuestMatcher(event_bus)
    template = _create_template(db_session, {"type": "yes_no"})
    _create_user_quest(db_session, sample_user.id, template=template)
    entry = _create_entry(db_session, sample_user.id, "Did it.", {"manual_completion": True})

    updated = matcher.match_journal_entry(db_session, entry)

    assert len(updated) == 1


def test_quest_matcher_skips_completed_quests(db_session, sample_user) -> None:
    event_bus = _make_event_bus()
    matcher = QuestMatcher(event_bus)
    template = _create_template(db_session, {"type": "yes_no"})
    _create_user_quest(db_session, sample_user.id, template=template, status="completed")
    entry = _create_entry(db_session, sample_user.id, "Did it.", {"manual_completion": True})

    updated = matcher.match_journal_entry(db_session, entry)

    assert updated == []
    assert event_bus.emit.call_count == 0


def test_quest_matcher_updates_quest_progress(db_session, sample_user) -> None:
    event_bus = _make_event_bus()
    matcher = QuestMatcher(event_bus)
    template = _create_template(
        db_session,
        {"type": "accumulation", "target": 100, "unit": "minutes"},
    )
    quest = _create_user_quest(db_session, sample_user.id, template=template)
    entry = _create_entry(db_session, sample_user.id, "Worked out for 20 minutes.")

    updated = matcher.match_journal_entry(db_session, entry)

    assert len(updated) == 1
    assert quest.completion_progress == 20


def test_quest_matcher_completes_quest_on_threshold(db_session, sample_user) -> None:
    event_bus = _make_event_bus()
    matcher = QuestMatcher(event_bus)
    template = _create_template(
        db_session,
        {"type": "accumulation", "target": 20, "unit": "minutes"},
    )
    quest = _create_user_quest(db_session, sample_user.id, template=template)
    quest.completion_target = 100
    db_session.commit()
    entry = _create_entry(db_session, sample_user.id, "Worked out for 20 minutes.")

    updated = matcher.match_journal_entry(db_session, entry)

    assert len(updated) == 1
    assert quest.status == "completed"
    assert quest.completion_progress == 100


def test_quest_matcher_emits_progress_updated_event(db_session, sample_user) -> None:
    event_bus = _make_event_bus()
    matcher = QuestMatcher(event_bus)
    template = _create_template(
        db_session,
        {"type": "accumulation", "target": 100, "unit": "minutes"},
    )
    _create_user_quest(db_session, sample_user.id, template=template)
    entry = _create_entry(db_session, sample_user.id, "Worked out for 10 minutes.")

    matcher.match_journal_entry(db_session, entry)

    assert event_bus.emit.call_count == 1
    args, _ = event_bus.emit.call_args
    assert args[0] == "quest.progress_updated"


def test_quest_matcher_emits_quest_completed_event(db_session, sample_user) -> None:
    event_bus = _make_event_bus()
    matcher = QuestMatcher(event_bus)
    template = _create_template(db_session, {"type": "yes_no"})
    _create_user_quest(db_session, sample_user.id, template=template)
    entry = _create_entry(db_session, sample_user.id, "Did it.", {"manual_completion": True})

    matcher.match_journal_entry(db_session, entry)

    assert event_bus.emit.call_count == 1
    args, _ = event_bus.emit.call_args
    assert args[0] == "quest.completed"


def test_quest_matcher_autostart_ignores_unmatched_entry(db_session, sample_user) -> None:
    event_bus = _make_event_bus()
    matcher = QuestMatcher(event_bus)
    template = _create_template(
        db_session,
        {"type": "accumulation", "target": 100, "unit": "minutes"},
    )
    quest = _create_user_quest(
        db_session,
        sample_user.id,
        template=template,
        status="not_started",
        autostart=True,
    )
    entry = _create_entry(db_session, sample_user.id, "Rested today.")

    updated = matcher.match_journal_entry(db_session, entry)

    assert updated == []
    assert quest.status == "not_started"


def test_quest_matcher_autostart_starts_on_progress(db_session, sample_user) -> None:
    event_bus = _make_event_bus()
    matcher = QuestMatcher(event_bus)
    template = _create_template(
        db_session,
        {"type": "accumulation", "target": 100, "unit": "minutes"},
        autostart=True,
        autostart_condition={"type": "accumulation", "unit": "minutes"},
    )
    quest = _create_user_quest(
        db_session,
        sample_user.id,
        template=template,
        status="not_started",
        autostart=True,
    )
    entry = _create_entry(db_session, sample_user.id, "Worked out for 15 minutes.")

    updated = matcher.match_journal_entry(db_session, entry)

    assert len(updated) == 1
    assert quest.status == "in_progress"
    assert quest.completion_progress == 15


def test_quest_matcher_autostart_can_complete_immediately(db_session, sample_user) -> None:
    event_bus = _make_event_bus()
    matcher = QuestMatcher(event_bus)
    template = _create_template(
        db_session,
        {"type": "yes_no"},
        autostart=True,
        autostart_condition={"type": "yes_no"},
    )
    quest = _create_user_quest(
        db_session,
        sample_user.id,
        template=template,
        status="not_started",
        autostart=True,
    )
    entry = _create_entry(db_session, sample_user.id, "Did it.", {"manual_completion": True})

    updated = matcher.match_journal_entry(db_session, entry)

    assert len(updated) == 1
    assert quest.status == "completed"


def test_quest_matcher_autostart_without_condition_does_not_start(
    db_session, sample_user
) -> None:
    event_bus = _make_event_bus()
    matcher = QuestMatcher(event_bus)
    template = _create_template(
        db_session,
        {"type": "accumulation", "target": 100, "unit": "minutes"},
        autostart=True,
    )
    quest = _create_user_quest(
        db_session,
        sample_user.id,
        template=template,
        status="not_started",
        autostart=True,
    )
    entry = _create_entry(db_session, sample_user.id, "Worked out for 10 minutes.")

    updated = matcher.match_journal_entry(db_session, entry)

    assert updated == []
    assert quest.status == "not_started"


def test_quest_matcher_autostart_condition_blocks_start(db_session, sample_user) -> None:
    event_bus = _make_event_bus()
    matcher = QuestMatcher(event_bus)
    template = _create_template(
        db_session,
        {"type": "accumulation", "target": 100, "unit": "minutes"},
        autostart=True,
        autostart_condition={"type": "keyword_match", "keywords": ["gym"]},
    )
    quest = _create_user_quest(
        db_session,
        sample_user.id,
        template=template,
        status="not_started",
        autostart=True,
    )
    entry = _create_entry(db_session, sample_user.id, "Rested today.")

    updated = matcher.match_journal_entry(db_session, entry)

    assert updated == []
    assert quest.status == "not_started"


def test_quest_matcher_autostart_condition_allows_start(db_session, sample_user) -> None:
    event_bus = _make_event_bus()
    matcher = QuestMatcher(event_bus)
    template = _create_template(
        db_session,
        {"type": "accumulation", "target": 100, "unit": "minutes"},
        autostart=True,
        autostart_condition={"type": "keyword_match", "keywords": ["gym"]},
    )
    quest = _create_user_quest(
        db_session,
        sample_user.id,
        template=template,
        status="not_started",
        autostart=True,
    )
    entry = _create_entry(db_session, sample_user.id, "Gym for 10 minutes.")

    updated = matcher.match_journal_entry(db_session, entry)

    assert len(updated) == 1
    assert quest.status == "in_progress"
    assert quest.completion_progress == 10


def test_quest_matcher_handles_multiple_quests_in_one_entry(db_session, sample_user) -> None:
    event_bus = _make_event_bus()
    matcher = QuestMatcher(event_bus)
    accumulation_template = _create_template(
        db_session,
        {"type": "accumulation", "target": 100, "unit": "minutes"},
    )
    keyword_template = _create_template(
        db_session,
        {"type": "keyword_match", "keywords": ["gym"]},
    )
    _create_user_quest(db_session, sample_user.id, template=accumulation_template)
    _create_user_quest(db_session, sample_user.id, template=keyword_template)
    entry = _create_entry(db_session, sample_user.id, "Gym for 30 minutes.")

    updated = matcher.match_journal_entry(db_session, entry)

    assert len(updated) == 2


def test_quest_matcher_prepare_context_extracts_amounts(db_session, sample_user) -> None:
    matcher = QuestMatcher(_make_event_bus())
    entry = _create_entry(db_session, sample_user.id, "Walked 45 minutes 3 times.")

    context = matcher._prepare_context(entry)

    assert context["detected_minutes"] == 45
    assert context["detected_count"] == 3


def test_quest_matcher_detect_amounts_finds_minutes() -> None:
    matcher = QuestMatcher(_make_event_bus())

    amounts = matcher._detect_amounts("Worked out for 45 minutes.")

    assert amounts["minutes"] == 45


def test_quest_matcher_detect_amounts_finds_counts() -> None:
    matcher = QuestMatcher(_make_event_bus())

    amounts = matcher._detect_amounts("Did it 3 times.")

    assert amounts["count"] == 3


def test_quest_matcher_no_active_quests_returns_empty(db_session, sample_user) -> None:
    matcher = QuestMatcher(_make_event_bus())
    entry = _create_entry(db_session, sample_user.id, "Nothing special.")

    updated = matcher.match_journal_entry(db_session, entry)

    assert updated == []


def test_quest_matcher_handles_checker_exception_gracefully(db_session, sample_user) -> None:
    event_bus = _make_event_bus()
    matcher = QuestMatcher(event_bus)
    template = _create_template(db_session, {"type": "yes_no"})
    _create_user_quest(db_session, sample_user.id, template=template)
    entry = _create_entry(db_session, sample_user.id, "Did it.", {"manual_completion": True})

    class FailingChecker:
        def check_completion(self, db, user_quest, context):
            raise RuntimeError("boom")

    matcher._checkers["yes_no"] = FailingChecker()

    updated = matcher.match_journal_entry(db_session, entry)

    assert updated == []
    assert event_bus.emit.call_count == 0


def test_frequency_checker_ignores_invalid_occurrence_dates(db_session, sample_user) -> None:
    event_bus = _make_event_bus()
    matcher = QuestMatcher(event_bus)
    template = _create_template(
        db_session,
        {"type": "frequency", "target": 3, "period": "week"},
    )
    quest = _create_user_quest(db_session, sample_user.id, template=template)
    quest.quest_metadata = {"occurrences": [{"entry_id": "legacy", "date": "bad-date"}]}
    db_session.commit()

    entry = _create_entry(db_session, sample_user.id, "Workout session.")
    updated = matcher.match_journal_entry(db_session, entry)

    assert len(updated) == 1
    assert quest.completion_progress == 33
    occurrences = quest.quest_metadata.get("occurrences", [])
    assert len(occurrences) == 1
    assert occurrences[0]["entry_id"] == entry.id


def test_frequency_checker_deduplicates_same_entry_id(db_session, sample_user) -> None:
    event_bus = _make_event_bus()
    matcher = QuestMatcher(event_bus)
    template = _create_template(
        db_session,
        {"type": "frequency", "target": 3, "period": "week"},
    )
    quest = _create_user_quest(db_session, sample_user.id, template=template)
    entry = _create_entry(db_session, sample_user.id, "Gym day.")

    first_update = matcher.match_journal_entry(db_session, entry)
    second_update = matcher.match_journal_entry(db_session, entry)

    assert len(first_update) == 1
    assert second_update == []
    assert quest.completion_progress == 33
    occurrences = quest.quest_metadata.get("occurrences", [])
    assert len(occurrences) == 1
    assert occurrences[0]["entry_id"] == entry.id
