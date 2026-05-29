"""merge training and workout details heads

Revision ID: 7d5c0c8f2a11
Revises: a8f3d2c9e1b7, 2d316787b998

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "7d5c0c8f2a11"
down_revision: Union[str, tuple[str, str], None] = (
    "a8f3d2c9e1b7",
    "2d316787b998",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
