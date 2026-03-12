"""MB72 add user realm preferences container.

Revision ID: b10000000009
Revises: b10000000008
Create Date: 2026-03-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "b10000000009"
down_revision: Union[str, Sequence[str], None] = "b10000000008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "user_preferences" not in columns:
        op.add_column(
            "users",
            sa.Column(
                "user_preferences",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "user_preferences" in columns:
        op.drop_column("users", "user_preferences")
