"""Recorded iOS exploration/rare-loot policy; commands own persistence and grants."""
import copy
import math
import os

STATE_KEY = 'ios_loot'
FIXED_KEY = 'ios_fixed_loot'
WRIT = '20:290060400'


def settings(data):
    if STATE_KEY not in data:
        return None
    try:
        state = data[STATE_KEY]
        values = state['settings']
        if (type(state['version']) is not int or state['version'] != 1 or
                set(values) != {'field_encounters', 'writ_chance'} or
                type(values['field_encounters']) is not bool or
                type(values['writ_chance']) not in (int, float) or
                not 0 <= values['writ_chance'] <= 100 or not math.isfinite(values['writ_chance'])):
            raise ValueError('unsupported settings')
        return values
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid iOS loot settings: {exc}') from exc


def initialize(data):
    if settings(data) is not None:
        return False
    try:
        values = {'field_encounters': os.environ.get('EXVIUS_FIELD_ENCOUNTERS', '1').strip().lower()
                  not in ('0', 'off', 'false', 'no'),
                  'writ_chance': float(os.environ.get('EXVIUS_CALAMITY_WRIT_DROP', '0.5'))}
        candidate = {STATE_KEY: {'version': 1, 'settings': values}}
        settings(candidate)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid iOS loot defaults: {exc}') from exc
    data[STATE_KEY] = candidate[STATE_KEY]
    return True


def chance(player, persist=True):
    if player is None or player.mode != 'live' or not persist:
        return 0
    values = settings(player.data)
    if values is None or not values['writ_chance']:
        return 0
    # Never offer an item missing from this installation's masters.
    return values['writ_chance'] if player._can_credit({'kind':20, 'id':290060400, 'count':1}) else 0


def add_writ(items, percent, random):
    if percent > 0 and random() * 100 < percent:
        return list(items) + [WRIT + ':1:100']
    return list(items)


def _writ_count(rows):
    count = 0
    for row in rows:
        for entry in str(row.get('9BetM2Ds') or '').split(','):
            fields = entry.split(':')
            if ':'.join(fields[:2]) == WRIT:
                if len(fields) < 4 or not fields[2].isascii() or not fields[2].isdigit():
                    raise ValueError('invalid recorded Writ quantity')
                count += int(fields[2])
    return count


def fixed_receipt(data):
    try:
        attempt = data.get('exvius_repeat', {}).get('attempt', {})
        if FIXED_KEY not in attempt:
            return None
        receipt = attempt[FIXED_KEY]
        rows = receipt['rows']
        if (type(receipt['version']) is not int or receipt['version'] != 1 or
                set(receipt) != {'version', 'rows', 'writ_count'} or
                not isinstance(rows, list) or not rows or
                type(receipt['writ_count']) is not int or not 0 <= receipt['writ_count'] <= 1000000):
            raise ValueError('invalid fixed drop receipt')
        phases = []
        for row in rows:
            phase = row['6v7y3QcJ']
            if (row.get('qo3PECw6', attempt['mid']) != attempt['mid'] or not isinstance(phase, str)
                    or not phase.isascii() or not phase.isdigit() or int(phase) < 1):
                raise ValueError('invalid recorded phase identity')
            phases.append(phase)
        if len(phases) != len(set(phases)) or receipt['writ_count'] != _writ_count(rows):
            raise ValueError('conflicting fixed drop facts')
        return receipt
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid iOS fixed loot receipt: {exc}') from exc


def pending(data, mid):
    attempt = data.get('exvius_repeat', {}).get('attempt', {})
    return attempt.get('mid') == str(mid) and attempt.get('status') == 'pending'


def record_fixed(player, spec):
    rows = copy.deepcopy(spec.get('y35YvQjZ') or [])
    if not rows:
        return
    receipt = {'version':1, 'rows':rows, 'writ_count':_writ_count(rows)}
    candidate = copy.deepcopy(player.data)
    candidate['exvius_repeat']['attempt'][FIXED_KEY] = receipt
    fixed_receipt(candidate)
    player.data['exvius_repeat']['attempt'][FIXED_KEY] = receipt
    player.dirty = True


def fixed_bonus(player, mid):
    if player.mode != 'live':
        return 0
    attempt = player.data.get('exvius_repeat', {}).get('attempt', {})
    if attempt.get('mid') != str(mid):
        return 0
    receipt = fixed_receipt(player.data)
    return receipt['writ_count'] if receipt else 0
