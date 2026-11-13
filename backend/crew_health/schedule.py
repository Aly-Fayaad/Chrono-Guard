"""Schedule-aware alertness simulation.

Combines the published three-process model with mission task times:

* builds a 5-minute sleep/wake timeline from planned sleep opportunities;
* simulates homeostatic + circadian alertness (``crew_health.fatigue.tpm``);
* reports each task's alertness percentile within the simulated window;
* answers counterfactuals such as "what if this task moved 2 h later?".

Risk bands are **relative to the simulated distribution**, never clinical
thresholds.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from crew_health.fatigue.tpm import TPMParams, kss_reference_limits, simulate


def build_sleep_mask(start, end, sleep_windows: list[tuple], dt_min: float = 5.0) -> np.ndarray:
    """Boolean sleep mask at ``dt_min`` resolution for [start, end)."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    n = int(np.ceil((end - start).total_seconds() / 60 / dt_min))
    times = pd.date_range(start, periods=n, freq=f"{dt_min}min")
    mask = np.zeros(n, dtype=bool)
    for w_start, w_end in sleep_windows:
        w_start, w_end = pd.Timestamp(w_start), pd.Timestamp(w_end)
        mask |= (times >= w_start) & (times < w_end)
    return mask


def simulate_schedule(start, end, sleep_windows: list[tuple],
                      dt_min: float = 5.0, params: TPMParams | None = None,
                      s0: float | None = None,
                      mission: "MissionParams | None" = None) -> pd.DataFrame:
    """Simulate a schedule.

    ``sleep_windows`` may contain any number of episodes per mission day; split
    sleep is represented as several windows. ``mission`` adds the operational
    mission clock (MET / mission local time / day index).
    """
    mask = build_sleep_mask(start, end, sleep_windows, dt_min)
    return simulate(start, mask, dt_min=dt_min, params=params, s0=s0, mission=mission)


def risk_band(percentile: float) -> str:
    if percentile < 10:
        return "much_below_typical"
    if percentile < 25:
        return "below_typical"
    if percentile <= 75:
        return "typical"
    if percentile <= 90:
        return "above_typical"
    return "much_above_typical"


