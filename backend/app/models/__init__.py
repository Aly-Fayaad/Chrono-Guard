"""Import every table model so SQLModel metadata is complete."""

from app.models.assessment import Assessment
from app.models.checkin import CheckIn, HealthMeasurement, SleepRecord
from app.models.crew import CrewProfile
from app.models.guidance import ActionHistory, Countermeasure
from app.models.mission import MissionTask

__all__ = [
    "ActionHistory",
    "Assessment",
    "CheckIn",
    "Countermeasure",
    "CrewProfile",
    "HealthMeasurement",
    "MissionTask",
    "SleepRecord",
]
