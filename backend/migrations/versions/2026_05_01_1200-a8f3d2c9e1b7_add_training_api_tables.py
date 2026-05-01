"""add training api tables

Revision ID: a8f3d2c9e1b7
Revises: cdac07b15b04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a8f3d2c9e1b7"
down_revision: Union[str, None] = "cdac07b15b04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "training_workout",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("workout_name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sport", sa.String(length=32), nullable=False),
        sa.Column("steps_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("workout_provider", sa.String(length=20), nullable=False),
        sa.Column("workout_source_id", sa.String(length=20), nullable=False),
        sa.Column("garmin_workout_id", sa.String(length=100), nullable=True),
        sa.Column("garmin_owner_id", sa.String(length=100), nullable=True),
        sa.Column("publish_status", sa.String(length=32), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_training_workout_user_provider", "training_workout", ["user_id", "provider"])
    op.create_index("ix_training_workout_garmin_workout_id", "training_workout", ["garmin_workout_id"])

    op.create_table(
        "training_schedule",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("workout_id", sa.UUID(), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("garmin_schedule_id", sa.String(length=100), nullable=True),
        sa.Column("publish_status", sa.String(length=32), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workout_id"], ["training_workout.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_training_schedule_user_provider_date",
        "training_schedule",
        ["user_id", "provider", "scheduled_date"],
    )
    op.create_index("ix_training_schedule_garmin_schedule_id", "training_schedule", ["garmin_schedule_id"])

    op.create_table(
        "training_publish_job",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("garmin_status_code", sa.Integer(), nullable=True),
        sa.Column("garmin_response_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_training_publish_job_user_status", "training_publish_job", ["user_id", "status"])
    op.create_index("ix_training_publish_job_entity", "training_publish_job", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_index("ix_training_publish_job_entity", table_name="training_publish_job")
    op.drop_index("ix_training_publish_job_user_status", table_name="training_publish_job")
    op.drop_table("training_publish_job")

    op.drop_index("ix_training_schedule_garmin_schedule_id", table_name="training_schedule")
    op.drop_index("ix_training_schedule_user_provider_date", table_name="training_schedule")
    op.drop_table("training_schedule")

    op.drop_index("ix_training_workout_garmin_workout_id", table_name="training_workout")
    op.drop_index("ix_training_workout_user_provider", table_name="training_workout")
    op.drop_table("training_workout")
