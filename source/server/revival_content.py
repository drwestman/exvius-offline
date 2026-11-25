"""Pinned iOS authored content from revival 47a13c084f42cf1b83b53173d0c21065c78fc2de.

Only the six absent Halloween encounters are reconstructed here. The other added
areas retain the canonical exploration/story/index paths and original masters.
Metadata reads and returned copies never write, initialize campaigns, or fetch art.
"""
import copy
from datetime import date
from functools import lru_cache
import json
from pathlib import Path

PACKET = Path(__file__).with_name('event_encounters_added.json')
ADDED_AREAS = frozenset({'703', '711', '712', '746', '747', '749', '797', '919', '921'})
RECONSTRUCTED_MISSIONS = frozenset(f'{area}000{step}' for area in ('919', '921') for step in (1, 2, 3))


@lru_cache(maxsize=1)
def encounters():
    try:
        document = json.loads(PACKET.read_text(encoding='utf-8'))
        if type(document['version']) is not int or document['version'] != 1:
            raise ValueError('unsupported packet version')
        entries = document['missions']
        if set(entries) != RECONSTRUCTED_MISSIONS:
            raise ValueError('incomplete or unexpected reconstructed missions')
        for mid, entry in entries.items():
            bundle = entry['bundle']
            for group in ('an6TB4WS', 'Bi6hVv34', 'wbet57nF', 'bV34YIJQ', 'y35YvQjZ', 'Wp39QX52', '1IfDqR4n'):
                if not isinstance(bundle[group], list) or any(not isinstance(r, dict) for r in bundle[group]):
                    raise ValueError(f'{mid}: invalid native group {group}')
            phases, missions = bundle['an6TB4WS'], bundle['1IfDqR4n']
            if (not phases or len(missions) != 1 or missions[0]['qo3PECw6'] != mid
                    or int(missions[0]['8xi6Xvyk']) != len(phases)
                    or str(missions[0]['uv60hgDW']) != mid[:3]):
                raise ValueError(f'{mid}: mission identity or original wave count differs')
            if (any(r.get('qo3PECw6') != mid or r.get('gou39JeI') != '2' for r in phases)
                    or [int(r['6v7y3QcJ']) for r in phases] != list(range(1, len(phases) + 1))):
                raise ValueError(f'{mid}: invalid combat phases')
            groups = {r['2fY1IomW'] for r in bundle['Bi6hVv34']}
            if groups != {r['2fY1IomW'] for r in phases}:
                raise ValueError(f'{mid}: missing or unrelated battle groups')
            enemies = {r['xqartN26'] for r in bundle['Bi6hVv34']}
            monsters = {r['xqartN26'] for r in bundle['wbet57nF']}
            parts = {r['xqartN26'] for r in bundle['bV34YIJQ']}
            if not enemies or enemies != monsters or enemies != parts:
                raise ValueError(f'{mid}: incomplete enemy definitions')
            if any(not r.get('V9j8wJcC') or not r.get('G4L0YIB2') for r in bundle['wbet57nF']):
                raise ValueError(f'{mid}: missing enemy identity')
            if any(int(r['fh31sk7B']) <= 0 for r in bundle['bV34YIJQ']):
                raise ValueError(f'{mid}: invalid enemy HP')
        return entries
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid pinned iOS authored encounters: {exc}') from exc


def encounter(mission):
    if str(mission) not in RECONSTRUCTED_MISSIONS:
        return None
    entry = encounters().get(str(mission))
    return copy.deepcopy(entry['bundle']) if entry else None


def added_events(rows):
    """Validate the tracked history additions before advertising any new gates."""
    try:
        if {row['area'] for row in rows} != ADDED_AREAS or len(rows) != len(ADDED_AREAS):
            raise ValueError('incomplete or duplicate event areas')
        seen = set()
        for row in rows:
            date.fromisoformat(row['release'])
            if (not row['name'] or not row['missions'] or not row['dungeons']
                    or row['first_mission'] not in row['missions']
                    or row['first_dungeon'] not in row['dungeons']
                    or any(not mid.isascii() or not mid.isdigit() or not mid.startswith(row['area'])
                           or mid in seen for mid in row['missions'])
                    or len(set(row['missions'])) != len(row['missions'])):
                raise ValueError(f"invalid authored area {row['area']}")
            seen.update(row['missions'])
        if len(seen) != 118:
            raise ValueError('incomplete authored mission inventory')
        encounters()  # An unavailable reconstruction must not produce a playable gate.
        from revival_exploration import plans
        plans()
        return copy.deepcopy(rows)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid pinned iOS authored events: {exc}') from exc
