from datetime import date
from uuid import UUID

from sqlalchemy import and_

from app.database import DbSession
from app.models import TrainingPublishJob, TrainingSchedule, TrainingWorkout
from app.repositories.repositories import CrudRepository
from app.schemas.training import (
    TrainingPublishJobCreateInternal,
    TrainingPublishJobUpdateInternal,
    TrainingScheduleCreateInternal,
    TrainingScheduleUpdateInternal,
    TrainingWorkoutCreateInternal,
    TrainingWorkoutUpdateInternal,
)


class TrainingWorkoutRepository(
    CrudRepository[TrainingWorkout, TrainingWorkoutCreateInternal, TrainingWorkoutUpdateInternal],
):
    def __init__(self, model: type[TrainingWorkout] = TrainingWorkout):
        super().__init__(model)

    def get_for_user(self, db: DbSession, user_id: UUID, workout_id: UUID) -> TrainingWorkout | None:
        return (
            db.query(self.model).filter(and_(self.model.id == workout_id, self.model.user_id == user_id)).one_or_none()
        )


class TrainingScheduleRepository(
    CrudRepository[TrainingSchedule, TrainingScheduleCreateInternal, TrainingScheduleUpdateInternal],
):
    def __init__(self, model: type[TrainingSchedule] = TrainingSchedule):
        super().__init__(model)

    def get_for_user(self, db: DbSession, user_id: UUID, schedule_id: UUID) -> TrainingSchedule | None:
        return (
            db.query(self.model).filter(and_(self.model.id == schedule_id, self.model.user_id == user_id)).one_or_none()
        )

    def list_for_user_in_range(
        self,
        db: DbSession,
        user_id: UUID,
        start_date: date,
        end_date: date,
    ) -> list[TrainingSchedule]:
        return (
            db.query(self.model)
            .filter(
                and_(
                    self.model.user_id == user_id,
                    self.model.scheduled_date >= start_date,
                    self.model.scheduled_date <= end_date,
                ),
            )
            .order_by(self.model.scheduled_date.asc())
            .all()
        )


class TrainingPublishJobRepository(
    CrudRepository[TrainingPublishJob, TrainingPublishJobCreateInternal, TrainingPublishJobUpdateInternal],
):
    def __init__(self, model: type[TrainingPublishJob] = TrainingPublishJob):
        super().__init__(model)

    def get_for_user(self, db: DbSession, user_id: UUID, job_id: UUID) -> TrainingPublishJob | None:
        return db.query(self.model).filter(and_(self.model.id == job_id, self.model.user_id == user_id)).one_or_none()
