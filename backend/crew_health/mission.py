"""Mission time: configurable day length, mission elapsed time, mission local time.

The published three-process model (Ingre et al. 2014) is parameterised on a
24-hour day. **This module does not change that.** It adds an *operational*
mission clock on top of the model:

* **mission day length** (default **24.65 h**, the value specified for this
  project) — determines mission local time ``MLT`` and the mission day index;
* **mission elapsed time** ``MET``, defined relative to an explicit epoch;
* **sleep episodes** may occur several times per mission day (see
  :mod:`crew_health.features.episodes`).

A note on 24.65 h
-----------------
24.65 h is the **Martian sol** (24 h 39 min 35 s), not the lunar day. The Moon's
synodic day is about **29.53 Earth days**, so a true lunar solar day would make
"day length" almost meaningless for a sleep schedule. The 24.65 h default is
therefore an *operational near-Earth day convention* chosen for this project,
not a property of the Moon. It is configurable precisely because the right value
is a mission-design decision.

What is validated and what is not
---------------------------------
* The circadian ``C`` and ultradian ``U`` equations remain exactly as published
  (24 h and 12 h). By default ``circadian_time_source="earth_clock"``, so the
  alertness curve is **identical** to the Earth-day implementation regardless of
  the mission day length.
* Setting ``circadian_time_source="mission_local"`` re-expresses circadian phase
  on the mission clock and is an **unvalidated extrapolation**.
* Setting ``circadian_period_h`` away from 24 h assumes entrainment to a
  non-24-hour day. That is also **unvalidated**; the human entrainment range is
  generally reported to be narrower than 24.65 h, so a free-running or
  partially-entrained crew is at least as plausible.
* Nothing here is a claim about actual lunar operations or astronaut physiology.

Definitions
-----------
With an epoch ``t0`` at which ``MET = met_hours_at_epoch``::

    MET(t)    = met_hours_at_epoch + (t - t0) / 1 h
    MLT(t)    = MET(t) mod mission_day_h
    day_index = floor(MET(t) / mission_day_h)

``MET`` may be negative (before the epoch), which is represented as a negative
day index with a positive ``MLT``; this is deliberate so that history before
``as_of`` does not wrap into day 0.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

CIRCADIAN_TIME_SOURCES = ("earth_clock", "mission_local")


@dataclass(frozen=True)
class MissionParams:
    """Operational mission clock configuration.

    ``mission_day_h`` is an operational convention, not a measured physiological
    period. 24.65 h is the Martian sol; the lunar synodic day is ~29.53 Earth
    days. The default follows this project's specification and is configurable
    because the operational day length is a mission-design decision.
    """

    mission_day_h: float = 24.65
    met_hours_at_epoch: float = 0.0
    epoch: pd.Timestamp | None = None
    circadian_period_h: float = 24.0
    ultradian_period_h: float = 12.0
    circadian_time_source: str = "earth_clock"

    def __post_init__(self) -> None:
        if not np.isfinite(self.mission_day_h) or self.mission_day_h <= 0:
            raise ValueError("mission_day_h must be a positive finite number")
        if not np.isfinite(self.circadian_period_h) or self.circadian_period_h <= 0:
            raise ValueError("circadian_period_h must be a positive finite number")
        if not np.isfinite(self.ultradian_period_h) or self.ultradian_period_h <= 0:
            raise ValueError("ultradian_period_h must be a positive finite number")
        if self.circadian_time_source not in CIRCADIAN_TIME_SOURCES:
            raise ValueError(
                f"circadian_time_source must be one of {CIRCADIAN_TIME_SOURCES}, "
                f"got {self.circadian_time_source!r}"
            )
        if self.epoch is not None:
            epoch = pd.Timestamp(self.epoch)
            if epoch.tzinfo is None:
                raise ValueError("MissionParams.epoch must be timezone-aware")

    @property
    def uses_published_circadian_period(self) -> bool:
        return (
            self.circadian_period_h == 24.0
            and self.ultradian_period_h == 12.0
            and self.circadian_time_source == "earth_clock"
        )

    def to_dict(self) -> dict:
        return {
            "mission_day_hours": float(self.mission_day_h),
            "met_hours_at_epoch": float(self.met_hours_at_epoch),
            "epoch": self.epoch.isoformat() if self.epoch is not None else None,
            "circadian_period_hours": float(self.circadian_period_h),
            "ultradian_period_hours": float(self.ultradian_period_h),
            "circadian_time_source": self.circadian_time_source,
            "circadian_equations_status": (
                "published 24 h / 12 h equations unchanged"
                if self.uses_published_circadian_period
                else "non-default circadian configuration; unvalidated extrapolation"
            ),
            "validated": False,
        }


def _timestamps(values, tz: str = "UTC") -> pd.DatetimeIndex:
    if isinstance(values, (pd.Timestamp, np.datetime64, str)) or np.isscalar(values):
        values = [values]
    idx = pd.DatetimeIndex(pd.to_datetime(values))
    if idx.tz is None:
        idx = idx.tz_localize(tz)
    return idx


def mission_elapsed_hours(timestamps, params: MissionParams) -> np.ndarray:
    """``MET`` in hours for each timestamp."""
    idx = _timestamps(timestamps)
    epoch = pd.Timestamp(params.epoch) if params.epoch is not None else idx[0]
    if epoch.tzinfo is None:
        epoch = epoch.tz_localize("UTC")
    elapsed = np.array([(t - epoch).total_seconds() / 3600.0 for t in idx])
    return params.met_hours_at_epoch + elapsed


def mission_local_time_hours(timestamps, params: MissionParams) -> np.ndarray:
    """``MLT`` in ``[0, mission_day_h)`` for each timestamp."""
    met = mission_elapsed_hours(timestamps, params)
    return np.mod(met, params.mission_day_h)


def mission_day_index(timestamps, params: MissionParams) -> np.ndarray:
    """Signed mission day index (``floor(MET / mission_day_h)``)."""
    met = mission_elapsed_hours(timestamps, params)
    return np.floor(met / params.mission_day_h).astype(int)


def earth_clock_hours(timestamps) -> np.ndarray:
    """Absolute UTC clock hour in ``[0, 24)`` (the published model's phase)."""
    idx = _timestamps(timestamps)
    return np.array([t.hour + t.minute / 60.0 + t.second / 3600.0 for t in idx])


def circadian_phase_hours(timestamps, params: MissionParams) -> np.ndarray:
    """Phase fed to processes C and U.

    ``earth_clock`` (default) reproduces the published implementation exactly.
    ``mission_local`` uses MLT instead, which is an unvalidated extrapolation.
    """
    if params.circadian_time_source == "mission_local":
        return mission_local_time_hours(timestamps, params)
    return earth_clock_hours(timestamps)


def mission_summary(timestamps, params: MissionParams) -> dict:
    """Mission clock summary at one or more timestamps."""
    idx = _timestamps(timestamps)
    met = mission_elapsed_hours(idx, params)
    mlt = mission_local_time_hours(idx, params)
    day = mission_day_index(idx, params)
    return {
        "mission_day_hours": float(params.mission_day_h),
        "met_hours": met.tolist() if met.size > 1 else float(met[0]),
        "mission_local_time_hours": mlt.tolist() if mlt.size > 1 else float(mlt[0]),
        "mission_day_index": day.tolist() if day.size > 1 else int(day[0]),
        "circadian_period_hours": float(params.circadian_period_h),
        "ultradian_period_hours": float(params.ultradian_period_h),
        "circadian_time_source": params.circadian_time_source,
        "validated": False,
    }


def mission_params_from_dict(cfg: dict | None, default_epoch) -> MissionParams:
    """Build :class:`MissionParams` from an API/JSON mapping.

    ``default_epoch`` is used when the mapping does not supply one; mission
    elapsed time is then measured relative to that timestamp.
    """
    cfg = cfg or {}
    epoch_raw = cfg.get("epoch")
    epoch = pd.Timestamp(epoch_raw if epoch_raw is not None else default_epoch)
    if epoch.tzinfo is None:
        epoch = epoch.tz_localize("UTC")
    return MissionParams(
        mission_day_h=float(cfg.get("mission_day_hours", 24.65)),
        met_hours_at_epoch=float(cfg.get("met_hours", 0.0)),
        epoch=epoch,
        circadian_period_h=float(cfg.get("circadian_period_hours", 24.0)),
        ultradian_period_h=float(cfg.get("ultradian_period_hours", 12.0)),
        circadian_time_source=cfg.get("circadian_time_source", "earth_clock"),
    )
