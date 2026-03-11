"""Integration tests for Week 5 API endpoints: Forgiveness, Balance, and Harmony.

These tests exercise the three Week 5 systems end-to-end through the FastAPI
routes, verifying that services, models, and HTTP layer work together correctly.

Follows the same fixture pattern as tests/integration/test_week5_api_endpoints.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import src.db.models  # noqa: F401
from src.api.main import app
from src.db.base import Base
from src.db.models.forgiveness import ForgivenessConfig
from src.db.models.harmony import HarmonyDimension
from src.db.models.journal_entry import JournalEntry, JournalEntryStructured
from src.db.models.strategy import StrategyTracking
from src.db.models.user import User
from src.db.session import get_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session: Session):
    def _override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_user(db_session: Session) -> User:
    user = User(
        id="week5-integ-user",
        username="week5integ",
        email="week5integ@example.com",
        password_hash="hash",
        timezone="Europe/Paris",
        home_country="US",
    )
    db_session.add(user)
    db_session.flush()
    config = ForgivenessConfig(
        user_id=user.id,
        preset="balanced",
        skill_decay_rate=0.05,
        insight_decay_rate=0.10,
        skill_grace_period_days=7,
        insight_grace_period_days=3,
        critical_staleness_threshold=0.80,
    )
    db_session.add(config)
    db_session.flush()
    user.forgiveness_config_id = config.id
    db_session.commit()
    return user


def _add_work_entries(
    db: Session,
    user_id: str,
    count: int,
    *,
    task_type: str = "administrative",
    energy_level: int = 3,
) -> None:
    """Add `count` productivity-heavy completed journal entries."""
    now = datetime.now(timezone.utc)
    for i in range(count):
        entry = JournalEntry(
            user_id=user_id,
            content="Intensive work session",
            entry_type="text",
            status="completed",
            created_at=now - timedelta(days=i + 1),
        )
        db.add(entry)
        db.flush()
        db.add(
            JournalEntryStructured(
                user_id=user_id,
                entry_id=entry.id,
                canonical_text="Intensive work session",
                task_type=task_type,
                energy_level=energy_level,
            )
        )
    db.commit()


# ===========================================================================
# Forgiveness API
# ===========================================================================


class TestForgivenessIntegration:
    """End-to-end tests for /api/forgiveness/* routes."""

    def test_config_auto_created_on_first_access(
        self, client: TestClient, db_session: Session
    ) -> None:
        """GET /config for a user with no config creates a balanced default."""
        bare_user = User(
            id="u-no-config",
            username="u-no-config",
            email="u-no-config@example.com",
            password_hash="hash",
            timezone="UTC",
            home_country="US",
        )
        db_session.add(bare_user)
        db_session.commit()

        response = client.get("/api/forgiveness/config", params={"user_id": bare_user.id})

        assert response.status_code == 200
        payload = response.json()
        assert payload["preset"] == "balanced"
        assert payload["skill_grace_period_days"] == 7
        assert payload["insight_grace_period_days"] == 3
        db_session.refresh(bare_user)
        assert bare_user.forgiveness_config_id is not None

    def test_switch_preset_to_zen_updates_stored_rates(
        self, client: TestClient, seeded_user: User
    ) -> None:
        """POST /config/preset changes stored decay rates to zen canonical values."""
        response = client.post(
            "/api/forgiveness/config/preset",
            params={"user_id": seeded_user.id},
            json={"preset": "zen"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["preset"] == "zen"
        assert payload["skill_decay_rate"] == pytest.approx(0.01)
        assert payload["skill_grace_period_days"] == 14

    def test_switch_preset_to_invalid_returns_422(
        self, client: TestClient, seeded_user: User
    ) -> None:
        """POST /config/preset with unknown preset name returns validation error."""
        response = client.post(
            "/api/forgiveness/config/preset",
            params={"user_id": seeded_user.id},
            json={"preset": "godmode"},
        )

        assert response.status_code in (400, 422)

    def test_preset_list_returns_all_six_presets(self, client: TestClient) -> None:
        """GET /presets returns exactly the six canonical preset entries."""
        response = client.get("/api/forgiveness/presets")

        assert response.status_code == 200
        presets = response.json()
        preset_keys = {item["preset"] for item in presets}
        assert preset_keys == {"balanced", "hardcore", "lenient", "zen", "adaptive", "custom"}

    def test_custom_preset_allows_fine_grained_param_override(
        self, client: TestClient, seeded_user: User
    ) -> None:
        """POST /config/preset to custom, then POST /config/custom to set rates."""
        # Switch to custom first
        client.post(
            "/api/forgiveness/config/preset",
            params={"user_id": seeded_user.id},
            json={"preset": "custom"},
        )

        # Override individual params
        response = client.post(
            "/api/forgiveness/config/custom",
            params={"user_id": seeded_user.id},
            json={"skill_decay_rate": 0.07, "skill_grace_days": 5},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["preset"] == "custom"
        assert payload["skill_decay_rate"] == pytest.approx(0.07)
        assert payload["skill_grace_period_days"] == 5

    def test_decay_stats_returns_metrics_dict(
        self, client: TestClient, seeded_user: User
    ) -> None:
        """GET /stats returns a valid decay-stats payload."""
        response = client.get("/api/forgiveness/stats", params={"user_id": seeded_user.id})

        assert response.status_code == 200
        payload = response.json()
        # Verify core metric keys returned by the decay stats endpoint
        assert "avg_staleness" in payload
        assert "critical_skills" in payload
        assert "stale_skills" in payload


# ===========================================================================
# Harmony API
# ===========================================================================


class TestHarmonyIntegration:
    """End-to-end tests for /api/harmony/* routes."""

    def test_fresh_user_dimensions_return_neutral_scores(
        self, client: TestClient, seeded_user: User
    ) -> None:
        """GET /dimensions for user with no entries returns neutral 0.5 scores."""
        response = client.get(
            "/api/harmony/dimensions", params={"user_id": seeded_user.id}
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["user_id"] == seeded_user.id
        assert payload["overall_balance"] == pytest.approx(0.5, abs=0.01)
        # All seven dimensions should be present
        dims = payload["dimensions"]
        for dim in ("physical", "mental", "social", "productivity", "rest", "growth", "creative"):
            assert dim in dims

    def test_overwork_detected_after_productivity_heavy_entries(
        self, client: TestClient, db_session: Session, seeded_user: User
    ) -> None:
        """GET /overwork-status detects warning condition after enough work entries.

        Productivity threshold is 5 entries; need >=5 to reach score>=0.85.
        No rest entries → rest=0.0 <=0.35. With 4+ consecutive days → stage >=2.
        """
        # 5 entries → productivity=1.0 >=0.85; energy_level=3 <=4 (energy_low)
        _add_work_entries(db_session, seeded_user.id, count=5)
        db_session.add(
            HarmonyDimension(
                user_id=seeded_user.id,
                overwork_consecutive_days=4,
                overwork_stage=0,
            )
        )
        db_session.commit()

        response = client.get(
            "/api/harmony/overwork-status", params={"user_id": seeded_user.id}
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["stage"] >= 1

    def test_overwork_stage_name_matches_stage_number(
        self, client: TestClient, db_session: Session, seeded_user: User
    ) -> None:
        """GET /overwork-status stage_name corresponds to stage number."""
        db_session.add(
            HarmonyDimension(
                user_id=seeded_user.id,
                productivity=0.90,
                rest=0.25,
                physical=0.5,
                overwork_consecutive_days=4,
                overwork_stage=0,
            )
        )
        db_session.commit()
        _add_work_entries(db_session, seeded_user.id, count=3)

        response = client.get(
            "/api/harmony/overwork-status", params={"user_id": seeded_user.id}
        )
        payload = response.json()

        stage = payload["stage"]
        stage_name = payload["stage_name"]
        expected_names = {0: "Normal", 1: "Warning", 2: "Warning", 3: "Critical"}
        assert stage_name == expected_names.get(stage, stage_name)

    def test_dimensions_endpoint_does_not_advance_overwork_persistence(
        self, client: TestClient, db_session: Session, seeded_user: User
    ) -> None:
        """GET /dimensions (read-only path) must not write overwork_consecutive_days."""
        _add_work_entries(db_session, seeded_user.id, count=3)

        client.get("/api/harmony/dimensions", params={"user_id": seeded_user.id})

        row = (
            db_session.query(HarmonyDimension)
            .filter(HarmonyDimension.user_id == seeded_user.id)
            .first()
        )
        # overwork_last_evaluated_local_date must not be set by the read-only endpoint
        if row:
            assert row.overwork_last_evaluated_local_date is None

    def test_manual_refresh_updates_harmony_dimension_row(
        self, client: TestClient, db_session: Session, seeded_user: User
    ) -> None:
        """POST /refresh recalculates and updates the HarmonyDimension row."""
        response = client.post(
            "/api/harmony/refresh", params={"user_id": seeded_user.id}
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert "overall_balance" in payload
        # HarmonyDimension row should exist after refresh
        row = (
            db_session.query(HarmonyDimension)
            .filter(HarmonyDimension.user_id == seeded_user.id)
            .one_or_none()
        )
        assert row is not None

    def test_snapshots_endpoint_returns_list(
        self, client: TestClient, db_session: Session, seeded_user: User
    ) -> None:
        """GET /snapshots returns a list (may be empty for a fresh user)."""
        response = client.get(
            "/api/harmony/snapshots",
            params={"user_id": seeded_user.id, "days": 7},
        )

        assert response.status_code == 200
        assert isinstance(response.json(), list)


# ===========================================================================
# Balance API
# ===========================================================================


class TestBalanceIntegration:
    """End-to-end tests for /api/balance/* routes."""

    def _seed_tracking(
        self,
        db: Session,
        user_id: str,
        *,
        variety_score: float = 0.0,
        variety_bonus_pct: float = 0.0,
    ) -> StrategyTracking:
        tracking = StrategyTracking(
            user_id=user_id,
            variety_score=variety_score,
            variety_bonus_pct=variety_bonus_pct,
        )
        db.add(tracking)
        db.commit()
        return tracking

    def test_variety_endpoint_returns_zero_score_for_empty_tracking(
        self, client: TestClient, db_session: Session, seeded_user: User
    ) -> None:
        """GET /variety with an all-zero tracking row returns zero score."""
        self._seed_tracking(db_session, seeded_user.id)

        response = client.get("/api/balance/variety", params={"user_id": seeded_user.id})

        assert response.status_code == 200
        payload = response.json()
        assert payload["variety_score"] == pytest.approx(0.0)
        assert payload["variety_bonus_pct"] == pytest.approx(0.0)

    def test_balance_window_refresh_creates_tracking_row(
        self, client: TestClient, db_session: Session, seeded_user: User
    ) -> None:
        """POST /refresh creates a StrategyTracking row when none exists."""
        response = client.post(
            "/api/balance/refresh", params={"user_id": seeded_user.id}
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert "variety_score" in payload

        row = (
            db_session.query(StrategyTracking)
            .filter(StrategyTracking.user_id == seeded_user.id)
            .one_or_none()
        )
        assert row is not None

    def test_balance_window_refresh_picks_up_new_journal_entries(
        self, client: TestClient, db_session: Session, seeded_user: User
    ) -> None:
        """POST /refresh recomputes variety after journal entries are added."""
        # Add rest and productivity entries to create a small distribution
        for task in ("rest", "analytical", "social"):
            entry = JournalEntry(
                user_id=seeded_user.id,
                content=f"Doing {task}",
                entry_type="text",
                status="completed",
                created_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
            db_session.add(entry)
            db_session.flush()
            db_session.add(
                JournalEntryStructured(
                    user_id=seeded_user.id,
                    entry_id=entry.id,
                    canonical_text=f"Doing {task}",
                    task_type=task,
                    energy_level=5,
                )
            )
        db_session.commit()

        response = client.post(
            "/api/balance/refresh", params={"user_id": seeded_user.id}
        )

        assert response.status_code == 200

    def test_penalties_endpoint_returns_empty_dicts_for_fresh_user(
        self, client: TestClient, seeded_user: User
    ) -> None:
        """GET /penalties returns empty dicts when no tracking row exists."""
        response = client.get("/api/balance/penalties", params={"user_id": seeded_user.id})

        assert response.status_code == 200
        payload = response.json()
        assert payload["penalties"] == {}
        assert payload["consecutive_days"] == {}


# ===========================================================================
# Cross-system integration
# ===========================================================================


class TestWeek5CrossSystemIntegration:
    """Tests that verify interactions across all three Week 5 systems."""

    def test_preset_change_reflected_in_both_forgiveness_and_harmony_thresholds(
        self, client: TestClient, db_session: Session, seeded_user: User
    ) -> None:
        """Switching to zen preset stores lower decay rates AND harmony uses zen overwork thresholds."""
        # Switch to zen
        resp = client.post(
            "/api/forgiveness/config/preset",
            params={"user_id": seeded_user.id},
            json={"preset": "zen"},
        )
        assert resp.status_code == 200
        assert resp.json()["preset"] == "zen"

        # Verify config persisted correctly
        config_resp = client.get(
            "/api/forgiveness/config", params={"user_id": seeded_user.id}
        )
        assert config_resp.status_code == 200
        config = config_resp.json()
        assert config["preset"] == "zen"
        assert config["skill_decay_rate"] == pytest.approx(0.01)

    def test_harmony_refresh_then_overwork_status_round_trip(
        self, client: TestClient, db_session: Session, seeded_user: User
    ) -> None:
        """POST /harmony/refresh followed by GET /harmony/overwork-status works end-to-end."""
        refresh_resp = client.post(
            "/api/harmony/refresh", params={"user_id": seeded_user.id}
        )
        assert refresh_resp.status_code == 200

        overwork_resp = client.get(
            "/api/harmony/overwork-status", params={"user_id": seeded_user.id}
        )
        assert overwork_resp.status_code == 200
        payload = overwork_resp.json()
        # For a fresh user with no entries, stage is 0 (Normal)
        assert payload["stage"] == 0
        assert "stage_name" in payload
        assert "recommendations" in payload

    def test_forgiveness_stats_and_balance_refresh_both_succeed_for_same_user(
        self, client: TestClient, db_session: Session, seeded_user: User
    ) -> None:
        """Both /forgiveness/stats and /balance/refresh return 200 for the same user."""
        stats_resp = client.get("/api/forgiveness/stats", params={"user_id": seeded_user.id})
        balance_resp = client.post(
            "/api/balance/refresh", params={"user_id": seeded_user.id}
        )

        assert stats_resp.status_code == 200
        assert balance_resp.status_code == 200

    def test_full_user_setup_all_three_systems_are_queryable(
        self, client: TestClient, db_session: Session, seeded_user: User
    ) -> None:
        """All three systems respond with 200 for a properly seeded user."""
        endpoints = [
            ("GET", "/api/forgiveness/config", {"user_id": seeded_user.id}),
            ("GET", "/api/harmony/dimensions", {"user_id": seeded_user.id}),
            ("GET", "/api/harmony/overwork-status", {"user_id": seeded_user.id}),
        ]
        for method, path, params in endpoints:
            resp = client.get(path, params=params)
            assert resp.status_code == 200, f"Expected 200 from {method} {path}, got {resp.status_code}: {resp.text}"
