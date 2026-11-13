"""Loader for a single BIDSleep night (Apple Watch ACC + PPG HR + EEG labels).

Verified against the real files:

* ``motion.csv``: ``Timestamp,x,y,z``; ~50 Hz; units are g; contains occasional
  malformed timestamps that must be filtered.
* ``hr.csv``: headerless ``timestamp,hr``; ~0.2 Hz; bpm.
* ``labels.mat``: ``recStart`` is a *naive US/Eastern* string; ``expert_label``
  and ``dreem_label`` are 30 s epochs with 0=Wake, 1=N1, 2=N2, 3=N3, 4=REM,
  5=Unknown.

The loader never raises on a single bad row; it records QC warnings instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import scipy.io as sio

STAGE_NAMES = {0: "Wake", 1: "N1", 2: "N2", 3: "N3", 4: "REM", 5: "Unknown"}
SLEEP_STAGES = (1, 2, 3, 4)


@dataclass
class Night:
    subject: str
    night: int
    rec_start: pd.Timestamp
    epoch_seconds: int
    n_epochs: int
    expert: np.ndarray | None = None
    dreem: np.ndarray | None = None
    motion_t: np.ndarray | None = None
    motion_xyz: np.ndarray | None = None
    hr_t: np.ndarray | None = None
    hr_bpm: np.ndarray | None = None
    meta: dict = field(default_factory=dict)

    @property
    def has_motion(self) -> bool:
        return self.motion_t is not None and self.motion_t.size > 0

    @property
    def has_hr(self) -> bool:
        return self.hr_t is not None and self.hr_t.size > 0


def parse_rec_start(value) -> pd.Timestamp:
    """Convert the ``recStart`` field to a tz-aware UTC timestamp.

    The dataset stores a naive US/Eastern wall-clock string. Some releases may
    store an epoch number instead, so both are handled.
    """
    raw = np.asarray(value).ravel()[0]
    if isinstance(raw, (bytes, np.bytes_)):
        raw = raw.decode()
    if isinstance(raw, str):
        ts = pd.Timestamp(raw)
    else:
        # numeric -> epoch seconds
        ts = pd.Timestamp(float(raw), unit="s", tz="UTC")
    if ts.tzinfo is None:
        ts = ts.tz_localize(ZoneInfo("America/New_York"))
    return ts.tz_convert("UTC")


def _load_labels(path: Path) -> tuple[pd.Timestamp, np.ndarray, np.ndarray | None]:
    mat = sio.loadmat(path)
    rec_start = parse_rec_start(mat["recStart"])
    expert = np.asarray(mat["expert_label"]).ravel().astype(np.int8)
    dreem = np.asarray(mat["dreem_label"]).ravel().astype(np.int8) if "dreem_label" in mat else None
    return rec_start, expert, dreem


def _load_motion(path: Path, rec_start: pd.Timestamp) -> tuple[np.ndarray, np.ndarray, dict]:
    df = pd.read_csv(
        path,
        usecols=["Timestamp", "x", "y", "z"],
        dtype={"Timestamp": np.float64, "x": np.float32, "y": np.float32, "z": np.float32},
    )
    t = df["Timestamp"].to_numpy(dtype=np.float64)
    xyz = df[["x", "y", "z"]].to_numpy(dtype=np.float32)

    lo = rec_start.timestamp() - 6 * 3600
    hi = rec_start.timestamp() + 24 * 3600
    ok = np.isfinite(t) & (t >= lo) & (t <= hi)
    n_bad = int((~ok).sum())
    t, xyz = t[ok], xyz[ok]

    order = np.argsort(t, kind="stable")
    t, xyz = t[order], xyz[order]
    keep = np.concatenate(([True], np.diff(t) > 0))
    t, xyz = t[keep], xyz[keep]

    dt = np.diff(t)
    median_dt = float(np.median(dt)) if dt.size else float("nan")
    return t, xyz, {"motion_rows_used": int(t.size), "motion_rows_dropped": n_bad,
                    "motion_median_dt_s": median_dt}


def _load_hr(path: Path, rec_start: pd.Timestamp) -> tuple[np.ndarray, np.ndarray, dict]:
    df = pd.read_csv(path, header=None, names=["t", "hr"])
    t = df["t"].to_numpy(dtype=np.float64)
    hr = df["hr"].to_numpy(dtype=np.float64)
    lo = rec_start.timestamp() - 6 * 3600
    hi = rec_start.timestamp() + 24 * 3600
    ok = np.isfinite(t) & np.isfinite(hr) & (t >= lo) & (t <= hi) & (hr > 20) & (hr < 250)
    t, hr = t[ok], hr[ok]
    order = np.argsort(t, kind="stable")
    return t[order], hr[order], {"hr_samples": int(t.size)}


def load_night(raw_dir: str | Path, subject: str, night: int,
               epoch_seconds: int = 30) -> Night:
    """Load one night and align samples to 30 s epochs relative to ``recStart``."""
    folder = Path(raw_dir) / subject / str(night)
    if not folder.exists():
        raise FileNotFoundError(f"night folder not found: {folder}")

    rec_start, expert, dreem = _load_labels(folder / "labels.mat")
    meta: dict = {"folder": str(folder), "warnings": []}

    motion_t = motion_xyz = None
    motion_path = folder / "motion.csv"
    if motion_path.exists():
        motion_t, motion_xyz, mm = _load_motion(motion_path, rec_start)
        meta.update(mm)
        if mm["motion_rows_dropped"]:
            meta["warnings"].append(
                f"dropped {mm['motion_rows_dropped']} motion rows with invalid timestamps"
            )
    else:
        meta["warnings"].append("motion.csv missing")

    hr_t = hr_bpm = None
    hr_path = folder / "hr.csv"
    if hr_path.exists():
        hr_t, hr_bpm, hm = _load_hr(hr_path, rec_start)
        meta.update(hm)
    else:
        meta["warnings"].append("hr.csv missing")

    return Night(
        subject=subject, night=int(night), rec_start=rec_start,
        epoch_seconds=int(epoch_seconds), n_epochs=int(expert.size),
        expert=expert, dreem=dreem,
        motion_t=motion_t, motion_xyz=motion_xyz, hr_t=hr_t, hr_bpm=hr_bpm,
        meta=meta,
    )


def epoch_index(t: np.ndarray, rec_start: pd.Timestamp, epoch_seconds: int) -> np.ndarray:
    return np.floor((t - rec_start.timestamp()) / epoch_seconds).astype(np.int64)


def epoch_coverage(n: Night) -> np.ndarray:
    """Fraction of expected motion samples present in each 30 s epoch (0..1)."""
    if not n.has_motion:
        return np.zeros(n.n_epochs)
    dt = n.meta.get("motion_median_dt_s") or 0.02
    expected = n.epoch_seconds / dt
    idx = epoch_index(n.motion_t, n.rec_start, n.epoch_seconds)
    within = (idx >= 0) & (idx < n.n_epochs)
    counts = np.bincount(idx[within], minlength=n.n_epochs).astype(float)
    return np.clip(counts / max(expected, 1.0), 0.0, 1.0)


def stage_hypnogram(n: Night, source: str = "expert") -> np.ndarray | None:
    arr = n.expert if source == "expert" else n.dreem
    return None if arr is None else arr.copy()[: n.n_epochs]
