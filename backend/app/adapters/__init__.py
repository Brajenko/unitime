from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DiscoveredCalendar:
    external_id: str
    display_name: str
    selected_by_default: bool = True


@dataclass(frozen=True)
class BusyOccurrence:
    uid: str
    start: datetime
    end: datetime
