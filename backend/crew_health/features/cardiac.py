"""Nocturnal cardiac features from wrist PPG heart rate.

The BIDSleep recordings provide heart rate at ~0.2 Hz (one sample every ~5 s)
alongside accelerometry. This module extracts *measured* cardiac summaries
within the detected sleep episode; nothing here is a model estimate.

Two constraints shaped the feature set and are reported with every result:

1. The recordings begin at sleep onset, so there is no reliable pre-sleep
   baseline. A "sleep vs pre-sleep HR dip" therefore cannot be computed from
   this data and is **not** reported.
2. A sleep-to-wake difference (``hr_sleep_wake_delta_bpm``) is only computed
   when at least ``MIN_WAKE_SAMPLES`` heart-rate samples exist in the hour
   after final wake. Otherwise the field is ``None``, never a guess.

No clinical thresholds are applied. Low resting heart rate, HR variability and
the absence of a nocturnal dip are meaningful in cardiology, but this project
makes no diagnostic claim and, importantly, the PPG signal here has not been
validated against ECG.
"""

from __future__ import annotations

import numpy as np

from crew_health.io.bidsleep import Night

# Sampling is ~0.2 Hz (5 s). 20 samples = ~100 s of post-wake data.
MIN_WAKE_SAMPLES = 20
WAKE_WINDOW_MIN = 60.0


def cardiac_features(
    n: Night,
    onset_epoch: int,
    final_wake_epoch: int,
) -> dict:
    """Summarise heart rate inside and just after the sleep episode.

    Returns a dict of measured summaries plus QC fields. Any metric that the
    data cannot support is set to ``None`` with the reason recorded in
    ``unavailable``.
    """
    out: dict = {
        "hr_source": "wrist_ppg",
        "hr_samples": 0,
        "unavailable": [],
    }
    if not n.has_hr:
        out["unavailable"].append("no heart-rate samples in recording")
        return out

    t = n.hr_t
    hr = n.hr_bpm
    ep = float(n.epoch_seconds)

    t_sleep = n.rec_start.timestamp() + onset_epoch * ep
    t_wake = n.rec_start.timestamp() + final_wake_epoch * ep

    in_sleep = (t >= t_sleep) & (t <= t_wake) & np.isfinite(hr)
    vals = hr[in_sleep]
    out["hr_samples"] = int(vals.size)
    out["hr_coverage"] = float(vals.size * 5.0 / max((t_wake - t_sleep), 1.0))
    if vals.size < 20:
        out["unavailable"].append("fewer than 20 heart-rate samples during sleep")
        return out

    p5, p10, p50, p90 = np.percentile(vals, [5, 10, 50, 90])
    out.update({
        "sleep_hr_mean_bpm": float(vals.mean()),
        "sleep_hr_median_bpm": float(p50),
        "sleep_hr_min5_bpm": float(p5),
        "sleep_hr_p90_bpm": float(p90),
        "sleep_hr_sd_bpm": float(vals.std(ddof=1)) if vals.size > 1 else None,
        # Within-sleep spread: a proxy for autonomic variation, NOT RMSSD
        # (RMSSD needs beat-to-beat intervals; we only have 5 s HR samples).
        "sleep_hr_p90_minus_p10_bpm": float(p90 - p10),
    })

    # --- sleep-to-wake difference, only when enough post-wake data exists ----
    in_wake = (
        (t > t_wake)
        & (t <= t_wake + WAKE_WINDOW_MIN * 60.0)
        & np.isfinite(hr)
    )
    wake_vals = hr[in_wake]
    out["wake_hr_samples"] = int(wake_vals.size)
    if wake_vals.size >= MIN_WAKE_SAMPLES:
        out["wake_hr_mean_bpm"] = float(wake_vals.mean())
        out["hr_sleep_wake_delta_bpm"] = float(wake_vals.mean() - vals.mean())
    else:
        out["wake_hr_mean_bpm"] = None
        out["hr_sleep_wake_delta_bpm"] = None
        out["unavailable"].append(
            "fewer than %d post-wake HR samples; sleep-wake difference not computed"
            % MIN_WAKE_SAMPLES
        )

    return out


def cardiac_quality(features: dict) -> str:
    """Coarse usability label for the cardiac block (not a clinical grade)."""
    if not features.get("hr_samples"):
        return "unavailable"
    if features.get("hr_coverage", 0.0) < 0.5:
        return "low_coverage"
    if features.get("hr_samples", 0) < 100:
        return "sparse"
    return "usable"
