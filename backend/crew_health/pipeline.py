"""End-to-end analysis pipeline.

Two entry points:

* ``analyze_night_file`` - processes one real wearable night (ACC + HR + EEG
  labels when present), runs HDCZA sleep/wake detection and returns features,
  QC and agreement metrics.
* ``analyze`` - the product-level call used by the API. Takes nightly sleep
  records and a mission schedule and returns baseline deviations, circadian
  summary, predicted alertness/KSS and schedule risk.

Nothing here claims clinical or astronaut validity; limitations are returned
with every response.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from crew_health.baseline import (
    DEFAULT_FEATURES,
    detect_deviations,
    fit_baseline,
    persistent_deviations,
)
from crew_health.fatigue.tpm import (
    PARAMETER_PROVENANCE,
    TPMParams,
    alertness_percentile,
    kss_percentile,
    kss_reference_limits,
    sleep_debt_hours,
    summarize,
)
from crew_health.features.cardiac import cardiac_features, cardiac_quality
from crew_health.features.episodes import circadian_summary, night_features
from crew_health.features.sleepwake import agreement, sleep_wake_van_hees
from crew_health.io.bidsleep import load_night
from crew_health.mission import (
    mission_local_time_hours,
    mission_params_from_dict,
    mission_summary,
)
from crew_health.schedule import counterfactual_shift, risk_band, simulate_schedule, task_risk
from crew_health.workload import (
    WorkloadParams,
    apply_workload,
    summarize_workload,
    task_workload_summary,
)

LIMITATIONS = [
    "Research prototype; not a medical device and not an autonomous mission decision aid.",
    "Predicted KSS is a group-level prediction from the published three-process "
    "model (Ingre et al. 2014, validated on 136 aircrew). It is not calibrated to "
    "the individual, has a residual SD of 1.42 KSS units, and is NOT a PVT or "
    "performance prediction.",
    "Sleep inertia is reported as a diagnostic only; the validation paper found "
    "that adding process W decreased goodness of fit.",
    "Risk bands are percentiles within the simulated schedule, not clinical thresholds.",
    "The mission-day length (default 24.65 h) is an operational convention. The "
    "published circadian equations are 24 h / 12 h and are not validated for "
    "non-24-hour days; overriding the circadian period is an unvalidated "
    "extrapolation.",
    "Split-sleep episodes are supported, but the three-process model was validated "
    "on consolidated sleep; nap-specific effects are not modelled.",
    "Model parameters were estimated on Earth populations; not validated in "
    "microgravity or on astronaut crews.",
]


def _ts(value, tz: str | None = None) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(tz or "UTC")
    return ts


def _clock_hour(ts: pd.Timestamp) -> float:
    return ts.hour + ts.minute / 60 + ts.second / 3600


def normalize_records(records: list[dict], tz: str) -> list[dict]:
    """Turn the app's nightly records into the feature dicts the models use."""
    out = []
    for rec in records:
        r = dict(rec)
        start = rec.get("sleep_start")
        end = rec.get("sleep_end")
        if start and end:
            # Convert every timestamp to the analysis timezone so the
            # simulation's clock-hour terms are interpreted consistently.
            s, e = _ts(start, tz).tz_convert(tz), _ts(end, tz).tz_convert(tz)
            duration_h = (e - s).total_seconds() / 3600.0
            r.setdefault("sleep_duration_hours", duration_h)
            r.setdefault("tst_min", duration_h * 60.0)
            mid = s + (e - s) / 2
            r.setdefault("sleep_midpoint_clock_h", _clock_hour(mid))
            r.setdefault("sleep_start_clock_h", _clock_hour(s))
            r.setdefault("sleep_end_clock_h", _clock_hour(e))
            r["_sleep_start_ts"] = s
            r["_sleep_end_ts"] = e
        episodes = rec.get("sleep_episodes") or []
        episode_windows = [
            (_ts(ep["start"], tz).tz_convert(tz), _ts(ep["end"], tz).tz_convert(tz))
            for ep in episodes
            if ep.get("start") and ep.get("end")
        ]
        if episode_windows:
            r["_sleep_windows"] = episode_windows
            if "_sleep_start_ts" not in r:
                longest = max(
                    episodes,
                    key=lambda ep: ep.get("tst_min") or 0.0,
                )
                if longest.get("start") and longest.get("end"):
                    r["_sleep_start_ts"] = _ts(longest["start"], tz).tz_convert(tz)
                    r["_sleep_end_ts"] = _ts(longest["end"], tz).tz_convert(tz)
        if r.get("date") is None:
            r["date"] = (r["_sleep_end_ts"].date().isoformat()
                         if "_sleep_end_ts" in r else None)
        out.append(r)
    return sorted(out, key=lambda x: x.get("date") or "")


