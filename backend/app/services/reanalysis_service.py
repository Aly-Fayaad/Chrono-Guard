"""Safe historical re-analysis of stored check-ins.

The operation is additive: original check-ins, measurements and sleep records
are never modified, and previous assessments are never deleted. Re-running the
same engine version is idempotent because a check-in that already has an
assessment from that version is skipped.
"""

from __future__ import annotations

import logging

from sqlmodel import Session, select

from app.models.assessment import Assessment
from app.models.enums import AssessmentStatus
from app.schemas.assessment import ReanalysisItem, ReanalysisResult
from app.services import checkin_service
from app.services.analysis import AnalysisEngine

logger = logging.getLogger(__name__)

UNKNOWN_ENGINE_VERSION = "unknown"


def reanalyze_crew(
    session: Session, crew_id: str, engine: AnalysisEngine
) -> ReanalysisResult:
    """Re-analyse every stored check-in for one crew member, oldest first."""
    engine_version = getattr(engine, "version", UNKNOWN_ENGINE_VERSION)
    checkins = checkin_service.list_all_checkins(session, crew_id)
    existing = {
        (row.checkin_id, row.engine_version)
        for row in session.exec(
            select(Assessment).where(Assessment.crew_id == crew_id)
        ).all()
    }

    results: list[ReanalysisItem] = []
    succeeded = 0
    skipped = 0
    failed = 0
    insufficient = 0

    for checkin in checkins:
        if (
            engine_version != UNKNOWN_ENGINE_VERSION
            and (checkin.id, engine_version) in existing
        ):
            skipped += 1
            results.append(
                ReanalysisItem(
                    checkin_id=checkin.id,
                    status="skipped",
                    reason=f"already analysed by engine version {engine_version}",
                )
            )
            continue

        try:
            assessment = engine.analyze(session, crew_id, checkin.id)
            if assessment is None:
                skipped += 1
                results.append(
                    ReanalysisItem(
                        checkin_id=checkin.id,
                        status="skipped",
                        reason="analysis engine returned no assessment",
                    )
                )
                continue

            key = (
                assessment.checkin_id or checkin.id,
                assessment.engine_version,
            )
            if key in existing:
                skipped += 1
                results.append(
                    ReanalysisItem(
                        checkin_id=checkin.id,
                        status="skipped",
                        reason=(
                            "an assessment from this engine version already exists"
                        ),
                    )
                )
                continue

            session.add(assessment)
            session.commit()
            existing.add(key)
            succeeded += 1
            if assessment.status == AssessmentStatus.insufficient_data:
                insufficient += 1
            results.append(
                ReanalysisItem(
                    checkin_id=checkin.id,
                    status="succeeded",
                    assessment_id=assessment.id,
                    assessment_status=assessment.status,
                )
            )
        except Exception as exc:  # noqa: BLE001 - one failure must not stop the batch
            session.rollback()
            failed += 1
            logger.exception("Re-analysis failed for check-in %s", checkin.id)
            results.append(
                ReanalysisItem(
                    checkin_id=checkin.id,
                    status="failed",
                    reason=str(exc) or exc.__class__.__name__,
                )
            )

    return ReanalysisResult(
        crew_id=crew_id,
        engine_version=engine_version,
        processed=len(checkins),
        succeeded=succeeded,
        skipped=skipped,
        failed=failed,
        insufficient=insufficient,
        results=results,
    )
