from datetime import datetime, timezone
from logging import getLogger
from typing import Any
from uuid import UUID

from fastapi import HTTPException

from app.database import SessionLocal
from app.models import TrainingPublishJob
from app.repositories import TrainingPublishJobRepository, TrainingScheduleRepository, TrainingWorkoutRepository
from app.schemas.training import (
    TrainingJobAction,
    TrainingJobEntityType,
    TrainingJobStatus,
    TrainingPublishStatus,
)
from app.services.providers.garmin.strategy import GarminStrategy
from app.services.providers.garmin.training import (
    GarminTrainingPermanentError,
    GarminTrainingRetryableError,
    build_garmin_schedule_payload,
    build_garmin_workout_payload,
    handle_garmin_training_http_exception,
)
from app.utils.sentry_helpers import log_and_capture_error
from app.utils.structured_logging import log_structured
from celery import shared_task

logger = getLogger(__name__)

MAX_ATTEMPTS = 4
RETRY_COUNTDOWN_SECONDS = 60


@shared_task(bind=True, max_retries=MAX_ATTEMPTS - 1)
def publish_garmin_training_item(self: Any, job_id: str) -> dict[str, Any]:
    """Publish one local training workout or schedule to Garmin Connect."""
    try:
        job_uuid = UUID(job_id)
    except ValueError as e:
        log_and_capture_error(e, logger, f"Invalid Garmin training job id: {job_id}")
        return {"status": "failed", "error": "invalid_job_id"}

    with SessionLocal() as db:
        try:
            job = _mark_job_running(db, job_uuid)
            result = _execute_job(db, job)
            _mark_job_succeeded(db, job, result)
            return {"status": "succeeded", "job_id": str(job.id), "result": result}
        except GarminTrainingPermanentError as e:
            job = _get_job(db, job_uuid)
            if job:
                _mark_job_failed(db, job, e.code, e.message, e.status_code)
                _mark_entity_failed(db, job, e.message)
            return {"status": "failed", "job_id": job_id, "error_code": e.code, "error": e.message}
        except GarminTrainingRetryableError as e:
            job = _get_job(db, job_uuid)
            if not job:
                return {"status": "failed", "job_id": job_id, "error": e.message}
            if job.attempts >= MAX_ATTEMPTS:
                error_code = "RATE_LIMITED" if e.status_code == 429 else "GARMIN_UNAVAILABLE"
                _mark_job_failed(db, job, error_code, e.message, e.status_code)
                _mark_entity_failed(db, job, e.message)
                return {"status": "failed", "job_id": job_id, "error_code": error_code, "error": e.message}
            _mark_job_retrying(db, job, e.message, e.status_code)
            raise self.retry(countdown=RETRY_COUNTDOWN_SECONDS * job.attempts, exc=e) from e
        except HTTPException as e:
            try:
                handle_garmin_training_http_exception(e)
            except (GarminTrainingPermanentError, GarminTrainingRetryableError) as converted:
                raise converted from e
            raise
        except Exception as e:
            log_and_capture_error(e, logger, f"Unexpected Garmin training publish failure for job {job_id}")
            job = _get_job(db, job_uuid)
            if job:
                if job.attempts >= MAX_ATTEMPTS:
                    _mark_job_failed(db, job, "GARMIN_UNAVAILABLE", str(e), None)
                    _mark_entity_failed(db, job, str(e))
                    return {"status": "failed", "job_id": job_id, "error_code": "GARMIN_UNAVAILABLE", "error": str(e)}
                _mark_job_retrying(db, job, str(e), None)
            raise self.retry(countdown=RETRY_COUNTDOWN_SECONDS, exc=e) from e


def _execute_job(db: Any, job: TrainingPublishJob) -> dict[str, Any]:
    strategy = GarminStrategy()
    if not strategy.training:
        raise GarminTrainingPermanentError(None, "TRAINING_NOT_CONFIGURED", "Garmin Training client is not configured")

    client = strategy.training
    try:
        client.assert_workout_import_permission(db, job.user_id)
        entity_type = TrainingJobEntityType(job.entity_type)
        action = TrainingJobAction(job.action)
        if entity_type == TrainingJobEntityType.WORKOUT:
            return _execute_workout_job(db, client, job, action)
        return _execute_schedule_job(db, client, job, action)
    except HTTPException as e:
        handle_garmin_training_http_exception(e)
        raise


def _execute_workout_job(db: Any, client: Any, job: TrainingPublishJob, action: TrainingJobAction) -> dict[str, Any]:
    workout = TrainingWorkoutRepository().get_for_user(db, job.user_id, job.entity_id)
    if not workout:
        raise GarminTrainingPermanentError(None, "WORKOUT_NOT_FOUND", "Training workout not found")

    if action == TrainingJobAction.DELETE:
        if workout.garmin_workout_id:
            result = client.delete_workout(db, job.user_id, workout.garmin_workout_id)
        else:
            result = {"status_code": 204, "accepted": True}
        workout.publish_status = TrainingPublishStatus.DELETED.value
        workout.updated_at = datetime.now(timezone.utc)
        db.add(workout)
        db.commit()
        return result

    include_ids = action == TrainingJobAction.UPDATE
    payload = build_garmin_workout_payload(workout, include_ids=include_ids)
    result = (
        client.update_workout(db, job.user_id, workout.garmin_workout_id, payload)
        if action == TrainingJobAction.UPDATE and workout.garmin_workout_id
        else client.create_workout(db, job.user_id, payload)
    )
    if action == TrainingJobAction.CREATE:
        garmin_workout_id = result.get("workoutId")
        if garmin_workout_id is None:
            raise GarminTrainingPermanentError(None, "MISSING_GARMIN_WORKOUT_ID", "Garmin did not return workoutId")
        workout.garmin_workout_id = str(garmin_workout_id)
        owner_id = result.get("ownerId")
        workout.garmin_owner_id = str(owner_id) if owner_id is not None else workout.garmin_owner_id
    workout.publish_status = TrainingPublishStatus.PUBLISHED.value
    workout.last_error = None
    workout.updated_at = datetime.now(timezone.utc)
    db.add(workout)
    db.commit()
    return result


