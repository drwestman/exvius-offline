"""Pure iOS Vortex projections over annual event dates and saved dungeon rotations.

Undated dungeon rotations follow event_archive.py at revival commit
47a13c084f42cf1b83b53173d0c21065c78fc2de. Historical runs/windows are pinned
metadata; queries neither fetch art nor create replay/rotation state files.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import copy
import json
from pathlib import Path
import random

import revival_summons

HERE = Path(__file__).resolve().parent
HOLIDAY_EVENTS = {
    'Christmas': {'906', '952', '992', '993', '1039', '1040', '1088', '1098', '9920', '9921'},
    'Easter': {'911', '9909', '962', '1056', '1057'},
    'Halloween': {'919', '921', '983', '986', '1033', '1034', '1081', '1082', '9910', '9911'},
    "Valentine's Day": {'1004', '1005'},
}
HOLIDAY_PERMANENT = {'902': 'Halloween', '903': 'Halloween', '904': 'Halloween', '905': 'Christmas'}


@lru_cache(maxsize=1)
def history():
    try:
        doc = json.loads((HERE / 'event_history.json').read_text(encoding='utf-8'))
        if type(doc['version']) is not int or doc['version'] != 1 or not isinstance(doc['added'], list):
            raise ValueError('unsupported event history')
        for runs in doc['runs'].values():
            for run in runs:
                date.fromisoformat(run)
        for windows in doc['windows'].values():
            for first, last in windows:
                if date.fromisoformat(first) > date.fromisoformat(last):
                    raise ValueError('reversed event window')
        return doc
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ValueError(f'Invalid pinned event history: {exc}') from exc


@lru_cache(maxsize=1)
def catalogue():
    doc = json.loads((HERE / 'event_archive.json').read_text(encoding='utf-8'))
    extra = history()
    rows = []
    from revival_content import added_events
    additions = added_events(extra['added'])
    added_areas = {str(row['area']) for row in additions}
    for original in [row for row in doc['events'] if str(row['area']) not in added_areas] + additions:
        row = copy.deepcopy(original)
        area = str(row['area'])
        row['runs'] = sorted(set(extra['runs'].get(area, []) + ([row['release']] if row.get('release') else [])))
        if area in extra['windows']:
            row['windows'] = copy.deepcopy(extra['windows'][area])
        rows.append(row)
    return tuple(rows)


@lru_cache(maxsize=1)
def _art():
    return json.loads((HERE / 'event_art.json').read_text(encoding='utf-8'))['events']


def _art_key(row, art):
    info = art.get(str(row['area']), {})
    return info.get('runtime_sha256') or info.get('filename') or row.get('art_url') or str(row['area'])


def _one_per_look(rows, pick, art):
    groups = {}
    for row in rows:
        groups.setdefault((row['name'], _art_key(row, art)), []).append(row)
    keep = {str(pick(group)['area']) for group in groups.values()}
    return [row for row in rows if str(row['area']) in keep]


def _without_clones(rows):
    """Apply pinned mission identities to every iOS campaign without migrating it."""
    from revival_update import document
    clones = document('clone_quests.json')['areas']
    out = []
    for row in rows:
        hidden = clones.get(str(row['area']), {}).get('hidden', {})
        removed = [mid for mid in row['missions'] if str(mid) in hidden]
        if not removed:
            out.append(row)
            continue
        kept = [mid for mid in row['missions'] if str(mid) not in hidden]
        if not kept:
            continue
        held_back = list(row.get('held_back') or [])
        held_back.extend(mid for mid in removed if mid not in held_back)
        out.append(dict(row, missions=kept, first_mission=kept[0], held_back=held_back))
    return out


def _holiday_runs(row):
    out = {}
    for name, areas in HOLIDAY_EVENTS.items():
        if str(row['area']) not in areas:
            continue
        when = revival_summons.HOLIDAYS[name][0]
        for text in row.get('runs') or [row.get('release')]:
            if not text:
                continue
            run = date.fromisoformat(text)
            if -30 <= (run - when(run.year)).days <= 14:
                out[run] = name
    return out


@dataclass(frozen=True)
class EventPlan:
    events: tuple
    known_areas: frozenset
    context: dict

    @property
    def areas(self):
        return frozenset(str(row['area']) for row in self.events)

    def can_enter(self, data, mission, *, resume=False):
        if not mission or str(mission.get('uv60hgDW')) not in self.known_areas:
            return True  # Story and unrelated modes keep their existing entry contract.
        if not self.context['summons'].anchored:
            return False
        mid = str(mission.get('qo3PECw6'))
        if resume:
            attempt = data.get('exvius_repeat', {}).get('attempt', {})
            if attempt.get('mid') == mid and attempt.get('status') == 'pending':
                return True
        return any(mid in row['missions'] for row in self.events)

    def gate_windows(self, spec):
        from exvius_events import DATE_START, DATE_END
        from event_calendar import window
        week = self.context['week']
        from event_calendar import EventWindow
        fallback = EventWindow(week.starts, week.ends).wire()
        bounds = {str(row['area']): window(row) for row in self.events}
        out = copy.deepcopy(spec)
        for row in out.get('0xkoNP8U', []):
            area = str(row.get('uv60hgDW'))
            if area in bounds:
                first, last = bounds[area].wire() if bounds[area] else fallback
                row.update({key: first for key in DATE_START})
                row.update({key: last for key in DATE_END})
        return out

    def describe(self):
        return [{'area': str(row['area']), 'name': row['name'], 'group': row['group'],
                 'release': row.get('release'), 'first_release': row.get('first_release'),
                 'missions': len(row['missions']), 'event_windows': copy.deepcopy(row.get('event_windows', []))} for row in self.events]


def plan(data, now=None, *, rows=None, summons=None, art=None, until=None):
    now = now if now is not None else revival_summons.clock()
    supplied = rows is not None
    rows = catalogue() if rows is None else rows
    art = _art() if art is None else art
    holiday_runs = {str(row['area']): _holiday_runs(row) for row in rows}
    event_keys = {}
    for runs in holiday_runs.values():
        for run, name in runs.items():
            event_keys.setdefault(name, []).append(run.isoformat())
    context = revival_summons.event_context(data, now, event_keys, selected=summons)
    current, week = context['summons'], context['week']
    from event_calendar import select
    holiday = context['holiday']
    number = week.number
    from revival_update import settings as update_settings
    update = update_settings(data)
    kept, extra, permanent = [], [], []
    for row in select(rows, now, until=until):
        if row.get('event_windows'):
            kept.append(row)
        elif row.get('group') == 'permanent':
            permanent.append(row)
        else:
            extra.append(row)
    if extra:
        names = sorted({row['name'] for row in extra})
        cycle, start = divmod(number * 2, len(names))
        order = list(range(len(names)))
        random.Random(f'vortex-extra:{cycle}').shuffle(order)
        picked = {names[order[(start + i) % len(names)]] for i in range(min(2, len(names)))}
        for name in sorted(picked):
            variants = sorted((row for row in extra if row['name'] == name), key=lambda row: int(row['area']))
            kept.append(variants[cycle % len(variants)])

    def take_turns(group):
        themed = [r for r in group if HOLIDAY_PERMANENT.get(str(r['area'])) == holiday]
        plain = [r for r in group if str(r['area']) not in HOLIDAY_PERMANENT]
        return sorted(themed or plain or group, key=lambda r: int(r['area']))[number % len(themed or plain or group)]

    permanent = [row for row in permanent if str(row['area']) not in HOLIDAY_PERMANENT or
                 HOLIDAY_PERMANENT[str(row['area'])] == holiday or
                 not any(r['name'] == row['name'] and str(r['area']) not in HOLIDAY_PERMANENT for r in permanent)]
    permanent = _one_per_look(permanent, take_turns, art)
    # Dated areas with distinct missions must not disappear merely because their art matches.
    kept.sort(key=lambda row: (row.get('event_windows', [{}])[0].get('starts_at', ''),
                              int(row['area'])), reverse=True)
    selected = _without_clones(kept + permanent)
    if update:
        from revival_update import document
        mission_dates = document('event_quest_dates.json')['missions']
        cutoff = current.window['to'] if not current.finished else '9999-12-31'
        filtered = []
        for row in selected:
            if str(row['area']) == '711':
                continue
            if row.get('event_windows'):
                filtered.append(row)
                continue
            missions = [mid for mid in row['missions'] if mission_dates.get(str(mid), '') < cutoff]
            if missions:
                filtered.append(dict(row, missions=missions, first_mission=missions[0],
                    held_back=list(row.get('held_back') or []) + [m for m in row['missions'] if m not in missions]))
        selected = filtered
    known = {str(row['area']) for row in rows}
    if not supplied:
        known.update(str(row['area']) for row in history()['added'])
    return EventPlan(tuple(selected), frozenset(known), context)


def can_enter(data, mission, *, resume=False):
    return plan(data).can_enter(data, mission, resume=resume)
