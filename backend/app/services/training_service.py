from datetime import date, datetime, timezone
from logging import Logger, getLogger
from uuid import UUID

from fastapi import HTTPException, status
from pydantic import TypeAdapter

from app.database import DbSession
from app.models import TrainingPublishJob, TrainingSchedule, TrainingWorkout, User
from app.repositories import (
    TrainingPublishJobRepository,
    TrainingScheduleRepository,
    TrainingWorkoutRepository,
    UserConnectionRepository,
    UserRepository,
)
from app.schemas.training import (
    TrainingJobAction,
    TrainingJobEntityType,
    TrainingPublishJobCreateInternal,
    TrainingPublishJobRead,
    TrainingPublishStatus,
    TrainingScheduleCreate,
    TrainingScheduleCreateInternal,
    TrainingScheduleMutationResponse,
    TrainingScheduleRead,
    TrainingScheduleUpdateInternal,
    TrainingStep,
    TrainingWorkoutCreate,
    TrainingWorkoutCreateInternal,
    TrainingWorkoutMutationResponse,
    TrainingWorkoutRead,
    TrainingWorkoutUpdate,
    TrainingWorkoutUpdateInternal,
)


class TrainingService:
    def __init__(self, log: Logger, **kwargs):
        super().__init__(**kwargs)
        self.logger = log
        self.user_repo = UserRepository(User)
        self.connection_repo = UserConnectionRepository()
        self.workout_repo = TrainingWorkoutRepository()
        self.schedule_repo = TrainingScheduleRepository()
        self.job_repo = TrainingPublishJobRepository()

    def create_workout(
        self,
        db: DbSession,
        user_id: UUID,
        payload: TrainingWorkoutCreate,
    ) -> TrainingWorkoutMutationResponse:
        self._require_user_and_garmin_connection(db, user_id)
        workout = self.workout_repo.create(
            db,
            TrainingWorkoutCreateInternal(
                user_id=user_id,
                workout_name=payload.workout_name,
                description=payload.description,
                sport=payload.sport.value,
                steps_json={"steps": TypeAdapter(list[TrainingStep]).dump_python(payload.steps, mode="json")},
                workout_provider=payload.workout_provider,
                workout_source_id=payload.workout_source_id,
                publish_status=TrainingPublishStatus.QUEUED if payload.publish else TrainingPublishStatus.DRAFT,
            ),
        )
        job = None
        if payload.publish:
            job = self._create_job(db, user_id, TrainingJobEntityType.WORKOUT, workout.id, TrainingJobAction.CREATE)
            self._enqueue_job(job.id)
        return TrainingWorkoutMutationResponse(
            workout=self._workout_read(workout),
            job=self._job_read(job) if job else None,
        )

    def get_workout(self, db: DbSession, user_id: UUID, workout_id: UUID) -> TrainingWorkoutRead:
        workout = self._get_workout_or_404(db, user_id, workout_id)
        return self._workout_read(workout)

    def update_workout(
        self,
        db: DbSession,
        user_id: UUID,
        workout_id: UUID,
        payload: TrainingWorkoutUpdate,
    ) -> TrainingWorkoutMutationResponse:
        self._require_user_and_garmin_connection(db, user_id)
        workout = self._get_workout_or_404(db, user_id, workout_id)
        updated = self.workout_repo.update(
            db,
            workout,
            TrainingWorkoutUpdateInternal(
                workout_name=payload.workout_name,
                description=payload.description,
                sport=payload.sport.value,
                steps_json={"steps": TypeAdapter(list[TrainingStep]).dump_python(payload.steps, mode="json")},
                workout_provider=payload.workout_provider,
                workout_source_id=payload.workout_source_id,
                publish_status=TrainingPublishStatus.QUEUED if payload.publish else TrainingPublishStatus.DRAFT,
            ),
        )
        job = None
        if payload.publish:
            action = TrainingJobAction.UPDATE if updated.garmin_workout_id else TrainingJobAction.CREATE
            job = self._create_job(db, user_id, TrainingJobEntityType.WORKOUT, updated.id, action)
            self._enqueue_job(job.id)
        return TrainingWorkoutMutationResponse(
            workout=self._workout_read(updated),
            job=self._job_read(job) if job else None,
        )

    def delete_workout(
        self,
        db: DbSession,
        user_id: UUID,
        workout_id: UUID,
    ) -> TrainingWorkoutMutationResponse:
        self._require_user_and_garmin_connection(db, user_id)
        workout = self._get_workout_or_404(db, user_id, workout_id)
        if not workout.garmin_workout_id:
            workout.publish_status = TrainingPublishStatus.DELETED.value
            deleted_read = self._workout_read(workout)
            self.workout_repo.delete(db, workout)
            return TrainingWorkoutMutationResponse(workout=deleted_read, job=None)

        updated = self.workout_repo.update(
            db,
            workout,
            TrainingWorkoutUpdateInternal(publish_status=TrainingPublishStatus.QUEUED),
        )
        job = self._create_job(db, user_id, TrainingJobEntityType.WORKOUT, workout.id, TrainingJobAction.DELETE)
        self._enqueue_job(job.id)
        return TrainingWorkoutMutationResponse(workout=self._workout_read(updated), job=self._job_read(job))

    def publish_workout(self, db: DbSession, user_id: UUID, workout_id: UUID) -> TrainingPublishJobRead:
        self._require_user_and_garmin_connection(db, user_id)
        workout = self._get_workout_or_404(db, user_id, workout_id)
        action = TrainingJobAction.UPDATE if workout.garmin_workout_id else TrainingJobAction.CREATE
        self._set_workout_status(db, workout, TrainingPublishStatus.QUEUED)
        job = self._create_job(db, user_id, TrainingJobEntityType.WORKOUT, workout.id, action)
        self._enqueue_job(job.id)
        return self._job_read(job)

    def create_schedule(
        self,
        db: DbSession,
        user_id: UUID,
        payload: TrainingScheduleCreate,
    ) -> TrainingScheduleMutationResponse:
        self._require_user_and_garmin_connection(db, user_id)
        workout = self._get_workout_or_404(db, user_id, payload.workout_id)
        schedule = self.schedule_repo.create(
            db,
            TrainingScheduleCreateInternal(
                user_id=user_id,
                workout_id=workout.id,
                scheduled_date=payload.scheduled_date,
                publish_status=TrainingPublishStatus.QUEUED if payload.publish else TrainingPublishStatus.DRAFT,
            ),
        )
        job = None
        if payload.publish:
            if not workout.garmin_workout_id:
                workout_job = self._create_job(
                    db,
                    user_id,
                    TrainingJobEntityType.WORKOUT,
                    workout.id,
                    TrainingJobAction.CREATE,
                )
                self._set_workout_status(db, workout, TrainingPublishStatus.QUEUED)
                self._enqueue_job(workout_job.id)
            job = self._create_job(db, user_id, TrainingJobEntityType.SCHEDULE, schedule.id, TrainingJobAction.CREATE)
            self._enqueue_job(job.id)
        return TrainingScheduleMutationResponse(
            schedule=self._schedule_read(schedule),
            job=self._job_read(job) if job else None,
        )

    def list_schedules(
        self,
        db: DbSession,
        user_id: UUID,
        start_date: date,
        end_date: date,
    ) -> list[TrainingScheduleRead]:
        self._require_user(db, user_id)
        if start_date > end_date:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="start_date must be before end_date")
        schedules = self.schedule_repo.list_for_user_in_range(db, user_id, start_date, end_date)
        return [self._schedule_read(schedule) for schedule in schedules]

    def delete_schedule(
        self,
        db: DbSession,
        user_id: UUID,
        schedule_id: UUID,
    ) -> TrainingScheduleMutationResponse:
        self._require_user_and_garmin_connection(db, user_id)
        schedule = self._get_schedule_or_404(db, user_id, schedule_id)
        if not schedule.garmin_schedule_id:
            schedule.publish_status = TrainingPublishStatus.DELETED.value
            deleted_read = self._schedule_read(schedule)
            self.schedule_repo.delete(db, schedule)
            return TrainingScheduleMutationResponse(schedule=deleted_read, job=None)

        updated = self.schedule_repo.update(
            db,
            schedule,
            TrainingScheduleUpdateInternal(publish_status=TrainingPublishStatus.QUEUED),
        )
        job = self._create_job(db, user_id, TrainingJobEntityType.SCHEDULE, schedule.id, TrainingJobAction.DELETE)
        self._enqueue_job(job.id)
        return TrainingScheduleMutationResponse(schedule=self._schedule_read(updated), job=self._job_read(job))

    def get_job(self, db: DbSession, user_id: UUID, job_id: UUID) -> TrainingPublishJobRead:
        job = self.job_repo.get_for_user(db, user_id, job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training publish job not found")
        return self._job_read(job)

    def _create_job(
        self,
        db: DbSession,
        user_id: UUID,
        entity_type: TrainingJobEntityType,
        entity_id: UUID,
        action: TrainingJobAction,
    ) -> TrainingPublishJob:
        return self.job_repo.create(
            db,
            TrainingPublishJobCreateInternal(
                user_id=user_id,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
            ),
        )

    def _enqueue_job(self, job_id: UUID) -> None:
        from app.integrations.celery.tasks.garmin_training_task import publish_garmin_training_item

        publish_garmin_training_item.delay(str(job_id))

    def _require_user_and_garmin_connection(self, db: DbSession, user_id: UUID) -> None:
        self._require_user(db, user_id)
        connection = self.connection_repo.get_active_connection(db, user_id, "garmin")
        if not connection:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is not connected to Garmin")

    def _require_user(self, db: DbSession, user_id: UUID) -> None:
        if not self.user_repo.get(db, user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    def _get_workout_or_404(self, db: DbSession, user_id: UUID, workout_id: UUID) -> TrainingWorkout:
        workout = self.workout_repo.get_for_user(db, user_id, workout_id)
        if not workout:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training workout not found")
        return workout

    def _get_schedule_or_404(self, db: DbSession, user_id: UUID, schedule_id: UUID) -> TrainingSchedule:
        schedule = self.schedule_repo.get_for_user(db, user_id, schedule_id)
        if not schedule:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training schedule not found")
        return schedule

    def _set_workout_status(
        self,
        db: DbSession,
        workout: TrainingWorkout,
        publish_status: TrainingPublishStatus,
        last_error: str | None = None,
    ) -> TrainingWorkout:
        workout.publish_status = publish_status.value
        workout.last_error = last_error
        workout.updated_at = datetime.now(timezone.utc)
        db.add(workout)
        db.commit()
        db.refresh(workout)
        return workout

    def _workout_read(self, workout: TrainingWorkout) -> TrainingWorkoutRead:
        return TrainingWorkoutRead(
            id=workout.id,
            user_id=workout.user_id,
            provider=workout.provider,
            workout_name=workout.workout_name,
            description=workout.description,
            sport=workout.sport,
            steps=TypeAdapter(list[TrainingStep]).validate_python(workout.steps_json["steps"]),
            workout_provider=workout.workout_provider,
            workout_source_id=workout.workout_source_id,
            garmin_workout_id=workout.garmin_workout_id,
            garmin_owner_id=workout.garmin_owner_id,
            publish_status=TrainingPublishStatus(workout.publish_status),
            last_error=workout.last_error,
            created_at=workout.created_at,
            updated_at=workout.updated_at,
        )

    def _schedule_read(self, schedule: TrainingSchedule) -> TrainingScheduleRead:
        return TrainingScheduleRead.model_validate(schedule)

    def _job_read(self, job: TrainingPublishJob) -> TrainingPublishJobRead:
        return TrainingPublishJobRead.model_validate(job)


training_service = TrainingService(log=getLogger(__name__))