def _execute_schedule_job(db: Any, client: Any, job: TrainingPublishJob, action: TrainingJobAction) -> dict[str, Any]:
    schedule_repo = TrainingScheduleRepository()
    schedule = schedule_repo.get_for_user(db, job.user_id, job.entity_id)
    if not schedule:
        raise GarminTrainingPermanentError(None, "SCHEDULE_NOT_FOUND", "Training schedule not found")

    if action == TrainingJobAction.DELETE:
        if schedule.garmin_schedule_id:
            result = client.delete_schedule(db, job.user_id, schedule.garmin_schedule_id)
        else:
            result = {"status_code": 204, "accepted": True}
        schedule.publish_status = TrainingPublishStatus.DELETED.value
        schedule.updated_at = datetime.now(timezone.utc)
        db.add(schedule)
        db.commit()
        return result

    workout = TrainingWorkoutRepository().get_for_user(db, job.user_id, schedule.workout_id)
    if not workout or not workout.garmin_workout_id:
        raise GarminTrainingRetryableError(None, "Workout must be published before schedule can be published")

    payload = build_garmin_schedule_payload(
        workout.garmin_workout_id,
        schedule.scheduled_date.isoformat(),
        schedule.garmin_schedule_id if action == TrainingJobAction.UPDATE else None,
    )
    result = (
        client.update_schedule(db, job.user_id, schedule.garmin_schedule_id, payload)
        if action == TrainingJobAction.UPDATE and schedule.garmin_schedule_id
        else client.create_schedule(db, job.user_id, payload)
    )
    if action == TrainingJobAction.CREATE:
        schedule_id = result.get("scheduleId")
        if schedule_id is None:
            raise GarminTrainingPermanentError(None, "MISSING_GARMIN_SCHEDULE_ID", "Garmin did not return scheduleId")
        schedule.garmin_schedule_id = str(schedule_id)
    schedule.publish_status = TrainingPublishStatus.PUBLISHED.value
    schedule.last_error = None
    schedule.updated_at = datetime.now(timezone.utc)
    db.add(schedule)
    db.commit()
    return result


def _get_job(db: Any, job_id: UUID) -> TrainingPublishJob | None:
    return TrainingPublishJobRepository().get(db, job_id)


def _mark_job_running(db: Any, job_id: UUID) -> TrainingPublishJob:
    job = _get_job(db, job_id)
    if not job:
        raise GarminTrainingPermanentError(None, "JOB_NOT_FOUND", "Training publish job not found")
    job.status = TrainingJobStatus.RUNNING.value
    job.attempts += 1
    job.error_code = None
    job.error_message = None
    job.updated_at = datetime.now(timezone.utc)
    db.add(job)
    db.commit()
    db.refresh(job)
    log_structured(logger, "info", "Publishing Garmin training item", job_id=str(job.id), attempts=job.attempts)
    return job


def _mark_job_succeeded(db: Any, job: TrainingPublishJob, result: dict[str, Any]) -> None:
    job.status = TrainingJobStatus.SUCCEEDED.value
    job.garmin_status_code = result.get("status_code") if isinstance(result, dict) else None
    job.garmin_response_json = result if isinstance(result, dict) else None
    job.error_code = None
    job.error_message = None
    job.updated_at = datetime.now(timezone.utc)
    db.add(job)
    db.commit()


def _mark_job_retrying(db: Any, job: TrainingPublishJob, message: str, status_code: int | None) -> None:
    job.status = TrainingJobStatus.RETRYING.value
    job.garmin_status_code = status_code
    job.error_code = "RATE_LIMITED" if status_code == 429 else "GARMIN_UNAVAILABLE"
    job.error_message = message
    job.updated_at = datetime.now(timezone.utc)
    db.add(job)
    db.commit()


def _mark_job_failed(
    db: Any,
    job: TrainingPublishJob,
    error_code: str,
    message: str,
    status_code: int | None,
) -> None:
    job.status = TrainingJobStatus.FAILED.value
    job.garmin_status_code = status_code
    job.error_code = error_code
    job.error_message = message
    job.updated_at = datetime.now(timezone.utc)
    db.add(job)
    db.commit()


def _mark_entity_failed(db: Any, job: TrainingPublishJob, message: str) -> None:
    if job.entity_type == TrainingJobEntityType.WORKOUT.value:
        entity = TrainingWorkoutRepository().get_for_user(db, job.user_id, job.entity_id)
    else:
        entity = TrainingScheduleRepository().get_for_user(db, job.user_id, job.entity_id)
    if entity:
        entity.publish_status = TrainingPublishStatus.FAILED.value
        entity.last_error = message
        entity.updated_at = datetime.now(timezone.utc)
        db.add(entity)
        db.commit()
