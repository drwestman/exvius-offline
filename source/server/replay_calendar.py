"""Pure historical calendar, ported from the pinned revival's replay/rotation modules.

An anchor is a recorded campaign fact. Previews use a provisional anchor and
never create one. Wall-clock weeks continue while the host is stopped.
"""
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from engine_profile import IOS_REVIVAL, ReplaySettings

_EPOCH = date(2026, 1, 4)  # Same Sunday/week-zero convention as the pinned fork.


@dataclass(frozen=True)
class RotationWeek:
    number: int
    starts: datetime
    ends: datetime


def rotation_week(now: datetime, settings: ReplaySettings = IOS_REVIVAL.replay) -> RotationWeek:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('Replay time must include a timezone.')
    local = now.astimezone(ZoneInfo(settings.timezone))
    start = (local - timedelta(days=(local.weekday() - settings.weekday) % 7)).replace(
        hour=settings.hour, minute=0, second=0, microsecond=0)
    if start > local:
        start -= timedelta(weeks=1)
    epoch = _EPOCH + timedelta(days=(settings.weekday - _EPOCH.weekday()) % 7)
    return RotationWeek((start.date() - epoch).days // 7, start, start + timedelta(weeks=1))


def historical_start(index: int, settings: ReplaySettings) -> date:
    """Preserve the fork's rule: choose the pace at each historical week's start."""
    remaining = max(0, index)
    day = settings.start
    if day < settings.nv_era:
        step = 7 * settings.initial_pace
        initial_weeks = min(remaining, ((settings.nv_era - day).days + step - 1) // step)
        day += timedelta(days=initial_weeks * step)
        remaining -= initial_weeks
    return day + timedelta(weeks=remaining * settings.nv_pace)


def new_anchor(now: datetime, settings: ReplaySettings) -> dict:
    config = asdict(settings)
    config['start'] = settings.start.isoformat()
    config['nv_era'] = settings.nv_era.isoformat()
    return {'anchor_week': rotation_week(now, settings).number, 'settings': config}


def read_anchor(data: dict) -> tuple[int, ReplaySettings] | None:
    """Read without setdefault, migration or repair; malformed recorded facts fail loudly."""
    if 'ios_revival' not in data:
        return None
    try:
        campaign = data['ios_revival']
        if type(campaign['version']) is not int or campaign['version'] != 1:
            raise ValueError('unsupported campaign version')
        anchor = campaign['replay']['anchor_week']
        raw = campaign['replay']['settings']
        if type(anchor) is not int:
            raise ValueError('anchor_week must be an integer')
        if not (date.min - _EPOCH).days // 7 <= anchor <= (date.max - _EPOCH).days // 7:
            raise ValueError('anchor_week is outside the supported calendar')
        if set(raw) != set(ReplaySettings.__dataclass_fields__):
            raise ValueError('the recorded replay settings are incomplete or unsupported')
        settings = ReplaySettings(**{**raw, 'start': date.fromisoformat(raw['start']),
                                    'nv_era': date.fromisoformat(raw['nv_era'])})
        for value, upper in ((settings.weekday, 6), (settings.hour, 23)):
            if type(value) is not int or not 0 <= value <= upper:
                raise ValueError('invalid rollover')
        for pace in (settings.initial_pace, settings.nv_pace):
            if type(pace) is not int or not 1 <= pace <= 52:
                raise ValueError('invalid replay pace')
        ZoneInfo(settings.timezone)
        return anchor, settings
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid iOS replay anchor: {exc}') from exc


def preview(data: dict, now: datetime, weeks: int = 1) -> dict:
    if not 1 <= weeks <= 52:
        raise ValueError('Preview weeks must be between 1 and 52.')
    saved = read_anchor(data)
    anchor, settings = saved or (rotation_week(now).number, IOS_REVIVAL.replay)
    week = rotation_week(now, settings)
    windows = []
    for offset in range(weeks):
        start = week.starts + timedelta(weeks=offset)
        index = max(0, week.number - anchor + offset)
        windows.append({'index': index, 'starts': start.isoformat(),
                        'ends': (start + timedelta(weeks=1)).isoformat(),
                        'from': historical_start(index, settings).isoformat(),
                        'to': historical_start(index + 1, settings).isoformat()})
    return {'anchored': saved is not None, 'anchor_week': anchor,
            'timezone': settings.timezone, 'windows': windows}
