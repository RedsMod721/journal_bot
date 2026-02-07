"""
CRUD tests for UserStats.
"""
from datetime import datetime

from app.crud.user_stats import (
    adjust_stat,
    create_user_stats,
    get_user_stats,
    reset_user_stats,
    update_user_stats,
)
from app.schemas.user_stats import UserStatsCreate, UserStatsUpdate


class TestUserStatsCRUD:
    def test_create_user_stats(self, db_session, sample_user):
        stats = create_user_stats(
            db_session,
            UserStatsCreate(user_id=sample_user.id),
        )

        assert stats.user_id == sample_user.id
        assert stats.hp == 100
        assert stats.mp == 100
        assert stats.mental_health == 70
        assert stats.physical_health == 70
        assert stats.relationship_quality == 50
        assert stats.socialization_level == 50

    def test_get_user_stats_by_user_id(self, db_session, sample_user):
        created = create_user_stats(
            db_session,
            UserStatsCreate(user_id=sample_user.id),
        )

        fetched = get_user_stats(db_session, sample_user.id)

        assert fetched is not None
        assert fetched.id == created.id

    def test_update_user_stats_partial(self, db_session, sample_user):
        created = create_user_stats(
            db_session,
            UserStatsCreate(user_id=sample_user.id),
        )
        created.updated_at = datetime(2000, 1, 1)
        db_session.commit()

        updated = update_user_stats(
            db_session,
            sample_user.id,
            UserStatsUpdate(hp=85, mental_health=60),
        )

        assert updated is not None
        assert updated.hp == 85
        assert updated.mental_health == 60
        assert updated.mp == 100
        assert updated.updated_at > datetime(2000, 1, 1)

    def test_adjust_stat_increases_value(self, db_session, sample_user):
        create_user_stats(
            db_session,
            UserStatsCreate(user_id=sample_user.id),
        )

        updated = adjust_stat(db_session, sample_user.id, "mental_health", 5)

        assert updated is not None
        assert updated.mental_health == 75

    def test_adjust_stat_decreases_value(self, db_session, sample_user):
        create_user_stats(
            db_session,
            UserStatsCreate(user_id=sample_user.id),
        )

        updated = adjust_stat(db_session, sample_user.id, "mp", -10)

        assert updated is not None
        assert updated.mp == 90

    def test_adjust_stat_clamps_to_max_100(self, db_session, sample_user):
        create_user_stats(
            db_session,
            UserStatsCreate(user_id=sample_user.id),
        )

        updated = adjust_stat(db_session, sample_user.id, "hp", 10)

        assert updated is not None
        assert updated.hp == 100

    def test_adjust_stat_clamps_to_min_0(self, db_session, sample_user):
        create_user_stats(
            db_session,
            UserStatsCreate(user_id=sample_user.id),
        )

        updated = adjust_stat(db_session, sample_user.id, "relationship_quality", -100)

        assert updated is not None
        assert updated.relationship_quality == 0

    def test_reset_user_stats_to_defaults(self, db_session, sample_user):
        create_user_stats(
            db_session,
            UserStatsCreate(user_id=sample_user.id),
        )
        adjust_stat(db_session, sample_user.id, "hp", -40)
        adjust_stat(db_session, sample_user.id, "socialization_level", 20)

        reset = reset_user_stats(db_session, sample_user.id)

        assert reset is not None
        assert reset.hp == 100
        assert reset.mp == 100
        assert reset.mental_health == 70
        assert reset.physical_health == 70
        assert reset.relationship_quality == 50
        assert reset.socialization_level == 50