def apply_mission_clock(records: list[dict], mission) -> list[dict]:
    """Re-express recorded sleep clock hours on the mission clock (MLT).

    Only used when the caller sets ``mission.records_on_mission_clock = true``.
    The default leaves Earth-recorded clock hours untouched; reinterpreting a
    24 h clock on a 24.65 h dial without this conversion would be wrong.

    Both record-level fields and per-episode rows are converted, so split-sleep
    timing statistics stay consistent with the record they belong to.
    """

    def to_mlt(ts) -> float:
        return float(mission_local_time_hours([ts], mission)[0])

    for rec in records:
        start = rec.get("_sleep_start_ts")
        end = rec.get("_sleep_end_ts")
        if start is not None and end is not None:
            rec["sleep_start_clock_h"] = to_mlt(start)
            rec["sleep_end_clock_h"] = to_mlt(end)
            rec["sleep_midpoint_clock_h"] = to_mlt(start + (end - start) / 2)

        for episode in rec.get("sleep_episodes") or []:
            raw_start = episode.get("start_utc") or episode.get("start")
            raw_end = episode.get("end_utc") or episode.get("end")
            if not raw_start or not raw_end:
                continue
            default_tz = mission.epoch.tz if mission.epoch is not None else "UTC"
            ep_start = pd.Timestamp(raw_start)
            ep_end = pd.Timestamp(raw_end)
            if ep_start.tzinfo is None:
                ep_start = ep_start.tz_localize(default_tz)
            if ep_end.tzinfo is None:
                ep_end = ep_end.tz_localize(default_tz)
            episode["start_clock_h"] = to_mlt(ep_start)
            episode["end_clock_h"] = to_mlt(ep_end)
            episode["midpoint_clock_h"] = to_mlt(ep_start + (ep_end - ep_start) / 2)
            # Keep both spellings in sync for downstream timing statistics.
            episode["sleep_midpoint_clock_h"] = episode["midpoint_clock_h"]
            episode["sleep_start_clock_h"] = episode["start_clock_h"]
            episode["sleep_end_clock_h"] = episode["end_clock_h"]
    return records


def _history_windows(records: list[dict]) -> list[tuple]:
    """All sleep windows, including every episode of a split-sleep night."""
    windows = []
    for r in records:
        if r.get("_sleep_windows"):
            windows.extend(r["_sleep_windows"])
        elif "_sleep_start_ts" in r and "_sleep_end_ts" in r:
            windows.append((r["_sleep_start_ts"], r["_sleep_end_ts"]))
    return windows


def _habitual(records: list[dict]) -> tuple[float, float]:
    """Median bedtime clock hour and sleep duration, circularly averaged."""
    starts = [r["sleep_start_clock_h"] for r in records if r.get("sleep_start_clock_h") is not None]
    durations = [r["sleep_duration_hours"] for r in records
                 if r.get("sleep_duration_hours") is not None]
    if not starts:
        return 23.0, 8.0
    ang = 2 * np.pi * np.array(starts) / 24
    mean_h = float((np.degrees(np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())) % 360) / 15)
    return mean_h, float(np.median(durations)) if durations else 8.0


