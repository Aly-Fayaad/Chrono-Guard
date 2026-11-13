"""Server-side personal-baseline detector for the overview series.

This is a faithful port of the frontend detector that shipped with the
prototype (``median + 1.4826 * MAD``, three-reading trend window). Moving it to
the backend keeps a single source of truth: the UI now only renders detections
that the API computed from the same series it returned.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

DetectionStatus = Literal[
    "normal", "anomaly", "insufficient_baseline", "data_quality"
]

DEFAULT_CONFIG = {
    "z_threshold": 3.5,
    "trend_window": 3,
    "min_baseline": 5,
}


@dataclass(frozen=True)
class VitalPoint:
    """One reading in a metric series, oldest first."""

    value: float
    quality: str
    recorded_at: datetime


@dataclass(frozen=True)
class Baseline:
    """Personal typical level and robust spread."""

    median: float
    scale: float
    n: int


def _quantile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolated quantile (matches the frontend helper)."""
    pos = (len(sorted_values) - 1) * q
    low = math.floor(pos)
    high = math.ceil(pos)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (pos - low)


def build_baseline(points: list[VitalPoint]) -> Baseline | None:
    """Build a median/MAD baseline from valid readings only."""
    values = sorted(point.value for point in points if point.quality == "valid")
    if len(values) < DEFAULT_CONFIG["min_baseline"]:
        return None
    median = _quantile(values, 0.5)
    deviations = sorted(abs(value - median) for value in values)
    mad = _quantile(deviations, 0.5)
    floor = max(0.02 * abs(median), 1e-6)
    scale = max(1.4826 * mad, floor)
    return Baseline(median=median, scale=scale, n=len(values))


def detect(metric: str, points: list[VitalPoint]) -> dict[str, object]:
    """Classify the latest readings against the crew member's own baseline."""
    config = DEFAULT_CONFIG
    if len(points) < config["min_baseline"] + 1:
        return {
            "metric": metric,
            "status": "insufficient_baseline",
            "z_score": None,
            "reason": (
                f"At least {config['min_baseline']} valid readings are needed before "
                "today's value can be compared to your personal baseline."
            ),
            "event": None,
        }

    window = config["trend_window"]
    recent = points[-window:]
    baseline = build_baseline(points[:-window])
    if baseline is None:
        return {
            "metric": metric,
            "status": "insufficient_baseline",
            "z_score": None,
            "reason": "Not enough clean history to build a personal baseline yet.",
            "event": None,
        }

    if any(point.quality != "valid" for point in recent):
        return {
            "metric": metric,
            "status": "data_quality",
            "z_score": None,
            "reason": (
                "One or more recent readings were flagged by quality checks — "
                "re-measure before trusting the trend."
            ),
            "event": None,
        }

    z_scores = [
        (point.value - baseline.median) / baseline.scale for point in recent
    ]
    last_z = z_scores[-1]
    flagged = sum(1 for z in z_scores if abs(z) >= config["z_threshold"])

    if flagged == len(z_scores):
        return {
            "metric": metric,
            "status": "anomaly",
            "z_score": round(last_z, 4),
            "reason": None,
            "event": {
                "kind": "sustained",
                "explanation": (
                    f"All of the last {window} readings sit {abs(last_z):.1f}σ from "
                    f"your usual {baseline.median:.1f} level."
                ),
            },
        }

    if abs(last_z) >= config["z_threshold"]:
        return {
            "metric": metric,
            "status": "anomaly",
            "z_score": round(last_z, 4),
            "reason": None,
            "event": {
                "kind": "sudden",
                "explanation": (
                    f"Today's reading jumps {abs(last_z):.1f}σ away from your usual "
                    f"{baseline.median:.1f} level after a stable stretch."
                ),
            },
        }

    return {
        "metric": metric,
        "status": "normal",
        "z_score": round(last_z, 4),
        "reason": None,
        "event": None,
    }
