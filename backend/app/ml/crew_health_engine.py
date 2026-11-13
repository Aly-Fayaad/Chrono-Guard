"""Analysis engine backed by the vendored ``crew-health`` pipeline.

Implements Chrono-Guard's :class:`app.services.analysis.AnalysisEngine` contract
by converting stored check-ins, sleep records and mission tasks into the
``crew_health.pipeline.analyze`` payload, then translating the result into an
:class:`app.models.assessment.Assessment`.

Scientific scope (deliberate, mirrored in the generated text):

* the predicted KSS is a **group-level** output of the published three-process
  model (Ingre et al. 2014); it is not individually calibrated and is not
  validated in microgravity or for astronauts;
* the workload adjustment is a **modelling extension**, not a measurement;
* a short personal baseline (``baseline.status != "established"``) is reported
  as a factor; it does not by itself mean the sleep data are insufficient;
* Chrono-Guard stores self-reported sleep windows (time in bed) with an
  interruption count, not measured sleep stages, so ``tst_min`` is derived from
  the reported window. The self-reported KSS is shown for reference only and is
  never used as a model input.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.core.database import to_utc, utcnow
from app.models.assessment import Assessment
from app.models.checkin import CheckIn, SleepRecord
from app.models.enums import AssessmentStatus, MeasurementType
from app.services.history_service import (
    get_measurements,
    get_sleep_records,
    get_upcoming_tasks,
)
from app.services.mission_clock import compute_mission_clock

from crew_health.pipeline import analyze as analyze_payload

logger = logging.getLogger(__name__)

ENGINE_VERSION = "crew-health 0.2.0 (tpm-ingre2014 + workload-ext; status-rule v1)"

SLEEP_HISTORY_DAYS = 14
WORKLOAD_HORIZON_HOURS = 48
# One night yields a sleep/wake timeline, but two nights are the minimum for a
# personal comparison. Below this the engine reports insufficient_data.
MIN_NIGHTS = 2

# Anchors from the Karolinska Sleepiness Scale instrument itself (1-9):
# 6 = "some signs of sleepiness",
# 7 = "sleepy, but no difficulty remaining awake".
# These are instrument anchors used as a transparent, configurable product rule,
# not clinical or operational limits. The pipeline's own p75/p90 values are
# between-individual bands around the prediction and are reported as context only.
KSS_MONITOR = 6.0
KSS_CONCERN = 7.0

STATUS_RULE_REFERENCE = (
    "provisional product rule: predicted KSS >= 6 -> monitor; predicted KSS "
    ">= 7 with a recent persistent deviation or a high-risk task -> "
    "elevated_concern; low alertness band or recent persistent deviation -> "
    "monitor; otherwise no_flag"
)
STATUS_RULE_NOTE = (
    "KSS 6/7 are published instrument descriptors, not clinical or operational "
    "thresholds. Predicted KSS is a group-level model estimate (residual SD "
    "1.42) and is not individually calibrated. Alertness bands are percentiles "
    "within this simulation. Persistent deviation is a statistical "
    "|robust z| >= 2 on >= 2 consecutive recent nights. This status rule is a "
    "provisional prototype heuristic, not a validated impairment indicator."
)

_LIMITATION_NOTE = (
    "Group-level prediction from the published three-process model "
    "(Ingre et al. 2014); not individually calibrated, not validated in "
    "microgravity, and not a clinical threshold or validated impairment indicator."
)


class CrewHealthEngine:
    """Run the vendored crew-health analysis for one check-in."""

    version = ENGINE_VERSION

    def analyze(
        self, session: Session, crew_id: str, checkin_id: str | None
    ) -> Assessment | None:
        """Return an unsaved assessment for the crew member's latest state."""
        as_of = _analysis_time(session, checkin_id)
        available = _available_checkin_ids(session, crew_id, as_of)
        records = [
            record
            for record in get_sleep_records(
                session,
                crew_id,
                since=as_of - timedelta(days=SLEEP_HISTORY_DAYS),
                until=as_of,
            )
            # A later check-in may describe a past sleep window. Historical
            # re-analysis must not see records that did not exist at this as_of.
            if record.checkin_id is None or record.checkin_id in available
        ]
        nights = _nights(records)

        if len(nights) < MIN_NIGHTS:
            return _insufficient_assessment(crew_id, checkin_id, len(nights))

        tasks = _tasks(session, crew_id, as_of)
        clock = compute_mission_clock(as_of)
        payload = {
            "subject_id": crew_id,
            "as_of": as_of.isoformat(),
            "timezone": "UTC",
            "nightly_records": nights,
            "upcoming_tasks": tasks,
            "mission": {
                "mission_day_hours": clock.day_hours,
                "epoch": clock.epoch.isoformat(),
                # Records are stored on the 24 h Earth clock. Reinterpreting
                # them on the 24.65 h dial is not validated, so we keep the
                # published circadian equations unchanged.
                "records_on_mission_clock": False,
            },
        }

        result = analyze_payload(payload)
        self_reported = _self_reported_kss(session, crew_id, as_of, available)
        return _assessment(crew_id, checkin_id, result, tasks, self_reported)


