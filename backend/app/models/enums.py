"""Domain enumerations used by tables, schemas, and validation."""

from enum import Enum


class MeasurementType(str, Enum):
    """Supported health measurement types."""

    heart_rate = "heart_rate"
    systolic_bp = "systolic_bp"
    diastolic_bp = "diastolic_bp"
    body_temperature = "body_temperature"
    mood = "mood"
    sleepiness_kss = "sleepiness_kss"
    perceived_stress = "perceived_stress"


class MeasurementSource(str, Enum):
    """Origin of a measurement or sleep record."""

    simulated = "simulated"
    manual = "manual"
    device_import = "device_import"


class QualityFlag(str, Enum):
    """Data quality assigned by server-side validation."""

    valid = "valid"
    questionable = "questionable"
    missing = "missing"


class TaskType(str, Enum):
    """Mission task categories."""

    eva = "eva"
    maintenance = "maintenance"
    science = "science"
    exercise = "exercise"
    medical = "medical"
    rest = "rest"
    other = "other"


class WorkloadLevel(str, Enum):
    """Relative workload of a mission task."""

    low = "low"
    medium = "medium"
    high = "high"


class AssessmentStatus(str, Enum):
    """Assessment outcome written by the analysis engine."""

    insufficient_data = "insufficient_data"
    no_flag = "no_flag"
    monitor = "monitor"
    elevated_concern = "elevated_concern"


class ActionStatus(str, Enum):
    """Lifecycle of a countermeasure action."""

    suggested = "suggested"
    accepted = "accepted"
    skipped = "skipped"
    completed = "completed"


def enum_values(enum_cls: type[Enum]) -> list[str]:
    """Return member values for SQLAlchemy Enum storage."""
    return [member.value for member in enum_cls]
