from datetime import date, datetime, timezone
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TrainingProvider(str, Enum):
    GARMIN = "garmin"


class TrainingSport(str, Enum):
    RUNNING = "RUNNING"
    CYCLING = "CYCLING"


class TrainingDurationType(str, Enum):
    TIME = "TIME"
    DISTANCE = "DISTANCE"
    OPEN = "OPEN"


class TrainingIntensity(str, Enum):
    REST = "REST"
    WARMUP = "WARMUP"
    COOLDOWN = "COOLDOWN"
    RECOVERY = "RECOVERY"
    ACTIVE = "ACTIVE"
    INTERVAL = "INTERVAL"


class TrainingTargetType(str, Enum):
    OPEN = "OPEN"
    HEART_RATE = "HEART_RATE"
    POWER = "POWER"
    CADENCE = "CADENCE"
    PACE = "PACE"
    SPEED = "SPEED"


class TrainingValueType(str, Enum):
    PERCENT = "PERCENT"


class TrainingRepeatType(str, Enum):
    REPEAT_UNTIL_STEPS_CMPLT = "REPEAT_UNTIL_STEPS_CMPLT"


class TrainingPublishStatus(str, Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"
    DELETED = "deleted"


class TrainingJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"


class TrainingJobEntityType(str, Enum):
    WORKOUT = "workout"
    SCHEDULE = "schedule"


class TrainingJobAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class TrainingWorkoutStep(BaseModel):
    type: Literal["step"] = "step"
    intensity: TrainingIntensity = TrainingIntensity.ACTIVE
    description: str | None = Field(None, max_length=512)
    duration_type: TrainingDurationType
    duration_value: float | None = Field(None, gt=0)
    target_type: TrainingTargetType = TrainingTargetType.OPEN
    target_value: float | None = None
    target_value_low: float | None = None
    target_value_high: float | None = None
    target_value_type: TrainingValueType | None = None

    @model_validator(mode="after")
    def validate_step(self) -> "TrainingWorkoutStep":
        if self.duration_type == TrainingDurationType.OPEN:
            if self.duration_value is not None:
                raise ValueError("duration_value must be omitted when duration_type is OPEN")
        elif self.duration_value is None:
            raise ValueError("duration_value is required for TIME and DISTANCE durations")

        has_zone = self.target_value is not None
        has_range = self.target_value_low is not None or self.target_value_high is not None
        if self.target_type == TrainingTargetType.OPEN:
            if has_zone or has_range or self.target_value_type is not None:
                raise ValueError("target values must be omitted when target_type is OPEN")
        else:
            if has_zone and has_range:
                raise ValueError("use either target_value or target_value_low/target_value_high, not both")
            if has_range and (self.target_value_low is None or self.target_value_high is None):
                raise ValueError("both target_value_low and target_value_high are required for target ranges")
            if not has_zone and not has_range:
                raise ValueError("target_value or target range is required for non-OPEN targets")
            if (
                self.target_value_low is not None
                and self.target_value_high is not None
                and self.target_value_low > self.target_value_high
            ):
                raise ValueError("target_value_low must be less than or equal to target_value_high")
            if has_zone:
                if self.target_type == TrainingTargetType.HEART_RATE and not 1 <= self.target_value <= 5:
                    raise ValueError("heart rate target_value zones must be between 1 and 5")
                if self.target_type == TrainingTargetType.POWER and not 1 <= self.target_value <= 7:
                    raise ValueError("power target_value zones must be between 1 and 7")
        return self


class TrainingRepeatStep(BaseModel):
    type: Literal["repeat"] = "repeat"
    repeat_type: TrainingRepeatType = TrainingRepeatType.REPEAT_UNTIL_STEPS_CMPLT
    repeat_value: int = Field(gt=0)
    steps: list[TrainingWorkoutStep] = Field(min_length=1)


TrainingStep = Annotated[TrainingWorkoutStep | TrainingRepeatStep, Field(discriminator="type")]


class TrainingWorkoutBase(BaseModel):
    workout_name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(None, max_length=1024)
    sport: TrainingSport
    steps: list[TrainingStep] = Field(min_length=1)
    workout_provider: str = Field("Meala", min_length=1, max_length=20)
    workout_source_id: str = Field("Meala", min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_workout(self) -> "TrainingWorkoutBase":
        if self.flattened_step_count() > 100:
            raise ValueError("running and cycling workouts may not exceed 100 flattened steps")
        return self

    def flattened_step_count(self) -> int:
        total = 0
        for step in self.steps:
            if isinstance(step, TrainingRepeatStep):
                total += step.repeat_value * len(step.steps)
            else:
                total += 1
        return total


class TrainingWorkoutCreate(TrainingWorkoutBase):
    publish: bool = True


class TrainingWorkoutUpdate(TrainingWorkoutBase):
    publish: bool = True


class TrainingWorkoutCreateInternal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    provider: str = TrainingProvider.GARMIN.value
    workout_name: str
    description: str | None = None
    sport: str
    steps_json: dict
    workout_provider: str = "Meala"
    workout_source_id: str = "Meala"
    publish_status: TrainingPublishStatus = TrainingPublishStatus.DRAFT
    garmin_workout_id: str | None = None
    garmin_owner_id: str | None = None
    last_error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TrainingWorkoutUpdateInternal(BaseModel):
    workout_name: str | None = None
    description: str | None = None
    sport: str | None = None
    steps_json: dict | None = None
    workout_provider: str | None = None
    workout_source_id: str | None = None
    garmin_workout_id: str | None = None
    garmin_owner_id: str | None = None
    publish_status: TrainingPublishStatus | None = None
    last_error: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TrainingWorkoutRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    provider: str
    workout_name: str
    description: str | None
    sport: str
    steps: list[TrainingStep]
    workout_provider: str
    workout_source_id: str
    garmin_workout_id: str | None
    garmin_owner_id: str | None
    publish_status: TrainingPublishStatus
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class TrainingScheduleCreate(BaseModel):
    workout_id: UUID
    scheduled_date: date
    publish: bool = True


class TrainingScheduleCreateInternal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    provider: str = TrainingProvider.GARMIN.value
    workout_id: UUID
    scheduled_date: date
    garmin_schedule_id: str | None = None
    publish_status: TrainingPublishStatus = TrainingPublishStatus.DRAFT
    last_error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TrainingScheduleUpdateInternal(BaseModel):
    garmin_schedule_id: str | None = None
    publish_status: TrainingPublishStatus | None = None
    last_error: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TrainingScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    provider: str
    workout_id: UUID
    scheduled_date: date
    garmin_schedule_id: str | None
    publish_status: TrainingPublishStatus
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class TrainingPublishJobCreateInternal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    provider: str = TrainingProvider.GARMIN.value
    entity_type: TrainingJobEntityType
    entity_id: UUID
    action: TrainingJobAction
    status: TrainingJobStatus = TrainingJobStatus.QUEUED
    attempts: int = 0
    garmin_status_code: int | None = None
    garmin_response_json: dict | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TrainingPublishJobUpdateInternal(BaseModel):
    status: TrainingJobStatus | None = None
    attempts: int | None = None
    garmin_status_code: int | None = None
    garmin_response_json: dict | None = None
    error_code: str | None = None
    error_message: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TrainingPublishJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    provider: str
    entity_type: TrainingJobEntityType
    entity_id: UUID
    action: TrainingJobAction
    status: TrainingJobStatus
    attempts: int
    garmin_status_code: int | None
    garmin_response_json: dict | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class TrainingWorkoutMutationResponse(BaseModel):
    workout: TrainingWorkoutRead
    job: TrainingPublishJobRead | None = None


class TrainingScheduleMutationResponse(BaseModel):
    schedule: TrainingScheduleRead
    job: TrainingPublishJobRead | None = None
