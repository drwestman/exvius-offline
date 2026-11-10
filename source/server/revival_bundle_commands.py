"""Atomic iOS bundle purchases; source-priced contents bypass earned conversion."""
import copy

from replay_calendar import read_anchor


def purchase(spec, reply_id, plaintext):
    from ffbe_state import State, STATE_FILE, STATE_PERSIST
    from ffbe_player import _serve_lapis_shop
    player = State.player
    if player is None or player.mode != 'live' or read_anchor(player.data) is None:
        return spec
    if not STATE_PERSIST:
        raise ValueError('iOS purchases require state persistence.')
    candidate = copy.deepcopy(player)
    dirty = State.state_dirty
    State.player = candidate
    try:
        out = _serve_lapis_shop(spec, reply_id, plaintext)
    finally:
        State.player = player
        State.state_dirty = dirty
    if candidate.data != player.data:
        if not candidate.save(STATE_FILE):
            raise OSError('The iOS purchase could not be saved; the previous balance and stock are preserved.')
        player.data, player.dirty = candidate.data, candidate.dirty
    return out