def analyze(payload: dict) -> dict:
    subject = payload.get("subject_id")
    if not subject:
        raise ValueError("subject_id is required")
    tz = payload.get("timezone", "UTC")
    as_of = _ts(payload["as_of"], tz) if payload.get("as_of") else pd.Timestamp.now(tz="UTC")
    as_of = as_of.tz_convert(tz)
    records = normalize_records(payload.get("nightly_records", []), tz)
    if not records:
        raise ValueError("nightly_records is required")

    # --- operational mission clock (item 3) ---------------------------------
    # Defaults to a 24.65 h lunar mission day. This affects mission local time,
    # MET and day indexing; the published 24 h circadian equations are used
    # unchanged unless the caller explicitly overrides them.
    mission_cfg = payload.get("mission") or {}
    mission = mission_params_from_dict(mission_cfg, default_epoch=as_of)
    records_on_mission_clock = bool(mission_cfg.get("records_on_mission_clock", False))
    if records_on_mission_clock:
        # Reinterpret recorded sleep times on the mission dial. Without this the
        # flag would only change the circular statistics period while leaving
        # Earth-clock hour values in place, which would be wrong.
        records = apply_mission_clock(records, mission)

    # --- baseline uses nights strictly before the latest night ---------------
    history = records[:-1] if len(records) > 1 else records
    baseline = fit_baseline(history)
    latest = records[-1]
    deviations = detect_deviations(latest, baseline) if baseline["features"] else []
    persistent = []
    for feat in ("tst_min", "sleep_efficiency", "sleep_midpoint_clock_h"):
        if feat in baseline["features"]:
            persistent.extend(persistent_deviations(history, baseline, feat,
                                                    persistence_nights=2))
    for ev in persistent:
        ev["feature"] = str(ev["feature"])

    circ = circadian_summary(
        records,
        period_h=(
            mission.mission_day_h
            if (payload.get("mission") or {}).get("records_on_mission_clock")
            else 24.0
        ),
    )

    # --- alertness: simulate past history + next 48 h ------------------------
    # Only the most recent week of sleep history is relevant to the current
    # alertness state; older nights would otherwise create long spurious
    # wake periods when recordings are weeks apart.
    all_windows = _history_windows(records)
    recent = [w for w in all_windows if w[1] >= as_of - pd.Timedelta(days=7)]
    windows = recent or all_windows
    horizon_end = as_of + pd.Timedelta(hours=48)
    sleep_opps = payload.get("sleep_opportunities", [])
    for opp in sleep_opps:
        windows.append((
            _ts(opp["start"], tz).tz_convert(tz),
            _ts(opp["end"], tz).tz_convert(tz),
        ))

    debt = sleep_debt_hours(records)

    # If no planned sleep exists in the next 24 h, assume habitual sleep.
    if windows:
        future = [w for w in windows if w[1] > as_of + pd.Timedelta(hours=24)]
        if not future:
            bedtime_h, dur_h = _habitual(records)
            day = as_of.normalize()
            for d in range(0, 3):
                start = (day + pd.Timedelta(days=d, hours=bedtime_h))
                if start < as_of:
                    start += pd.Timedelta(days=1)
                windows.append((start, start + pd.Timedelta(hours=dur_h)))
        history_start = max(min(w[0] for w in windows) - pd.Timedelta(hours=1),
                            as_of - pd.Timedelta(days=14))
    else:
        history_start = as_of - pd.Timedelta(hours=6)

    if windows:
        tasks = payload.get("upcoming_tasks", [])
        sim = simulate_schedule(history_start, horizon_end, windows, dt_min=5,
                                mission=mission)
        # Workload is a modelling extension; it only adds columns, never
        # overwrites the validated KSS.
        sim = apply_workload(sim, tasks) if tasks else sim
        sim_summary = summarize(sim)
        workload_summary = summarize_workload(sim)
        sleep_flags = sim["sleep"].to_numpy(dtype=bool)
        padded = np.concatenate(([False], sleep_flags, [False]))
        edges = np.flatnonzero(padded[1:] != padded[:-1])
        simulated_episodes = []
        for i in range(0, edges.size, 2):
            a, b = int(edges[i]), int(edges[i + 1] - 1)
            simulated_episodes.append({
                "start": sim.index[a].isoformat(),
                "end": sim.index[b].isoformat(),
                "duration_h": (sim.index[b] - sim.index[a]).total_seconds() / 3600.0,
                "met_h": float(sim["met_h"].iloc[a]),
                "mission_day_index": int(sim["mission_day_index"].iloc[a]),
            })
        current_pct = alertness_percentile(sim, as_of)
        as_of_idx = sim.index.get_indexer([as_of], method="nearest")[0]
        current_kss = float(sim["kss"].iloc[as_of_idx])
        alertness = {
            "model": "three_process_model_ingre2014",
            "status": "estimated",
            # Not calibrated to this individual; the KSS transfer itself is
            # the published, validated group-level function.
            "calibrated": False,
            "individual_calibration": "none",
            "units": "KSS (1-9) group-level prediction",
            "current_alertness_raw": float(sim["alertness_raw"].iloc[as_of_idx]),
            "current_percentile_within_simulation": current_pct,
            "current_band": risk_band(current_pct),
            "current_predicted_kss": current_kss,
            "kss_reference_limits": kss_reference_limits(current_kss),
            "kss_percentile_within_simulation": kss_percentile(sim, as_of),
            "sleep_debt_hours": debt,
            "homeostatic_pressure": float(sim["s"].iloc[as_of_idx]),
            "circadian_component": float(sim["c"].iloc[as_of_idx]),
            "ultradian_component": float(sim["u"].iloc[as_of_idx]),
            "sleep_inertia": float(sim["w"].iloc[as_of_idx]),
            "met_hours": float(sim["met_h"].iloc[as_of_idx]),
            "mission_local_time_hours": float(sim["mission_local_time_h"].iloc[as_of_idx]),
            "mission_day_index": int(sim["mission_day_index"].iloc[as_of_idx]),
            "simulation_summary": sim_summary,
            "simulated_sleep_episodes": simulated_episodes,
            "workload": workload_summary,
            "workload_tasks": task_workload_summary(sim, tasks) if tasks else [],
            "provenance": PARAMETER_PROVENANCE,
            "validation_status": (
                "KSS mapping validated on aircrew (Ingre et al. 2014); not validated "
                "in microgravity, not a PVT/performance prediction, no individual "
                "calibration. Workload-adjusted KSS is a modelling extension and is "
                "not validated at all."
            ),
        }
        risks = task_risk(sim, tasks) if tasks else []
        counterfactuals = {}
        for task in tasks[:3]:
            shifts = counterfactual_shift(sim, task)
            if shifts:
                counterfactuals[task.get("task_id", "task")] = shifts
    else:
        alertness = {
            "model": "three_process_model_ingre2014",
            "calibrated": False,
            "individual_calibration": "none",
            "units": "KSS (1-9) group-level prediction",
            "status": "unavailable",
            "reason": ("The three-process model needs sleep timing (bedtime and wake "
                       "time). These records contain only durations, so no sleep/wake "
                       "timeline can be reconstructed."),
            "sleep_debt_hours": debt,
            "provenance": PARAMETER_PROVENANCE,
        }
        risks, counterfactuals = [], {}

    return {
        "subject_id": subject,
        "analysis_date": as_of.date().isoformat(),
        "as_of": as_of.isoformat(),
        "window": {
            "nights_observed": len(records),
            "first_night": records[0].get("date"),
            "last_night": records[-1].get("date"),
        },
        "baseline": {
            "status": baseline["status"],
            # The baseline is fitted on the nights *before* the latest one, so
            # the latest night is never compared against a baseline that
            # includes itself.
            "n_nights": baseline["n_nights"],
            "n_nights_observed": len(records),
            "n_nights_used": baseline["n_nights"],
            "method": baseline["method"],
            "note": (
                "Fitted on the nights preceding the latest night, excluding the "
                "latest night itself. Thresholds: <7 prior nights = insufficient, "
                "7-13 = provisional, >=14 = established."
            ),
        },
        "latest_night": {
            k: latest.get(k) for k in
            ("date", "tst_min", "sleep_duration_hours", "sleep_efficiency",
             "sleep_onset_latency_min", "waso_min", "awakenings",
             "sleep_midpoint_clock_h", "fragmentation_index_per_h",
             "sleep_hr_mean_bpm", "sleep_hr_min5_bpm",
             "n_sleep_episodes", "split_sleep")
        },
        "deviations": deviations,
        "persistent_deviations": persistent,
        "circadian": circ,
        "mission_time": {
            **mission_summary(as_of, mission),
            "epoch": mission.epoch.isoformat() if mission.epoch is not None else None,
            "records_time_basis": (
                "mission_clock" if records_on_mission_clock else "earth_clock"
            ),
            "published_circadian_equations_unchanged": (
                mission.uses_published_circadian_period
            ),
            "circadian_equations_status": (
                "published 24 h / 12 h equations unchanged"
                if mission.uses_published_circadian_period
                else "non-default circadian period/time source; unvalidated extrapolation"
            ),
            "note": (
                "The mission day length is an operational convention. It drives "
                "MET, mission local time and the day index. It does not change the "
                "published circadian equations unless circadian_period_hours or "
                "circadian_time_source is overridden."
            ),
        },
        "alertness": alertness,
        "schedule_risk": risks,
        "counterfactuals": counterfactuals,
        "limitations": LIMITATIONS,
        "confidence": None,
    }


