"""Pinned finite encounters for the ten added iOS exploration missions only."""
from collections import Counter
from functools import lru_cache
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKET = HERE / 'content' / 'exploration_encounters_added.json'
MISSIONS = frozenset([f'711010{i}' for i in range(1, 6)] + ['7490101', '7490102', '7030101', '7030102', '7030103'])
TAG = '6v0LPiRe'
FIELDS = (10, 11, 12, 13, 14, 20, 21, 22, 30, 31, 32, 40, 50)


@lru_cache(maxsize=1)
def plans():
    try:
        doc = json.loads(PACKET.read_text(encoding='utf-8'))
        if type(doc['version']) is not int or doc['version'] != 1 or set(doc['missions']) != MISSIONS:
            raise ValueError('incomplete exploration inventory')
        wanted = set()
        for mid, plan in doc['missions'].items():
            if plan['missing'] or len(plan['zones']) != 1 or type(plan['zones'][0]['zone']) is not int or plan['zones'][0]['zone'] != 0:
                raise ValueError(f'{mid}: unsupported or incomplete zone plan')
            battles = plan['zones'][0]['battles']
            if not battles or any(not isinstance(g, str) or not g.isascii() or not g.isdigit() for g in battles):
                raise ValueError(f'{mid}: invalid encounter groups')
            wanted.update(battles)
        if not set(doc['groups']) <= wanted:
            raise ValueError('unrelated authored groups')
        for gid, members in doc['groups'].items():
            if not members or any(r['2fY1IomW'] != gid for r in members):
                raise ValueError('invalid authored group formation')
        return doc
    except (OSError, AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid pinned iOS exploration encounters: {exc}') from exc


@lru_cache(maxsize=1)
def _bindings():
    return json.loads((HERE / 'content' / 'field_group_bindings.json').read_text(encoding='utf-8'))


def encounter_rows(mid, battles, bundle, source):
    slots = {}
    for row in bundle.get('Bi6hVv34', []):
        slots.setdefault(row['2fY1IomW'], []).append(row)
    parts = {}
    for row in source.load('F_MONSTER_PARTS_MST'):
        parts.setdefault(row['xqartN26'], []).append(row)
    rows = []
    for gid, count in Counter(battles).items():
        members = sorted(slots[gid], key=lambda r: int(r['Z0EN6jSh']))
        drops = list(dict.fromkeys(item for member in members for part in parts.get(member['xqartN26'], [])
                                  for item in str(part.get('9BetM2Ds') or '').split(',') if item and len(item.split(':')) >= 4))
        for field in FIELDS:
            for index in range(count):
                rows.append({'qo3PECw6': mid, 'YzGa63QM': str(field), '2fY1IomW': gid, 'h4Sjf96p': str(index),
                    'Z0EN6jSh': '1', 'xqartN26': members[0]['xqartN26'], '6Yc4RkdM': '1',
                    '9BetM2Ds': ','.join(drops), 'MZn8LC6H': '', 'g4voc2Aw': '', 'Vf5DGw07': '',
                    '4K8t5dVh': '0', 'V2mCH5UR': '', '14FMQseU': '0'})
    return rows


def field_bundle(carrier, mission, source, groups):
    mid = str(mission['qo3PECw6'])
    if mid not in MISSIONS:
        return None
    import battle_content as battle
    packet = plans()
    battles = packet['missions'][mid]['zones'][0]['battles']
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
    rows = encounter_rows(mid, battles, bundle, adapted)
    bundle.pop('an6TB4WS', None)
    bundle.pop('y35YvQjZ', None)
    result = battle.story_mission_bundle(carrier, mission)
    result.update(bundle)
    result[TAG] = rows
    return result


def roll_drops(spec, fallback, randint):
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
        projected = dict(row)
        if items:
            projected['9BetM2Ds'] = ','.join(hits or items[-1:])
        else:
            projected.pop('9BetM2Ds', None)
        out.append(projected)
    return dict(spec, **{TAG: out})