def _available_checkin_ids(
    session: Session, crew_id: str, as_of: datetime
) -> set[str]:
    """Check-ins that had already been submitted at ``as_of``."""
    rows = session.exec(
        select(CheckIn.id).where(
            CheckIn.crew_id == crew_id,
            CheckIn.submitted_at <= as_of,
        )
    ).all()
    return {str(row) for row in rows}


def _analysis_time(session: Session, checkin_id: str | None) -> datetime:
    """Use the check-in timestamp so the analysis matches the submitted form."""
    if checkin_id:
        checkin = session.get(CheckIn, checkin_id)
        if checkin is not None:
            return to_utc(checkin.submitted_at)
    return utcnow()


def _nights(records: list[SleepRecord]) -> list[dict]:
    """Convert stored sleep rows (newest first) into ascending nightly records."""
    nights = []
    for record in sorted(records, key=lambda item: to_utc(item.sleep_start)):
        start = to_utc(record.sleep_start)
        end = to_utc(record.sleep_end)
        nights.append(
            {
                "date": end.date().isoformat(),
                "sleep_start": start.isoformat(),
                "sleep_end": end.isoformat(),
                # Reported interruptions, not scored awakenings.
                "awakenings": int(record.interruptions or 0),
                "sleep_duration_hours": float(record.duration_hours),
            }
        )
    return nights


def _tasks(session: Session, crew_id: str, as_of: datetime) -> list[dict]:
    """Upcoming/in-progress mission tasks in the analysis horizon."""
    rows = get_upcoming_tasks(
        session,
        crew_id,
        from_time=as_of - timedelta(hours=12),
        horizon_hours=WORKLOAD_HORIZON_HOURS,
    )
    return [
        {
            "task_id": task.id,
            "title": task.title,
            "start": to_utc(task.start_time).isoformat(),
            "end": to_utc(task.end_time).isoformat(),
            "workload_level": task.workload_level.value,
            "task_type": task.task_type.value,
            "is_critical": bool(task.is_critical),
        }
        for task in rows
    ]


def _self_reported_kss(
    session: Session,
    crew_id: str,
    as_of: datetime,
    available_checkins: set[str],
) -> float | None:
    """Latest self-reported sleepiness (1-9) submitted at or before as_of."""
    rows = get_measurements(
        session,
        crew_id,
        types=[MeasurementType.sleepiness_kss],
        until=as_of,
    )
    for row in rows:
        if row.checkin_id is None or row.checkin_id in available_checkins:
            return float(row.value)
    return None


