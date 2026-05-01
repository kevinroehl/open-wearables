from datetime import date, datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import BaseDbModel
from app.mappings import FKUser, ManyToOne, OneToMany, PrimaryKey, str_32, str_64, str_100


class TrainingWorkout(BaseDbModel):
    __tablename__ = "training_workout"
    __table_args__ = (
        Index("ix_training_workout_user_provider", "user_id", "provider"),
        Index("ix_training_workout_garmin_workout_id", "garmin_workout_id"),
    )

    id: Mapped[PrimaryKey[UUID]]
    user_id: Mapped[FKUser]
    provider: Mapped[str_64]

    workout_name: Mapped[str_100]
    description: Mapped[str | None]
    sport: Mapped[str_32]
    steps_json: Mapped[dict] = mapped_column(JSONB)
    workout_provider: Mapped[str] = mapped_column(String(20))
    workout_source_id: Mapped[str] = mapped_column(String(20))

    garmin_workout_id: Mapped[str_100 | None]
    garmin_owner_id: Mapped[str_100 | None]
    publish_status: Mapped[str_32]
    last_error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    user: Mapped[ManyToOne["User"]] = relationship("User")
    schedules: Mapped[OneToMany["TrainingSchedule"]] = relationship(
        "TrainingSchedule",
        back_populates="workout",
        cascade="all, delete-orphan",
    )


class TrainingSchedule(BaseDbModel):
    __tablename__ = "training_schedule"
    __table_args__ = (
        Index("ix_training_schedule_user_provider_date", "user_id", "provider", "scheduled_date"),
        Index("ix_training_schedule_garmin_schedule_id", "garmin_schedule_id"),
    )

    id: Mapped[PrimaryKey[UUID]]
    user_id: Mapped[FKUser]
    provider: Mapped[str_64]
    workout_id: Mapped[UUID] = mapped_column(ForeignKey("training_workout.id", ondelete="CASCADE"))

    scheduled_date: Mapped[date]
    garmin_schedule_id: Mapped[str_100 | None]
    publish_status: Mapped[str_32]
    last_error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    user: Mapped[ManyToOne["User"]] = relationship("User")
    workout: Mapped[ManyToOne[TrainingWorkout]] = relationship("TrainingWorkout", back_populates="schedules")


class TrainingPublishJob(BaseDbModel):
    __tablename__ = "training_publish_job"
    __table_args__ = (
        Index("ix_training_publish_job_user_status", "user_id", "status"),
        Index("ix_training_publish_job_entity", "entity_type", "entity_id"),
    )

    id: Mapped[PrimaryKey[UUID]]
    user_id: Mapped[FKUser]
    provider: Mapped[str_64]

    entity_type: Mapped[str_32]
    entity_id: Mapped[UUID]
    action: Mapped[str_32]
    status: Mapped[str_32]
    attempts: Mapped[int]

    garmin_status_code: Mapped[int | None]
    garmin_response_json: Mapped[dict | None] = mapped_column(JSONB)
    error_code: Mapped[str_64 | None]
    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    user: Mapped[ManyToOne["User"]] = relationship("User")
