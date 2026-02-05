"""
Base Pydantic schemas and utilities for Status Window API.

This module provides:
- BaseSchema: Base class with ORM mode configuration
- Common field validators for UUIDs, strings, and other types
- Utility functions for schema conversions

All entity schemas should inherit from BaseSchema to ensure
consistent behavior across the API.
"""
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BaseSchema(BaseModel):
    """
    Base schema class with common configuration for all Pydantic models.

    Features:
    - ORM mode enabled for SQLAlchemy model conversion
    - Strict validation by default
    - Populate by field name for flexibility

    Usage:
        class UserBase(BaseSchema):
            username: str
            email: str
    """

    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM mode (was orm_mode in v1)
        str_strip_whitespace=True,  # Strip whitespace from strings
        validate_default=True,  # Validate default values
        extra="forbid",  # Forbid extra fields not in schema
    )


class TimestampMixin(BaseModel):
    """
    Mixin for schemas that include timestamp fields.

    Provides created_at field with proper serialization.
    Can be extended with updated_at if needed.
    """

    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# ANNOTATED TYPES FOR COMMON FIELDS
# =============================================================================

# UUID string field (36 characters including hyphens)
UUIDStr = Annotated[
    str,
    Field(
        min_length=36,
        max_length=36,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        description="UUID string in standard format",
    ),
]

# Username field with validation
UsernameStr = Annotated[
    str,
    Field(
        min_length=3,
        max_length=50,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Username: 3-50 characters, alphanumeric with underscores and hyphens",
    ),
]

# Email field
EmailStr = Annotated[
    str,
    Field(
        max_length=255,
        pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
        description="Valid email address",
    ),
]

# Name fields (for themes, skills, etc.)
NameStr = Annotated[
    str,
    Field(
        min_length=1,
        max_length=100,
        description="Name field: 1-100 characters",
    ),
]

# Description fields
DescriptionStr = Annotated[
    str | None,
    Field(
        max_length=500,
        default=None,
        description="Optional description: up to 500 characters",
    ),
]

# XP fields (non-negative float)
XPFloat = Annotated[
    float,
    Field(
        ge=0.0,
        description="XP value (non-negative)",
    ),
]

# Level fields (non-negative integer)
LevelInt = Annotated[
    int,
    Field(
        ge=0,
        description="Level value (non-negative integer)",
    ),
]


# =============================================================================
# COMMON VALIDATORS
# =============================================================================


def validate_non_empty_string(value: str, field_name: str = "field") -> str:
    """
    Validate that a string is not empty after stripping whitespace.

    Args:
        value: The string value to validate
        field_name: Name of the field for error messages

    Returns:
        The stripped string

    Raises:
        ValueError: If the string is empty after stripping
    """
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} cannot be empty or whitespace only")
    return stripped


def validate_uuid_format(value: str) -> str:
    """
    Validate that a string is a valid UUID format.

    Args:
        value: The string value to validate

    Returns:
        The lowercase UUID string

    Raises:
        ValueError: If the string is not a valid UUID format
    """
    import re

    pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    if not re.match(pattern, value.lower()):
        raise ValueError("Invalid UUID format")
    return value.lower()


# =============================================================================
# RESPONSE WRAPPER SCHEMAS
# =============================================================================


class MessageResponse(BaseSchema):
    """Generic message response for simple confirmations."""

    message: str


class PaginatedResponse(BaseSchema):
    """Base schema for paginated responses."""

    total: int = Field(ge=0, description="Total number of items")
    page: int = Field(ge=1, description="Current page number")
    page_size: int = Field(ge=1, le=100, description="Items per page")
    items: list[Any] = Field(default_factory=list, description="List of items")

    @property
    def total_pages(self) -> int:
        """Calculate total number of pages."""
        return (self.total + self.page_size - 1) // self.page_size if self.total > 0 else 0

    @property
    def has_next(self) -> bool:
        """Check if there is a next page."""
        return self.page < self.total_pages

    @property
    def has_previous(self) -> bool:
        """Check if there is a previous page."""
        return self.page > 1
