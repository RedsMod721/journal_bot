"""
Tests for base schema utilities and validators.

These tests cover:
- validate_non_empty_string function
- validate_uuid_format function
- TimestampMixin
- MessageResponse
- PaginatedResponse with properties
"""
from datetime import datetime

import pytest

from app.schemas.base import (
    BaseSchema,
    TimestampMixin,
    MessageResponse,
    PaginatedResponse,
    validate_non_empty_string,
    validate_uuid_format,
    UUIDStr,
    UsernameStr,
    EmailStr,
    NameStr,
    DescriptionStr,
    XPFloat,
    LevelInt,
)


class TestValidateNonEmptyString:
    """Tests for validate_non_empty_string function."""

    def test_valid_string_returns_stripped(self):
        """Valid string should be returned stripped."""
        result = validate_non_empty_string("  hello world  ")
        assert result == "hello world"

    def test_valid_string_without_whitespace(self):
        """String without extra whitespace should be returned as-is."""
        result = validate_non_empty_string("hello")
        assert result == "hello"

    def test_empty_string_raises_value_error(self):
        """Empty string should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            validate_non_empty_string("")
        assert "cannot be empty or whitespace only" in str(exc_info.value)

    def test_whitespace_only_raises_value_error(self):
        """Whitespace-only string should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            validate_non_empty_string("   ")
        assert "cannot be empty or whitespace only" in str(exc_info.value)

    def test_custom_field_name_in_error_message(self):
        """Custom field name should appear in error message."""
        with pytest.raises(ValueError) as exc_info:
            validate_non_empty_string("", field_name="username")
        assert "username cannot be empty" in str(exc_info.value)


class TestValidateUUIDFormat:
    """Tests for validate_uuid_format function."""

    def test_valid_uuid_lowercase(self):
        """Valid lowercase UUID should be returned."""
        uuid = "123e4567-e89b-12d3-a456-426614174000"
        result = validate_uuid_format(uuid)
        assert result == uuid

    def test_valid_uuid_uppercase_returns_lowercase(self):
        """Valid uppercase UUID should be returned lowercase."""
        uuid = "123E4567-E89B-12D3-A456-426614174000"
        result = validate_uuid_format(uuid)
        assert result == uuid.lower()

    def test_valid_uuid_mixed_case_returns_lowercase(self):
        """Valid mixed-case UUID should be returned lowercase."""
        uuid = "123E4567-e89b-12D3-a456-426614174000"
        result = validate_uuid_format(uuid)
        assert result == uuid.lower()

    def test_invalid_uuid_short_raises_value_error(self):
        """UUID that is too short should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            validate_uuid_format("123e4567-e89b-12d3-a456")
        assert "Invalid UUID format" in str(exc_info.value)

    def test_invalid_uuid_wrong_format_raises_value_error(self):
        """UUID with wrong format should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            validate_uuid_format("not-a-valid-uuid-format-string")
        assert "Invalid UUID format" in str(exc_info.value)

    def test_invalid_uuid_no_hyphens_raises_value_error(self):
        """UUID without hyphens should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            validate_uuid_format("123e4567e89b12d3a456426614174000")
        assert "Invalid UUID format" in str(exc_info.value)


class TestTimestampMixin:
    """Tests for TimestampMixin schema."""

    def test_timestamp_mixin_with_datetime(self):
        """TimestampMixin should accept datetime."""
        now = datetime.utcnow()
        mixin = TimestampMixin(created_at=now)
        assert mixin.created_at == now


class TestMessageResponse:
    """Tests for MessageResponse schema."""

    def test_message_response_creation(self):
        """MessageResponse should hold a message."""
        response = MessageResponse(message="Operation successful")
        assert response.message == "Operation successful"


class TestPaginatedResponse:
    """Tests for PaginatedResponse schema."""

    def test_paginated_response_creation(self):
        """PaginatedResponse should be created with valid values."""
        response = PaginatedResponse(
            total=100,
            page=1,
            page_size=10,
            items=["a", "b", "c"]
        )
        assert response.total == 100
        assert response.page == 1
        assert response.page_size == 10
        assert response.items == ["a", "b", "c"]

    def test_total_pages_calculation(self):
        """total_pages should calculate correctly."""
        # 100 items, 10 per page = 10 pages
        response = PaginatedResponse(total=100, page=1, page_size=10)
        assert response.total_pages == 10

        # 101 items, 10 per page = 11 pages
        response = PaginatedResponse(total=101, page=1, page_size=10)
        assert response.total_pages == 11

        # 95 items, 10 per page = 10 pages
        response = PaginatedResponse(total=95, page=1, page_size=10)
        assert response.total_pages == 10

    def test_total_pages_zero_items(self):
        """total_pages should be 0 when no items."""
        response = PaginatedResponse(total=0, page=1, page_size=10)
        assert response.total_pages == 0

    def test_has_next_true(self):
        """has_next should be True when more pages exist."""
        response = PaginatedResponse(total=100, page=5, page_size=10)
        assert response.has_next is True

    def test_has_next_false_on_last_page(self):
        """has_next should be False on last page."""
        response = PaginatedResponse(total=100, page=10, page_size=10)
        assert response.has_next is False

    def test_has_next_false_when_empty(self):
        """has_next should be False when no items."""
        response = PaginatedResponse(total=0, page=1, page_size=10)
        assert response.has_next is False

    def test_has_previous_true(self):
        """has_previous should be True when not on first page."""
        response = PaginatedResponse(total=100, page=5, page_size=10)
        assert response.has_previous is True

    def test_has_previous_false_on_first_page(self):
        """has_previous should be False on first page."""
        response = PaginatedResponse(total=100, page=1, page_size=10)
        assert response.has_previous is False

    def test_default_items_empty_list(self):
        """items should default to empty list."""
        response = PaginatedResponse(total=0, page=1, page_size=10)
        assert response.items == []


class TestBaseSchema:
    """Tests for BaseSchema configuration."""

    def test_base_schema_strips_whitespace(self):
        """BaseSchema should strip whitespace from strings."""
        class TestSchema(BaseSchema):
            name: str

        schema = TestSchema(name="  hello  ")
        assert schema.name == "hello"

    def test_base_schema_forbids_extra_fields(self):
        """BaseSchema should reject extra fields."""
        class TestSchema(BaseSchema):
            name: str

        with pytest.raises(Exception):  # ValidationError
            TestSchema(name="test", extra_field="not allowed")
