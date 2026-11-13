"""Sleep/wake detection from wrist accelerometry: van Hees 2015 / HDCZA.

This is a faithful reimplementation of the algorithm as used by **GGIR**
(``R/HASIB.R``, ``HASIB.algo = "vanHees2015"``), which is the reference
implementation of van Hees et al. (2015), PLoS ONE 10(11):e0142533.

Why this instead of a neural checkpoint: the verified sleep-staging checkpoints
(SleepFM, OSF) require clinical PSG and cannot consume wrist accelerometry. For
wrist ACC, HDCZA is a peer-reviewed deterministic algorithm with no weights.

Algorithm (exactly as in GGIR):
  1. aggregate ACC to 5 s epochs and compute the arm angle
     ``anglez = atan2(z, sqrt(x^2 + y^2))`` in degrees;
  2. a *posture change* occurs where ``|anglez[i] - anglez[i-1]| > anglethreshold``
     (default 3.0 deg);
  3. if two consecutive posture changes are separated by more than
     ``timethreshold`` (default 5 min), everything between them is a
     *sustained inactivity bout* (SIB) and labelled sleep;
  4. if there are fewer than 10 posture changes in the whole recording, the
     recording is considered not worn/constantly still and all of it is SIB.

The 30 s epoch is sleep when at least half of its 5 s sub-epochs are SIB.
"""

from __future__ import annotations

import numpy as np

from crew_health.io.bidsleep import Night, epoch_index


def _binned_means(n: Night, bin_seconds: float = 5.0) -> tuple[np.ndarray, np.ndarray]:
    rel = n.motion_t - n.rec_start.timestamp()
    idx = np.floor(rel / bin_seconds).astype(np.int64)
    max_bins = int((n.n_epochs * n.epoch_seconds) / bin_seconds) + 1
    keep = (idx >= 0) & (idx < max_bins)
    idx, xyz = idx[keep], n.motion_xyz[keep]
    nbins = int(idx.max()) + 1 if idx.size else 0
    sums = np.zeros((nbins, 3), dtype=np.float64)
    counts = np.zeros(nbins, dtype=np.float64)
    np.add.at(sums, idx, xyz)
    np.add.at(counts, idx, 1.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        means = sums / counts[:, None]
    return means, counts


def sleep_wake_van_hees(
    n: Night,
    bin_seconds: float = 5.0,
    angle_threshold_deg: float = 3.0,
    time_threshold_min: float = 5.0,
) -> tuple[np.ndarray, dict]:
    """Return (sleep_mask per epoch, diagnostics)."""
    means, counts = _binned_means(n, bin_seconds)
    if means.shape[0] < 10:
        return np.zeros(n.n_epochs, dtype=bool), {"error": "insufficient motion data"}

    x, y, z = means[:, 0], means[:, 1], means[:, 2]
    angle = np.degrees(np.arctan2(z, np.sqrt(x**2 + y**2)))
    # bins without samples: hold the previous angle (GGIR uses fix_NA_invector)
    missing = counts == 0
    if missing.any() and (~missing).any():
        w = np.flatnonzero(~missing)
        angle = np.interp(np.arange(angle.size), w, angle[w])

    # GGIR HDCZA: posture changes and the gaps between them.
    postch = np.flatnonzero(np.abs(np.diff(angle)) > angle_threshold_deg)
    min_gap_bins = int(round(time_threshold_min * 60 / bin_seconds))
    sib = np.zeros(angle.size, dtype=bool)
    if postch.size > 1:
        gaps = np.flatnonzero(np.diff(postch) > min_gap_bins)
        for gi in gaps:
            sib[postch[gi] : postch[gi + 1] + 1] = True
    elif postch.size < 10:
        # possibly not worn / constantly still: GGIR labels the whole record SIB
        sib[:] = True

    bins_per_epoch = int(round(n.epoch_seconds / bin_seconds))
    usable = (sib.size // bins_per_epoch) * bins_per_epoch
    per_epoch = sib[:usable].reshape(-1, bins_per_epoch).mean(axis=1)
    sleep = np.zeros(n.n_epochs, dtype=bool)
    k = min(n.n_epochs, per_epoch.size)
    sleep[:k] = per_epoch[:k] >= 0.5

    diag = {
        "algorithm": "van_hees_2015_HDCZA (GGIR HASIB)",
        "angle_threshold_deg": angle_threshold_deg,
        "time_threshold_min": time_threshold_min,
        "posture_changes": int(postch.size),
        "sib_minutes": float(sib.sum() * bin_seconds / 60.0),
        "recording_minutes": float(sib.size * bin_seconds / 60.0),
    }
    return sleep, diag


def sleep_wake_enmo_baseline(n: Night, active_threshold_g: float = 0.02) -> np.ndarray:
    """Naive comparator only: sleep where epoch-mean ENMO < threshold.

    Not a validated sleep algorithm; included so results can be compared against
    a trivial threshold baseline.
    """
    idx = epoch_index(n.motion_t, n.rec_start, n.epoch_seconds)
    ok = (idx >= 0) & (idx < n.n_epochs)
    idx, xyz = idx[ok], n.motion_xyz[ok]
    enmo = np.clip(np.linalg.norm(xyz, axis=1) - 1.0, 0.0, None)
    sums = np.bincount(idx, weights=enmo, minlength=n.n_epochs)
    counts = np.bincount(idx, minlength=n.n_epochs)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_enmo = sums / np.maximum(counts, 1)
    return mean_enmo < active_threshold_g


def agreement(pred_sleep: np.ndarray, n: Night) -> dict:
    """Agreement with expert EEG sleep stages (sleep = N1/N2/N3/REM)."""
    if n.expert is None:
        return {"error": "no expert labels"}
    k = min(pred_sleep.size, n.expert.size)
    truth = np.isin(n.expert[:k], (1, 2, 3, 4))
    pred = pred_sleep[:k].astype(bool)
    tp = int(np.sum(pred & truth)); tn = int(np.sum(~pred & ~truth))
    fp = int(np.sum(pred & ~truth)); fn = int(np.sum(~pred & truth))
    sens = tp / (tp + fn) if tp + fn else float("nan")
    spec = tn / (tn + fp) if tn + fp else float("nan")
    acc = (tp + tn) / max(k, 1)
    p_yes, p_true = pred.mean(), truth.mean()
    pe = p_yes * p_true + (1 - p_yes) * (1 - p_true)
    kappa = (acc - pe) / (1 - pe) if pe < 1 else float("nan")
    return {
        "n_epochs": int(k),
        "accuracy": float(acc),
        "sensitivity_sleep": float(sens),
        "specificity_wake": float(spec),
        "kappa": float(kappa),
        "predicted_sleep_fraction": float(pred.mean()),
        "expert_sleep_fraction": float(truth.mean()),
    }
