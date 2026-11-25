"""Atomic iOS relationship commands using the canonical social state machine."""
import copy

from replay_calendar import read_anchor
from revival_friends import settings


def execute(spec, request, action, apply):
    from ffbe_state import State, STATE_FILE
    player = State.player
    if (player is None or player.mode != 'live' or read_anchor(player.data) is None or
            settings(player.data) is None):
        return dict(spec) if isinstance(spec, dict) else {}
    candidate = copy.deepcopy(player)
    State.player = candidate
    try:
        out = apply(spec, request, action)
    finally:
        State.player = player
    if candidate.data != player.data:
        if not candidate.save(STATE_FILE):
            raise OSError('The iOS friendship could not be saved; the previous relationship is preserved.')
        player.data, player.dirty = candidate.data, candidate.dirty
    return out
