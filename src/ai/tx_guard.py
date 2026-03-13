"""Guards against external AI/vector calls during Tx B finalization."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_NETWORK_FORBIDDEN: ContextVar[bool] = ContextVar(
    "network_forbidden_in_transaction",
    default=False,
)


class NetworkInTransactionError(RuntimeError):
    """Raised when an external AI/vector call is attempted during Tx B."""


def assert_network_allowed(operation: str) -> None:
    """Fail fast when a guarded client is invoked inside Tx B."""
    if _NETWORK_FORBIDDEN.get():
        raise NetworkInTransactionError(
            f"{operation} is forbidden during transaction finalization"
        )


@contextmanager
def forbid_network_calls() -> Iterator[None]:
    """Context manager used by the pipeline while Tx B is active."""
    token = _NETWORK_FORBIDDEN.set(True)
    try:
        yield
    finally:
        _NETWORK_FORBIDDEN.reset(token)
