"""Pure annual Vortex windows. Source metadata is cached; clock selections are not."""
import calendar
import copy
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
import json
from pathlib import Path
from zoneinfo import ZoneInfo

EVENT_TIMEZONE = ZoneInfo('America/New_York')


@dataclass(frozen=True, order=True)
class EventWindow:
    starts_at: datetime
    ends_at: datetime  # Exclusive: midnight following the recorded last day.

    def wire(self):
        return (self.starts_at.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                (self.ends_at.astimezone(timezone.utc) - timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S'))

    def describe(self):
        return {'starts_at': self.starts_at.isoformat(), 'ends_at': self.ends_at.isoformat()}

    @classmethod
    def from_description(cls, value):
        return cls(**{key: datetime.fromisoformat(text) for key, text in value.items()})


def clock():
    return datetime.now(timezone.utc)


def _period(first, last):
    first, last = date.fromisoformat(first), date.fromisoformat(last)
    if last < first:
        raise ValueError('Reversed annual event window')
    return first, last


@lru_cache(maxsize=1)
def metadata():
    from revival_update import document
    runs = document('event_runs.json')
    history = json.loads(Path(__file__).with_name('event_history.json').read_text(encoding='utf-8'))
    if history.get('version') != 1:
        raise ValueError('Invalid annual event history version')
    periods = {area: tuple(_period(row['start'], row['end']) for row in values)
               for area, values in runs['runs'].items()}
    # Ranked periods are authoritative even when the archive calls the area permanent.
    ranked = {area: tuple(_period(first, last) for first, last in values)
              for area, values in history['windows'].items()}
    return periods, ranked


def periods(row):
    if row.get('windows'):
        return tuple(_period(first, last) for first, last in row['windows'])
    recorded, ranked = metadata()
    area = str(row['area'])
    if area in ranked:
        return ranked[area]
    if row.get('group') == 'permanent' or row.get('availability') == 'permanent':
        return ()
    if area in recorded:
        return recorded[area]
    # Retain the existing 14-day fallback for release-only catalogue entries.
    return tuple((first, first + timedelta(days=13)) for first in
                 (date.fromisoformat(raw) for raw in row.get('runs') or [row.get('release')] if raw))


def _anniversary(day, year):
    return date(year, day.month, 28 if day.month == 2 and day.day == 29 and
                not calendar.isleap(year) else day.day)


def _selection_interval(start, end):
    if start.utcoffset() is None or end.utcoffset() is None or end <= start:
        raise ValueError('Event selection requires an increasing timezone-aware interval')
    return start.astimezone(EVENT_TIMEZONE), end.astimezone(EVENT_TIMEZONE)


def _occurrences(values, start, end):
    found = []
    for first, last in values:
        wraps = (last.month, last.day) < (first.month, first.day)
        for year in range(max(1, start.year - 1), min(9998, end.year) + 1):
            begin = datetime.combine(_anniversary(first, year), time.min, EVENT_TIMEZONE)
            finish = datetime.combine(_anniversary(last, year + wraps) + timedelta(days=1), time.min, EVENT_TIMEZONE)
            if begin < end and finish > start:
                found.append(EventWindow(begin, finish))
    merged = []
    for window in sorted(set(found)):
        if merged and window.starts_at <= merged[-1].ends_at:
            previous = merged.pop()
            window = EventWindow(previous.starts_at, max(previous.ends_at, window.ends_at))
        merged.append(window)
    return tuple(merged)


def occurrences(row, start, end):
    """Return merged occurrences overlapping [start, end); () also marks undated rows.

    Call periods(row) to distinguish an undated/permanent row from a closed dated row.
    """
    start, end = _selection_interval(start, end)
    return _occurrences(periods(row), start, end)


def select(rows, now=None, *, until=None):
    """Rows open in [now, until); every returned row is an independent copy."""
    now = clock() if now is None else now
    end = until if until is not None else now + timedelta(microseconds=1)
    interval = _selection_interval(now, end)
    chosen = []
    for row in rows:
        values = periods(row)
        windows = _occurrences(values, *interval)
        if windows:
            chosen.append(dict(copy.deepcopy(row), event_windows=[w.describe() for w in windows]))
        elif not values:
            chosen.append(copy.deepcopy(row))
    return tuple(chosen)


def window(row):
    """The active occurrence, or the first occurrence in an interval preview."""
    values = row.get('event_windows')
    return EventWindow.from_description(values[0]) if values else None


@dataclass(frozen=True)
class Availability:
    """Annual availability of every catalogue area at one moment (a read model).

    Built once per request and passed to projections and guards, so a request is
    judged against a single instant and the catalogue is selected only once.
    """
    moment: datetime
    dated: frozenset
    active: dict  # area -> selected row carrying event_windows

    @classmethod
    def at(cls, catalogue, moment):
        interval = _selection_interval(moment, moment + timedelta(microseconds=1))
        dated, active = set(), {}
        for row in catalogue:
            values = periods(row)
            if not values:
                continue
            area = str(row['area'])
            dated.add(area)
            windows = _occurrences(values, *interval)
            if windows:
                active[area] = dict(copy.deepcopy(row), event_windows=[w.describe() for w in windows])
        return cls(moment, frozenset(dated), active)

    def is_open(self, area):
        area = str(area)
        return area not in self.dated or area in self.active

    def window(self, area):
        return window(self.active.get(str(area), {}))
