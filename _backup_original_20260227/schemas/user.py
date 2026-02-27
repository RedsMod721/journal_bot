"""
User Pydantic schemas for Status Window API.

This module defines schemas for User data validation and serialization:
- UserBase: Shared fields for user data
- UserCreate: Schema for creating new users (POST requests)
- UserResponse: Schema for API responses with full user data

All schemas use the base types defined in app.schemas.base for consistency.
"""
from datetime import datetime

from pydantic import ConfigDict

from app.schemas.base import BaseSchema, EmailStr, UsernameStr, UUIDStr


class UserBase(BaseSchema):
    """
    Base schema with shared user fields.

    Used as a parent class for UserCreate and UserResponse.
    Contains fields that are required for both creation and display.

    Attributes:
        username: Unique username (3-50 chars, alphanumeric with _ and -)
        email: Valid email address
    """

    username: UsernameStr
    email: EmailStr


class UserCreate(UserBase):
    """
    Schema for creating a new user.

    Used for POST /users endpoint. Inherits username and email
    from UserBase with no additional fields.

    Example:
        {
            "username": "john_doe",
            "email": "john@example.com"
        }
    """

    pass


class UserResponse(UserBase):
    """
    Schema for user API responses.

    Includes all user fields returned by the API, including
    auto-generated fields like id and created_at.

    Attributes:
        id: Unique UUID identifier
        created_at: Timestamp of account creation
        is_active: Whether the account is active

    Example:
        {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "username": "john_doe",
            "email": "john@example.com",
            "created_at": "2025-01-15T10:30:00",
            "is_active": true
        }
    """

    id: UUIDStr
    created_at: datetime
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
