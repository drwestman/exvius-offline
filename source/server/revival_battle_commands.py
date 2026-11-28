"""iOS normal-battle command boundary; invoke under the canonical STATE_LOCK."""
from contextvars import ContextVar
import copy

_IN_TRANSACTION: ContextVar[bool] = ContextVar('revival_in_transaction', default=False)


def in_transaction() -> bool:
    """Return True while executing inside an active ``settle`` transaction."""
    return _IN_TRANSACTION.get()


def settle(state, path, run):
    """Run the result pipeline with deferred saves, then publish one durable candidate."""
    player = state.player
    if player is None or player.mode != 'live':
        raise ValueError('iOS battle settlement requires live persistence.')
    candidate = copy.deepcopy(player)
    dirty_before = state.state_dirty
    state.player, state.state_dirty = candidate, False
    token = _IN_TRANSACTION.set(True)
    try:
        result = run()
    finally:
        _IN_TRANSACTION.reset(token)
        state.player, state.state_dirty = player, dirty_before
    if candidate.data != player.data:
        if not candidate.save(str(path)):
            raise OSError('The iOS battle result could not be saved; the previous attempt is preserved.')
        player.data, player.dirty = candidate.data, candidate.dirty
        state.state_dirty = False
    return result
