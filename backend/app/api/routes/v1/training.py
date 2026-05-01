from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.database import DbSession
from app.schemas.training import (
    TrainingPublishJobRead,
    TrainingScheduleCreate,
    TrainingScheduleMutationResponse,
    TrainingScheduleRead,
    TrainingWorkoutCreate,
    TrainingWorkoutMutationResponse,
    TrainingWorkoutRead,
    TrainingWorkoutUpdate,
)
from app.services import ApiKeyDep
from app.services.training_service import training_service

router = APIRouter()


@router.post(
    "/users/{user_id}/training/workouts",
    status_code=status.HTTP_201_CREATED,
)
def create_training_workout(
    user_id: UUID,
    payload: TrainingWorkoutCreate,
    db: DbSession,
    _api_key: ApiKeyDep,
) -> TrainingWorkoutMutationResponse:
    return training_service.create_workout(db, user_id, payload)


@router.get("/users/{user_id}/training/workouts/{workout_id}")
def get_training_workout(
    user_id: UUID,
    workout_id: UUID,
    db: DbSession,
    _api_key: ApiKeyDep,
) -> TrainingWorkoutRead:
    return training_service.get_workout(db, user_id, workout_id)


@router.put("/users/{user_id}/training/workouts/{workout_id}")
def update_training_workout(
    user_id: UUID,
    workout_id: UUID,
    payload: TrainingWorkoutUpdate,
    db: DbSession,
    _api_key: ApiKeyDep,
) -> TrainingWorkoutMutationResponse:
    return training_service.update_workout(db, user_id, workout_id, payload)


@router.delete("/users/{user_id}/training/workouts/{workout_id}")
def delete_training_workout(
    user_id: UUID,
    workout_id: UUID,
    db: DbSession,
    _api_key: ApiKeyDep,
) -> TrainingWorkoutMutationResponse:
    return training_service.delete_workout(db, user_id, workout_id)


@router.post("/users/{user_id}/training/workouts/{workout_id}/publish")
def publish_training_workout(
    user_id: UUID,
    workout_id: UUID,
    db: DbSession,
    _api_key: ApiKeyDep,
) -> TrainingPublishJobRead:
    return training_service.publish_workout(db, user_id, workout_id)


@router.post(
    "/users/{user_id}/training/schedules",
    status_code=status.HTTP_201_CREATED,
)
def create_training_schedule(
    user_id: UUID,
    payload: TrainingScheduleCreate,
    db: DbSession,
    _api_key: ApiKeyDep,
) -> TrainingScheduleMutationResponse:
    return training_service.create_schedule(db, user_id, payload)


@router.get("/users/{user_id}/training/schedules")
def list_training_schedules(
    user_id: UUID,
    db: DbSession,
    _api_key: ApiKeyDep,
    start_date: Annotated[date, Query(description="Start date in YYYY-MM-DD format")],
    end_date: Annotated[date, Query(description="End date in YYYY-MM-DD format")],
) -> list[TrainingScheduleRead]:
    return training_service.list_schedules(db, user_id, start_date, end_date)


@router.delete("/users/{user_id}/training/schedules/{schedule_id}")
def delete_training_schedule(
    user_id: UUID,
    schedule_id: UUID,
    db: DbSession,
    _api_key: ApiKeyDep,
) -> TrainingScheduleMutationResponse:
    return training_service.delete_schedule(db, user_id, schedule_id)


@router.get("/users/{user_id}/training/jobs/{job_id}")
def get_training_job(
    user_id: UUID,
    job_id: UUID,
    db: DbSession,
    _api_key: ApiKeyDep,
) -> TrainingPublishJobRead:
    return training_service.get_job(db, user_id, job_id)