def analyze_night_file(raw_dir: str, subject: str, night: int,
                       angle_threshold_deg: float = 3.0) -> dict:
    """Process one real wearable night and report features + validation."""
    from crew_health.features.episodes import sleep_episode

    n = load_night(raw_dir, subject, night)
    pred, diag = sleep_wake_van_hees(n, angle_threshold_deg=angle_threshold_deg)
    feats = night_features(n, pred, stage_labels=n.expert)
    ep = sleep_episode(pred, n.epoch_seconds)
    cardiac = cardiac_features(n, ep["onset_epoch"], ep["final_wake_epoch"]) \
        if "onset_epoch" in ep else {"unavailable": ["no sleep episode"]}
    result = {
        "subject_id": subject,
        "night": int(night),
        "rec_start": n.rec_start.isoformat(),
        "sleep_wake": diag,
        "features": feats,
        "cardiac": cardiac,
        "cardiac_quality": cardiac_quality(cardiac),
        "validation_vs_expert_eeg": agreement(pred, n),
        "qc": {
            "motion_samples": int(n.motion_t.size) if n.has_motion else 0,
            "hr_samples": int(n.hr_t.size) if n.has_hr else 0,
            "epochs": int(n.n_epochs),
            "warnings": n.meta.get("warnings", []),
        },
        "limitations": LIMITATIONS,
    }
    if n.expert is not None and feats.get("stage_source"):
        result["sleep_architecture"] = {
            k: feats.get(k) for k in
            ("n1_min", "n2_min", "n3_min", "rem_min", "wake_min",
             "rem_pct_tst", "deep_pct_tst", "stage_source")
        }
    return result


