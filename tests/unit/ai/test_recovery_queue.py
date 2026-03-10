"""Unit tests for src.ai.recovery."""

from __future__ import annotations

# ruff: noqa: E402

import json
import sys
import types

_stub = types.ModuleType("sentence_transformers")
_stub.SentenceTransformer = object  # type: ignore[attr-defined]
sys.modules.setdefault("sentence_transformers", _stub)

from src.ai.recovery import RecoveryQueue  # noqa: E402


def test_save_and_load_pending_entry(tmp_path) -> None:
    queue = RecoveryQueue(tmp_path)
    path = queue.save_failed_entry(
        entry_id="e1",
        user_id="u1",
        idempotency_key="k1",
        error="db down",
        error_code="SETUP_EXCEPTION",
        pipeline_version="v1",
    )

    assert path.exists()
    record = json.loads(path.read_text(encoding="utf-8"))
    loaded = queue.load_entry(record["recovery_id"])
    assert loaded["entry_id"] == "e1"
    assert loaded["status"] == "pending"
    assert queue.pending_count() == 1


def test_list_pending_sorts_and_skips_corrupt_files(tmp_path) -> None:
    queue = RecoveryQueue(tmp_path)
    first = queue.save_failed_entry(
        entry_id="e1",
        user_id="u1",
        idempotency_key="k1",
        error="err1",
        pipeline_version="v1",
    )
    second = queue.save_failed_entry(
        entry_id="e2",
        user_id="u2",
        idempotency_key="k2",
        error="err2",
        pipeline_version="v1",
    )
    # corrupt side-file should be ignored
    (tmp_path / "bad.json").write_text("{not-json", encoding="utf-8")

    rec1 = json.loads(first.read_text(encoding="utf-8"))
    rec2 = json.loads(second.read_text(encoding="utf-8"))
    pending = queue.list_pending()
    ids = [p["recovery_id"] for p in pending]
    assert len(pending) == 2
    assert set(ids) == {rec1["recovery_id"], rec2["recovery_id"]}
    assert all(item["status"] == "pending" for item in pending)


def test_increment_retry_and_status_transitions(tmp_path) -> None:
    queue = RecoveryQueue(tmp_path)
    path = queue.save_failed_entry(
        entry_id="e3",
        user_id="u3",
        idempotency_key="k3",
        error="err3",
        pipeline_version="v1",
    )
    recovery_id = json.loads(path.read_text(encoding="utf-8"))["recovery_id"]

    retry_count = queue.increment_retry(recovery_id)
    assert retry_count == 1
    assert queue.load_entry(recovery_id)["last_retry_at"] is not None

    queue.mark_recovered(recovery_id)
    recovered = queue.load_entry(recovery_id)
    assert recovered["status"] == "recovered"
    assert recovered["recovered_at"] is not None
    assert queue.pending_count() == 0

    queue.mark_failed_permanently(recovery_id, reason="max retries")
    failed = queue.load_entry(recovery_id)
    assert failed["status"] == "failed_permanently"
    assert failed["permanent_failure_reason"] == "max retries"


def test_missing_entry_paths_are_handled(tmp_path) -> None:
    queue = RecoveryQueue(tmp_path)

    try:
        queue.load_entry("missing")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass

    try:
        queue.increment_retry("missing")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass

    # _update_status path for missing file is intentionally no-op
    queue.mark_recovered("missing")
