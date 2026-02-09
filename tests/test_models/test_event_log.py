"""
Tests for EventLog model.
"""
from datetime import datetime, timedelta

from app.models.event_log import EventLog
from app.models.user import User


class TestEventLogModel:
    def test_event_log_creation(self, db_session, sample_user):
        event_log = EventLog(
            user_id=sample_user.id,
            event_type="xp.awarded",
            event_payload={"amount": 50, "source": "journal"},
        )
        db_session.add(event_log)
        db_session.commit()

        assert event_log.id is not None
        assert len(event_log.id) == 36
        assert event_log.user_id == sample_user.id
        assert event_log.event_type == "xp.awarded"
        assert event_log.event_payload["amount"] == 50
        assert event_log.created_at is not None

    def test_event_log_defaults(self, db_session, sample_user):
        event_log = EventLog(
            user_id=sample_user.id,
            event_type="journal_entry.created",
        )
        db_session.add(event_log)
        db_session.commit()

        assert event_log.event_payload == {}
        assert event_log.created_at > datetime.utcnow() - timedelta(minutes=1)

    def test_event_log_user_relationship(self, db_session, sample_user):
        event_log = EventLog(
            user_id=sample_user.id,
            event_type="quest.completed",
            event_payload={"quest_id": "q-1"},
        )
        db_session.add(event_log)
        db_session.commit()
        db_session.refresh(sample_user)

        assert event_log.user is not None
        assert event_log.user.id == sample_user.id
        assert event_log in sample_user.event_logs

    def test_event_log_query_by_type(self, db_session, sample_user):
        log_a = EventLog(
            user_id=sample_user.id,
            event_type="xp.awarded",
            event_payload={"amount": 10},
        )
        log_b = EventLog(
            user_id=sample_user.id,
            event_type="title.unlocked",
            event_payload={"title_id": "t-1"},
        )
        db_session.add_all([log_a, log_b])
        db_session.commit()

        results = (
            db_session.query(EventLog)
            .filter(EventLog.event_type == "xp.awarded")
            .all()
        )

        assert len(results) == 1
        assert results[0].id == log_a.id

    def test_event_log_query_by_user_and_type(self, db_session, sample_user, fake):
        other_user = User(username=fake.user_name(), email=fake.email())
        db_session.add(other_user)
        db_session.commit()

        log_user = EventLog(
            user_id=sample_user.id,
            event_type="xp.awarded",
            event_payload={"amount": 5},
        )
        log_other = EventLog(
            user_id=other_user.id,
            event_type="xp.awarded",
            event_payload={"amount": 7},
        )
        db_session.add_all([log_user, log_other])
        db_session.commit()

        results = (
            db_session.query(EventLog)
            .filter(EventLog.user_id == sample_user.id)
            .filter(EventLog.event_type == "xp.awarded")
            .all()
        )

        assert len(results) == 1
        assert results[0].id == log_user.id

    def test_event_log_repr_includes_type_and_user_prefix(self, db_session, sample_user):
        event_log = EventLog(
            user_id=sample_user.id,
            event_type="xp.awarded",
        )
        db_session.add(event_log)
        db_session.commit()

        representation = repr(event_log)

        assert "<EventLog xp.awarded user=" in representation
        assert sample_user.id[:8] in representation
