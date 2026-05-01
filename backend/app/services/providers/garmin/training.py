from typing import Any
from uuid import UUID

from fastapi import HTTPException
from pydantic import TypeAdapter

from app.database import DbSession
from app.models import TrainingWorkout
from app.repositories import UserConnectionRepository
from app.schemas.training import (
    TrainingDurationType,
    TrainingRepeatStep,
    TrainingStep,
    TrainingTargetType,
    TrainingWorkoutStep,
)
from app.services.providers.api_client import make_authenticated_request
from app.services.providers.templates.base_oauth import BaseOAuthTemplate

GARMIN_WORKOUT_IMPORT_PERMISSION = "WORKOUT_IMPORT"


class GarminTrainingRetryableError(Exception):
    def __init__(self, status_code: int | None, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class GarminTrainingPermanentError(Exception):
    def __init__(self, status_code: int | None, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


class GarminTrainingClient:
    """Client for Garmin Training API workout and schedule import endpoints."""

    def __init__(
        self,
        provider_name: str,
        api_base_url: str,
        oauth: BaseOAuthTemplate,
        connection_repo: UserConnectionRepository | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.api_base_url = api_base_url
        self.oauth = oauth
        self.connection_repo = connection_repo or UserConnectionRepository()

    def _request(
        self,
        db: DbSession,
        user_id: UUID,
        endpoint: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        expect_json: bool = True,
    ) -> Any:
        return make_authenticated_request(
            db=db,
            user_id=user_id,
            connection_repo=self.connection_repo,
            oauth=self.oauth,
            api_base_url=self.api_base_url,
            provider_name=self.provider_name,
            endpoint=endpoint,
            method=method,
            params=params,
            json_data=json_data,
            headers={"Content-Type": "application/json"} if json_data is not None else None,
            expect_json=expect_json,
        )

    def get_permissions(self, db: DbSession, user_id: UUID) -> list[str]:
        response = self._request(db, user_id, "/userPermissions/")
        if isinstance(response, list):
            return [str(item) for item in response]
        if isinstance(response, dict):
            permissions = response.get("permissions") or response.get("userPermissions") or response.get("data")
            if isinstance(permissions, list):
                return [str(item) for item in permissions]
        return []

    def assert_workout_import_permission(self, db: DbSession, user_id: UUID) -> None:
        if GARMIN_WORKOUT_IMPORT_PERMISSION not in self.get_permissions(db, user_id):
            raise GarminTrainingPermanentError(
                status_code=412,
                code="MISSING_WORKOUT_IMPORT_PERMISSION",
                message="Garmin user has not granted WORKOUT_IMPORT permission.",
            )

    def create_workout(self, db: DbSession, user_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
        result = self._request(db, user_id, "/workoutportal/workout/v2", method="POST", json_data=payload)
        return result if isinstance(result, dict) else {}

    def retrieve_workout(self, db: DbSession, user_id: UUID, workout_id: str) -> dict[str, Any]:
        result = self._request(db, user_id, f"/training-api/workout/v2/{workout_id}")
        return result if isinstance(result, dict) else {}

    def update_workout(self, db: DbSession, user_id: UUID, workout_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = self._request(
            db,
            user_id,
            f"/training-api/workout/v2/{workout_id}",
            method="PUT",
            json_data=payload,
            expect_json=False,
        )
        return result if isinstance(result, dict) else {}

    def delete_workout(self, db: DbSession, user_id: UUID, workout_id: str) -> dict[str, Any]:
        result = self._request(
            db,
            user_id,
            f"/training-api/workout/v2/{workout_id}",
            method="DELETE",
            expect_json=False,
        )
        return result if isinstance(result, dict) else {}

    def create_schedule(self, db: DbSession, user_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
        result = self._request(db, user_id, "/training-api/schedule/", method="POST", json_data=payload)
        return result if isinstance(result, dict) else {}

    def retrieve_schedule(self, db: DbSession, user_id: UUID, schedule_id: str) -> dict[str, Any]:
        result = self._request(db, user_id, f"/training-api/schedule/{schedule_id}")
        return result if isinstance(result, dict) else {}

    def update_schedule(
        self,
        db: DbSession,
        user_id: UUID,
        schedule_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        result = self._request(
            db,
            user_id,
            f"/training-api/schedule/{schedule_id}",
            method="PUT",
            json_data=payload,
        )
        return result if isinstance(result, dict) else {}

    def delete_schedule(self, db: DbSession, user_id: UUID, schedule_id: str) -> dict[str, Any]:
        result = self._request(
            db,
            user_id,
            f"/training-api/schedule/{schedule_id}",
            method="DELETE",
            expect_json=False,
        )
        return result if isinstance(result, dict) else {}

    def retrieve_schedules_by_date(
        self,
        db: DbSession,
        user_id: UUID,
        start_date: str,
        end_date: str,
    ) -> Any:
        return self._request(
            db,
            user_id,
            "/training-api/schedule",
            params={"startDate": start_date, "endDate": end_date},
        )


def handle_garmin_training_http_exception(exc: HTTPException) -> None:
    status_code = exc.status_code
    message = str(exc.detail)
    if status_code == 429:
        raise GarminTrainingRetryableError(status_code, message) from exc
    if status_code >= 500:
        raise GarminTrainingRetryableError(status_code, message) from exc
    if status_code in {400, 401, 403, 412}:
        code = {
            400: "INVALID_GARMIN_PAYLOAD",
            401: "GARMIN_AUTH_EXPIRED",
            403: "GARMIN_FORBIDDEN",
            412: "MISSING_WORKOUT_IMPORT_PERMISSION",
        }.get(status_code, "GARMIN_ERROR")
        raise GarminTrainingPermanentError(status_code, code, message) from exc
    raise GarminTrainingPermanentError(status_code, "GARMIN_ERROR", message) from exc


def build_garmin_workout_payload(workout: TrainingWorkout, include_ids: bool = False) -> dict[str, Any]:
    steps = TypeAdapter(list[TrainingStep]).validate_python(workout.steps_json["steps"])
    step_order = 1

    def next_order() -> int:
        nonlocal step_order
        current = step_order
        step_order += 1
        return current

    garmin_steps = [_map_step(step, next_order) for step in steps]
    payload: dict[str, Any] = {
        "workoutName": workout.workout_name,
        "description": workout.description,
        "sport": workout.sport,
        "poolLength": None,
        "poolLengthUnit": None,
        "workoutProvider": workout.workout_provider,
        "workoutSourceId": workout.workout_source_id,
        "isSessionTransitionEnabled": False,
        "segments": [
            {
                "segmentOrder": 1,
                "sport": workout.sport,
                "poolLength": None,
                "poolLengthUnit": None,
                "estimatedDurationInSecs": None,
                "estimatedDistanceInMeters": None,
                "steps": garmin_steps,
            }
        ],
    }
    if include_ids:
        if workout.garmin_workout_id:
            payload["workoutId"] = int(workout.garmin_workout_id)
        if workout.garmin_owner_id:
            payload["ownerId"] = int(workout.garmin_owner_id)
    return payload


def build_garmin_schedule_payload(
    workout_id: str,
    scheduled_date: str,
    schedule_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"workoutId": int(workout_id), "date": scheduled_date}
    if schedule_id:
        payload["scheduleId"] = int(schedule_id)
    return payload


def _map_step(step: TrainingStep, next_order: Any) -> dict[str, Any]:
    if isinstance(step, TrainingRepeatStep):
        return {
            "type": "WorkoutRepeatStep",
            "stepOrder": next_order(),
            "repeatType": step.repeat_type.value,
            "repeatValue": step.repeat_value,
            "skipLastRestStep": False,
            "steps": [_map_workout_step(child, next_order) for child in step.steps],
        }
    return _map_workout_step(step, next_order)


def _map_workout_step(step: TrainingWorkoutStep, next_order: Any) -> dict[str, Any]:
    return {
        "type": "WorkoutStep",
        "stepOrder": next_order(),
        "intensity": step.intensity.value,
        "description": step.description,
        "durationType": step.duration_type.value,
        "durationValue": step.duration_value,
        "durationValueType": _duration_value_type(step.duration_type),
        "targetType": step.target_type.value if step.target_type != TrainingTargetType.OPEN else "OPEN",
        "targetValue": step.target_value,
        "targetValueLow": step.target_value_low,
        "targetValueHigh": step.target_value_high,
        "targetValueType": step.target_value_type.value if step.target_value_type else None,
        "secondaryTargetType": None,
        "secondaryTargetValue": None,
        "secondaryTargetValueLow": None,
        "secondaryTargetValueHigh": None,
        "secondaryTargetValueType": None,
        "strokeType": None,
        "drillType": None,
        "equipmentType": None,
        "exerciseCategory": None,
        "exerciseName": None,
        "weightValue": None,
        "weightDisplayUnit": None,
    }


def _duration_value_type(duration_type: TrainingDurationType) -> str | None:
    if duration_type == TrainingDurationType.DISTANCE:
        return "METER"
    if duration_type == TrainingDurationType.TIME:
        return "SECOND"
    return None
