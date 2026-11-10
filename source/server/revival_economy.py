"""Recorded iOS economy policy; raw reward rows remain the source denomination.

Only earned grants are multiplied. Purchases, refunds and already-normalized
daily rewards explicitly bypass this conversion; direct balance edits do too.
"""
import copy
import math
import os
import json
from pathlib import Path
from functools import lru_cache


def settings(data):
    if 'ios_economy' not in data:
        if isinstance(data.get('daily_quest'), dict) and 'ios' in data['daily_quest']:
            raise ValueError('Invalid iOS economy: daily rewards have no recorded economy settings.')
        return None
    try:
        state = data['ios_economy']
        if type(state['version']) is not int or state['version'] != 1:
            raise ValueError('unsupported version')
        s = state['settings']
        if set(s) != {'multiplier', 'daily_lapis', 'all_bonus', 'custom', 'count'}:
            raise ValueError('incomplete settings')
        if (type(s['multiplier']) not in (int, float) or not math.isfinite(s['multiplier']) or
                not 0 <= s['multiplier'] <= 1000 or type(s['custom']) is not bool or
                any(type(s[k]) is not int or not 0 <= s[k] <= 1000000 for k in ('daily_lapis', 'all_bonus')) or
                type(s['count']) is not int or not 1 <= s['count'] <= 8):
            raise ValueError('invalid economy values')
        return s
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid iOS economy: {exc}') from exc


def initialize(data):
    if settings(data) is not None:
        return False
    try:
        state = {'multiplier': float(os.environ.get('EXVIUS_LAPIS_MULTIPLIER', '5')),
                 'daily_lapis': int(os.environ.get('EXVIUS_DAILY_QUEST_LAPIS', '150')),
                 'all_bonus': int(os.environ.get('EXVIUS_DAILY_ALL_BONUS', '200')),
                 'custom': os.environ.get('EXVIUS_DAILY_CUSTOM', '1').strip().lower() not in ('0', 'false', 'off', ''),
                 'count': int(os.environ.get('EXVIUS_DAILY_QUEST_COUNT', '5'))}
        candidate = {**data, 'ios_economy': {'version': 1, 'settings': state}}
        settings(candidate)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid iOS economy defaults: {exc}') from exc
    data['ios_economy'] = candidate['ios_economy']
    return True


def earned(data, amount):
    s = settings(data)
    return int(round(amount * s['multiplier'])) if amount > 0 and s else int(amount)


def rewards(data, rows):
    out = copy.deepcopy(rows)
    for row in out:
        if int(row['kind']) == 50:
            row['count'] = earned(data, int(row['count']))
    return out


def display(data, raw):
    """Normalize native reward text without dropping any metadata fields."""
    out = []
    for entry in filter(None, str(raw or '').split(',')):
        # Mission-result rewards wrap the same CSV item in source@item@state.
        # Keep those fields, and unit metadata, byte-for-byte.
        wrapped = entry.split('@')
        index = 1 if len(wrapped) == 3 else 0
        f = wrapped[index].split(':')
        if f[0] == '50' and len(f) >= 3:
            f[2] = str(earned(data, int(f[2])))
        wrapped[index] = ':'.join(f)
        out.append('@'.join(wrapped))
    return ','.join(out)


@lru_cache(maxsize=1)
def bundles():
    rows = json.loads(Path(__file__).with_name('content').joinpath('revival_bundles.json').read_text())['bundles']
    if not rows or len({row['id'] for row in rows}) != len(rows):
        raise ValueError('Invalid pinned revival bundles.')
    return tuple(rows)


def bundle_active(data, bundle, now=None):
    start, until = bundle.get('from'), bundle.get('until')
    if not start and not until:
        return True
    from replay_calendar import preview
    from revival_summons import unit_dates
    from revival_daily import clock
    window = preview(data, now if now is not None else clock())['windows'][0]
    if window['from'] > max(max(unit_dates().values()), '2024-08-22'):
        return not until
    return (not start or start < window['to']) and (not until or until >= window['from'])


def transform_master(data, name, rows):
    """Pure preparation input for native master displays; never edit shared data."""
    columns = {'F_CHALLENGE_MST': ('dX6cor8j',), 'F_PANEL_QUEST_MST': ('dX6cor8j',),
               'F_SP_CHALLENGE_MST': ('dX6cor8j',), 'F_RB_SS_MST': ('dJ1g6p8h', '6Emk0agT'),
               'F_RB_SS_REWARD_MST': ('dX6cor8j',)}.get(name, ())
    result = copy.deepcopy(rows)
    for row in result:
        for column in columns:
            if column in row:
                row[column] = display(data, row[column])
    return result


def project(spec, player):
    """Response-only conversion of raw native reward channels, after commands."""
    from engine_profile import current_profile
    if (current_profile().replay is None or not isinstance(spec, dict) or player is None or
            not set(spec).intersection({'f5bA4wFx', '09HRWXDf', 'g3JFd0y7', 'ELPwhZj0', '3KLU4mSD'})):
        return spec
    out = copy.deepcopy(spec)
    for row in out.get('f5bA4wFx', []):
        if str(row.get('YWF08vZS')) == '50':
            row['5GNDIwPX'] = str(earned(player.data, int(row['5GNDIwPX'])))
    for group, columns in (('09HRWXDf', ('REB5tAL9',)),
                           ('g3JFd0y7', ('k9pWH78Z',)),
                           ('ELPwhZj0', ('dX6cor8j',)), ('3KLU4mSD', ('dX6cor8j',))):
        for row in out.get(group, []):
            for column in columns:
                if column in row:
                    row[column] = display(player.data, row[column])
    return out
