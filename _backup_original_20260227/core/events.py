"""
Custom event system with configurable logging for Status Window API.

This module provides a pub/sub event system for decoupling game mechanics:
- Journal entries trigger XP distribution
- XP awards trigger level-up checks
- Level-ups trigger title unlock checks
- Quest progress updates trigger completion checks

Usage:
    from app.core.events import get_event_bus, EVENT_TYPES

    bus = get_event_bus()

    # Subscribe to events
    def on_xp_awarded(payload):
        print(f"XP awarded: {payload}")

    bus.subscribe("xp.awarded", on_xp_awarded)

    # Emit events
    bus.emit("xp.awarded", {"user_id": "123", "amount": 50, "source": "journal"})

    # Configure logging
    bus.configure_logging("xp.awarded", should_log=True)
"""
from typing import Any, Callable, TypedDict

from app.utils.logging_config import get_logger

logger = get_logger(__name__)


# Event payload schemas (for documentation and basic validation)
class JournalEntryCreatedPayload(TypedDict):
    user_id: str
    entry_id: str
    content: str
    entry_type: str


class XPAwardedPayload(TypedDict):
    user_id: str
    amount: float
    source: str  # "journal", "quest", "title"
    target_type: str  # "theme", "skill"
    target_id: str


class ThemeLeveledUpPayload(TypedDict):
    user_id: str
    theme_id: str
    new_level: int
    theme_name: str


class SkillLeveledUpPayload(TypedDict):
    user_id: str
    skill_id: str
    new_level: int
    skill_name: str
    new_rank: str


class TitleUnlockedPayload(TypedDict):
    user_id: str
    title_id: str
    title_name: str
    title_rank: str


class TitleEquippedPayload(TypedDict):
    user_id: str
    title_id: str
    title_name: str
    is_equipped: bool


class QuestCreatedPayload(TypedDict):
    user_id: str
    quest_id: str
    quest_name: str
    quest_type: str


class QuestProgressUpdatedPayload(TypedDict):
    user_id: str
    quest_id: str
    progress: int
    target: int


class QuestCompletedPayload(TypedDict):
    user_id: str
    quest_id: str
    quest_name: str
    reward_xp: int
    reward_coins: int


class StatsUpdatedPayload(TypedDict):
    user_id: str
    stat_name: str
    old_value: float
    new_value: float


# Core event types with their expected payload schemas
EVENT_TYPES: dict[str, type] = {
    "journal_entry.created": JournalEntryCreatedPayload,
    "xp.awarded": XPAwardedPayload,
    "theme.leveled_up": ThemeLeveledUpPayload,
    "skill.leveled_up": SkillLeveledUpPayload,
    "title.unlocked": TitleUnlockedPayload,
    "title.equipped": TitleEquippedPayload,
    "quest.created": QuestCreatedPayload,
    "quest.progress_updated": QuestProgressUpdatedPayload,
    "quest.completed": QuestCompletedPayload,
    "stats.updated": StatsUpdatedPayload,
}

# Type alias for event callbacks
EventCallback = Callable[[dict[str, Any]], Any]


class EventBus:
    """
    Synchronous event bus for publishing and subscribing to game events.

    Features:
    - Subscribe/unsubscribe callbacks to event types
    - Emit events with payload validation
    - Configurable per-event logging
    - Graceful error handling (listener exceptions don't stop other listeners)
    """

    def __init__(self) -> None:
        """Initialize the event bus with empty listeners and logging config."""
        self._listeners: dict[str, list[EventCallback]] = {}
        self._logging_config: dict[str, bool] = {}

        # Enable logging for important events by default
        for event_type in EVENT_TYPES:
            self._logging_config[event_type] = False

    def subscribe(self, event_type: str, callback: EventCallback) -> None:
        """
        Register a listener for an event type.

        Args:
            event_type: The event type to listen for
            callback: Function to call when event is emitted
        """
        if event_type not in self._listeners:
            self._listeners[event_type] = []

        if callback not in self._listeners[event_type]:
            self._listeners[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: EventCallback) -> None:
        """
        Remove a listener from an event type.

        Args:
            event_type: The event type to unsubscribe from
            callback: The callback to remove
        """
        if event_type in self._listeners:
            try:
                self._listeners[event_type].remove(callback)
            except ValueError:
                pass  # Callback not in list, ignore

    def emit(self, event_type: str, payload: dict[str, Any]) -> list[Any]:
        """
        Emit an event to all registered listeners.

        Args:
            event_type: The event type to emit
            payload: Event data to pass to listeners

        Returns:
            List of results from all listeners (None for failed listeners)

        Raises:
            ValueError: If event_type is not in EVENT_TYPES
        """
        # Validate event type
        if event_type not in EVENT_TYPES:
            raise ValueError(
                f"Unknown event type: {event_type}. "
                f"Valid types: {list(EVENT_TYPES.keys())}"
            )

        # Basic payload validation (check required keys exist)
        expected_schema = EVENT_TYPES[event_type]
        required_keys = set(expected_schema.__annotations__.keys())
        provided_keys = set(payload.keys())
        missing_keys = required_keys - provided_keys

        if missing_keys:
            logger.warning(
                "Event payload missing keys",
                event_type=event_type,
                missing_keys=list(missing_keys),
            )

        # Log event if configured
        if self._logging_config.get(event_type, False):
            logger.info(
                f"Event emitted: {event_type}",
                event_type=event_type,
                payload=payload,
            )

        # Execute listeners and collect results
        results: list[Any] = []
        listeners = self._listeners.get(event_type, [])

        for callback in listeners:
            try:
                result = callback(payload)
                results.append(result)
            except Exception as e:
                logger.error(
                    f"Listener exception for {event_type}",
                    event_type=event_type,
                    callback_name=callback.__name__,
                    error=str(e),
                    exc_info=True,
                )
                results.append(None)

        return results

    def configure_logging(self, event_type: str, should_log: bool) -> None:
        """
        Enable or disable logging for a specific event type.

        Args:
            event_type: The event type to configure
            should_log: Whether to log emissions of this event
        """
        self._logging_config[event_type] = should_log

    def get_listeners(self, event_type: str) -> list[EventCallback]:
        """
        Get all listeners registered for an event type.

        Args:
            event_type: The event type to query

        Returns:
            List of registered callbacks (empty list if none)
        """
        return self._listeners.get(event_type, []).copy()


# Global singleton instance
_event_bus_instance: EventBus | None = None


def get_event_bus() -> EventBus:
    """
    Get the global EventBus singleton.

    Returns:
        The global EventBus instance
    """
    global _event_bus_instance
    if _event_bus_instance is None:
        _event_bus_instance = EventBus()
    return _event_bus_instance