def _status(
    kss: float | None,
    has_persistent_deviation: bool,
    low_alertness: bool,
    high_risk_task: bool,
) -> AssessmentStatus:
    """Provisional product rule built on KSS instrument anchors.

    ``low_alertness`` means the simulated alertness percentile (higher = more
    alert) is in one of the two lower bands, at the check-in time or at an
    upcoming task. No clinical or operational threshold is implied. This
    combination is a prototype heuristic, not a validated impairment rule.
    """
    if kss is None:
        return AssessmentStatus.insufficient_data
    if kss >= KSS_CONCERN and (has_persistent_deviation or high_risk_task):
        return AssessmentStatus.elevated_concern
    if kss >= KSS_MONITOR or low_alertness or has_persistent_deviation:
        return AssessmentStatus.monitor
    return AssessmentStatus.no_flag


def _recent_persistent(
    persistent: list[dict], history_nights: int
) -> list[dict]:
    """Keep only runs that reach the most recent completed baseline night.

    The pipeline reports every persistent run in the supplied history. Old,
    resolved runs must not keep a crew member in ``monitor`` after recovery.
    """
    if not persistent or history_nights <= 0:
        return []
    last_index = history_nights - 1
    return [
        event
        for event in persistent
        if int(event.get("end_index", -1)) == last_index
    ]


def _assessment(
    crew_id: str,
    checkin_id: str | None,
    result: dict,
    tasks: list[dict],
    self_reported: float | None,
) -> Assessment:
    alertness = result.get("alertness") or {}
    baseline = result.get("baseline") or {}
    latest = result.get("latest_night") or {}
    mission = result.get("mission_time") or {}
    history_nights = int(baseline.get("n_nights_used") or 0)
    persistent = _recent_persistent(
        result.get("persistent_deviations") or [], history_nights
    )
    risks = result.get("schedule_risk") or []

    kss = alertness.get("current_predicted_kss")
    high_risk_task = any(
        task.get("workload_level") == "high" or task.get("is_critical")
        for task in tasks
    )
    low_alertness_band = alertness.get("current_band") in {
        "below_typical",
        "much_below_typical",
    } or any(
        risk.get("band") in {"below_typical", "much_below_typical"} for risk in risks
    )
    status = _status(
        kss,
        bool(persistent),
        low_alertness_band,
        high_risk_task,
    )

    factors = _factors(
        alertness, baseline, latest, mission, persistent, self_reported, tasks
    )
    factors.append(
        {
            "indicator": "status_rule",
            "observed": status.value,
            "reference": STATUS_RULE_REFERENCE,
            "note": STATUS_RULE_NOTE,
        }
    )
    met_text = _met_text(mission)
    summary = _summary(kss, status, len(factors), met_text)
    explanation = _explanation(
        alertness, baseline, latest, mission, persistent, tasks, kss
    )
    return Assessment(
        crew_id=crew_id,
        checkin_id=checkin_id,
        status=status,
        summary=summary,
        explanation=explanation,
        contributing_factors=factors,
        engine_version=ENGINE_VERSION,
    )


def _summary(
    kss: float | None,
    status: AssessmentStatus,
    n_factors: int,
    met_text: str | None,
) -> str:
    head = {
        AssessmentStatus.no_flag: "No fatigue flag",
        AssessmentStatus.monitor: "Monitor",
        AssessmentStatus.elevated_concern: "Elevated concern",
        AssessmentStatus.insufficient_data: "Insufficient sleep history",
    }[status]
    if kss is None:
        return f"{head}: no predicted KSS available."
    met = f", {met_text}" if met_text else ""
    return (
        f"{head}: predicted KSS {kss:.2f} (group-level; provisional KSS "
        f"anchors {KSS_MONITOR:.0f}/{KSS_CONCERN:.0f}){met}; "
        f"{n_factors} contributing factor(s)."
    )