# ---------------------------------------------------------------------------
# Real-data path: wrist ACC -> sleep episode -> product pipeline
# ---------------------------------------------------------------------------

REAL_TZ = "America/New_York"   # BIDSleep recordings were collected in the US


def record_from_night(n, sleep_mask=None, angle_threshold_deg: float = 3.0) -> dict:
    """Convert one wearable night into the pipeline's nightly record schema.

    For a split-sleep night the record keeps every episode in
    ``sleep_episodes``; the top-level ``sleep_start``/``sleep_end`` describe the
    **longest** episode, and ``tst_min`` is total sleep across all episodes.
    """
    from crew_health.features.episodes import sleep_episode

    if sleep_mask is None:
        sleep_mask, _ = sleep_wake_van_hees(n, angle_threshold_deg=angle_threshold_deg)
    ep = sleep_episode(sleep_mask, n.epoch_seconds)
    if "onset_epoch" not in ep:
        raise ValueError(f"{n.subject} night {n.night}: no sleep episode detected")

    feats = night_features(n, sleep_mask, stage_labels=n.expert)
    episodes = feats.get("sleep_episodes") or []
    main = max(episodes, key=lambda e: e.get("tst_min") or 0.0) if episodes else None
    if main is not None:
        start = pd.Timestamp(main["start_utc"]).tz_convert(REAL_TZ)
        end = pd.Timestamp(main["end_utc"]).tz_convert(REAL_TZ)
        cardiac_onset, cardiac_wake = main["onset_epoch"], main["final_wake_epoch"]
    else:
        start = (n.rec_start + pd.Timedelta(seconds=ep["onset_epoch"] * n.epoch_seconds)).tz_convert(REAL_TZ)
        end = (n.rec_start + pd.Timedelta(seconds=ep["final_wake_epoch"] * n.epoch_seconds)).tz_convert(REAL_TZ)
        cardiac_onset, cardiac_wake = ep["onset_epoch"], ep["final_wake_epoch"]

    total_tst = ep["tst_min"]
    if len(episodes) > 1:
        assigned_tst = sum(e["tst_min"] for e in episodes)
        total_span = sum(e["span_min"] for e in episodes)
        efficiency = assigned_tst / total_span if total_span else ep["sleep_efficiency"]
        waso = total_span - assigned_tst
    else:
        efficiency = ep["sleep_efficiency"]
        waso = ep["waso_min"]
    cardiac = cardiac_features(n, cardiac_onset, cardiac_wake)

    return {
        "date": end.date().isoformat(),
        "sleep_start": start.isoformat(),
        "sleep_end": end.isoformat(),
        "tst_min": float(total_tst),
        "sleep_duration_hours": float(total_tst) / 60.0,
        "sleep_efficiency": efficiency,
        "sleep_onset_latency_min": ep["sleep_onset_latency_min"],
        "waso_min": waso,
        "awakenings": ep["awakenings"],
        "fragmentation_index_per_h": ep["fragmentation_index_per_h"],
        "sleep_midpoint_clock_h": feats.get("sleep_midpoint_clock_h"),
        "longest_sleep_bout_min": ep["longest_sleep_bout_min"],
        "n_sleep_episodes": int(feats.get("n_sleep_episodes", 1)),
        "split_sleep": bool(feats.get("split_sleep", False)),
        "sleep_episodes": [
            {"start": e["start_utc"], "end": e["end_utc"], "tst_min": e["tst_min"]}
            for e in episodes
        ],
        # Measured cardiac summaries (None when the data cannot support them).
        "sleep_hr_mean_bpm": cardiac.get("sleep_hr_mean_bpm"),
        "sleep_hr_min5_bpm": cardiac.get("sleep_hr_min5_bpm"),
        "sleep_hr_sd_bpm": cardiac.get("sleep_hr_sd_bpm"),
        "cardiac": cardiac,
        "source": "wrist_acc_HDCZA + wrist_ppg_hr",
    }


