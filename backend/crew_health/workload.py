"""Workload interaction with the three-process alertness model.

**This module is a modelling extension, not a validated model.** It exists to
make the workload dimension of the mission risk statement functional instead of
decorative. Everything it produces is labelled ``validated: false``.

Design
------
Rather than inventing an alertness penalty in KSS points, workload is expressed
as **equivalent hours of wakefulness** ``Δ`` and applied through the *published*
homeostatic function. Because

    S(taw) = la + (sw - la) * exp(d * taw)

adding ``Δ`` equivalent hours gives, without needing ``sw`` or ``taw``,

    S_adj = la + (S - la) * exp(d * Δ)

and the KSS mapping is unchanged:

    KSS_adj = 9.68 - 0.46 * (S_adj + C + U)

So exactly one new quantity enters the model — the rate at which an hour of work
at a given intensity converts into equivalent wakefulness — and everything
downstream remains the published, validated transfer function.

What is assumed and what is not
-------------------------------
* **Assumed:** the intensity→rate table (``intensity_weights``), the recovery
  half-life, and the cap. These are ordinal assumptions, not estimates. There is
  no published estimate of "1 h of EVA equals X h of wakefulness" that we could
  find, and the three-process model contains no time-on-task term at all
  (Ingre et al. 2014 note that only SAFE, FAID and CAS model time on task).
* **Not assumed:** the shape of the homeostatic decay, the circadian terms, the
  KSS transfer, and the sleep/wake accounting. Those are unchanged from the
  validated implementation in :mod:`crew_health.fatigue.tpm`.
* **Consequence:** the *ordering* of schedules by workload-adjusted KSS is
  meaningful under the stated assumptions; the *absolute* adjusted KSS is not a
  measured impairment and must never be presented as one.

Cumulative load
---------------
Load is integrated over the simulation timeline: it rises **additively while a
task is in progress** (so an N-hour task at rate r contributes exactly N·r
equivalent hours) and decays exponentially during rest and sleep. Overlapping
tasks are combined with ``max`` rather than summed, because one person cannot
perform two tasks at once; overlapping entries are treated as a scheduling input
error and flagged.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from crew_health.fatigue.tpm import TPMParams, kss_from_alertness

#: Ordinal assumptions. Equivalent hours of wakefulness contributed by one hour
#: of work at each level. NOT estimated from data.
DEFAULT_INTENSITY_WEIGHTS = {
    "low": 0.10,
    "medium": 0.25,
    "high": 0.50,
}

VALIDATED = False


@dataclass(frozen=True)
class WorkloadParams:
    intensity_weights: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_INTENSITY_WEIGHTS)
    )
    default_weight: float = 0.25          # used when level is missing/unknown
    recovery_half_life_h: float = 4.0     # decay of accumulated load during rest
    max_equivalent_h: float = 8.0         # cap on accumulated equivalent hours
    min_task_min: float = 1.0             # ignore accidental near-zero tasks

    def weight_for(self, level: str | None) -> tuple[float, bool]:
        """Return (rate, was_defaulted)."""
        if level is None:
            return self.default_weight, True
        key = str(level).strip().lower()
        if key in self.intensity_weights:
            return float(self.intensity_weights[key]), False
        return self.default_weight, True


def _ts(value, tz: str | None = None) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(tz or "UTC")
    return ts


def task_intervals(tasks: list[dict], params: WorkloadParams | None = None) -> list[dict]:
    """Normalise tasks into intervals with intensity weights, skipping invalid ones."""
    params = params or WorkloadParams()
    out = []
    for task in tasks:
        start = task.get("start")
        end = task.get("end")
        if start is None or end is None:
            continue
        s, e = _ts(start), _ts(end)
        if e <= s:
            continue
        duration_h = (e - s).total_seconds() / 3600.0
        if duration_h * 60.0 < params.min_task_min:
            continue
        rate, defaulted = params.weight_for(task.get("workload_level"))
        out.append({
            "task_id": task.get("task_id"),
            "start": s,
            "end": e,
            "workload_level": task.get("workload_level"),
            "duration_h": duration_h,
            "intensity_rate": rate,
            "intensity_defaulted": defaulted,
        })
    return sorted(out, key=lambda x: x["start"])


def overlapping_tasks(intervals: list[dict]) -> list[tuple[str, str]]:
    """Pairs of task ids that overlap in time (treated as an input error).

    All pairs are compared, not just neighbours, so a long task containing two
    shorter ones is detected as two clashes.
    """
    clashes = []
    for i, a in enumerate(intervals):
        for b in intervals[i + 1:]:
            if b["start"] < a["end"] and a["start"] < b["end"]:
                clashes.append((a["task_id"], b["task_id"]))
    return clashes


def equivalent_hours_timeline(
    df: pd.DataFrame,
    tasks: list[dict],
    params: WorkloadParams | None = None,
) -> pd.Series:
    """Accumulated equivalent wakefulness hours at each simulation timestamp.

    Rise rate during a task = intensity rate (equivalent h per clock hour).
    Decay otherwise with ``recovery_half_life_h``. Capped at ``max_equivalent_h``.
    """
    params = params or WorkloadParams()
    intervals = task_intervals(tasks, params)
    if df.empty:
        return pd.Series(dtype=float)

    times = df.index
    dt_h = (
        (times[1] - times[0]).total_seconds() / 3600.0 if len(times) > 1 else 5.0 / 60.0
    )
    decay = 0.5 ** (dt_h / params.recovery_half_life_h)

    asleep = df["sleep"].to_numpy(dtype=bool) if "sleep" in df else np.zeros(len(df), bool)
    # Rate per step = max intensity among tasks active at this timestamp.
    rate = np.zeros(len(df))
    for iv in intervals:
        active = (times >= iv["start"]) & (times < iv["end"])
        rate[active] = np.maximum(rate[active], iv["intensity_rate"])

    load = np.empty(len(df))
    acc = 0.0
    for i in range(len(df)):
        if asleep[i] or rate[i] == 0.0:
            # Rest (or sleep): accumulated load decays with the recovery half-life.
            acc = acc * decay
        else:
            # Working: load accumulates additively, so an N-hour task at rate r
            # contributes exactly N*r equivalent hours (up to step resolution).
            acc = min(acc + rate[i] * dt_h, params.max_equivalent_h)
        load[i] = acc
    return pd.Series(load, index=times, name="workload_equiv_h")


def apply_workload(
    df: pd.DataFrame,
    tasks: list[dict],
    tpm_params: TPMParams | None = None,
    workload_params: WorkloadParams | None = None,
) -> pd.DataFrame:
    """Add workload-adjusted alertness columns.

    The adjustment is applied only while awake; during sleep, load decays and the
    homeostatic recovery is left untouched.
    """
    tpm_params = tpm_params or TPMParams()
    workload_params = workload_params or WorkloadParams()

    out = df.copy()
    load = equivalent_hours_timeline(df, tasks, workload_params)
    out["workload_equiv_h"] = load

    s = out["s"].to_numpy()
    # S_adj = la + (S - la) * exp(d * load), the published wake function with
    # additional equivalent time awake.
    s_adj = tpm_params.la + (s - tpm_params.la) * np.exp(tpm_params.d * load.to_numpy())
    asleep = out["sleep"].to_numpy(dtype=bool)
    s_adj = np.where(asleep, s, s_adj)

    alert_adj = s_adj + out["c"].to_numpy() + out["u"].to_numpy()
    out["s_workload_adjusted"] = s_adj
    out["alertness_workload_adjusted"] = alert_adj
    out["kss_workload_adjusted"] = kss_from_alertness(alert_adj, tpm_params)
    return out


def task_workload_summary(
    df: pd.DataFrame,
    tasks: list[dict],
    params: WorkloadParams | None = None,
) -> list[dict]:
    """Per-task workload description, including cumulative load at task start."""
    params = params or WorkloadParams()
    intervals = task_intervals(tasks, params)
    load = df["workload_equiv_h"] if "workload_equiv_h" in df else None
    out = []
    for iv in intervals:
        row = {
            "task_id": iv["task_id"],
            "workload_level": iv["workload_level"],
            "duration_h": round(iv["duration_h"], 3),
            "intensity_rate_equivalent_h_per_h": iv["intensity_rate"],
            "task_equivalent_h": round(iv["duration_h"] * iv["intensity_rate"], 3),
            "intensity_was_defaulted": iv["intensity_defaulted"],
            "validated": VALIDATED,
            "assumption": (
                "intensity->equivalent-wakefulness rates are ordinal modelling "
                "assumptions, not estimates"
            ),
        }
        if load is not None and len(df):
            idx = df.index.get_indexer([iv["start"]], method="nearest")[0]
            if 0 <= idx < len(df):
                row["cumulative_equivalent_h_at_start"] = round(float(load.iloc[idx]), 3)
        out.append(row)
    clashes = overlapping_tasks(intervals)
    if clashes:
        out.append({"warning": "overlapping tasks detected; combined with max(), not summed",
                    "pairs": clashes, "validated": VALIDATED})
    return out


def summarize_workload(df: pd.DataFrame, params: WorkloadParams | None = None) -> dict:
    """Duty-period workload summary for the simulated window."""
    params = params or WorkloadParams()
    if "workload_equiv_h" not in df:
        return {"status": "unavailable", "validated": VALIDATED}
    load = df["workload_equiv_h"]
    awake = ~df["sleep"].to_numpy(dtype=bool)
    awake_load = load.to_numpy()[awake]
    return {
        "status": "modelled",
        "validated": VALIDATED,
        "peak_equivalent_h": float(load.max()),
        "mean_equivalent_h_while_awake": float(awake_load.mean()) if awake_load.size else 0.0,
        "fraction_of_awake_time_above_2_equivalent_h": (
            float((awake_load >= 2.0).mean()) if awake_load.size else 0.0
        ),
        "params": {
            "intensity_weights": dict(params.intensity_weights),
            "default_weight": params.default_weight,
            "recovery_half_life_h": params.recovery_half_life_h,
            "max_equivalent_h": params.max_equivalent_h,
        },
        "interpretation": (
            "Equivalent hours of wakefulness accumulated from task intensity and "
            "duration. Modelled extension of the published model; NOT a measured "
            "impairment and NOT validated."
        ),
    }
