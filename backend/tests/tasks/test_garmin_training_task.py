from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.integrations.celery.tasks.garmin_training_task import (
    _execute_job,
    _mark_entity_failed,
    _mark_job_failed,
    _mark_job_running,
    _mark_job_succeeded,
)
from app.services.providers.garmin.training import GarminTrainingPermanentError
from tests.factories import TrainingPublishJobFactory, TrainingScheduleFactory, TrainingWorkoutFactory


def test_successful_workout_publish_stores_garmin_ids(db: Session) -> None:
    workout = TrainingWorkoutFactory()
    job = TrainingPublishJobFactory(user=workout.user, entity_id=workout.id, entity_type="workout", action="create")
    client = MagicMock()
    client.create_workout.return_value = {"workoutId": 321, "ownerId": 654}
    strategy = MagicMock(training=client)

    running_job = _mark_job_running(db, job.id)
    with patch("app.integrations.celery.tasks.garmin_training_task.GarminStrategy", return_value=strategy):
        result = _execute_job(db, running_job)
    _mark_job_succeeded(db, running_job, result)

    db.refresh(workout)
    db.refresh(running_job)
    assert workout.garmin_workout_id == "321"
    assert workout.garmin_owner_id == "654"
    assert workout.publish_status == "published"
    assert running_job.status == "succeeded"


def test_successful_schedule_publish_stores_garmin_schedule_id(db: Session) -> None:
    workout = TrainingWorkoutFactory(garmin_workout_id="321", garmin_owner_id="654", publish_status="published")
    schedule = TrainingScheduleFactory(workout=workout)
    job = TrainingPublishJobFactory(user=workout.user, entity_id=schedule.id, entity_type="schedule", action="create")
    client = MagicMock()
    client.create_schedule.return_value = {"scheduleId": 987}
    strategy = MagicMock(training=client)

    running_job = _mark_job_running(db, job.id)
    with patch("app.integrations.celery.tasks.garmin_training_task.GarminStrategy", return_value=strategy):
        result = _execute_job(db, running_job)
    _mark_job_succeeded(db, running_job, result)

    db.refresh(schedule)
    assert schedule.garmin_schedule_id == "987"
    assert schedule.publish_status == "published"


def test_permission_failure_marks_job_and_entity_failed(db: Session) -> None:
    workout = TrainingWorkoutFactory()
    job = TrainingPublishJobFactory(user=workout.user, entity_id=workout.id, entity_type="workout", action="create")
    client = MagicMock()
    client.assert_workout_import_permission.side_effect = GarminTrainingPermanentError(
        412,
        "MISSING_WORKOUT_IMPORT_PERMISSION",
        "missing permission",
    )
    strategy = MagicMock(training=client)

    running_job = _mark_job_running(db, job.id)
    with (
        patch("app.integrations.celery.tasks.garmin_training_task.GarminStrategy", return_value=strategy),
        pytest.raises(GarminTrainingPermanentError),
    ):
        _execute_job(db, running_job)

    _mark_job_failed(db, running_job, "MISSING_WORKOUT_IMPORT_PERMISSION", "missing permission", 412)
    _mark_entity_failed(db, running_job, "missing permission")

    db.refresh(workout)
    db.refresh(running_job)
    assert running_job.status == "failed"
    assert workout.publish_status == "failed"
    assert workout.last_error == "missing permission"


def test_schedule_publish_waits_for_workout_publish(db: Session) -> None:
    workout = TrainingWorkoutFactory(garmin_workout_id=None)
    schedule = TrainingScheduleFactory(workout=workout)
    job = TrainingPublishJobFactory(user=workout.user, entity_id=schedule.id, entity_type="schedule", action="create")
    client = MagicMock()
    strategy = MagicMock(training=client)

    running_job = _mark_job_running(db, job.id)
    with (
        patch("app.integrations.celery.tasks.garmin_training_task.GarminStrategy", return_value=strategy),
        pytest.raises(Exception, match="Workout must be published"),
    ):
        _execute_job(db, running_job)
