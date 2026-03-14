"""Story arcs timestamp utilities (Section 8.2.1).

Canonical format: YYYY-MM-DDTHH:MM:SS.mmmZ  (exactly 3 ms digits, UTC, RFC3339)

All story_arcs / arc_triggers timestamp columns store strings in this format.
Using a fixed 3-digit millisecond representation makes timestamps sortable as
plain strings and avoids microsecond drift between Python datetime and SQLite
TEXT storage.
"""

from datetime import datetime, timezone


def now_utc_fixed_ms() -> str:
    """Return the current UTC instant as a fixed-ms RFC3339 string.

    Example output: ``"2026-03-20T09:00:00.123Z"``
    """
    now = datetime.now(timezone.utc)
    ms = now.microsecond // 1000
    return f"{now.strftime('%Y-%m-%dT%H:%M:%S')}.{ms:03d}Z"


def parse_fixed_ms_timestamp(ts_str: str) -> datetime:
    """Parse a fixed-ms RFC3339 UTC string back to a timezone-aware datetime.

    Accepts both ``"...SSS.mmmZ"`` and the bare ``"...SSSZ"`` forms so the
    function is tolerant of values produced by other systems.

    Args:
        ts_str: Timestamp string, e.g. ``"2026-03-20T09:00:00.123Z"``.

    Returns:
        UTC-aware :class:`datetime`.
    """
    if "." in ts_str:
        dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S.%fZ")
    else:
        dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ")
    return dt.replace(tzinfo=timezone.utc)
