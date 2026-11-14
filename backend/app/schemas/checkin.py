"""Check-in form input and response schemas."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict

from app.models.enums import MeasurementSource, MeasurementType, QualityFlag
from app.schemas.assessment import AssessmentRead


class CheckInSource(str, Enum):
    """Sources an API client may submit.

    ``simulated`` is reserved for server-side demo seeding; accepting it here
    would let a client label synthetic data as a real check-in.
    """

    manual = "manual"
    device_import = "device_import"


class SleepInput(BaseModel):
    """Sleep section of the check-in form."""

    model_config = ConfigDict(extra="forbid")

    sleep_start: datetime
    sleep_end: datetime
    interruptions: int = 0


class BehavioralInput(BaseModel):
    """Behavioral section of the check-in form."""

    model_config = ConfigDict(extra="forbid")

    mood: int | None = None
    sleepiness_kss: int | None = None
    perceived_stress: int | None = None


class CardiovascularInput(BaseModel):
    """Cardiovascular section of the check-in form."""

    model_config = ConfigDict(extra="forbid")

    heart_rate: float | None = None
    hrv: float | None = None
    systolic_bp: float | None = None
    diastolic_bp: float | None = None


class PhysicalInput(BaseModel):
    """Physical section of the check-in form."""

    model_config = ConfigDict(extra="forbid")

    body_temperature: float | None = None


class CheckInCreate(BaseModel):
    """One check-in submission; every section and field is optional."""

    model_config = ConfigDict(extra="forbid")

    recorded_at: datetime | None = None
    source: CheckInSource = CheckInSource.manual
    sleep: SleepInput | None = None
    behavioral: BehavioralInput | None = None
    cardiovascular: CardiovascularInput | None = None
    physical: PhysicalInput | None = None
    notes: str | None = None


class CheckInRead(BaseModel):
    """Check-in header returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    crew_id: str
    submitted_at: datetime
    notes: str | None


class HealthMeasurementRead(BaseModel):
    """One stored health measurement."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    crew_id: str
    checkin_id: str | None
    type: MeasurementType
    value: float
    unit: str
    recorded_at: datetime
    source: MeasurementSource
    quality: QualityFlag


class SleepRecordRead(BaseModel):
    """One stored sleep interval."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    crew_id: str
    checkin_id: str | None
    sleep_start: datetime
    sleep_end: datetime
    duration_hours: float
    interruptions: int
    source: MeasurementSource
    quality: QualityFlag


class CheckInResponse(BaseModel):
    """Full check-in response including optional analysis."""

    checkin: CheckInRead
    measurements: list[HealthMeasurementRead]
    sleep_record: SleepRecordRead | None
    assessment: AssessmentRead | None