def _explanation(
    alertness: dict,
    baseline: dict,
    latest: dict,
    mission: dict,
    persistent: list[dict],
    tasks: list[dict],
    kss: float | None,
) -> str:
    lines = []
    if kss is None:
        lines.append(
            "The three-process model needs a usable sleep/wake timeline and "
            "could not produce a predicted KSS for this check-in."
        )
    else:
        lines.append(
            _LIMITATION_NOTE
        )
        band = alertness.get("current_band")
        if band:
            lines.append(f"Alertness is in the '{band}' band within this simulation.")
        lines.append(
            f"Status uses the provisional product rule: predicted KSS "
            f"{KSS_MONITOR:.0f} (some signs of sleepiness) or above -> monitor; "
            f"{KSS_CONCERN:.0f} (sleepy) or above plus a recent persistent "
            "deviation or a high-risk task -> elevated concern. The KSS 6/7 "
            "anchors are published instrument descriptors, not clinical or "
            "operational limits. Alertness bands are percentiles within this "
            "simulation, and persistent deviation means |robust z| >= 2 on at "
            "least two consecutive recent nights. This is a prototype heuristic, "
            "not a validated impairment indicator."
        )
        if alertness.get("sleep_debt_hours") is not None:
            lines.append(
                f"Descriptive sleep debt: {alertness['sleep_debt_hours']:.1f} h "
                "(accounting construct, no clinical threshold)."
            )

    lines.append(
        f"Sleep history: {baseline.get('n_nights_observed', 0)} night(s) observed, "
        f"{baseline.get('n_nights_used', 0)} prior night(s) used for the personal "
        f"baseline (status: {baseline.get('status', 'unknown')}). A short baseline "
        "limits personal comparison; it does not mean the sleep records are missing."
    )
    if latest.get("tst_min") is not None:
        lines.append(
            f"Latest night: reported sleep window {latest['tst_min'] / 60.0:.1f} h "
            f"with {latest.get('awakenings', 0)} interruption(s). This is a "
            "self-reported time in bed, not measured total sleep time."
        )
    if persistent:
        features = ", ".join(sorted({str(item.get("feature")) for item in persistent}))
        lines.append(
            f"Persistent deviation from the personal baseline on consecutive "
            f"nights: {features}."
        )
    if tasks:
        lines.append(
            f"{len(tasks)} mission task(s) in the next {WORKLOAD_HORIZON_HOURS} h. "
            "Any workload-adjusted KSS is a modelling extension with assumed "
            "intensity rates; it is not validated and not a measured impairment."
        )
    met_text = _met_text(mission)
    if met_text:
        published = mission.get("published_circadian_equations_unchanged")
        circadian_note = (
            "the published 24 h circadian equations are unchanged."
            if published is True
            else "the circadian configuration is non-default and is an "
            "unvalidated extrapolation."
        )
        lines.append(
            f"Mission clock: {met_text}, using a {mission.get('mission_day_hours')} h "
            f"operational day. This is a mission-design convention; {circadian_note}"
        )
    lines.append(
        "Self-reported sleepiness is displayed for reference only and is not an "
        "input to the model."
    )
    return " ".join(lines)


