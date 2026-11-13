from datetime import datetime

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Index
from sqlmodel import Field, SQLModel

from app.core.database import UTCDateTime, new_id, utcnow
from app.models.enums import MeasurementSource, MeasurementType, QualityFlag, enum_values

MEASUREMENT_TYPE = SAEnum(MeasurementType, values_callable=enum_values, name="measurement_type")
MEASUREMENT_SOURCE = SAEnum(MeasurementSource, values_callable=enum_values, name="measurement_source")
QUALITY_FLAG = SAEnum(QualityFlag, values_callable=enum_values, name="quality_flag")


class CheckIn(SQLModel, table=True):
    """One health check-in form submission."""

    __table_args__ = (Index("ix_checkin_crew_submitted", "crew_id", "submitted_at"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    crew_id: str = Field(foreign_key="crewprofile.id", nullable=False)
    submitted_at: datetime = Field(default_factory=utcnow, sa_type=UTCDateTime, nullable=False)
    notes: str | None = Field(default=None)


class HealthMeasurement(SQLModel, table=True):
    """Single numeric health measurement."""

    __table_args__ = (Index("ix_measurement_crew_recorded", "crew_id", "recorded_at"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    crew_id: str = Field(foreign_key="crewprofile.id", nullable=False)
    checkin_id: str | None = Field(default=None, foreign_key="checkin.id")
    type: MeasurementType = Field(sa_type=MEASUREMENT_TYPE, nullable=False)
    value: float = Field(nullable=False)
    unit: str = Field(nullable=False)
    recorded_at: datetime = Field(default_factory=utcnow, sa_type=UTCDateTime, nullable=False)
    source: MeasurementSource = Field(
        default=MeasurementSource.manual, sa_type=MEASUREMENT_SOURCE, nullable=False
    )
    quality: QualityFlag = Field(default=QualityFlag.valid, sa_type=QUALITY_FLAG, nullable=False)


class SleepRecord(SQLModel, table=True):
    """Sleep interval associated with a check-in."""

    __table_args__ = (Index("ix_sleep_crew_start", "crew_id", "sleep_start"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    crew_id: str = Field(foreign_key="crewprofile.id", nullable=False)
    checkin_id: str | None = Field(default=None, foreign_key="checkin.id")
    sleep_start: datetime = Field(sa_type=UTCDateTime, nullable=False)
    sleep_end: datetime = Field(sa_type=UTCDateTime, nullable=False)
    duration_hours: float = Field(nullable=False)
    interruptions: int = Field(default=0, nullable=False)
    source: MeasurementSource = Field(
        default=MeasurementSource.manual, sa_type=MEASUREMENT_SOURCE, nullable=False
    )
    quality: QualityFlag = Field(default=QualityFlag.valid, sa_type=QUALITY_FLAG, nullable=False)
