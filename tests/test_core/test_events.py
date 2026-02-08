"""
Tests for the custom event system.

Tests:
- Subscribe and emit events
- Multiple listeners execute in order
- Unsubscribe removes listeners
- Configure logging enables event logging
- Listener exceptions don't stop other listeners
- Emit with invalid event type raises error
- get_event_bus returns singleton
"""
from unittest.mock import MagicMock

import pytest

from app.core.events import EVENT_TYPES, EventBus, get_event_bus


class TestSubscribeAndEmit:
    """Test basic subscribe and emit functionality."""

    def test_subscribe_and_emit(self) -> None:
        """Should call subscribed callback when event is emitted."""
        # Arrange
        bus = EventBus()
        callback = MagicMock(return_value="result")

        bus.subscribe("xp.awarded", callback)

        payload = {
            "user_id": "user-123",
            "amount": 50.0,
            "source": "journal",
            "target_type": "theme",
            "target_id": "theme-456",
        }

        # Act
        results = bus.emit("xp.awarded", payload)

        # Assert
        callback.assert_called_once_with(payload)
        assert results == ["result"]

    def test_emit_returns_empty_list_when_no_listeners(self) -> None:
        """Should return empty list when no listeners are registered."""
        # Arrange
        bus = EventBus()
        payload = {
            "user_id": "user-123",
            "amount": 50.0,
            "source": "journal",
            "target_type": "theme",
            "target_id": "theme-456",
        }

        # Act
        results = bus.emit("xp.awarded", payload)

        # Assert
        assert results == []

    def test_subscribe_deduplicates_callbacks(self) -> None:
        """Should not register the same callback twice."""
        bus = EventBus()
        callback = MagicMock(return_value="ok")

        bus.subscribe("xp.awarded", callback)
        bus.subscribe("xp.awarded", callback)

        results = bus.emit("xp.awarded", {"user_id": "u", "amount": 1, "source": "journal", "target_type": "theme", "target_id": "t"})

        callback.assert_called_once()
        assert results == ["ok"]

    def test_emit_passes_same_payload_instance(self) -> None:
        """Listeners should receive the same payload object."""
        bus = EventBus()
        observed = []

        def listener_a(payload: dict) -> None:
            payload["mutated"] = True
            observed.append(payload)

        def listener_b(payload: dict) -> None:
            observed.append(payload)

        bus.subscribe("xp.awarded", listener_a)
        bus.subscribe("xp.awarded", listener_b)

        payload = {
            "user_id": "user-123",
            "amount": 50.0,
            "source": "journal",
            "target_type": "theme",
            "target_id": "theme-456",
        }

        bus.emit("xp.awarded", payload)

        assert observed[0] is payload
        assert observed[1] is payload
        assert observed[1]["mutated"] is True


class TestMultipleListeners:
    """Test multiple listener behavior."""

    def test_multiple_listeners_execute_in_order(self) -> None:
        """Should execute multiple listeners in subscription order."""
        # Arrange
        bus = EventBus()
        execution_order: list[int] = []

        def listener1(payload: dict) -> str:
            execution_order.append(1)
            return "first"

        def listener2(payload: dict) -> str:
            execution_order.append(2)
            return "second"

        def listener3(payload: dict) -> str:
            execution_order.append(3)
            return "third"

        bus.subscribe("xp.awarded", listener1)
        bus.subscribe("xp.awarded", listener2)
        bus.subscribe("xp.awarded", listener3)

        payload = {
            "user_id": "user-123",
            "amount": 50.0,
            "source": "journal",
            "target_type": "theme",
            "target_id": "theme-456",
        }

        # Act
        results = bus.emit("xp.awarded", payload)

        # Assert
        assert execution_order == [1, 2, 3]
        assert results == ["first", "second", "third"]


class TestUnsubscribe:
    """Test unsubscribe functionality."""

    def test_unsubscribe_removes_listener(self) -> None:
        """Should remove listener so it's not called on emit."""
        # Arrange
        bus = EventBus()
        callback = MagicMock()

        bus.subscribe("xp.awarded", callback)
        bus.unsubscribe("xp.awarded", callback)

        payload = {
            "user_id": "user-123",
            "amount": 50.0,
            "source": "journal",
            "target_type": "theme",
            "target_id": "theme-456",
        }

        # Act
        bus.emit("xp.awarded", payload)

        # Assert
        callback.assert_not_called()

    def test_unsubscribe_nonexistent_listener_doesnt_raise(self) -> None:
        """Should not raise when unsubscribing a listener that's not registered."""
        # Arrange
        bus = EventBus()
        callback = MagicMock()

        # Act & Assert (should not raise)
        bus.unsubscribe("xp.awarded", callback)

    def test_unsubscribe_from_unknown_event_type_does_not_raise(self) -> None:
        """Should not raise when unsubscribing from an unknown event type."""
        bus = EventBus()
        callback = MagicMock()

        bus.unsubscribe("unknown.event", callback)

    def test_get_listeners_returns_registered_callbacks(self) -> None:
        """Should return list of registered callbacks."""
        # Arrange
        bus = EventBus()
        callback1 = MagicMock()
        callback2 = MagicMock()

        bus.subscribe("xp.awarded", callback1)
        bus.subscribe("xp.awarded", callback2)

        # Act
        listeners = bus.get_listeners("xp.awarded")

        # Assert
        assert len(listeners) == 2
        assert callback1 in listeners
        assert callback2 in listeners


