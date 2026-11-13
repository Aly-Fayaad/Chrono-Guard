"""Personal baseline and deviation detection. No model training involved.

Two established statistical ideas are used:

1. **Robust location/scale** per subject: median and scaled MAD
   (``1.4826 * MAD``), which tolerate the short, skewed nightly series typical of
   crew monitoring better than mean/SD.
2. **Empirical-Bayes shrinkage** toward a population baseline, so a crew member
   with 3 nights is not treated as if their median were equally reliable as one
   with 30 nights. This is the standard partial-pooling estimator
   ``m_i = (n_i * m_hat_i + k * m_pop) / (n_i + k)``.
3. **Persistence-gated deviations**: a single unusual night is not a flag; a
   deviation must persist for ``persistence_nights`` consecutive nights.

No thresholds here are clinical. They are statistical deviations from the
individual's own history.
"""

from __future__ import annotations

import numpy as np

DEFAULT_FEATURES = [
    "tst_min",
    "sleep_efficiency",
    "sleep_onset_latency_min",
    "waso_min",
    "fragmentation_index_per_h",
    "sleep_midpoint_clock_h",
    "longest_sleep_bout_min",
    # Cardiac features are only fitted when the records actually carry them
    # (real wearable path). Generic duration-only payloads skip them.
    "sleep_hr_mean_bpm",
    "sleep_hr_min5_bpm",
]

# Minimum usable scale per feature. Clock-time features are genuinely circular:
# if every night had the same midpoint, MAD would be 0 and a 1-hour shift would
# produce a meaningless infinite z-score, so a 30-minute floor is used instead.
SCALE_FLOORS = {"sleep_midpoint_clock_h": 0.5}


def baseline_status(n_nights: int, provisional: int = 7, established: int = 14) -> str:
    if n_nights >= established:
        return "established"
    if n_nights >= provisional:
        return "provisional"
    return "insufficient"


def _median_mad(values: np.ndarray) -> tuple[float, float]:
    med = float(np.median(values))
    mad = float(1.4826 * np.median(np.abs(values - med)))
    return med, mad


def fit_baseline(records: list[dict], features: list[str] | None = None,
                 population: dict | None = None, shrinkage_k: float = 3.0,
                 provisional_nights: int = 7, established_nights: int = 14) -> dict:
    """Fit per-subject robust baselines from nightly feature dicts."""
    features = features or DEFAULT_FEATURES
    stats: dict[str, dict] = {}
    for feat in features:
        vals = np.array([r[feat] for r in records
                         if r.get(feat) is not None and np.isfinite(r[feat])], dtype=float)
        if vals.size == 0:
            continue
        med, mad = _median_mad(vals)
        q1, q3 = np.percentile(vals, [25, 75])
        n = int(vals.size)
        mad_raw = mad
        mad = max(mad, SCALE_FLOORS.get(feat, 1e-9))

        if population and feat in population:
            m_pop, s_pop = population[feat]["median"], population[feat]["mad"]
            w = n / (n + shrinkage_k)
            med = w * med + (1 - w) * m_pop
            mad = w * mad + (1 - w) * s_pop

        stats[feat] = {
            "median": med,
            "mad": mad,
            "mad_raw": mad_raw,
            "iqr": float(q3 - q1),
            "n": n,
            "min": float(vals.min()),
            "max": float(vals.max()),
        }

    n_main = stats.get("tst_min", {}).get("n", 0)
    return {
        "features": stats,
        "n_nights": int(n_main),
        "status": baseline_status(n_main, provisional_nights, established_nights),
        "method": "median/scaled-MAD" + (" + empirical-Bayes shrinkage" if population else ""),
    }


def fit_population(subject_baselines: list[dict]) -> dict:
    """Population prior = median across subjects of each subject's median/MAD."""
    out: dict[str, dict] = {}
    keys = {f for b in subject_baselines for f in b.get("features", {})}
    for feat in keys:
        meds = [b["features"][feat]["median"] for b in subject_baselines
                if feat in b.get("features", {})]
        mads = [b["features"][feat]["mad"] for b in subject_baselines
                if feat in b.get("features", {})]
        if meds:
            out[feat] = {"median": float(np.median(meds)),
                         "mad": float(np.median(mads)) if mads else 1e-6,
                         "n_subjects": len(meds)}
    return out


def robust_z(value: float, stat: dict) -> float:
    """Robust z-score, guarded against a degenerate MAD.

    When MAD is ~0 (a very stable subject) the IQR is used instead; if that is
    also 0 the feature is treated as having no usable scale and 0 is returned
    rather than an infinite z. Circular clock features carry a 30 min floor
    (see ``SCALE_FLOORS``).
    """
    if value is None or not np.isfinite(value):
        return float("nan")
    scale = stat["mad"]
    if scale < 1e-6:
        scale = stat.get("iqr", 0.0) / 1.349
    if scale < 1e-6:
        # Near-zero variance history: floor at 2% of the median so a genuine
        # change is still flagged, but without producing an infinite z-score.
        scale = max(1e-6, 0.02 * abs(stat["median"]))
    return float((value - stat["median"]) / scale)


def detect_deviations(record: dict, baseline: dict, features: list[str] | None = None,
                      warn_z: float = 2.0, alert_z: float = 3.0) -> list[dict]:
    """Per-night univariate deviations from the personal baseline."""
    features = features or list(baseline["features"])
    out = []
    for feat in features:
        if feat not in baseline["features"]:
            continue
        value = record.get(feat)
        z = robust_z(value, baseline["features"][feat])
        if not np.isfinite(z):
            continue
        if abs(z) >= warn_z:
            out.append({
                "feature": feat,
                "value": float(value),
                "baseline_median": baseline["features"][feat]["median"],
                "robust_z": z,
                "direction": "above" if z > 0 else "below",
                "severity": "alert" if abs(z) >= alert_z else "warn",
            })
    return out


def persistent_deviations(records: list[dict], baseline: dict, feature: str,
                          z_threshold: float = 2.0, persistence_nights: int = 2) -> list[dict]:
    """Flag runs where |z| stays above threshold for N consecutive nights."""
    zs = [robust_z(r.get(feature), baseline["features"][feature])
          if feature in baseline["features"] else np.nan for r in records]
    events, run = [], []
    for i, z in enumerate(zs + [np.nan]):
        if np.isfinite(z) and abs(z) >= z_threshold:
            run.append(i)
            continue
        if len(run) >= persistence_nights:
            events.append({
                "feature": feature,
                "start_index": run[0],
                "end_index": run[-1],
                "nights": len(run),
                "mean_robust_z": float(np.mean([zs[j] for j in run])),
                "direction": "above" if np.mean([zs[j] for j in run]) > 0 else "below",
            })
        run = []
    return events
