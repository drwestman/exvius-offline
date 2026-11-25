"""Explicit iOS inbox commands; invoke under the canonical engine's STATE_LOCK."""
import copy
from datetime import timezone

from engine_profile import current_profile
import revival_mail_rewards as policy

SYNC_REPLIES = frozenset({'75fYdNxq', 'Daud71Hn'})  # Initialize and RoutineHomeUpdate.


def synchronize(state, state_file, *, now=None):
    player = state.player
    if player is None or player.mode != 'live':
        return False
    now = now if now is not None else policy.clock()
    due = policy.plan(player.data, now)
    if not due:
        return False
    candidate = copy.deepcopy(player)
    ledger = candidate.data[policy.STATE_KEY]
    occupied = {str(row['mail_id']) for row in candidate.mailbox} | set(ledger['issued'].values())
    from player_state import _mail_item_string
    for grant in due:
        rows = [dict(zip(('kind', 'id', 'count'), item)) for item in grant.items]
        if not rows or any(not candidate._can_credit(row) or not _mail_item_string([
                {'item_type': row['kind'], 'item_id': row['id'], 'count': row['count']}]) for row in rows):
            raise ValueError(f'The iOS gift {grant.key} has unsupported attachments; delivery was not recorded.')
        mid = ledger['next_id']
        while str(mid) in occupied:
            mid -= 1
        if mid <= policy.ID_BOTTOM:
            raise ValueError('The iOS reward inbox ID range is exhausted.')
        delivered = candidate.deliver_mail(grant.title, grant.items, mail_id=str(mid), message=grant.message,
            icon_type=2, attach_type=1, send_date=now.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))
        if delivered is None:
            raise ValueError(f'The iOS gift {grant.key} could not be delivered.')
        delivered['ios_reward_key'] = grant.key
        ledger['issued'][grant.key] = str(mid)
        ledger['next_id'] = mid - 1
        if grant.key.startswith('weekly:'):
            ledger['weekly_last'] = int(grant.key.split(':')[1])
        occupied.add(str(mid))
    if not candidate.save(str(state_file)):
        raise OSError('The iOS reward delivery could not be saved; the previous inbox is preserved.')
    player.data, player.dirty = candidate.data, candidate.dirty
    return True


def synchronize_for_reply(spec, reply_id, state, state_file, *, persist=True):
    if current_profile().replay is not None and reply_id in SYNC_REPLIES:
        if not persist:
            raise ValueError('iOS reward delivery requires state persistence.')
        synchronize(state, state_file)
    return spec


def receipt(spec, plaintext):
    from ffbe_state import State, STATE_FILE, STATE_PERSIST
    from ffbe_player import _serve_mail
    player = State.player
    policy.read_state(player.data)
    if player.mode == 'frozen':
        return _serve_mail(spec, 'XK7efER9', plaintext)
    if player.mode != 'live':
        return spec
    if not STATE_PERSIST:
        raise ValueError('iOS mail receipts require state persistence.')
    candidate = copy.deepcopy(player)
    State.player = candidate
    try:
        out = _serve_mail(spec, 'XK7efER9', plaintext)
    finally:
        State.player = player
    if candidate.data != player.data:
        if not candidate.save(STATE_FILE):
            raise OSError('The iOS mail receipt could not be saved; the previous inbox and inventory are preserved.')
        player.data, player.dirty = candidate.data, candidate.dirty
    return out
