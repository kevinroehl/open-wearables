"""merge latest migration heads

Revision ID: 3a7b9c2d4e6f
Revises: 7d5c0c8f2a11, 5aaff4551af6

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "3a7b9c2d4e6f"
down_revision: Union[str, tuple[str, str], None] = (
    "7d5c0c8f2a11",
    "5aaff4551af6",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
