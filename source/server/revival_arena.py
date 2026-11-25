"""Read-only iOS arena policy from revival 47a13c084f42's arena_ladder.py.

One request-local ladder shares the saved calendar and simulated friend pool.
Only the command adapter initializes settings, settles rewards or resets scores.
"""
from datetime import datetime, timedelta, timezone
from functools import cached_property
import math
import random

from replay_calendar import read_anchor, rotation_week
from revival_friends import Directory, _setting

REFRESH_SECONDS = 600
GLOBAL_LAST_BRACKET = 300000


def clock():
    return datetime.now(timezone.utc)


def defaults():
    return {'version': 1, 'top_score': _setting('EXVIUS_ARENA_TOP', 12000, 10000000),
            'rivals': max(1, _setting('EXVIUS_ARENA_RIVALS', 5, 10))}


def configuration(data):
    model = data.get('exvius_arena', {})
    if not isinstance(model, dict):
        raise ValueError('Invalid iOS arena state.')
    if 'ladder' not in model:
        return defaults()
    raw = model['ladder']
    if (not isinstance(raw, dict) or set(raw) != {'version', 'top_score', 'rivals'} or
            type(raw['version']) is not int or raw['version'] != 1 or
            type(raw['top_score']) is not int or not 0 <= raw['top_score'] <= 10000000 or
            type(raw['rivals']) is not int or not 1 <= raw['rivals'] <= 10):
        raise ValueError('Invalid iOS arena ladder settings.')
    return raw


def master(name, key):
    from exvius_actions import _mst
    return _mst(name, key)


def select_season(rows, historical):
    rows = sorted((r for r in rows if str(r['6Z9DxQFf']).isdigit() and int(r['6Z9DxQFf']) > 0),
                  key=lambda r: (r.get('VjJQ51uG', ''), int(r['6Z9DxQFf'])))
    if not rows:
        return '0'
    if historical is None:
        return str(rows[-1]['6Z9DxQFf'])
    started = [r for r in rows if r.get('VjJQ51uG', '') <= historical + ' 23:59:59']
    return str((started[-1] if started else rows[0])['6Z9DxQFf'])


def strength(friend_id, number):
    rng = random.Random(f'arena-strength-{friend_id}-{number}')
    base = random.Random(f'arena-persona-{friend_id}').random()
    return min(1.0, max(0.0, 0.75 * base ** 1.8 + 0.25 * rng.random() ** 2))


def placement(rank, total):
    return max(1, math.ceil(rank / max(1, total) * GLOBAL_LAST_BRACKET))


def clean(name):
    return str(name).replace(':', ' ').replace(',', ' ').replace(';', ' ')


class Ladder:
    def __init__(self, data, now=None):
        self.data = data
        self.now = now if now is not None else clock()
        self.directory = Directory(data, self.now)
        self.config = configuration(data)
        saved = read_anchor(data)
        self.week = rotation_week(self.now, saved[1]) if saved else rotation_week(self.now)

    @property
    def enabled(self):
        return bool(self.directory.ids())

    def season_id(self):
        rows = master('F_RB_SS_MST.ndjson', '6Z9DxQFf').values()
        historical = self.directory.window['from'] if self.directory.cutoff is not None else None
        return select_season(rows, historical)

    def team(self, friend):
        from player_state import limit_burst
        leader = friend['unit']
        pool = self.directory.unit_pool(friend['rank'])
        rng = random.Random(f"arena-team-{friend['friend_id']}-{self.week.number}")
        picks, seen = [], {str(leader['master_id'])}
        for uid, level in rng.sample(pool, min(len(pool), 12)):
            if uid not in seen and len(picks) < 4:
                seen.add(uid)
                picks.append((uid, level))
        units = [{'master_id': str(leader['master_id']), 'level': int(leader['level']),
                  'lb_level': int(leader.get('lb_level') or 0)}]
        units += [{'master_id': uid, 'level': level, 'lb_level': 1 if limit_burst(uid) else 0}
                  for uid, level in picks]
        for order, unit in enumerate(units):
            unit['instance_id'] = str(int(friend['friend_id']) * 10 + order + 1)
            unit['gear'] = 0.25 + 0.35 * strength(friend['friend_id'], self.week.number)
        return units

    @cached_property
    def targets(self):
        raw = {int(fid): strength(int(fid), self.week.number) ** 1.4 *
               random.Random(f'arena-target-{fid}-{self.week.number}').uniform(0.85, 1.0)
               for fid in self.directory.ids()}
        best = max(raw.values(), default=1) or 1
        jitter = random.Random(f'arena-top-{self.week.number}').uniform(0.94, 1.0)
        return {fid: int(round(self.config['top_score'] * jitter * value / best / 10) * 10)
                for fid, value in raw.items()}

    def points(self, friend_id):
        # UTC arithmetic counts the actual 167/169 hours across Eastern DST.
        start, end = self.week.starts.timestamp(), self.week.ends.timestamp()
        done = min(1.0, max(0.0, (self.now.timestamp() - start) / max(1.0, end - start)))
        pace = random.Random(f'arena-pace-{friend_id}-{self.week.number}').uniform(0.7, 1.4)
        return int(self.targets.get(int(friend_id), 0) * done ** pace) // 10 * 10

    def standings(self, own_points):
        rows = sorted(((self.points(fid), fid) for fid in self.directory.ids()),
                      key=lambda row: (-row[0], int(row[1])))
        rank = sum(pts >= own_points for pts, _fid in rows)
        rows.insert(rank, (own_points, None))
        return rows

    def rank_of(self, own_points):
        return next(i for i, (_pts, fid) in enumerate(self.standings(own_points), 1) if fid is None)

    def ranking_entries(self, own_points, user, limit=100):
        out = []
        for rank, (pts, fid) in enumerate(self.standings(own_points), 1):
            if fid is None:
                fields = (user['id'], clean(user['name']), user['unit'], user['unit_level'],
                          pts, rank, user['rank'], 100, 0, 0)
            elif rank <= limit:
                friend = self.directory.by_id(fid)
                fields = (fid, clean(friend['display_name']), friend['unit']['master_id'],
                          friend['unit']['level'], pts, rank, friend['rank'], 100, friend['emblem_id'], 0)
            else:
                continue
            out.append(':'.join(map(str, fields)))
        return ','.join(out)

    def candidates(self, party):
        ids = self.directory.ids()
        window = int(self.now.timestamp() // REFRESH_SECONDS)
        rng = random.Random(f'arena-list-{self.week.number}-{window}')
        picked = rng.sample(ids, min(len(ids), self.config['rivals'] * 3))
        scored = []
        for fid in picked:
            friend = self.directory.by_id(fid)
            units = self.team(friend)
            scored.append((ratio(units, party), friend, units))
        scored.sort(key=lambda row: row[0])
        size = self.config['rivals']
        if len(scored) > size:
            step = (len(scored) - 1) / (size - 1) if size > 1 else 0
            scored = [scored[round(i * step)] for i in range(size)]
        return [(friend, units, rate) for rate, friend, units in scored]

    def candidate_entries(self, rows):
        ranks = {fid: i for i, (_pts, fid) in enumerate(self.standings(-1), 1) if fid is not None}
        return ','.join(':'.join(map(str, (f['friend_id'], clean(f['display_name']),
            f['unit']['master_id'], f['unit']['level'], self.points(f['friend_id']), ranks[str(f['friend_id'])],
            f['rank'], rate, f['emblem_id'], 0, 0))) for f, _units, rate in rows)


def for_model(data, model, now=None):
    """An unsettled/active older week remains an older-week view until entry rolls it."""
    now = now if now is not None else clock()
    if model.get('week') is not None:
        try:
            start = datetime.fromisoformat(model['week_starts'])
            end = datetime.fromisoformat(model['week_ends'])
            if start.utcoffset() is None or end.utcoffset() is None:
                raise ValueError('Arena boundaries must include timezones.')
            recorded = rotation_week(start, read_anchor(data)[1])
            if (type(model['week']) is not int or model['week'] != recorded.number or
                    start.timestamp() != recorded.starts.timestamp() or end.timestamp() != recorded.ends.timestamp()):
                raise ValueError('Arena boundaries do not match the recorded week.')
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f'Invalid iOS arena week: {exc}') from exc
        end = end.astimezone(timezone.utc)
        start = start.astimezone(timezone.utc)
        if now < start:
            now = start
        elif now >= end:
            now = end - timedelta(seconds=1)
    return Ladder(data, now)


