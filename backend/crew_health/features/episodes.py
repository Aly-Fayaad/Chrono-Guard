"""Sleep-episode and circadian features from a 30 s hypnogram.

All definitions are explicit because "sleep efficiency" and "sleep onset" have
several incompatible conventions. We use the commonly reported actigraphy
definitions and document them in ``docs/FEATURES.md``:

* sleep onset  = start of the first >=10 min sleep run;
* final wake   = end of the last >=10 min sleep run;
* TIB          = recorded span (no sleep diary is available, so the recording
                 is our time-in-bed proxy - this is stated in the output);
* TST          = number of sleep epochs * epoch length;
* WASO         = wake epochs between onset and final wake;
* awakenings   = wake runs >= 1 min between onset and final wake;
* fragmentation= awakenings per hour of TST.

Clock times are expressed in the recording's local timezone (US/Eastern for
BIDSleep). For a mission deployment this should be the mission clock.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from crew_health.io.bidsleep import SLEEP_STAGES, Night

TZ = ZoneInfo("America/New_York")


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    if mask.size == 0:
        return []
    padded = np.concatenate(([False], mask, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return [(int(edges[i]), int(edges[i + 1] - 1)) for i in range(0, edges.size, 2)]


def sleep_episode(mask: np.ndarray, epoch_seconds: int = 30,
                  min_run_min: float = 10.0) -> dict:
    """Compute episode metrics from a boolean sleep mask."""
    mask = np.asarray(mask, dtype=bool)
    n = mask.size
    if n == 0:
        return {"error": "empty hypnogram"}

    min_epochs = max(1, int(round(min_run_min * 60 / epoch_seconds)))
    runs = [r for r in _runs(mask) if r[1] - r[0] + 1 >= min_epochs]
    if not runs:
        return {"error": "no sleep episode >= min_run_min"}

    onset = runs[0][0]
    final_wake = runs[-1][1]
    tst_min = mask.sum() * epoch_seconds / 60.0
    tib_min = n * epoch_seconds / 60.0
    in_bed = mask[onset : final_wake + 1]
    waso_min = (~in_bed).sum() * epoch_seconds / 60.0
    wake_runs = [r for r in _runs(~mask[onset : final_wake + 1])
                 if r[1] - r[0] + 1 >= max(1, int(60 / epoch_seconds))]
    longest = max((r[1] - r[0] + 1) for r in runs) * epoch_seconds / 60.0

    return {
        "tst_min": float(tst_min),
        "tib_min": float(tib_min),
        "sleep_efficiency": float(tst_min / tib_min) if tib_min else float("nan"),
        "sleep_onset_latency_min": float(onset * epoch_seconds / 60.0),
        "waso_min": float(waso_min),
        "awakenings": int(len(wake_runs)),
        "fragmentation_index_per_h": float(len(wake_runs) / (tst_min / 60.0))
        if tst_min > 0 else float("nan"),
        "longest_sleep_bout_min": float(longest),
        "onset_epoch": int(onset),
        "final_wake_epoch": int(final_wake),
    }


def sleep_episodes(mask: np.ndarray, epoch_seconds: int = 30,
                   min_run_min: float = 10.0, gap_min: float = 60.0) -> list[dict]:
    """Split a hypnogram into sleep episodes separated by a long wake gap.

    A new episode starts when the wake gap between two qualifying sleep runs is
    at least ``gap_min`` minutes. This is what makes **split sleep** (e.g. a
    short night plus an afternoon nap) visible instead of being merged into one
    first-onset-to-last-wake block.

    The definition is explicit and configurable; ``gap_min=60`` is a convention,
    not a validated threshold.
    """
    mask = np.asarray(mask, dtype=bool)
    if mask.size == 0:
        return []
    min_epochs = max(1, int(round(min_run_min * 60 / epoch_seconds)))
    min_gap = max(1, int(round(gap_min * 60 / epoch_seconds)))
    runs = [r for r in _runs(mask) if r[1] - r[0] + 1 >= min_epochs]
    if not runs:
        return []

    groups: list[list[tuple[int, int]]] = [[runs[0]]]
    for run in runs[1:]:
        gap = run[0] - groups[-1][-1][1] - 1
        if gap >= min_gap:
            groups.append([run])
        else:
            groups[-1].append(run)

    out = []
    for group in groups:
        onset = group[0][0]
        final_wake = group[-1][1]
        span_min = (final_wake - onset + 1) * epoch_seconds / 60.0
        # Count every sleep epoch inside the episode span, including short runs
        # that did not qualify as onset/offset runs, so episode TST is consistent
        # with the recording-level TST definition.
        tst_min = float(mask[onset:final_wake + 1].sum()) * epoch_seconds / 60.0
        out.append({
            "onset_epoch": int(onset),
            "final_wake_epoch": int(final_wake),
            "tst_min": float(tst_min),
            "span_min": float(span_min),
            "waso_min": float(span_min - tst_min),
            "sleep_efficiency": float(tst_min / span_min) if span_min else float("nan"),
            "n_sleep_runs": int(len(group)),
            "longest_run_min": float(
                max(e - s + 1 for s, e in group) * epoch_seconds / 60.0),
        })
    return out


def _clock_hour(epoch: int, rec_start: pd.Timestamp, epoch_seconds: int = 30,
                tz: ZoneInfo = TZ) -> float:
    ts = (rec_start + pd.Timedelta(seconds=epoch * epoch_seconds)).tz_convert(tz)
    return ts.hour + ts.minute / 60 + ts.second / 3600


def night_features(n: Night, sleep_mask: np.ndarray,
                   stage_labels: np.ndarray | None = None,
                   episode_gap_min: float = 60.0) -> dict:
    """One row of nightly features, including clock times and architecture.

    ``sleep_episodes`` lists each sleep episode separately (split sleep is
    preserved); the top-level ``tst_min`` remains total sleep time across the
    whole recording, so existing consumers are unaffected.
    """
    ep = sleep_episode(sleep_mask, n.epoch_seconds)
    out: dict = {
        "subject_id": n.subject,
        "night": n.night,
        "rec_start_utc": n.rec_start.isoformat(),
        "n_epochs": int(min(sleep_mask.size, n.n_epochs)),
        "warnings": list(n.meta.get("warnings", [])),
    }
    out.update(ep)

    if "onset_epoch" in ep:
        onset_ts = (n.rec_start + pd.Timedelta(seconds=ep["onset_epoch"] * n.epoch_seconds))
        wake_ts = (n.rec_start + pd.Timedelta(seconds=ep["final_wake_epoch"] * n.epoch_seconds))
        mid_ts = onset_ts + (wake_ts - onset_ts) / 2
        local = mid_ts.tz_convert(TZ)
        out["sleep_start_clock_h"] = _clock_hour(ep["onset_epoch"], n.rec_start)
        out["sleep_end_clock_h"] = _clock_hour(ep["final_wake_epoch"], n.rec_start)
        out["sleep_midpoint_clock_h"] = local.hour + local.minute / 60 + local.second / 3600
        out["analysis_date"] = local.date().isoformat()

    episodes = sleep_episodes(sleep_mask, n.epoch_seconds, gap_min=episode_gap_min)
    episode_rows = []
    for i, e in enumerate(episodes):
        start_ts = n.rec_start + pd.Timedelta(seconds=e["onset_epoch"] * n.epoch_seconds)
        end_ts = n.rec_start + pd.Timedelta(seconds=e["final_wake_epoch"] * n.epoch_seconds)
        mid_local = (start_ts + (end_ts - start_ts) / 2).tz_convert(TZ)
        episode_rows.append({
            **e,
            "episode_index": i,
            "start_utc": start_ts.isoformat(),
            "end_utc": end_ts.isoformat(),
            "start_clock_h": _clock_hour(e["onset_epoch"], n.rec_start),
            "end_clock_h": _clock_hour(e["final_wake_epoch"], n.rec_start),
            "midpoint_clock_h": mid_local.hour + mid_local.minute / 60
            + mid_local.second / 3600,
        })
    out["sleep_episodes"] = episode_rows
    out["n_sleep_episodes"] = len(episode_rows)
    out["split_sleep"] = len(episode_rows) > 1
    out["episode_gap_min"] = float(episode_gap_min)

    if stage_labels is not None:
        k = min(stage_labels.size, sleep_mask.size)
        stages = np.asarray(stage_labels[:k])
        dur = lambda s: float(np.sum(stages == s) * n.epoch_seconds / 60.0)  # noqa: E731
        tst = dur(1) + dur(2) + dur(3) + dur(4)
        out.update({
            "stage_source": "expert_eeg",
            "n1_min": dur(1), "n2_min": dur(2), "n3_min": dur(3), "rem_min": dur(4),
            "wake_min": dur(0), "unknown_min": dur(5),
            "rem_pct_tst": float(100 * dur(4) / tst) if tst else None,
            "deep_pct_tst": float(100 * dur(3) / tst) if tst else None,
        })

    return out


def circular_stats(hours: list[float] | np.ndarray, period_h: float = 24.0) -> dict:
    """Circular mean / SD / regularity for clock hours on a ``period_h`` dial.

    24 h is the default and reproduces earlier results. Pass ``period_h`` equal
    to the mission day length to analyse mission-clock times.
    """
    h = np.asarray([x for x in hours if x is not None and np.isfinite(x)], dtype=float)
    if h.size == 0:
        return {"n": 0}
    h = np.mod(h, period_h)
    ang = 2 * np.pi * h / period_h
    c, s = np.cos(ang).mean(), np.sin(ang).mean()
    r = float(np.hypot(c, s))
    mean_h = float((np.degrees(np.arctan2(s, c)) % 360) * period_h / 360.0)
    sd_h = float(np.sqrt(max(-2 * np.log(max(r, 1e-9)), 0)) * period_h / (2 * np.pi))
    return {"n": int(h.size), "mean_clock_h": mean_h, "sd_hours": sd_h,
            "regularity_r": r, "period_hours": float(period_h)}


#: Episode rows from ``night_features`` use short keys (``midpoint_clock_h``),
#: while API callers often use the record-level names. Accept both.
_EPISODE_KEY_ALIASES = {
    "sleep_midpoint_clock_h": ("sleep_midpoint_clock_h", "midpoint_clock_h"),
    "sleep_start_clock_h": ("sleep_start_clock_h", "start_clock_h"),
    "sleep_end_clock_h": ("sleep_end_clock_h", "end_clock_h"),
}


def _episode_values(records: list[dict], key: str) -> list[float]:
    """Collect per-episode values, falling back to the record-level value.

    Using per-episode values is what makes split sleep visible in the timing
    statistics: a short night and a later nap contribute two midpoints. Both
    key spellings are accepted because ``night_features`` emits ``midpoint_clock_h``
    on episode rows while record-level fields use ``sleep_midpoint_clock_h``.
    """
    aliases = _EPISODE_KEY_ALIASES.get(key, (key,))
    values = []
    for rec in records:
        episodes = rec.get("sleep_episodes") or []
        found = []
        for episode in episodes:
            for alias in aliases:          # first available spelling wins
                if episode.get(alias) is not None:
                    found.append(episode[alias])
                    break
        if found:
            values.extend(found)
        elif rec.get(key) is not None:
            values.append(rec[key])
    return values


def circadian_summary(records: list[dict], period_h: float = 24.0) -> dict:
    """Across-night timing regularity + timing shifts.

    A true Sleep Regularity Index needs 24/7 wear; these recordings cover only
    the sleep period, so SRI is deliberately not reported.

    ``period_h`` is the dial length: 24 by default, or the mission day length.
    """
    mid = _episode_values(records, "sleep_midpoint_clock_h")
    starts = _episode_values(records, "sleep_start_clock_h")
    ends = _episode_values(records, "sleep_end_clock_h")
    mid_stats = circular_stats(mid, period_h)

    # Night-to-night change in midpoint (absolute circular distance in hours)
    valid = [m for m in mid if m is not None and np.isfinite(m)]
    shifts = []
    for a, b in zip(valid, valid[1:]):
        d = abs(b - a) % period_h
        shifts.append(min(d, period_h - d))

    return {
        "n_nights": len(records),
        "n_midpoints": len(valid),
        "sleep_midpoint": mid_stats,
        "bedtime": circular_stats(starts, period_h),
        "wake_time": circular_stats(ends, period_h),
        "mean_abs_night_to_night_midpoint_shift_h": float(np.mean(shifts)) if shifts else None,
        "max_abs_night_to_night_midpoint_shift_h": float(np.max(shifts)) if shifts else None,
        "sri_reported": False,
        "sri_reason": "Sleep Regularity Index requires 24/7 wear; dataset covers sleep period only.",
    }
