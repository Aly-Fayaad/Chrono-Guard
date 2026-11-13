"""History response envelopes."""

from pydantic import BaseModel

from app.schemas.checkin import HealthMeasurementRead, SleepRecordRead


class MeasurementHistory(BaseModel):
    """Filtered measurement history."""

    measurements: list[HealthMeasurementRead]


class SleepHistory(BaseModel):
    """Filtered sleep history."""

    sleep_records: list[SleepRecordRead]
