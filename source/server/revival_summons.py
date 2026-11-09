"""Read-only iOS summon policy, using the campaign's recorded replay calendar.

Selection, holidays, ticket exceptions and the post-history shuffle follow revival
47a13c084f42cf1b83b53173d0c21065c78fc2de (replay.py/gacha_rotation.py).
Unlike that implementation this module never imports the engine or writes anchors.
The existing catalogue remains authoritative; deals are a subsequent port.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import copy
import json
from pathlib import Path
import random
import re
from zoneinfo import ZoneInfo

from engine_profile import IOS_REVIVAL
from replay_calendar import historical_start, new_anchor, preview, read_anchor, rotation_week

HERE = Path(__file__).resolve().parent
PERMANENT_NAMES = {'Standard Summon', 'Rare Summon', 'Premium 10+1 Summon',
                   '5★ Guaranteed 10+1 Summon'}
OFFER_KEYS = ('cost', 'draws', 'steps', 'ticket_group_id', 'guarantee', 'secondary_offer',
              'pool', 'reward_pool', 'selection', 'daily_limit', 'weekly_limit',
              'purchase_limit', 'lap_limit', 'milestone_bonus', 'bonus_rewards',
              'bonus_choice', 'guarantee_slots')


def clock():
    return datetime.now(timezone.utc)


@lru_cache(maxsize=1)
def catalogue():
    """Same override order as ffbe_gacha; no process flags or player-state imports."""
    by_id = {}
    for name in ('catalogue', 'community', 'named', 'authored'):
        for banner in json.loads((HERE / f'gacha_{name}.json').read_text(encoding='utf-8'))['banners']:
            by_id[str(banner['id'])] = banner
    for banner in _standard():
        if banner.get('serve', True):
            by_id.setdefault(str(banner['id']), banner)
    return tuple(by_id.values())


@lru_cache(maxsize=1)
def _standard():
    return json.loads((HERE / 'gacha_standard.json').read_text(encoding='utf-8'))['banners']


@lru_cache(maxsize=1)
def unit_dates():
    # Fail visibly for damaged metadata rather than silently opening every future unit.
    try:
        rows = json.loads((HERE / 'unit_release.json').read_text(encoding='utf-8'))['units']
        if not isinstance(rows, dict) or not rows:
            raise ValueError('the unit date map is empty or malformed')
        return {str(uid): date.fromisoformat(day).isoformat() for uid, day in rows.items()}
    except (KeyError, AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid pinned unit-release metadata: {exc}') from exc


@lru_cache(maxsize=1)
def _unlimited_tickets():
    rows = ticket_bundles(json.loads((HERE / 'global_bundles.json').read_text(encoding='utf-8'))['bundles'])
    return {':'.join(str(item).split(':')[:2]) for row in rows if not row.get('limit')
            for item in row.get('contents', [])}


def ticket_bundles(rows):
    """The pinned SP exceptions require their tickets to be one-off purchases on iOS."""
    return [dict(row, limit='once') if str(row['id']) in {'990000108', '990000109'} else copy.deepcopy(row)
            for row in rows if str(row['id']) != '990000107']


def full_pool(banner):
    bid = str(banner['id'])
    if bid == '9200106':  # Plain SP tickets retain the replay limit, including already held tickets.
        return False
    if bid in {'9200107', '9200108'}:
        return True
    cost = banner.get('cost')
    cost = cost[0] if isinstance(cost, list) and cost else cost
    if not isinstance(cost, dict) or cost.get('kind') not in ('item', 'important') or not cost.get('item_id'):
        return False
    kind = '20' if cost['kind'] == 'item' else '23'
    return f"{kind}:{cost['item_id']}" not in _unlimited_tickets()


def unit_allowed(banner, unit_id):
    rule = banner.get('_replay_pool')
    if rule is None or rule['cutoff'] is None:
        return True
    uid = str(unit_id)
    pool = banner.get('pool')
    featured = {str(u) for tier in pool.get('tiers', []) for u in tier.get('featured', [])} \
        if isinstance(pool, dict) else set()
    featured.update(str(u) for u in (banner.get('community') or {}).get('unit_ids', []))
    featured.update(rule['featured'])
    day = unit_dates().get(uid)
    return uid in featured or day is None or day <= rule['cutoff']


def reward_allowed(banner, reward):
    return int(reward['kind']) != 10 or unit_allowed(banner, reward['id'])


def released(banner):
    try:
        raw = (banner.get('community') or {}).get('release') or banner['release']
        return date(*(list(map(int, str(raw).split('-'))) + [1])[:3])
    except (KeyError, TypeError, ValueError):
        return None


def kind(banner):
    for key, label in (('selection', 'select'), ('steps', 'step-up'), ('deal', 'deal'), ('boxes', 'box')):
        if banner.get(key):
            return label
    cost = banner.get('cost')
    cost = cost[0] if isinstance(cost, list) and cost else cost
    return 'ticket' if isinstance(cost, dict) and cost.get('kind') in ('ticket', 'important', 'item') else 'featured'


def _easter(year):
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month, day = divmod(h + m - 7 * n + 114, 31)
    return date(year, month, day + 1)


HOLIDAYS = {
    "Valentine's Day": (lambda y: date(y, 2, 14), (-21, 3),
                        re.compile(r'valentine|white day|sakura & ayaka|sieghard & ignacio|cupid|sweet (luka|nichol)', re.I)),
    'Easter': (_easter, (-21, 7), re.compile(r'easter|egg|bunny', re.I)),
    'Halloween': (lambda y: date(y, 10, 31), (-16, 3),
                  re.compile(r'halloween|hallowe|grim lord|dracu|demon rain|black cat|pumpkin|lilith|full moon', re.I)),
    'Christmas': (lambda y: date(y, 12, 25), (-18, 8),
                  re.compile(r'christmas|santa|holiday|xmas|winter|white knight noel|kryla', re.I)),
}


def _holiday_of(key, names):
    try:
        day = date.fromisoformat(key)
    except ValueError:
        return None
    for name, (when, (before, after), mark) in HOLIDAYS.items():
        if before <= (day - when(day.year)).days <= after and any(mark.search(n or '') for n in names):
            return name
    return None


def _holiday_this_week(start, end):
    for name, (when, _bounds, _mark) in HOLIDAYS.items():
        for year in (start.year, start.year + 1):
            day = when(year)
            noon = datetime(day.year, day.month, day.day, 12, tzinfo=start.tzinfo)
            if start <= noon < end:
                return name, day, 1
            if start + timedelta(weeks=1) <= noon < end + timedelta(weeks=1):
                return name, day, 0
    return None


def _holiday_years(entries, name, day, slot, anchor, settings):
    years = sorted({key[:4] for key, _ids in entries})
    first_day = {y: min(key for key, _ids in entries if key[:4] == y) for y in years}
    when = HOLIDAYS[name][0]
    shown, pick = set(), []
    # Replay the occurrences from this campaign's anchor, with no auxiliary state file.
    anchor_start = rotation_week(datetime(day.year, day.month, day.day, 12,
                                        tzinfo=ZoneInfo(settings.timezone)), settings)
    anchor_start = anchor_start.starts - timedelta(weeks=anchor_start.number - anchor)
    for year in range(max(1, anchor_start.year), day.year + 1):
        occurrence = when(year)
        noon = datetime(year, occurrence.month, occurrence.day, 12, tzinfo=anchor_start.tzinfo)
        holiday_week = rotation_week(noon, settings).number
        if holiday_week < anchor:
            continue
        reached = historical_start(max(0, holiday_week - 1 - anchor), settings)
        pending = [y for y in years if y not in shown]
        if not pending:
            shown, pending = set(), list(years)
        pick = [y for y in pending if first_day[y] <= reached.isoformat()]
        horizon = (reached + timedelta(days=365)).isoformat()
        ahead = [y for y in pending if reached.isoformat() < first_day[y] <= horizon]
        if ahead:
            pick.append(ahead[0])
        shown.update(pick)
    if len(pick) > 1:
        half = (len(pick) + 1) // 2
        pick = pick[:half] if slot == 0 else pick[half:]
    return pick


def _pick(entries, count, number, label):
    if not entries:
        return []
    keys, chosen, used = sorted(entries), [], set()
    for slot in range(count):
        cycle, index = divmod(number * count + slot, len(keys))
        order = list(range(len(keys)))
        random.Random(f'exvius-weekly:{label}:{cycle}').shuffle(order)
        entry = keys[order[index]]
        if entry[0] not in used:
            chosen.append(entry)
            used.add(entry[0])
    return chosen


@dataclass(frozen=True)
class SummonPlan:
    anchored: bool
    window: dict
    finished: bool
    permanent: tuple
    sets: tuple
    by_id: dict
    holiday: str | None
    holiday_sets: dict

    @property
    def ids(self):
        return tuple(dict.fromkeys((*self.permanent, *(bid for _key, ids in self.sets for bid in ids))))

    def configure(self, banner):
        """Attach an operation's cutoff; a fresh command checks membership again before spending."""
        configured = copy.deepcopy(banner)
        pool = banner.get('pool')
        featured = [str(u) for tier in pool.get('tiers', []) for u in tier.get('featured', [])] \
            if isinstance(pool, dict) else []
        featured += [str(u) for u in (banner.get('community') or {}).get('unit_ids', [])]
        original = self.by_id.get(str(banner['id']), banner)
        cutoff = None if self.finished or full_pool(original) else \
            (date.fromisoformat(self.window['to']) - timedelta(days=1)).isoformat()
        configured['_replay_pool'] = {'cutoff': cutoff, 'featured': featured}
        configured['_replay_window'] = {
            'from': datetime.fromisoformat(self.window['starts']).astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            'to': (datetime.fromisoformat(self.window['ends']).astimezone(timezone.utc) -
                   timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S')}
        return configured

    def banners(self):
        return [dict(self.configure(self.by_id[bid]), schedule=dict(self.by_id[bid].get('schedule') or {},
                     disp_order=len(self.ids) - index)) for index, bid in enumerate(self.ids)]

    def describe(self):
        def row(bid):
            b = self.by_id[bid]
            return {'id': bid, 'name': b.get('name', bid), 'kind': kind(b),
                    'full_pool': self.finished or full_pool(b)}
        return dict(self.window, finished=self.finished, holiday=self.holiday,
                    permanent=[row(bid) for bid in self.permanent],
                    sets=[{'release': key, 'banners': [row(bid) for bid in ids]} for key, ids in self.sets])


def plan(data, now=None, *, banners=None, families=None):
    now = now if now is not None else clock()
    calendar = preview(data, now)
    anchor, settings = read_anchor(data) or (calendar['anchor_week'], IOS_REVIVAL.replay)
    window = calendar['windows'][0]
    week = rotation_week(now, settings)
    last = max(max(unit_dates().values()), '2024-08-22')
    finished = window['from'] > last
    banners = catalogue() if banners is None else banners
    families = {str(b['id']) for b in _standard()} if families is None else families
    by_id = {str(b['id']): b for b in banners}
    aliases = {str(alias) for b in banners for alias in b.get('alias_ids', []) if str(alias) != str(b['id'])}
    fixed, sets, seen = [], {}, set()
    for bid, b in by_id.items():
        if bid in aliases:
            continue
        is_fixed = bid in families or b.get('name') in PERMANENT_NAMES or b.get('type') == 'friend' or b.get('permanent')
        day = released(b)
        identity = (('standard', b.get('name')) if bid in families else
                    ((b.get('art') or {}).get('banner'), str(day)),
                    json.dumps({key: b.get(key) for key in OFFER_KEYS}, sort_keys=True))
        if identity in seen:
            continue
        seen.add(identity)
        if is_fixed:
            span = b.get('permanent')
            if isinstance(span, dict):
                if finished and span.get('until'):
                    continue
                if not finished and ((span.get('from') and span['from'] >= window['to']) or
                                     (span.get('until') and span['until'] < window['from'])):
                    continue
            if not finished and window['to'] <= settings.nv_era.isoformat() and 'NV' in b.get('name', ''):
                continue
            fixed.append(bid)
        else:
            sets.setdefault(day.isoformat() if day else 'undated-' + bid, []).append(bid)
    holidays, special, featured = {}, [], []
    for key, ids in sorted(sets.items()):
        if not finished and all(str(by_id[bid].get('source', '')).startswith('translated-jp') for bid in ids):
            continue
        holiday = _holiday_of(key, [by_id[bid].get('name', '') for bid in ids])
        if holiday:
            holidays.setdefault(holiday, []).append((key, ids))
        elif any(kind(by_id[bid]) != 'featured' for bid in ids):
            special.append((key, ids))
        else:
            featured.append((key, ids))
    chosen = _pick(special, 1, week.number, 'special') + _pick(featured, 2, week.number, 'featured') if finished else \
        sorted(entry for entry in special + featured if window['from'] <= entry[0] < window['to'])
    holiday = _holiday_this_week(week.starts, week.ends)
    shown = None
    if holiday and holiday[0] in holidays:
        name, day, slot = holiday
        entries = holidays[name]
        if finished:
            first_start = week.starts - timedelta(weeks=week.number - anchor)
            first_day = HOLIDAYS[name][0](first_start.year)
            first_year = first_start.year + (first_day <= first_start.date())
            years = sorted({key[:4] for key, _ids in entries})
            years = [years[max(0, day.year - first_year) % len(years)]]
        else:
            years = _holiday_years(entries, name, day, slot, anchor, settings)
        picked = [entry for entry in entries if entry[0][:4] in years]
        if picked:
            shown = name
            chosen = picked + [entry for entry in chosen if entry[0] not in {key for key, _ids in picked}]
    return SummonPlan(calendar['anchored'], window, finished, tuple(fixed), tuple(chosen), by_id, shown, holidays)


def event_context(data, now=None, event_keys=None, *, selected=None):
    """The pinned Vortex holiday calendar includes years with events but no summon set."""
    now = now if now is not None else clock()
    current = selected if selected is not None else plan(data, now)
    anchor, settings = read_anchor(data) or (rotation_week(now).number, IOS_REVIVAL.replay)
    week = rotation_week(now, settings)
    held = {key for entries in current.holiday_sets.values() for key, _ids in entries}
    dates = [date.fromisoformat(key) for key, _ids in current.sets if key not in held and not key.startswith('undated-')]
    holiday, years = None, set()
    occurrence = _holiday_this_week(week.starts, week.ends)
    if occurrence:
        name, day, slot = occurrence
        keys = sorted({key for key, _ids in current.holiday_sets.get(name, [])} |
                      set((event_keys or {}).get(name, [])))
        if keys:
            holiday = name
            years = {key[:4] for key, _ids in current.sets if key in keys} if current.finished else \
                set(_holiday_years([(key, []) for key in keys], name, day, slot, anchor, settings))
    return {'summons': current, 'week': week, 'dates': dates, 'holiday': holiday, 'years': years}


def authorize_pull(data, banner):
    current = plan(data)
    if not current.anchored or str(banner['id']) not in current.ids:
        return None
    return current.configure(banner)


def rotation(data, now, weeks):
    calendar = preview(data, now, weeks)
    # One provisional anchor for the whole preview; never restart history for each future week.
    selected = data if calendar['anchored'] else {
        **data, 'ios_revival': {'version': 1, 'replay': new_anchor(now, IOS_REVIVAL.replay)}}
    calendar['windows'] = [plan(selected, datetime.fromisoformat(window['starts']) + timedelta(seconds=1)).describe()
                           for window in calendar['windows']]
    return calendar
