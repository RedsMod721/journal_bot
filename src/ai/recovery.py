"""File-based recovery queue for pipeline failures.

When critical infrastructure (DB) is completely unavailable, failed processing
requests are persisted to a local JSON file store so they can be retried when
services recover.

This queue is a last-resort buffer — NOT a replacement for the DB audit trail.
It is only invoked when the normal ``ProcessingJob`` / ``OutboxEvent`` path
itself cannot be written.

Design guarantees
-----------------
- **No data loss**: every call to ``save_failed_entry`` writes a uniquely
  named file, so concurrent writers never collide.
- **Idempotency-key preserved**: callers store the original idempotency key so
  the retry worker can pass it back to ``PipelineProcessor.process_entry``,
  preventing double-processing once the DB recovers.
- **Lightweight**: pure-stdlib — no DB, no network.  Safe to call even when
  all other infrastructure is down.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RECOVERY_SCHEMA_VERSION = 1

# Statuses a recovery record can hold over its lifetime.
_STATUS_PENDING = "pending"
_STATUS_RECOVERED = "recovered"
_STATUS_FAILED_PERMANENTLY = "failed_permanently"


class RecoveryQueue:
    """File-based queue for pipeline entries that could not be DB-recorded.

    One JSON file is written per failure, named after a unique ``recovery_id``
    so concurrent pipeline workers never clobber each other's records.

    Usage::

        queue = RecoveryQueue()                    # default: data/recovery/
        queue = RecoveryQueue("data/recovery")     # explicit path

        # On failure:
        queue.save_failed_entry(
            entry_id="...",
            user_id="...",
            idempotency_key="...",
            error="SQLAlchemy connection refused",
            error_code="SETUP_EXCEPTION",
            pipeline_version="week3-v2",
        )

        # Recovery worker:
        for record in queue.list_pending():
            ...retry pipeline...
            queue.mark_recovered(record["recovery_id"])
    """

    def __init__(self, recovery_dir: str | Path = "data/recovery") -> None:
        """Initialise the queue and ensure the storage directory exists.

        Args:
            recovery_dir: Path to the directory where JSON recovery files are
                          written.  Created (including parents) if absent.

        Raises:
            OSError: If the directory cannot be created (e.g. permissions).
        """
        self.recovery_dir = Path(recovery_dir)
        self.recovery_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("RecoveryQueue ready dir=%s", self.recovery_dir)

    # ------------------------------------------------------------------
    # Write side
    # ------------------------------------------------------------------

    def save_failed_entry(
        self,
        *,
        entry_id: str,
        user_id: str,
        idempotency_key: str,
        error: str,
        error_code: str = "UNKNOWN",
        pipeline_version: str = "",
    ) -> Path:
        """Persist a failed processing request for later retry.

        Each call writes a new file with a unique ``recovery_id`` so multiple
        failures for the same entry (e.g. across retry attempts) are stored
        independently.

        Args:
            entry_id:         Journal entry UUID.
            user_id:          Owning user UUID.
            idempotency_key:  The key that was in-flight when the failure
                              occurred.  Pass back to the pipeline on retry to
                              avoid double-processing.
            error:            Human-readable error message.
            error_code:       Structured error code (e.g. ``SETUP_EXCEPTION``).
            pipeline_version: ``PIPELINE_VERSION`` constant from the pipeline.

        Returns:
            Path to the written recovery file.
        """
        recovery_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        record: dict[str, Any] = {
            "schema_version": RECOVERY_SCHEMA_VERSION,
            "recovery_id": recovery_id,
            "entry_id": entry_id,
            "user_id": user_id,
            "idempotency_key": idempotency_key,
            "error": error,
            "error_code": error_code,
            "pipeline_version": pipeline_version,
            "failed_at": now,
            "status": _STATUS_PENDING,
            "retry_count": 0,
            "last_retry_at": None,
            "recovered_at": None,
        }

        filepath = self.recovery_dir / f"{recovery_id}.json"
        # Write atomically via a temp file, then rename to avoid partial reads.
        tmp = filepath.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
        tmp.rename(filepath)

        logger.warning(
            "recovery_queue saved entry=%s user=%s recovery_id=%s error_code=%s",
            entry_id,
            user_id,
            recovery_id,
            error_code,
        )
        return filepath

    # ------------------------------------------------------------------
    # Read side
    # ------------------------------------------------------------------

    def list_pending(self) -> list[dict[str, Any]]:
        """Return all pending recovery records, oldest first.

        Unreadable or corrupt files are skipped with a warning.

        Returns:
            List of record dicts, sorted ascending by ``failed_at``.
        """
        records: list[dict[str, Any]] = []
        for path in self.recovery_dir.glob("*.json"):
            try:
                data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
                if data.get("status") == _STATUS_PENDING:
                    records.append(data)
            except Exception as exc:
                logger.warning(
                    "recovery_queue unreadable file=%s error=%s", path.name, exc
                )
        records.sort(key=lambda r: r.get("failed_at", ""))
        return records

    def load_entry(self, recovery_id: str) -> dict[str, Any]:
        """Load a single recovery record by its ``recovery_id``.

        Args:
            recovery_id: UUID string used as the filename stem.

        Returns:
            The full record dict.

        Raises:
            FileNotFoundError: If no file with that recovery_id exists.
            json.JSONDecodeError: If the file is corrupt.
        """
        filepath = self.recovery_dir / f"{recovery_id}.json"
        if not filepath.exists():
            raise FileNotFoundError(f"Recovery entry not found: {recovery_id}")
        return json.loads(filepath.read_text(encoding="utf-8"))

    def pending_count(self) -> int:
        """Return the number of pending recovery records.

        Returns:
            Count of ``.json`` files in the recovery directory whose
            ``status`` is ``pending``.
        """
        return sum(
            1
            for p in self.recovery_dir.glob("*.json")
            if self._read_status(p) == _STATUS_PENDING
        )

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def increment_retry(self, recovery_id: str) -> int:
        """Increment and persist the retry counter for a record.

        Args:
            recovery_id: UUID of the recovery record.

        Returns:
            The new retry count.

        Raises:
            FileNotFoundError: If the record does not exist.
        """
        filepath = self.recovery_dir / f"{recovery_id}.json"
        if not filepath.exists():
            raise FileNotFoundError(f"Recovery entry not found: {recovery_id}")
        data: dict[str, Any] = json.loads(filepath.read_text(encoding="utf-8"))
        data["retry_count"] = data.get("retry_count", 0) + 1
        data["last_retry_at"] = datetime.now(timezone.utc).isoformat()
        filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.debug(
            "recovery_queue retry_count=%s entry=%s recovery_id=%s",
            data["retry_count"],
            data.get("entry_id"),
            recovery_id,
        )
        return data["retry_count"]

    def mark_recovered(self, recovery_id: str) -> None:
        """Mark a recovery record as successfully retried.

        Args:
            recovery_id: UUID of the recovery record.
        """
        self._update_status(
            recovery_id,
            new_status=_STATUS_RECOVERED,
            extra={"recovered_at": datetime.now(timezone.utc).isoformat()},
        )
        logger.info("recovery_queue recovered recovery_id=%s", recovery_id)

    def mark_failed_permanently(self, recovery_id: str, *, reason: str) -> None:
        """Mark a recovery record as permanently unrecoverable.

        Args:
            recovery_id: UUID of the recovery record.
            reason:      Human-readable explanation for why retry was aborted.
        """
        self._update_status(
            recovery_id,
            new_status=_STATUS_FAILED_PERMANENTLY,
            extra={
                "permanent_failure_reason": reason,
                "failed_permanently_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        logger.error(
            "recovery_queue permanent_failure recovery_id=%s reason=%s",
            recovery_id,
            reason,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _update_status(
        self,
        recovery_id: str,
        *,
        new_status: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        filepath = self.recovery_dir / f"{recovery_id}.json"
        if not filepath.exists():
            logger.warning(
                "recovery_queue update_status: file not found recovery_id=%s",
                recovery_id,
            )
            return
        data: dict[str, Any] = json.loads(filepath.read_text(encoding="utf-8"))
        data["status"] = new_status
        if extra:
            data.update(extra)
        filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _read_status(self, path: Path) -> str | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("status")
        except Exception:
            return None
