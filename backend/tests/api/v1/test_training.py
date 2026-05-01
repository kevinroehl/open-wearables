from datetime import date, datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.schemas.auth import ConnectionStatus
from tests.factories import (
    ApiKeyFactory,
    TrainingScheduleFactory,
    TrainingWorkoutFactory,
    UserConnectionFactory,
    UserFactory,
)
from tests.utils import api_key_headers


def _payload() -> dict:
    return {
        "workout_name": "Tempo Run",
        "description": "Steady work",
        "sport": "RUNNING",
        "steps": [
            {
                "type": "step",
                "intensity": "WARMUP",
                "duration_type": "TIME",
                "duration_value": 600,
                "target_type": "OPEN",
            }
        ],
    }


class TestTrainingEndpoints:
    def test_create_workout_returns_local_record_and_job(self, client: TestClient, db: Session) -> None:
        user = UserFactory()
        UserConnectionFactory(user=user, provider="garmin", scope="WORKOUT_IMPORT")
        api_key = ApiKeyFactory()

        with patch("app.integrations.celery.tasks.garmin_training_task.publish_garmin_training_item.delay") as delay:
            response = client.post(
                f"/api/v1/users/{user.id}/training/workouts",
                headers=api_key_headers(api_key.id),
                json=_payload(),
            )

        assert response.status_code == 201
        data = response.json()
        assert data["workout"]["workout_name"] == "Tempo Run"
        assert data["workout"]["publish_status"] == "queued"
        assert data["job"]["entity_type"] == "workout"
        delay.assert_called_once()

    def test_create_workout_requires_garmin_connection(self, client: TestClient, db: Session) -> None:
        user = UserFactory()
        api_key = ApiKeyFactory()

        response = client.post(
            f"/api/v1/users/{user.id}/training/workouts",
            headers=api_key_headers(api_key.id),
            json=_payload(),
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "User is not connected to Garmin"

    def test_get_workout_scoped_to_user(self, client: TestClient, db: Session) -> None:
        workout = TrainingWorkoutFactory()
        api_key = ApiKeyFactory()

        response = client.get(
            f"/api/v1/users/{workout.user_id}/training/workouts/{workout.id}",
            headers=api_key_headers(api_key.id),
        )

        assert response.status_code == 200
        assert response.json()["id"] == str(workout.id)

    def test_schedule_unpublished_workout_creates_chained_jobs(self, client: TestClient, db: Session) -> None:
        user = UserFactory()
        UserConnectionFactory(user=user, provider="garmin", scope="WORKOUT_IMPORT")
        workout = TrainingWorkoutFactory(user=user, garmin_workout_id=None)
        api_key = ApiKeyFactory()

        with patch("app.integrations.celery.tasks.garmin_training_task.publish_garmin_training_item.delay") as delay:
            response = client.post(
                f"/api/v1/users/{user.id}/training/schedules",
                headers=api_key_headers(api_key.id),
                json={"workout_id": str(workout.id), "scheduled_date": date.today().isoformat()},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["schedule"]["workout_id"] == str(workout.id)
        assert data["job"]["entity_type"] == "schedule"
        assert delay.call_count == 2

    def test_list_schedules_by_date_range(self, client: TestClient, db: Session) -> None:
        workout = TrainingWorkoutFactory()
        schedule = TrainingScheduleFactory(workout=workout, scheduled_date=date(2026, 5, 2))
        TrainingScheduleFactory(workout=workout, scheduled_date=date(2026, 6, 1))
        api_key = ApiKeyFactory()

        response = client.get(
            f"/api/v1/users/{workout.user_id}/training/schedules",
            headers=api_key_headers(api_key.id),
            params={"start_date": "2026-05-01", "end_date": "2026-05-31"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == str(schedule.id)

    def test_manual_publish_requeues_job(self, client: TestClient, db: Session) -> None:
        user = UserFactory()
        UserConnectionFactory(user=user, provider="garmin", scope="WORKOUT_IMPORT")
        workout = TrainingWorkoutFactory(user=user, publish_status="failed", last_error="rate limited")
        api_key = ApiKeyFactory()

        with patch("app.integrations.celery.tasks.garmin_training_task.publish_garmin_training_item.delay") as delay:
            response = client.post(
                f"/api/v1/users/{user.id}/training/workouts/{workout.id}/publish",
                headers=api_key_headers(api_key.id),
            )

        assert response.status_code == 200
        assert response.json()["status"] == "queued"
        delay.assert_called_once()

    def test_delete_published_schedule_enqueues_delete(self, client: TestClient, db: Session) -> None:
        user = UserFactory()
        UserConnectionFactory(user=user, provider="garmin", scope="WORKOUT_IMPORT")
        workout = TrainingWorkoutFactory(user=user, garmin_workout_id="123", garmin_owner_id="456")
        schedule = TrainingScheduleFactory(user=user, workout=workout, garmin_schedule_id="99")
        api_key = ApiKeyFactory()

        with patch("app.integrations.celery.tasks.garmin_training_task.publish_garmin_training_item.delay") as delay:
            response = client.delete(
                f"/api/v1/users/{user.id}/training/schedules/{schedule.id}",
                headers=api_key_headers(api_key.id),
            )

        assert response.status_code == 200
        assert response.json()["job"]["action"] == "delete"
        delay.assert_called_once()

    def test_invalid_schedule_date_returns_error(self, client: TestClient, db: Session) -> None:
        user = UserFactory()
        UserConnectionFactory(user=user, provider="garmin", scope="WORKOUT_IMPORT")
        workout = TrainingWorkoutFactory(user=user)
        api_key = ApiKeyFactory()

        response = client.post(
            f"/api/v1/users/{user.id}/training/schedules",
            headers=api_key_headers(api_key.id),
            json={"workout_id": str(workout.id), "scheduled_date": "not-a-date"},
        )

        assert response.status_code == 400

    def test_revoked_connection_is_rejected(self, client: TestClient, db: Session) -> None:
        user = UserFactory()
        UserConnectionFactory(
            user=user,
            provider="garmin",
            status=ConnectionStatus.REVOKED,
            token_expires_at=datetime.now(timezone.utc),
        )
        api_key = ApiKeyFactory()

        response = client.post(
            f"/api/v1/users/{user.id}/training/workouts",
            headers=api_key_headers(api_key.id),
            json=_payload(),
        )

        assert response.status_code == 401

    def test_get_missing_job_returns_404(self, client: TestClient, db: Session) -> None:
        user = UserFactory()
        api_key = ApiKeyFactory()

        response = client.get(
            f"/api/v1/users/{user.id}/training/jobs/{uuid4()}",
            headers=api_key_headers(api_key.id),
        )

        assert response.status_code == 404
