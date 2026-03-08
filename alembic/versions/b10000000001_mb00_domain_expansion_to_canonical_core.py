"""MB00 domain expansion to canonical core.

Revision ID: b10000000001
Revises: 4ce8e78ab15d
Create Date: 2026-02-28
"""

from typing import Sequence, Union

from alembic import op

from src.db.base import Base
import src.db.models  # noqa: F401

revision: str = "b10000000001"
down_revision: Union[str, Sequence[str], None] = "4ce8e78ab15d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    # Explicit downgrades are intentionally conservative for large canonical packs.
    pass
