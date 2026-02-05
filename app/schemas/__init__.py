"""
Pydantic schemas for Status Window API.

This package contains all request/response schemas organized by entity.
All schemas inherit from BaseSchema for consistent ORM integration.

Re-exports common types and utilities for convenience.
"""
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.base import (
    BaseSchema,
    DescriptionStr,
    EmailStr,
    LevelInt,
    MessageResponse,
    NameStr,
    PaginatedResponse,
    TimestampMixin,
    UsernameStr,
    UUIDStr,
    XPFloat,
    validate_non_empty_string,
    validate_uuid_format,
)

__all__ = [
    # Pydantic core (re-exported for convenience)
    "BaseModel",
    "ConfigDict",
    "Field",
    "field_validator",
    # Base schema classes
    "BaseSchema",
    "TimestampMixin",
    # Annotated types
    "UUIDStr",
    "UsernameStr",
    "EmailStr",
    "NameStr",
    "DescriptionStr",
    "XPFloat",
    "LevelInt",
    # Validators
    "validate_non_empty_string",
    "validate_uuid_format",
    # Response wrappers
    "MessageResponse",
    "PaginatedResponse",
]
