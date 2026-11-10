"""Pinned finite iOS exploration encounters; declared gaps are never fabricated."""
from collections import Counter
from functools import lru_cache
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKET = HERE / 'content' / 'exploration_encounters.json'
ADDED_MISSIONS = frozenset([f'711010{i}' for i in range(1, 6)] + ['7490101', '7490102', '7030101', '7030102', '7030103'])
TAG = '6v0LPiRe'
FIELDS = (10, 11, 12, 13, 14, 20, 21, 22, 30, 31, 32, 40, 50)
EXTRA_FIELDS = {'70701': (70, 71, 72, 73, 74, 75)}


def field_zone(value):
    if value < 60:
        return value // 10
    if 60 <= value <= 63:
        return value - 59
    if 64 <= value <= 67:
        return value - 63
    if 70 <= value <= 75:
        return value - 69
    if 110 <= value <= 150:
        return (value - 100) // 10
    if 210 <= value <= 282:
        return (value - 200) // 10
    return 0


@lru_cache(maxsize=1)
def plans():
    try:
        doc = json.loads(PACKET.read_text(encoding='utf-8'))
        if (not isinstance(doc['missions'], dict) or len(doc['missions']) != 248 or
                not ADDED_MISSIONS <= doc['missions'].keys() or not isinstance(doc['groups'], dict)
                or len(doc['groups']) != 285 or not isinstance(doc['unresolved'], dict)
                or len(doc['unresolved']) != 189 or doc['missions'].keys() & doc['unresolved'].keys()):
            raise ValueError('incomplete exploration inventory')
        wanted = set()
        for mid, plan in doc['missions'].items():
            if (not mid.isascii() or not mid.isdigit() or not isinstance(plan['missing'], list)
                    or any(not isinstance(name, str) or not name for name in plan['missing']) or not plan['zones']):
                raise ValueError(f'{mid}: invalid exploration plan')
            zones = []
            for zone in plan['zones']:
                if type(zone['zone']) is not int or not 0 <= zone['zone'] <= 6:
                    raise ValueError(f'{mid}: unsupported zone')
                zones.append(zone['zone'])
                battles = zone['battles']
                if not isinstance(battles, list) or not battles or any(not isinstance(g, str) or not g.isascii() or not g.isdigit() for g in battles):
                    raise ValueError(f'{mid}: invalid encounter groups')
                wanted.update(battles)
            if len(zones) != len(set(zones)) or 0 in zones and len(zones) > 1:
                raise ValueError(f'{mid}: conflicting zone budgets')
        if not set(doc['groups']) <= wanted:
            raise ValueError('unrelated authored groups')
        for gid, members in doc['groups'].items():
            if not members or any(r['2fY1IomW'] != gid for r in members):
                raise ValueError('invalid authored group formation')
        return doc
    except (OSError, AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid pinned iOS exploration encounters: {exc}') from exc


def coverage():
    doc = plans()
    return {'planned': len(doc['missions']), 'partial': {mid: list(p['missing']) for mid,p in doc['missions'].items() if p['missing']},
            'unresolved': len(doc['unresolved'])}


def has_plan(mid):
    return str(mid) in plans()['missions']


@lru_cache(maxsize=1)
def _bindings():
    return json.loads((HERE / 'content' / 'field_group_bindings.json').read_text(encoding='utf-8'))


def encounter_rows(mid, battles, bundle, source, *, zones=None):
    slots = {}
    for row in bundle.get('Bi6hVv34', []):
        slots.setdefault(row['2fY1IomW'], []).append(row)
    parts = {}
    for row in source.load('F_MONSTER_PARTS_MST'):
        parts.setdefault(row['xqartN26'], []).append(row)
    rows = []
    for zone, battles in zones if zones is not None else [(0,battles)]:
        for gid, count in Counter(battles).items():
            members = sorted(slots[gid], key=lambda r: int(r['Z0EN6jSh']))
            drops = list(dict.fromkeys(item for member in members for part in parts.get(member['xqartN26'], [])
                                      for item in str(part.get('9BetM2Ds') or '').split(',') if item and len(item.split(':')) >= 4))
            for native in FIELDS + EXTRA_FIELDS.get(mid[:5], ()):
                if zone and field_zone(native) != zone:
                    continue
                for index in range(count):
                    rows.append({'qo3PECw6': mid, 'YzGa63QM': str(native), '2fY1IomW': gid, 'h4Sjf96p': str(index),
                        'Z0EN6jSh': '1', 'xqartN26': members[0]['xqartN26'], '6Yc4RkdM': '1',
                        '9BetM2Ds': ','.join(drops), 'MZn8LC6H': '', 'g4voc2Aw': '', 'Vf5DGw07': '',
                        '4K8t5dVh': '0', 'V2mCH5UR': '', '14FMQseU': '0'})
    return rows


def field_bundle(carrier, mission, source, groups, *, enabled=True):
    mid = str(mission['qo3PECw6'])
    if not enabled:
        return None
    import battle_content as battle
    packet = plans()
    plan = packet['missions'].get(mid)
    if plan is None:
        return None
    zones = [(z['zone'], z['battles']) for z in plan['zones']]
    battles = [g for zone, groups_in_zone in zones for g in groups_in_zone]
    wanted = set(battles)
    scripted = {str(link['group']) for links in _bindings().get('scenario_links', {}).values() for link in links}
    own = {g for g in groups if g.startswith(mid) and len(g) == len(mid) + 2}
    retained = groups - (own - scripted - set(_bindings()['missions'].get(mid, [])))
    extra = [row for gid in sorted(wanted) for row in packet['groups'].get(gid, [])]

    class WithGroups(battle.Source):
        def load(self, table):
            rows = source.load(table)
            return rows + extra if table == 'F_BATTLE_GROUP_MST' else rows

    adapted = WithGroups()
    bundle = battle.derive_mission(int(mid), adapted, field_groups=retained | wanted)
    rows = encounter_rows(mid, battles, bundle, adapted, zones=zones)
    bundle.pop('an6TB4WS', None)
    bundle.pop('y35YvQjZ', None)
    result = battle.story_mission_bundle(carrier, mission)
    result.update(bundle)
    result[TAG] = rows
    return result


def roll_drops(spec, fallback, randint, *, bonus=None):
    rows = spec.get(TAG)
    if not isinstance(rows, list) or not rows:
        return spec
    out = []
    for row in rows:
        if not isinstance(row, dict) or '9BetM2Ds' not in row:
            out.append(row)
            continue
        items = []
        for entry in str(row.get('9BetM2Ds') or fallback).split(','):
            if not entry:
                continue
            if len(entry.split(':')) < 3:
                raise ValueError('Invalid iOS field drop candidate.')
            items.append(entry + ':100' if len(entry.split(':')) == 3 else entry)
        hits = [s for s in items if randint(1, 100) <= (int(s.split(':')[3]) if len(s.split(':')) > 3 and s.split(':')[3].isdigit() else 100)]
        rolled = hits or items[-1:]
        if bonus is not None:
            rolled = bonus(rolled)
        projected = dict(row)
        if rolled:
            projected['9BetM2Ds'] = ','.join(rolled)
        else:
            projected.pop('9BetM2Ds', None)
        out.append(projected)
    return dict(spec, **{TAG: out})
