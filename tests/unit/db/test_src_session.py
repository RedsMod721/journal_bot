"""Unit tests for src.db.session."""

import shutil
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy.pool import StaticPool

from src.db import session


def _repo_tmp_dir() -> Path:
    base = session._REPO_ROOT / ".pytest_tmp"
    path = base / f"db-session-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def test_load_db_url_prefers_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///env-priority.db")
    monkeypatch.setenv("CONFIG_PATH", "/does/not/matter.yaml")

    assert session._load_db_url() == "sqlite:///env-priority.db"


def test_load_db_url_reads_postgres_from_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    tmp_dir = _repo_tmp_dir()
    try:
        config_path = tmp_dir / "dev.yaml"
        config_path.write_text(
            """
database:
  type: postgresql
  postgresql:
    username: app
    password: secret
    host: localhost
    port: 5433
    database: journal_bot
""".strip()
        )
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("CONFIG_PATH", str(config_path))

        url = session._load_db_url()
        assert url == "postgresql://app:secret@localhost:5433/journal_bot"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_load_db_url_reads_relative_sqlite_from_yaml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_dir = _repo_tmp_dir()
    try:
        config_path = tmp_dir / "dev.yaml"
        config_path.write_text(
            """
database:
  type: sqlite
  sqlite:
    path: data/db/custom.sqlite
""".strip()
        )
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("CONFIG_PATH", str(config_path))

        expected = f"sqlite:///{session._REPO_ROOT / 'data/db/custom.sqlite'}"
        assert session._load_db_url() == expected
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_load_db_url_falls_back_when_config_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CONFIG_PATH", "/path/that/does/not/exist.yaml")

    assert session._load_db_url() == f"sqlite:///{session._DEFAULT_SQLITE}"


def test_load_db_url_falls_back_when_yaml_parse_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_dir = _repo_tmp_dir()
    try:
        config_path = tmp_dir / "bad.yaml"
        config_path.write_text("database: [broken")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("CONFIG_PATH", str(config_path))

        assert session._load_db_url() == f"sqlite:///{session._DEFAULT_SQLITE}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_build_engine_uses_static_pool_for_in_memory_sqlite() -> None:
    engine = session._build_engine("sqlite:///:memory:")
    assert isinstance(engine.pool, StaticPool)


def test_build_engine_non_memory_sqlite_uses_default_pool() -> None:
    engine = session._build_engine("sqlite:////tmp/session-test.sqlite")
    assert not isinstance(engine.pool, StaticPool)


def test_build_engine_uses_pool_pre_ping_for_non_sqlite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}
    sentinel_engine = object()

    def fake_create_engine(url: str, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return sentinel_engine

    monkeypatch.setattr(session, "create_engine", fake_create_engine)

    engine = session._build_engine("postgresql://user:pw@localhost/db")

    assert engine is sentinel_engine
    assert captured["url"] == "postgresql://user:pw@localhost/db"
    assert captured["kwargs"]["pool_pre_ping"] is True
    assert "echo" in captured["kwargs"]


class _FakeSession:
    def __init__(self) -> None:
        self.commit_calls = 0
        self.rollback_calls = 0
        self.close_calls = 0

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1

    def close(self) -> None:
        self.close_calls += 1


def test_get_db_commits_and_closes_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeSession()
    monkeypatch.setattr(session, "SessionLocal", lambda: fake)

    gen = session.get_db()
    yielded = next(gen)
    assert yielded is fake
    with pytest.raises(StopIteration):
        next(gen)

    assert fake.commit_calls == 1
    assert fake.rollback_calls == 0
    assert fake.close_calls == 1


def test_get_db_rolls_back_and_closes_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeSession()
    monkeypatch.setattr(session, "SessionLocal", lambda: fake)

    gen = session.get_db()
    next(gen)
    with pytest.raises(RuntimeError):
        gen.throw(RuntimeError("boom"))

    assert fake.commit_calls == 0
    assert fake.rollback_calls == 1
    assert fake.close_calls == 1


def test_db_session_context_manager_commits_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeSession()
    monkeypatch.setattr(session, "SessionLocal", lambda: fake)

    with session.db_session() as db:
        assert db is fake

    assert fake.commit_calls == 1
    assert fake.rollback_calls == 0
    assert fake.close_calls == 1


def test_db_session_context_manager_rolls_back_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeSession()
    monkeypatch.setattr(session, "SessionLocal", lambda: fake)

    with pytest.raises(ValueError):
        with session.db_session():
            raise ValueError("fail")

    assert fake.commit_calls == 0
    assert fake.rollback_calls == 1
    assert fake.close_calls == 1


def test_init_db_creates_parent_dir_for_sqlite_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_dir = _repo_tmp_dir()
    try:
        sqlite_path = tmp_dir / "nested" / "db.sqlite"
        create_all = MagicMock()
        monkeypatch.setattr(session, "DATABASE_URL", f"sqlite:///{sqlite_path}")
        monkeypatch.setattr(session.Base.metadata, "create_all", create_all)

        session.init_db()

        assert sqlite_path.parent.exists()
        create_all.assert_called_once_with(bind=session.engine)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_drop_db_calls_drop_all(monkeypatch: pytest.MonkeyPatch) -> None:
    drop_all = MagicMock()
    monkeypatch.setattr(session.Base.metadata, "drop_all", drop_all)

    session.drop_db()

    drop_all.assert_called_once_with(bind=session.engine)


def test_check_connection_returns_true_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, _stmt) -> None:
            return None

    class _Engine:
        def connect(self):
            return _Conn()

    monkeypatch.setattr(session, "engine", _Engine())

    assert session.check_connection() is True


