from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from app.models import TrainingWorkout
from app.services.providers.garmin.oauth import GarminOAuth
from app.services.providers.garmin.training import (
    GarminTrainingClient,
    GarminTrainingPermanentError,
    GarminTrainingRetryableError,
    build_garmin_workout_payload,
    handle_garmin_training_http_exception,
)


def _workout() -> TrainingWorkout:
    return TrainingWorkout(
        id=uuid4(),
        user_id=uuid4(),
        provider="garmin",
        workout_name="Bike Intervals",
        description="Intervals",
        sport="CYCLING",
        steps_json={
            "steps": [
                {
                    "type": "step",
                    "intensity": "WARMUP",
                    "duration_type": "TIME",
                    "duration_value": 600,
                    "target_type": "OPEN",
                },
                {
                    "type": "repeat",
                    "repeat_value": 3,
                    "steps": [
                        {
                            "type": "step",
                            "intensity": "INTERVAL",
                            "duration_type": "DISTANCE",
                            "duration_value": 1000,
                            "target_type": "POWER",
                            "target_value": 4,
                        }
                    ],
                },
            ]
        },
        workout_provider="OpenWearables",
        workout_source_id="OpenWearables",
        garmin_workout_id="123",
        garmin_owner_id="456",
        publish_status="draft",
        last_error=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_build_garmin_workout_payload_maps_steps_and_ids() -> None:
    payload = build_garmin_workout_payload(_workout(), include_ids=True)

    assert payload["workoutId"] == 123
    assert payload["ownerId"] == 456
    assert payload["sport"] == "CYCLING"
    assert payload["isSessionTransitionEnabled"] is False
    steps = payload["segments"][0]["steps"]
    assert steps[0]["type"] == "WorkoutStep"
    assert steps[0]["durationValueType"] == "SECOND"
    assert steps[1]["type"] == "WorkoutRepeatStep"
    assert steps[1]["repeatValue"] == 3
    assert steps[1]["steps"][0]["stepOrder"] == 3
    assert steps[1]["steps"][0]["targetType"] == "POWER"
    assert steps[1]["steps"][0]["targetValue"] == 4


def test_garmin_training_client_uses_expected_endpoints() -> None:
    oauth = GarminOAuth(MagicMock(), MagicMock(), "garmin", "https://apis.garmin.com")
    client = GarminTrainingClient("garmin", "https://apis.garmin.com", oauth, MagicMock())

    with patch("app.services.providers.garmin.training.make_authenticated_request") as mock_request:
        mock_request.return_value = {"workoutId": 99, "ownerId": 10}
        result = client.create_workout(MagicMock(), uuid4(), {"workoutName": "Run"})

    assert result["workoutId"] == 99
    assert mock_request.call_args.kwargs["endpoint"] == "/workoutportal/workout/v2"
    assert mock_request.call_args.kwargs["method"] == "POST"


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (400, GarminTrainingPermanentError),
        (401, GarminTrainingPermanentError),
        (403, GarminTrainingPermanentError),
        (412, GarminTrainingPermanentError),
        (429, GarminTrainingRetryableError),
        (500, GarminTrainingRetryableError),
    ],
)
def test_handle_garmin_training_http_exception(status_code: int, expected: type[Exception]) -> None:
    with pytest.raises(expected):
        handle_garmin_training_http_exception(HTTPException(status_code=status_code, detail="Garmin error"))


def test_garmin_training_client_permission_parsing() -> None:
    oauth = GarminOAuth(MagicMock(), MagicMock(), "garmin", "https://apis.garmin.com")
    client = GarminTrainingClient("garmin", "https://apis.garmin.com", oauth, MagicMock())

    with patch("app.services.providers.garmin.training.make_authenticated_request", return_value=["WORKOUT_IMPORT"]):
        assert client.get_permissions(MagicMock(), uuid4()) == ["WORKOUT_IMPORT"]


def test_network_error_converts_to_retryable() -> None:
    request = httpx.Request("GET", "https://apis.garmin.com")
    response = httpx.Response(500, request=request, text="down")
    exc = HTTPException(status_code=response.status_code, detail=response.text)

    with pytest.raises(GarminTrainingRetryableError):
        handle_garmin_training_http_exception(exc)