def _factors(
    alertness: dict,
    baseline: dict,
    latest: dict,
    mission: dict,
    persistent: list[dict],
    self_reported: float | None,
    tasks: list[dict],
) -> list[dict]:
    factors: list[dict] = []

    kss = alertness.get("current_predicted_kss")
    limits = alertness.get("kss_reference_limits") or {}
    if kss is not None:
        factors.append(
            {
                "indicator": "predicted_kss",
                "observed": round(float(kss), 2),
                "reference": (
                    f"between-individual p75 {limits.get('p75_upper'):.2f} / p90 "
                    f"{limits.get('p90_upper'):.2f} (context only; status uses "
                    f"provisional KSS anchors {KSS_MONITOR:.0f}/{KSS_CONCERN:.0f})"
                    if limits.get("p75_upper") is not None
                    else "group-level KSS (1-9)"
                ),
                "note": _LIMITATION_NOTE,
            }
        )

    factors.append(
        {
            "indicator": "baseline_status",
            "observed": baseline.get("status"),
            "reference": ">= 14 prior nights = established; < 7 = insufficient",
            "note": (
                f"{baseline.get('n_nights_used', 0)} prior night(s) used; short "
                "baselines limit personal comparison, not sleep-data sufficiency"
            ),
        }
    )

    if latest.get("tst_min") is not None:
        factors.append(
            {
                "indicator": "latest_sleep_window_h",
                "observed": round(float(latest["tst_min"]) / 60.0, 2),
                "reference": "self-reported time in bed, not measured total sleep time",
                "note": f"{latest.get('awakenings', 0)} reported interruption(s)",
            }
        )

    if persistent:
        features = sorted({str(item.get("feature")) for item in persistent})
        factors.append(
            {
                "indicator": "persistent_deviation",
                "observed": features,
                "reference": (
                    "|robust z| >= 2 for >= 2 consecutive recent nights; "
                    "most recent completed night only"
                ),
                "note": "statistical deviation from this crew member's own baseline",
            }
        )

    workload = alertness.get("workload") or {}
    if tasks and workload.get("status") == "modelled":
        factors.append(
            {
                "indicator": "workload_equivalent_h",
                "observed": round(float(workload.get("peak_equivalent_h", 0.0)), 2),
                "reference": "peak equivalent wakefulness hours from task intensity",
                "note": (
                    "modelling extension with assumed intensity rates "
                    "(low 0.10 / medium 0.25 / high 0.50 h per h); not validated"
                ),
            }
        )

    if self_reported is not None:
        factors.append(
            {
                "indicator": "self_reported_kss",
                "observed": self_reported,
                "reference": "check-in self-report (1-9)",
                "note": "reported by the crew member; not used as a model input",
            }
        )

    met_text = _met_text(mission)
    if met_text:
        factors.append(
            {
                "indicator": "mission_elapsed_time",
                "observed": met_text,
                "reference": (
                    f"{mission.get('mission_day_hours')} h mission day, "
                    f"epoch {mission.get('epoch')}"
                ),
                "note": (
                    "operational mission clock; the published circadian "
                    "equations stay on the 24 h Earth clock"
                ),
            }
        )

    return factors


def _met_text(mission: dict) -> str | None:
    met = mission.get("met_hours")
    if met is None:
        return None
    day = int(mission.get("mission_day_index", 0))
    local = float(mission.get("mission_local_time_hours", 0.0))
    hours = int(local)
    minutes = int(round((local - hours) * 60)) % 60
    return f"MET {met:.1f} h (D+{day:03d} {hours:02d}:{minutes:02d})"


def _insufficient_assessment(
    crew_id: str, checkin_id: str | None, nights: int
) -> Assessment:
    return Assessment(
        crew_id=crew_id,
        checkin_id=checkin_id,
        status=AssessmentStatus.insufficient_data,
        summary=(
            f"Insufficient sleep history: {nights} usable night(s), "
            f"{MIN_NIGHTS} required for analysis."
        ),
        explanation=(
            "The analysis needs at least two stored sleep records (start and end "
            "times) to build a sleep/wake timeline and a personal comparison. This "
            "is about the amount of sleep history, not about a short baseline: once "
            "two nights exist, baseline sufficiency is reported as a contributing "
            "factor instead. No predicted KSS, workload or mission-clock result is "
            "produced for this check-in."
        ),
        contributing_factors=[
            {
                "indicator": "sleep_records_available",
                "observed": nights,
                "reference": f">= {MIN_NIGHTS} nights",
                "note": "records inside the last 14 days for this crew member",
            },
            {
                "indicator": "predicted_kss",
                "observed": None,
                "reference": "requires a sleep/wake timeline",
                "note": "not computed; no clinical inference is made",
            },
        ],
        engine_version=ENGINE_VERSION,
    )