def task_risk(df: pd.DataFrame, tasks: list[dict]) -> list[dict]:
    """Alertness and predicted KSS at each task, relative to this simulation.

    ``kss`` is a group-level prediction from the validated transfer function
    (Ingre et al. 2014); the reference limits are between-individual limits, not
    confidence intervals. When the frame carries workload columns (see
    :mod:`crew_health.workload`), an explicitly *unvalidated* workload-adjusted
    KSS is added alongside the validated one.
    """
    values = df["alertness_raw"].to_numpy()
    kss_values = df["kss"].to_numpy()
    has_workload = "kss_workload_adjusted" in df.columns
    out = []
    for task in tasks:
        ts = pd.Timestamp(task["start"])
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        if ts < df.index[0] or ts > df.index[-1]:
            out.append({
                "task_id": task.get("task_id"),
                "start": ts.isoformat(),
                "status": "outside_simulation_window",
            })
            continue
        idx = df.index.get_indexer([ts], method="nearest")[0]
        pct = float((values <= values[idx]).mean() * 100.0)
        kss_pct = float((kss_values <= kss_values[idx]).mean() * 100.0)
        row = {
            "task_id": task.get("task_id"),
            "start": ts.isoformat(),
            "workload_level": task.get("workload_level"),
            "alertness_raw": float(values[idx]),
            "alertness_percentile_within_simulation": pct,
            "predicted_kss": float(kss_values[idx]),
            "kss_reference_limits": kss_reference_limits(float(kss_values[idx])),
            "kss_percentile_within_simulation": kss_pct,
            "band": risk_band(pct),
            "band_basis": "alertness percentile within this simulation; higher = more alert",
            "homeostatic_pressure": float(df["s"].iloc[idx]),
            "circadian_component": float(df["c"].iloc[idx]),
            "sleep_inertia": float(df["w"].iloc[idx]),
        }
        if "met_h" in df.columns:
            row["met_h"] = float(df["met_h"].iloc[idx])
            row["mission_local_time_h"] = float(df["mission_local_time_h"].iloc[idx])
            row["mission_day_index"] = int(df["mission_day_index"].iloc[idx])
        if has_workload:
            kss_adj_start = float(df["kss_workload_adjusted"].iloc[idx])
            row["predicted_kss_workload_adjusted"] = kss_adj_start
            row["delta_kss_workload"] = kss_adj_start - float(kss_values[idx])
            row["workload_equivalent_h_at_start"] = float(df["workload_equiv_h"].iloc[idx])
            row["workload_validated"] = False
            # The workload effect accumulates during a task, so the start value
            # is the least informative one. Report the end and the peak as well.
            end_raw = task.get("end")
            if end_raw is not None:
                te = pd.Timestamp(end_raw)
                if te.tzinfo is None:
                    te = te.tz_localize("UTC")
                if df.index[0] <= te <= df.index[-1]:
                    eidx = df.index.get_indexer([te], method="nearest")[0]
                    end_adj = float(df["kss_workload_adjusted"].iloc[eidx])
                    row["predicted_kss_workload_adjusted_at_end"] = end_adj
                    row["delta_kss_workload_at_end"] = end_adj - float(kss_values[eidx])
                    row["workload_equivalent_h_at_end"] = float(df["workload_equiv_h"].iloc[eidx])
                    lo, hi = sorted((idx, eidx))
                    win = df["kss_workload_adjusted"].iloc[lo:hi + 1]
                    row["peak_kss_workload_adjusted_within_task"] = float(win.max())
                    row["peak_workload_equivalent_h_within_task"] = float(
                        df["workload_equiv_h"].iloc[lo:hi + 1].max())
            row["workload_note"] = (
                "workload-adjusted KSS is a modelling extension using assumed "
                "intensity rates; it is not validated and is not a measured impairment"
            )
        out.append(row)
    return out


def counterfactual_shift(df: pd.DataFrame, task: dict,
                         shifts_h: tuple[float, ...] = (-3, -2, -1, 1, 2, 3)) -> list[dict]:
    """Alertness if the same task started ``shift`` hours earlier/later.

    Sleep schedule is unchanged, which is the realistic operational question
    ("can we move the EVA?") for shifts within the same wake period.
    """
    ts0 = pd.Timestamp(task["start"])
    if ts0.tzinfo is None:
        ts0 = ts0.tz_localize("UTC")
    values = df["alertness_raw"].to_numpy()
    if ts0 < df.index[0] or ts0 > df.index[-1]:
        return []
    base_idx = df.index.get_indexer([ts0], method="nearest")[0]
    base = float(values[base_idx])
    out = []
    kss_values = df["kss"].to_numpy()
    base_kss = float(kss_values[base_idx])
    for shift in shifts_h:
        ts = ts0 + pd.Timedelta(hours=shift)
        if ts < df.index[0] or ts > df.index[-1]:
            continue
        idx = df.index.get_indexer([ts], method="nearest")[0]
        val = float(values[idx])
        row = {
            "shift_h": shift,
            "start": ts.isoformat(),
            "alertness_raw": val,
            "delta_vs_current": val - base,
            "percentile_within_simulation": float((values <= val).mean() * 100.0),
            "predicted_kss": float(kss_values[idx]),
            "delta_kss_vs_current": float(kss_values[idx] - base_kss),
            "kss_reference_limits": kss_reference_limits(float(kss_values[idx])),
        }
        if "met_h" in df.columns:
            row["met_h"] = float(df["met_h"].iloc[idx])
            row["mission_local_time_h"] = float(df["mission_local_time_h"].iloc[idx])
            row["mission_day_index"] = int(df["mission_day_index"].iloc[idx])
        out.append(row)
    return out
