"""Analysis engine protocol and plug-in loader."""

import importlib
from typing import Protocol

from sqlmodel import Session

from app.models.assessment import Assessment


class AnalysisEngine(Protocol):
    """Contract implemented by Person 3's analysis engine."""

    #: Stable identifier stored on assessments; used to make re-analysis
    #: idempotent for a given engine version.
    version: str

    def analyze(
        self, session: Session, crew_id: str, checkin_id: str | None
    ) -> Assessment | None:
        """Return an unsaved assessment, or None when no analysis is available."""
        ...


class NullEngine:
    """Default engine that performs no analysis."""

    version = "null-engine"

    def analyze(
        self, session: Session, crew_id: str, checkin_id: str | None
    ) -> Assessment | None:
        """Return None so check-ins are saved without an assessment."""
        return None


def load_engine(dotted_path: str) -> AnalysisEngine:
    """Instantiate an engine from a 'module:Class' dotted path."""
    module_path, separator, class_name = dotted_path.partition(":")
    if not module_path or not separator or not class_name:
        raise ValueError("ANALYSIS_ENGINE must use the form 'module:Class'")
    module = importlib.import_module(module_path)
    return getattr(module, class_name)()
