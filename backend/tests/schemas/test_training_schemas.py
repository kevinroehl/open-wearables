import pytest
from pydantic import ValidationError

from app.schemas.training import TrainingWorkoutCreate


def _valid_payload() -> dict:
    return {
        "workout_name": "Tempo Run",
        "description": "A controlled tempo session",
        "sport": "RUNNING",
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
                "repeat_value": 4,
                "steps": [
                    {
                        "type": "step",
                        "intensity": "INTERVAL",
                        "duration_type": "DISTANCE",
                        "duration_value": 1000,
                        "target_type": "PACE",
                        "target_value_low": 3.8,
                        "target_value_high": 4.2,
                    },
                    {
                        "type": "step",
                        "intensity": "RECOVERY",
                        "duration_type": "TIME",
                        "duration_value": 120,
                        "target_type": "OPEN",
                    },
                ],
            },
        ],
    }


def test_valid_running_workout_with_repeat() -> None:
    workout = TrainingWorkoutCreate.model_validate(_valid_payload())

    assert workout.sport == "RUNNING"
    assert workout.flattened_step_count() == 9


def test_valid_cycling_workout_with_power_target() -> None:
    payload = _valid_payload()
    payload["sport"] = "CYCLING"
    payload["steps"] = [
        {
            "type": "step",
            "intensity": "ACTIVE",
            "duration_type": "TIME",
            "duration_value": 1800,
            "target_type": "POWER",
            "target_value": 3,
        }
    ]

    workout = TrainingWorkoutCreate.model_validate(payload)

    assert workout.sport == "CYCLING"


def test_rejects_unsupported_sport() -> None:
    payload = _valid_payload()
    payload["sport"] = "STRENGTH_TRAINING"

    with pytest.raises(ValidationError):
        TrainingWorkoutCreate.model_validate(payload)


def test_rejects_nested_repeats() -> None:
    payload = _valid_payload()
    payload["steps"] = [
        {
            "type": "repeat",
            "repeat_value": 2,
            "steps": [
                {
                    "type": "repeat",
                    "repeat_value": 2,
                    "steps": [],
                }
            ],
        }
    ]

    with pytest.raises(ValidationError):
        TrainingWorkoutCreate.model_validate(payload)


def test_rejects_more_than_100_flattened_steps() -> None:
    payload = _valid_payload()
    payload["steps"] = [
        {
            "type": "repeat",
            "repeat_value": 101,
            "steps": [
                {
                    "type": "step",
                    "intensity": "ACTIVE",
                    "duration_type": "TIME",
                    "duration_value": 30,
                    "target_type": "OPEN",
                }
            ],
        }
    ]

    with pytest.raises(ValidationError, match="100 flattened steps"):
        TrainingWorkoutCreate.model_validate(payload)


def test_rejects_missing_duration_value_for_time_step() -> None:
    payload = _valid_payload()
    payload["steps"][0].pop("duration_value")

    with pytest.raises(ValidationError, match="duration_value is required"):
        TrainingWorkoutCreate.model_validate(payload)


def test_rejects_invalid_target_range() -> None:
    payload = _valid_payload()
    payload["steps"][0]["target_type"] = "PACE"
    payload["steps"][0]["target_value_low"] = 5
    payload["steps"][0]["target_value_high"] = 4

    with pytest.raises(ValidationError, match="target_value_low"):
        TrainingWorkoutCreate.model_validate(payload)
