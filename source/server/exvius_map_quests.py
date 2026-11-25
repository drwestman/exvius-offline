"""Original town-quest defeat counters: pure planning, explicit command updates.

GL9 UserQuestSubInfoResponse reads 0G7J2vfD as an ordered comma list of
dictionary-id:count pairs (QuestUtil::createTargetInfoList, 0x1a77dbc).
The result's f6M1cJgk instead uses battle monster IDs. Resolve those through
the loaded bundle's wbet57nF metadata, retained with the attempt for replay.
Reaching a target does not turn in the quest or grant its NPC reward.
"""
import re
from collections import Counter


def counts(raw):
    """Decode native ID:count pairs; reject ambiguous or malformed reports."""
    if raw in ('', None):
        return {}
    if not isinstance(raw, str):
        raise ValueError('defeat counts must be a native string')
    result = {}
    for entry in raw.split(','):
        if not re.fullmatch(r'[0-9]{1,10}:[0-9]{1,10}', entry):
            raise ValueError('invalid defeat count pair')
        key, amount = entry.split(':')
        if not 0 < int(key) <= 2147483647 or int(amount) > 2147483647 or key in result:
            raise ValueError('invalid or duplicate defeat count')
        result[key] = int(amount)
    return result


def monster_map(bundle):
    """Snapshot only unambiguous battle-monster -> dictionary-family mappings."""
    result, conflicts = {}, set()
    for row in bundle.get('wbet57nF') or []:
        if not isinstance(row, dict):
            continue
        monster, family = row.get('xqartN26'), row.get('V9j8wJcC')
        if not all(isinstance(v, str) and re.fullmatch(r'[0-9]{1,10}', v)
                   and 0 < int(v) <= 2147483647 for v in (monster, family)):
            continue
        if monster in result and result[monster] != family:
            conflicts.add(monster)
        result[monster] = family
    return {key: value for key, value in result.items() if key not in conflicts}


def plan_progress(quests, steps, defeated, *, floor=False, note=None):
    """Return changed subquest strings, without mutating state or completing quests.

    floor=True restores a verified historical total rather than adding it again.
    Both modes preserve target order, existing progress and original caps.
    """
    updates = {}
    for sid, saved in quests.items():
        step = steps.get(sid) or {}
        if (saved.get('4kcAD9fW') != '1' or saved.get('7Svg2kdT') != sid
                or saved.get('Z34jU7ue') != step.get('Z34jU7ue')
                or (step.get('89EvGKHx'), step.get('siLGXq94')) != ('2', '2')):
            continue
        try:
            after, previous = _advance(step, saved, defeated, floor)
        except ValueError as exc:
            # One inconsistent quest must not discard progress for the others.
            if note:
                note(f'map quests: quest {sid} skipped: {exc}')
            continue
        if after and any(after[key] != previous.get(key, 0) for key in after):
            updates[sid] = ','.join(f'{key}:{value}' for key, value in after.items())
    return updates


def _advance(step, saved, defeated, floor):
    """Compute one quest's new counters; raise ValueError if its data is inconsistent."""
    targets = counts(step.get('25oxcKwN'))
    if not targets or not any(defeated.get(key, 0) > 0 for key in targets):
        return {}, {}
    previous = counts(saved.get('0G7J2vfD'))
    if previous.keys() - targets.keys():
        raise ValueError('saved defeat progress names an unknown target')
    after = {}
    for key, maximum in targets.items():
        old, gain = previous.get(key, 0), defeated.get(key, 0)
        if maximum < 1 or old > maximum or type(gain) is not int or gain < 0:
            raise ValueError('invalid quest defeat progress')
        after[key] = min(maximum, max(old, gain) if floor else old + gain)
    return after, previous


def plan_battle(data, raw, steps, note=None):
    """Join reported defeats to the attempt's recorded families, never guessed IDs."""
    known = data.get('exvius_repeat', {}).get('attempt', {}).get('map_quest_monsters') or {}
    defeated = Counter()
    for monster, amount in counts(raw).items():
        family = known.get(monster)
        if family:
            defeated[family] += amount
    return plan_progress(data.get('exvius_map', {}).get('quests') or {}, steps, defeated, note=note)


def score_defeats(player, raw):
    """Command-side update, called only after claiming this attempt's quest receipt."""
    from player_state import _load_ndjson
    from ffbe_state import _note
    if player.mode == 'frozen':
        return
    try:
        updates = plan_battle(player.data, raw, _load_ndjson('F_QUEST_SUB_MST.ndjson', '7Svg2kdT'), _note)
    except ValueError as exc:
        _note(f'map quests: defeat progress withheld: {exc}')
        return
    for sid, progress in updates.items():
        player.data['exvius_map']['quests'][sid]['0G7J2vfD'] = progress
    if updates:
        player.dirty = True