def analyze_real_subject(raw_dir: str, subject: str, nights: list[int],
                         as_of: str | None = None,
                         tasks: list[dict] | None = None) -> dict:
    """Run the full pipeline on real wearable nights for one participant."""
    records, validation, per_night = [], [], []
    for night in nights:
        n = load_night(raw_dir, subject, night)
        mask, diag = sleep_wake_van_hees(n)
        rec = record_from_night(n, sleep_mask=mask)
        records.append(rec)
        val = agreement(mask, n)
        validation.append({"night": night, **val})
        cardiac = rec.get("cardiac", {})
        per_night.append({
            "night": night,
            "date": rec["date"],
            "tst_min": round(rec["tst_min"], 1),
            "sleep_efficiency": round(rec["sleep_efficiency"], 3),
            "midpoint_clock_h": round(rec["sleep_midpoint_clock_h"], 2),
            "sleep_hr_mean_bpm": cardiac.get("sleep_hr_mean_bpm"),
            "sleep_hr_min5_bpm": cardiac.get("sleep_hr_min5_bpm"),
            **{k: diag[k] for k in ("posture_changes", "sib_minutes")},
        })

    if not records:
        raise ValueError("no usable nights")

    records.sort(key=lambda r: r["date"])
    last_end = pd.Timestamp(records[-1]["sleep_end"])
    as_of = as_of or (last_end + pd.Timedelta(hours=10)).isoformat()

    if tasks is None:
        eva_day = (last_end + pd.Timedelta(days=1)).normalize() + pd.Timedelta(hours=9)
        tasks = [
            {"task_id": "EVA-12", "start": eva_day.isoformat(),
             "end": (eva_day + pd.Timedelta(hours=4)).isoformat(), "workload_level": "high"},
            {"task_id": "LAB-07", "start": (eva_day + pd.Timedelta(hours=7)).isoformat(),
             "end": (eva_day + pd.Timedelta(hours=9)).isoformat(), "workload_level": "medium"},
        ]

    payload = {
        "subject_id": subject,
        "as_of": as_of,
        "timezone": REAL_TZ,
        "nightly_records": records,
        "upcoming_tasks": tasks,
    }
    result = analyze(payload)
    result["data_path"] = (
        "real wearable accelerometry (HDCZA) -> sleep/wake -> nightly features; "
        "wrist PPG heart rate -> measured cardiac summaries"
    )
    result["sleep_wake_validation"] = validation
    result["nights"] = per_night
    result["cardiac_summary"] = _cardiac_summary(records)
    result["nightly_records_used"] = records
    return result


def _cardiac_summary(records: list[dict]) -> dict:
    """Across-night measured cardiac summary (no interpretation, no thresholds)."""
    means = [r["sleep_hr_mean_bpm"] for r in records if r.get("sleep_hr_mean_bpm") is not None]
    mins = [r["sleep_hr_min5_bpm"] for r in records if r.get("sleep_hr_min5_bpm") is not None]
    deltas = [r["cardiac"].get("hr_sleep_wake_delta_bpm") for r in records
              if r.get("cardiac") and r["cardiac"].get("hr_sleep_wake_delta_bpm") is not None]
    out = {
        "n_nights_with_hr": len(means),
        "sleep_hr_mean_bpm": float(np.mean(means)) if means else None,
        "sleep_hr_min5_bpm": float(np.mean(mins)) if mins else None,
        "n_nights_with_wake_hr": len(deltas),
        "mean_sleep_wake_delta_bpm": float(np.mean(deltas)) if deltas else None,
        "notes": [
            "Heart rate is wrist PPG, not ECG, and has not been validated against ECG here.",
            "Recordings start at sleep onset, so no pre-sleep baseline exists and a "
            "pre-sleep vs sleep heart-rate dip is not reported.",
            "No clinical thresholds are applied; values are measured summaries only.",
        ],
    }
    return out
