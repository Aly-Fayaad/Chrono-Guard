"""Three-process model of alertness (Åkerstedt & Folkard; Ingre et al. 2014).

This replaces the earlier arbitrary-unit implementation with the equations and
parameter values used by **FIPS** (``humanfactors/FIPS``,
``R/simulation_threeprocessmodel.R``), whose defaults come from:

    Ingre M, Van Leeuwen W, Klemets T, Ullvetter C, Hough S, Kecklund G,
    Karlsson D, Åkerstedt T (2014). *Validating and Extending the Three Process
    Model of Alertness in Airline Operations.* PLoS ONE 9(10):e108679.
    https://doi.org/10.1371/journal.pone.0108679

Model equations (transcribed exactly from the FIPS source):

S during wake::

    S(taw) = la + (sw - la) * exp(d * taw)

S during sleep, with the "brake" at ``bl``::

    bt     = (bl - ss) / (g * (bl - ha))
    S(tas) = ss + tas * g * (bl - ha)                if tas <= bt
           = ha - (ha - bl) * exp(g * (tas - bt))    if tas >  bt

C, 24 h circadian::

    C(tod) = Cm + Ca * cos((2*pi / 24) * (tod - p))

U, 12 h ultradian::

    U(tod) = Um + Ua * cos((2*pi / 12) * (tod - p - 3))

W, sleep inertia::

    W(taw) = Wc * exp(Wd * taw)

KSS transfer (Eq. 1.9 of the paper, estimated on 8040 KSS ratings)::

    KSS = kss_intercept + kss_slope * (SB + C + U)
        = 9.68 - 0.46 * (SB + C + U)

Choice of defaults, and what is *not* claimed
---------------------------------------------
* The paper found the best-fitting model to be **SB + C + U**; adding sleep
  inertia (W) *decreased* goodness of fit and its default magnitude was judged
  exaggerated. We therefore exclude W from the alertness/KSS projection by
  default and report it only as a diagnostic column.
* The validated transfer function is ``a = 9.68, b = -0.46`` (model 5c). FIPS
  ships the *legacy* pair ``a = 10.6, b = -0.6``; the paper notes the TPM has
  used several transfer functions that "may give very different levels of
  sleepiness", so we use the validated pair and record the alternative.
* The KSS prediction is **group-level** (fixed effects). It is not calibrated to
  an individual, not a PVT/performance prediction, and not validated in
  microgravity or on astronaut crews.
* Residual SD (``eps = 1.42``) is the within-individual prediction error;
  ``eta = 0.839`` is the between-subject SD of the intercept. Reference limits
  of +0.57 and +1.07 contain 75 % and 90 % of individuals (Eq. 1.16).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Constants that appear inside the published g formula (Eq. 1.3 of the paper).
_G_HA_TERM = 14.0
_G_S0_TERM = 7.96


def default_g(ha: float = 14.3) -> float:
    """``g = log((ha - 14) / (ha - 7.96)) / 8`` exactly as in FIPS."""
    return float(np.log((ha - _G_HA_TERM) / (ha - _G_S0_TERM)) / 8.0)


#: Machine-readable provenance, embedded in API responses.
PARAMETER_PROVENANCE = {
    "model": "three_process_model",
    "implementation_reference": "humanfactors/FIPS R/simulation_threeprocessmodel.R",
    "parameter_source": "Ingre et al. 2014, PLoS ONE 9(10):e108679",
    "parameter_source_doi": "10.1371/journal.pone.0108679",
    "kss_transfer_source": (
        "Ingre et al. 2014, Eq. 1.9 (model 5c: SB+C+U), estimated on 8040 KSS "
        "ratings from 136 aircrew"
    ),
    "kss_transfer": "KSS = 9.68 - 0.46 * (SB + C + U)",
    "reference_limits_source": "Ingre et al. 2014, Eq. 1.16 (eta = 0.839)",
    "validated_domain": (
        "group-level subjective sleepiness (KSS, 1-9) in airline operations; "
        "not performance, not microgravity, not individual calibration"
    ),
    "sleep_inertia_excluded_because": (
        "Adding process W decreased goodness of fit in the validation and the "
        "default W magnitude was reported as exaggerated (Ingre et al. 2014)."
    ),
}


@dataclass(frozen=True)
class TPMParams:
    """Published parameter values (Ingre et al. 2014 / FIPS defaults)."""

    # --- homeostatic process S ---
    la: float = 2.4                 # low asymptote of the alertness scale
    ha: float = 14.3                # high asymptote
    d: float = -0.0353              # decay rate while awake (per hour)
    g: float = default_g()          # recovery rate while asleep (per hour)
    bl: float = 12.2                # "brake" break level
    S0: float = 7.96                # initial value of S

    # --- 24 h circadian process C ---
    Cm: float = 0.0                 # mesor
    Ca: float = 2.5                 # amplitude
    p: float = 16.8                 # clock hour of the peak

    # --- 12 h ultradian process U ---
    Um: float = -0.5                # mesor
    Ua: float = 0.5                 # amplitude

    # --- sleep inertia W (diagnostic only; excluded from KSS by default) ---
    Wc: float = -5.72
    Wd: float = -1.51
    include_inertia_in_alertness: bool = False

    # --- KSS transfer (validated model 5c) ---
    kss_intercept: float = 9.68
    kss_slope: float = -0.46
    kss_residual_sd: float = 1.42
    kss_between_subject_sd: float = 0.839
    kss_limit_75: float = 0.57
    kss_limit_90: float = 1.07


def breaktime(ss: float, params: TPMParams = TPMParams()) -> float:
    """Hours of sleep after which the low-pressure phase begins."""
    denom = params.g * (params.bl - params.ha)
    if denom == 0:
        return float("inf")
    return float((params.bl - ss) / denom)


def s_wake(taw, sw: float, params: TPMParams = TPMParams()):
    """Homeostatic S while awake (Eq. 1.1)."""
    return params.la + (sw - params.la) * np.exp(params.d * np.asarray(taw, dtype=float))


def s_sleep(tas, ss: float, params: TPMParams = TPMParams()):
    """Homeostatic S while asleep, with the brake function (Eq. 1.3-1.5)."""
    tas = np.asarray(tas, dtype=float)
    bt = breaktime(ss, params)
    slope = params.g * (params.bl - params.ha)          # positive: S rises
    early = ss + tas * slope
    # exp argument is clipped only to avoid overflow in the unused branch.
    arg = np.clip(params.g * (tas - bt), -700.0, 700.0)
    late = params.ha - (params.ha - params.bl) * np.exp(arg)
    return np.where(tas <= bt, early, late)


def circadian(phase, params: TPMParams = TPMParams(), period_h: float = 24.0):
    """Circadian process C (Eq. 1.7).

    ``period_h`` is 24 by default, which reproduces the published equation
    exactly. Any other value is an unvalidated extrapolation (see
    :mod:`crew_health.mission`).
    """
    return params.Cm + params.Ca * np.cos(
        (2 * np.pi / float(period_h)) * (np.asarray(phase, float) - params.p)
    )


def ultradian(phase, params: TPMParams = TPMParams(), period_h: float = 12.0):
    """Ultradian process U (Eq. 1.8); 12 h by default."""
    return params.Um + params.Ua * np.cos(
        (2 * np.pi / float(period_h)) * (np.asarray(phase, float) - params.p - 3.0)
    )


def inertia(taw, params: TPMParams = TPMParams()):
    """Sleep inertia W (Eq. 1.6). Diagnostic only by default."""
    return params.Wc * np.exp(params.Wd * np.asarray(taw, dtype=float))


def kss_from_alertness(alertness, params: TPMParams = TPMParams()):
    """Validated linear transfer to the Karolinska Sleepiness Scale (Eq. 1.9)."""
    return params.kss_intercept + params.kss_slope * np.asarray(alertness, dtype=float)


def kss_reference_limits(kss: float, params: TPMParams = TPMParams()) -> dict:
    """Population reference limits from Eq. 1.16.

    These describe *between-individual* variation around the group prediction,
    not a confidence interval for the individual and not a measurement error
    band. Higher KSS = sleepier, so the limits are one-sided upwards.
    """
    return {
        "p50": float(kss),
        "p75_upper": float(kss + params.kss_limit_75),
        "p90_upper": float(kss + params.kss_limit_90),
    }


def simulate(start, sleep_mask: np.ndarray, dt_min: float = 5.0,
             params: TPMParams | None = None, s0: float | None = None,
             mission: "MissionParams | None" = None) -> pd.DataFrame:
    """Simulate S, C, U, W, alertness and predicted KSS over a sleep/wake timeline.

    Parameters
    ----------
    start
        Timezone-aware start timestamp.
    sleep_mask
        Boolean sleep state for each ``dt_min`` step. Multiple sleep episodes
        are represented directly as multiple ``True`` runs.
    dt_min
        Step size in minutes.
    params
        Published parameter set; defaults to :class:`TPMParams`.
    s0
        Optional override for the initial homeostatic value (default ``S0``).
    mission
        Optional :class:`crew_health.mission.MissionParams`. When supplied, the
        frame gains ``met_h``, ``mission_local_time_h`` and
        ``mission_day_index`` columns. The published C/U equations are unchanged
        unless the mission explicitly overrides the circadian period or time
        source.
    """
    params = params or TPMParams()
    start = pd.Timestamp(start)
    if start.tzinfo is None:
        raise ValueError("start must be timezone-aware")

    sleep = np.asarray(sleep_mask, dtype=bool)
    if sleep.size == 0:
        raise ValueError("sleep_mask must not be empty")

    times = pd.date_range(start, periods=sleep.size, freq=f"{dt_min}min")
    n = sleep.size

    s_anchor_wake = params.S0 if s0 is None else float(s0)
    s_anchor_sleep = params.S0 if s0 is None else float(s0)
    t_wake_anchor = times[0]
    t_sleep_anchor = times[0]

    s = np.empty(n)
    w = np.empty(n)
    for i in range(n):
        if i > 0 and sleep[i] != sleep[i - 1]:
            # Carry the current S across the transition, exactly like FIPS.
            if sleep[i]:
                s_anchor_sleep = s[i - 1]
                t_sleep_anchor = times[i]
            else:
                s_anchor_wake = s[i - 1]
                t_wake_anchor = times[i]

        if sleep[i]:
            tas = (times[i] - t_sleep_anchor).total_seconds() / 3600.0
            s[i] = float(s_sleep(tas, s_anchor_sleep, params))
            w[i] = 0.0
        else:
            taw = (times[i] - t_wake_anchor).total_seconds() / 3600.0
            s[i] = float(s_wake(taw, s_anchor_wake, params))
            w[i] = float(inertia(taw, params))

    tod = np.array([t.hour + t.minute / 60.0 + t.second / 3600.0 for t in times])
    if mission is None:
        c = circadian(tod, params)
        u = ultradian(tod, params)
        mission_cols = {}
    else:
        from crew_health.mission import (
            circadian_phase_hours,
            mission_day_index,
            mission_elapsed_hours,
            mission_local_time_hours,
        )

        phase = circadian_phase_hours(times, mission)
        c = circadian(phase, params, period_h=mission.circadian_period_h)
        u = ultradian(phase, params, period_h=mission.ultradian_period_h)
        mission_cols = {
            "met_h": mission_elapsed_hours(times, mission),
            "mission_local_time_h": mission_local_time_hours(times, mission),
            "mission_day_index": mission_day_index(times, mission),
            "circadian_phase_h": phase,
        }

    # The validated model is SB + C + U; W is available but excluded by default.
    alertness_core = s + c + u
    alertness_with_inertia = alertness_core + w
    alertness = (alertness_with_inertia if params.include_inertia_in_alertness
                 else alertness_core)

    df = pd.DataFrame({
        "sleep": sleep,
        "s": s,
        "c": c,
        "u": u,
        "w": w,
        "alertness_raw": alertness,
        "alertness_with_inertia": alertness_with_inertia,
        "kss": kss_from_alertness(alertness, params),
        "kss_p75_upper": kss_from_alertness(alertness, params) + params.kss_limit_75,
        "kss_p90_upper": kss_from_alertness(alertness, params) + params.kss_limit_90,
        "clock_hour": tod,
        **mission_cols,
    }, index=times)
    df.index.name = "timestamp"
    return df


def alertness_percentile(df: pd.DataFrame, timestamp) -> float:
    """Percentile of the alertness at ``timestamp`` within this simulation."""
    ts = pd.Timestamp(timestamp)
    idx = df.index.get_indexer([ts], method="nearest")[0]
    value = df["alertness_raw"].iloc[idx]
    return float((df["alertness_raw"] <= value).mean() * 100.0)


def kss_percentile(df: pd.DataFrame, timestamp) -> float:
    """Percentile of predicted KSS at ``timestamp`` within this simulation.

    Higher percentile means sleeper than usual *for this simulated window*.
    """
    ts = pd.Timestamp(timestamp)
    idx = df.index.get_indexer([ts], method="nearest")[0]
    value = df["kss"].iloc[idx]
    return float((df["kss"] <= value).mean() * 100.0)


def sleep_debt_hours(records: list[dict], target_sleep_h: float = 8.0,
                     half_life_days: float = 1.0) -> float:
    """Exponentially weighted cumulative sleep deficit (hours).

    This is a descriptive accounting construct, not part of the published
    three-process model, and it carries no clinical threshold.
    """
    debt = 0.0
    decay = 0.5 ** (1.0 / half_life_days)
    for rec in records:
        got = rec.get("sleep_duration_hours")
        if got is None and rec.get("tst_min") is not None:
            got = rec["tst_min"] / 60.0
        if got is None:
            continue
        debt = debt * decay + (target_sleep_h - float(got))
    return float(max(debt, 0.0))


def summarize(df: pd.DataFrame, params: TPMParams | None = None) -> dict:
    params = params or TPMParams()
    a = df["alertness_raw"].to_numpy()
    k = df["kss"].to_numpy()
    return {
        "alertness_min": float(np.min(a)),
        "alertness_max": float(np.max(a)),
        "alertness_median": float(np.median(a)),
        "alertness_p10": float(np.percentile(a, 10)),
        "alertness_p90": float(np.percentile(a, 90)),
        "alertness_with_inertia_min": float(df["alertness_with_inertia"].min()),
        "kss_median": float(np.median(k)),
        "kss_min": float(np.min(k)),
        "kss_max": float(np.max(k)),
        "kss_p90_sleepiness": float(np.percentile(k, 90)),
        "homeostatic_pressure_final": float(df["s"].iloc[-1]),
        # Retained for backwards compatibility; now the published KSS scale.
        "calibrated": False,
        "kss_scale": "Karolinska Sleepiness Scale (1-9), group-level prediction",
        "units": (
            "alertness_raw = SB + C + U on the published 2.4-14.3 internal scale; "
            "kss = 9.68 - 0.46 * alertness_raw"
        ),
        "uncertainty": {
            "residual_sd_kss": params.kss_residual_sd,
            "between_subject_sd_kss": params.kss_between_subject_sd,
            "reference_limits": "75%: +0.57 KSS, 90%: +1.07 KSS (upper)",
            "source": "Ingre et al. 2014, Eq. 1.16",
        },
        "provenance": PARAMETER_PROVENANCE,
    }