def _base(unit):
    from player_state import unit_stats
    return unit_stats(unit['master_id'], unit['level'])


def _power(stats):
    hp, mp, atk, df, mag, spr = stats
    return hp / 10 + mp / 10 + atk + df + mag + spr


def ratio(units, party):
    from player_state import owned_unit_stats
    equipment = master('F_EQUIP_ITEM_MST.ndjson', 'J1YX9kmM')
    tokens = ('fh31sk7B', 'PC97pWQj', '9NBV1XCS', 'Pn5w9dfh', '84FJM3PD', 'T8xMDAZ4')
    own = 0
    for unit in party:
        stats = list(owned_unit_stats(unit))
        worn = unit.get('equipment') or {}
        for iid in (worn.values() if isinstance(worn, dict) else worn):
            row = equipment.get(str(iid))
            if row:
                stats = [s + int(row.get(t) or 0) for s, t in zip(stats, tokens)]
        own += _power(stats)
    power = sum(_power([round(v * (1 + u['gear'])) for v in _base(u)]) for u in units)
    return int(min(150, max(50, round((100 * power / max(1.0, own)) / 5) * 5)))


def rival_string(units, number):
    from player_state import limit_burst
    patterns = list(master('F_RB_AI_PATTERN_MST.ndjson', 'UE3vKA5y').values())
    total = sum(int(row['ixDq7yJ8']) for row in patterns)
    if total <= 0:
        raise ValueError('Arena AI patterns are unavailable.')
    entries = []
    for order, unit in enumerate(units):
        draw = random.Random(f"arena-ai-{unit['instance_id']}-{number}").randrange(total)
        for row in patterns:
            draw -= int(row['ixDq7yJ8'])
            if draw < 0:
                pattern = row['UE3vKA5y']
                break
        stats = [f'{v}-{round(v * unit["gear"])}' for v in _base(unit)]
        lb = str(max(int(unit['lb_level']), 1 if limit_burst(unit['master_id']) else 0))
        entries.append(':'.join([unit['instance_id'], unit['master_id'], unit['master_id'], str(unit['level']),
            *stats, lb, '@'.join(f'{i}-0' for i in range(1, 7)), '@'.join(f'{i}-0' for i in range(1, 5)),
            '', '', '0' if order == 0 else '1', str(order), str(pattern)]))
    return ';'.join(entries)


def reward_row(season, global_rank):
    rows = [row for row in master('F_RB_SS_REWARD_MST.ndjson', None)['__rows__']
            if row['6Z9DxQFf'] == str(season) and row['vs48LZrt'] == '0']
    for row in sorted(rows, key=lambda row: int(row['ip94Nqb7'])):
        if int(row['ip94Nqb7']) <= global_rank <= int(row['XM4Ca3PF']):
            return row
    return max(rows, key=lambda row: int(row['XM4Ca3PF']), default=None)
