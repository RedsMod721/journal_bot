"""
Declarative base for all ORM models.

Kept minimal on purpose: every model file imports `Base` from here, so
nothing engine-specific should live in this module — that avoids circular
imports when `session.py` imports `Base` to call `Base.metadata.create_all()`.

Engine, session factory, and all database utilities live in `src.db.session`.

Usage:
    from src.db.base import Base

    class MyModel(Base):
        __tablename__ = "my_table"
        ...
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all RPG Life Tracker ORM models."""