class TestConfigureLogging:
    """Test logging configuration."""

    def test_configure_logging_enables_event_log(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should log event when logging is enabled for that event type."""
        # Arrange
        from app.utils.logging_config import configure_logging

        configure_logging()

        bus = EventBus()
        bus.configure_logging("xp.awarded", should_log=True)

        payload = {
            "user_id": "user-123",
            "amount": 50.0,
            "source": "journal",
            "target_type": "theme",
            "target_id": "theme-456",
        }

        # Act
        bus.emit("xp.awarded", payload)

        # Assert - structlog may output to stdout or stderr depending on config
        captured = capsys.readouterr()
        assert "xp.awarded" in captured.out or "xp.awarded" in captured.err

    def test_logging_disabled_by_default(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should not log events when logging is disabled (default)."""
        # Arrange
        from app.utils.logging_config import configure_logging

        configure_logging()

        bus = EventBus()
        # Logging is disabled by default, but explicitly disable to be sure
        bus.configure_logging("theme.leveled_up", should_log=False)

        payload = {
            "user_id": "user-123",
            "theme_id": "theme-456",
            "new_level": 5,
            "theme_name": "Education",
        }

        # Act
        bus.emit("theme.leveled_up", payload)

        # Assert
        captured = capsys.readouterr()
        assert "Event emitted: theme.leveled_up" not in captured.err


class TestListenerExceptionHandling:
    """Test graceful error handling for listener exceptions."""

    def test_listener_exception_doesnt_stop_other_listeners(self) -> None:
        """Should continue executing other listeners when one raises."""
        # Arrange
        bus = EventBus()
        results_collected: list[str] = []

        def listener1(payload: dict) -> str:
            results_collected.append("first")
            return "first"

        def failing_listener(payload: dict) -> None:
            raise ValueError("Intentional test error")

        def listener3(payload: dict) -> str:
            results_collected.append("third")
            return "third"

        bus.subscribe("xp.awarded", listener1)
        bus.subscribe("xp.awarded", failing_listener)
        bus.subscribe("xp.awarded", listener3)

        payload = {
            "user_id": "user-123",
            "amount": 50.0,
            "source": "journal",
            "target_type": "theme",
            "target_id": "theme-456",
        }

        # Act
        results = bus.emit("xp.awarded", payload)

        # Assert
        assert results_collected == ["first", "third"]
        assert results == ["first", None, "third"]  # None for failed listener


class TestInvalidEventType:
    """Test validation of event types."""

    def test_emit_with_invalid_event_type(self) -> None:
        """Should raise ValueError for unknown event type."""
        # Arrange
        bus = EventBus()
        payload = {"some": "data"}

        # Act & Assert
        with pytest.raises(ValueError, match="Unknown event type"):
            bus.emit("invalid.event", payload)

    def test_emit_with_non_string_event_type_raises(self) -> None:
        """Should raise ValueError when event_type is not a string."""
        bus = EventBus()

        with pytest.raises(ValueError, match="Unknown event type"):
            bus.emit(None, {})

    def test_all_event_types_are_valid(self) -> None:
        """All EVENT_TYPES should be emittable without error."""
        # Arrange
        bus = EventBus()

        # Act & Assert - each event type should be valid
        for event_type in EVENT_TYPES:
            # Create minimal payload (validation only warns, doesn't raise)
            results = bus.emit(event_type, {})
            assert results == []  # No listeners, but should not raise


class TestGetEventBusSingleton:
    """Test singleton behavior of get_event_bus."""

    def test_get_event_bus_returns_singleton(self) -> None:
        """Should return the same instance on multiple calls."""
        # Act
        bus1 = get_event_bus()
        bus2 = get_event_bus()

        # Assert
        assert bus1 is bus2

    def test_singleton_preserves_subscriptions(self) -> None:
        """Subscriptions should persist across get_event_bus calls."""
        # Arrange
        bus1 = get_event_bus()
        callback = MagicMock()
        bus1.subscribe("journal_entry.created", callback)

        # Act
        bus2 = get_event_bus()
        listeners = bus2.get_listeners("journal_entry.created")

        # Assert
        assert callback in listeners

    def test_event_bus_instances_are_independent(self) -> None:
        """New EventBus instances should not share listeners with singleton."""
        singleton_bus = get_event_bus()
        standalone_bus = EventBus()

        callback = MagicMock()
        singleton_bus.subscribe("journal_entry.created", callback)

        assert callback in singleton_bus.get_listeners("journal_entry.created")
        assert callback not in standalone_bus.get_listeners("journal_entry.created")


class TestGetListenersCopy:
    def test_get_listeners_returns_copy(self) -> None:
        """Mutating returned list should not affect internal state."""
        bus = EventBus()
        callback = MagicMock()
        bus.subscribe("xp.awarded", callback)

        listeners = bus.get_listeners("xp.awarded")
        listeners.clear()

        assert callback in bus.get_listeners("xp.awarded")
