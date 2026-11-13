"""Server-owned mission clock: epoch, elapsed time, mission day and local time.

The formulas intentionally mirror ``crew_health.mission`` so the API, the
analysis payload, and the UI labels can never drift apart:

``MET(t) = t - epoch``
``mission_day_index = floor(MET / mission_day_hours)``
``mission_local_time_hours = MET mod mission_day_hours``
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.database import to_utc, utcnow


@dataclass(frozen=True)
class MissionClock:
    """Mission-clock values at one instant."""

    as_of: datetime
    epoch: datetime
    day_hours: float
    met_hours: float
    mission_day_index: int
    local_time_hours: float
    local_time: str
    met_label: str

    def to_dict(self) -> dict[str, object]:
        """Return the JSON-friendly payload used by the analysis engine."""
        return {
            "epoch": self.epoch.isoformat(),
            "mission_day_hours": self.day_hours,
            "met_hours": self.met_hours,
            "mission_day_index": self.mission_day_index,
            "mission_local_time_hours": self.local_time_hours,
            "local_time": self.local_time,
            "met_label": self.met_label,
            "as_of": self.as_of.isoformat(),
        }


def parse_epoch(raw: str) -> datetime:
    """Parse an ISO-8601 epoch string and normalise it to UTC."""
    text = raw.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def compute_mission_clock(
    as_of: datetime | None = None,
    *,
    epoch: str | None = None,
    day_hours: float | None = None,
) -> MissionClock:
    """Compute the mission clock at ``as_of`` (defaults to the server time)."""
    settings = get_settings()
    moment = to_utc(as_of) if as_of is not None else utcnow()
    epoch_dt = parse_epoch(epoch if epoch is not None else settings.MISSION_EPOCH)
    hours = float(day_hours if day_hours is not None else settings.MISSION_DAY_HOURS)
    if not math.isfinite(hours) or hours <= 0:
        raise ValueError("MISSION_DAY_HOURS must be a positive finite number")

    met = (moment - epoch_dt).total_seconds() / 3600.0
    met = max(met, 0.0)
    day_index = int(math.floor(met / hours))
    local = met - day_index * hours
    local_h = int(local)
    local_m = int(round((local - local_h) * 60)) % 60
    return MissionClock(
        as_of=moment,
        epoch=epoch_dt,
        day_hours=hours,
        met_hours=round(met, 6),
        mission_day_index=day_index,
        local_time_hours=round(local, 6),
        local_time=f"{local_h:02d}:{local_m:02d}",
        met_label=f"D+{day_index:03d} {local_h:02d}:{local_m:02d}",
    )
