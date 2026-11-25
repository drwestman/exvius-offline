"""Explicit daily update and claim commands, invoked under the engine STATE_LOCK."""
import copy

from engine_profile import current_profile
import revival_daily as policy
import revival_economy as economy


def _commit(player, candidate, path):
    if candidate.data != player.data:
        if not candidate.save(str(path)):
            raise OSError('The iOS daily transaction could not be saved; the previous campaign is preserved.')
        player.data, player.dirty = candidate.data, candidate.dirty


def synchronize(state, path):
    player = state.player
    if player is None or player.mode != 'live' or economy.settings(player.data) is None:
        return False
    today = policy.day(player.data)[0]
    snap = policy.read(player.data)
    stored = player.daily_quest_day()
    if stored > today or (stored == today and snap is not None):
        return False
    candidate = copy.deepcopy(player)
    ids, pools = policy.choose(candidate.data, today)
    if stored == today and player.daily_quest_ids():
        ids = player.daily_quest_ids()  # Preserve pre-port claims and the set already on screen.
    candidate.roll_daily_quests(today, ids, pools)
    candidate.data['daily_quest']['ios'] = policy.snapshot(candidate.data, ids, today)
    candidate.dirty = True
    _commit(player, candidate, path)
    return True


def synchronize_for_reply(spec, reply_id, state, path, *, persist=True):
    if current_profile().replay is None:
        return spec
    from ffbe_config import PROGRESS_REQUESTS
    commands = {'75fYdNxq', 'Daud71Hn', '6QYd5Hym', '9fVIioy1', '9KN5rcwj', 'os4k7C0b', 'UiSC9y8R', '2pe3Xa8b'}
    commands.update(PROGRESS_REQUESTS.get('mission_clear', ()))
    commands.update(PROGRESS_REQUESTS.get('unit_mix', ()))
    from exvius_actions_modes import HANDLERS
    commands.update(rid for rid, fn in HANDLERS.items() if fn.__name__.endswith('_end'))
    if reply_id in commands:
        if not persist:
            raise ValueError('iOS daily updates require state persistence.')
        synchronize(state, path)
    return spec


def claim(spec, reply_id, plaintext):
    from ffbe_state import State, STATE_FILE, STATE_PERSIST
    from ffbe_config import DAILY_QUEST_CLAIM_ALL, DAILY_QUEST_CLAIM_GROUP, DQ_ID
    from ffbe_player import _request_obj
    player = State.player
    if player is None or player.mode != 'live':
        return spec
    if not STATE_PERSIST:
        raise ValueError('iOS daily claims require state persistence.')
    snap = policy.read(player.data)
    if not snap or snap['day'] != policy.day(player.data)[0]:
        return policy.serve(spec, reply_id, player)
    if reply_id == DAILY_QUEST_CLAIM_ALL:
        ids = list(snap['quests'])
    else:
        ids = [str(row.get(DQ_ID, '')) for row in _request_obj(plaintext).get(DAILY_QUEST_CLAIM_GROUP, [])
               if isinstance(row, dict)]
    candidate = copy.deepcopy(player)
    for qid in dict.fromkeys(ids):
        q = snap['quests'].get(qid)
        if q is None or candidate.progress_value(candidate.daily_claim_key(qid)):
            continue
        if candidate.progress_value(candidate.daily_progress_key(qid)) < q['target']:
            continue
        rewards = [r for r in q['reward'] if r['count'] > 0]
        if any(not candidate._can_credit(r) for r in rewards):
            raise ValueError('The daily reward has an unsupported master; nothing was claimed.')
        if candidate._grant_items(rewards, earned=False) != rewards:
            raise ValueError('The daily reward could not be granted completely.')
        candidate.bump_progress(candidate.daily_claim_key(qid), 1, cap=1, what=f'daily claim {qid}')
    key = 'daily_all_bonus:' + snap['day']
    if (candidate.data != player.data and snap['quests'] and not candidate.progress_value(key) and
            all(candidate.progress_value(candidate.daily_claim_key(qid)) for qid in snap['quests'])):
        reward = [{'kind': 50, 'id': 1, 'count': snap['bonus']}] if snap['bonus'] else []
        if candidate._grant_items(reward, earned=False) != reward:
            raise ValueError('The daily completion bonus could not be granted completely.')
        candidate.bump_progress(key, 1, cap=1, what='all daily quests claimed')
    _commit(player, candidate, STATE_FILE)
    out = policy.serve(spec, reply_id, player)
    out = dict(out) if isinstance(out, dict) else {}
    out.setdefault('LhVz6aD2', [])
    return out
