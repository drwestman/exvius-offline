"""Recorded quest-trust policy from revival 47a13c0; planning never grants or saves."""
import math
import os
import secrets

STATE_KEY = 'ios_quest_trust'


def settings(data):
    if STATE_KEY not in data:
        return None
    try:
        state = data[STATE_KEY]
        if type(state['version']) is not int or state['version'] != 1:
            raise ValueError('unsupported version')
        values = state['settings']
        if set(values) != {'enabled', 'chance', 'points', 'big_chance', 'big_points'}:
            raise ValueError('incomplete settings')
        if type(values['enabled']) is not bool:
            raise ValueError('enabled must be boolean')
        for key in ('chance', 'big_chance'):
            if (type(values[key]) not in (int, float) or not 0 <= values[key] <= 100
                    or not math.isfinite(values[key])):
                raise ValueError(f'{key} must be a finite percentage between 0 and 100')
        for key in ('points', 'big_points'):
            if type(values[key]) is not int or not 0 <= values[key] <= 1000000:
                raise ValueError(f'{key} must be a nonnegative integer up to 1000000')
        return values
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid iOS quest trust: {exc}') from exc


def initialize(data):
    if settings(data) is not None:
        return False
    try:
        values = {'enabled': os.environ.get('EXVIUS_QUEST_TRUST', '1').strip().lower()
                  not in ('0', 'false', 'off', ''),
                  'chance': float(os.environ.get('EXVIUS_QUEST_TRUST_CHANCE', '30')),
                  'points': int(os.environ.get('EXVIUS_QUEST_TRUST_POINTS', '10')),
                  'big_chance': float(os.environ.get('EXVIUS_QUEST_TRUST_BIG_CHANCE', '5')),
                  'big_points': int(os.environ.get('EXVIUS_QUEST_TRUST_BIG_POINTS', '50'))}
        candidate = {STATE_KEY: {'version': 1, 'settings': values}}
        settings(candidate)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid iOS quest trust defaults: {exc}') from exc
    data[STATE_KEY] = candidate[STATE_KEY]
    return True


def roll(player, *, randbelow=None):
    """Plan {own instance ID: capped gain}; caller owns the clear/attempt guard."""
    if player is None or player.mode != 'live':
        return {}
    values = settings(player.data)
    if values is None:
        raise ValueError('iOS quest trust must be initialized before battle settlement.')
    if not values['enabled'] or not values['points'] or not values['chance']:
        return {}
    randbelow = randbelow if randbelow is not None else secrets.randbelow
    gains = {}
    for iid in dict.fromkeys(player.party_instance_ids()):
        unit = player.roster_row(iid)
        if unit is None:
            continue
        target, _ = player._unit_trust_info(unit, 0)
        raw = (list(unit.get('affinity_points') or ['']) + [''])[0]
        current = int(raw) if str(raw).isdigit() else 0
        if not target or target[0] == 71 or target[3] <= current:
            continue
        if randbelow(10000) >= round(values['chance'] * 100):
            continue
        amount = values['points']
        if values['big_points'] and randbelow(10000) < round(values['big_chance'] * 100):
            amount = values['big_points']
        gains[iid] = min(amount, target[3] - current)
    return gains