def test_check_connection_returns_false_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Engine:
        def connect(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(session, "engine", _Engine())

    assert session.check_connection() is False


def test_enforce_sqlite_fks_executes_pragma() -> None:
    cursor = MagicMock()
    dbapi_connection = MagicMock()
    dbapi_connection.cursor.return_value = cursor

    session._enforce_sqlite_fks(dbapi_connection, None)

    cursor.execute.assert_called_once_with("PRAGMA foreign_keys=ON")
    cursor.close.assert_called_once()


def test_enforce_sqlite_fks_swallows_backend_errors() -> None:
    dbapi_connection = MagicMock()
    dbapi_connection.cursor.side_effect = RuntimeError("not sqlite")

    # Should not raise.
    session._enforce_sqlite_fks(dbapi_connection, None)


def test_schema_status_reports_ready_when_current_revision_matches_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session, "check_connection", lambda: True)
    monkeypatch.setattr(session, "get_current_schema_revision", lambda: "mb76")
    monkeypatch.setattr(session, "get_head_schema_revision", lambda: "mb76")
    monkeypatch.setattr(
        session, "check_runtime_schema_integrity", lambda: {"ok": True, "missing": []}
    )

    status = session.schema_status()

    assert status["connected"] is True
    assert status["current_revision"] == "mb76"
    assert status["head_revision"] == "mb76"
    assert status["ready"] is True
    assert status["trigger_integrity"] == {"ok": True, "missing": []}
    assert status["runtime_schema_integrity"] == {"ok": True, "missing": []}


def test_schema_status_reports_not_ready_when_revision_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session, "check_connection", lambda: True)
    monkeypatch.setattr(session, "get_current_schema_revision", lambda: None)
    monkeypatch.setattr(session, "get_head_schema_revision", lambda: "mb76")
    monkeypatch.setattr(
        session, "check_runtime_schema_integrity", lambda: {"ok": True, "missing": []}
    )

    status = session.schema_status()

    assert status["connected"] is True
    assert status["current_revision"] is None
    assert status["head_revision"] == "mb76"
    assert status["ready"] is False


def test_schema_status_reports_not_ready_when_runtime_integrity_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session, "check_connection", lambda: True)
    monkeypatch.setattr(session, "get_current_schema_revision", lambda: "mb76")
    monkeypatch.setattr(session, "get_head_schema_revision", lambda: "mb76")
    monkeypatch.setattr(
        session,
        "check_runtime_schema_integrity",
        lambda: {"ok": False, "missing": ["story_arcs.event_name"]},
    )

    status = session.schema_status()

    assert status["connected"] is True
    assert status["ready"] is False
    assert status["runtime_schema_integrity"] == {
        "ok": False,
        "missing": ["story_arcs.event_name"],
    }


def test_assert_schema_ready_passes_when_db_is_at_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        session,
        "schema_status",
        lambda: {
            "connected": True,
            "current_revision": "mb76",
            "head_revision": "mb76",
            "ready": True,
            "trigger_integrity": {"ok": True, "missing": []},
            "runtime_schema_integrity": {"ok": True, "missing": []},
        },
    )

    session.assert_schema_ready()


def test_assert_schema_ready_raises_when_schema_uninitialized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        session,
        "schema_status",
        lambda: {
            "connected": True,
            "current_revision": None,
            "head_revision": "mb76",
            "ready": False,
            "runtime_schema_integrity": {"ok": True, "missing": []},
        },
    )

    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        session.assert_schema_ready()


def test_assert_schema_ready_raises_when_schema_is_behind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        session,
        "schema_status",
        lambda: {
            "connected": True,
            "current_revision": "mb75",
            "head_revision": "mb76",
            "ready": False,
            "runtime_schema_integrity": {"ok": True, "missing": []},
        },
    )

    with pytest.raises(RuntimeError, match="Current revision: mb75. Head revision: mb76"):
        session.assert_schema_ready()


def test_assert_schema_ready_raises_when_runtime_schema_is_drifted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        session,
        "schema_status",
        lambda: {
            "connected": True,
            "current_revision": "mb76",
            "head_revision": "mb76",
            "ready": False,
            "trigger_integrity": {"ok": True, "missing": []},
            "runtime_schema_integrity": {
                "ok": False,
                "missing": ["story_arcs.event_name", "arc_triggers.confidence_score"],
            },
        },
    )

    with pytest.raises(RuntimeError, match="runtime-critical columns or indexes are missing"):
        session.assert_schema_ready()
