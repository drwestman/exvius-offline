"""iOS normal-battle command boundary; invoke under the canonical STATE_LOCK."""
import copy


def settle(state, path, run):
    """Run the result pipeline with deferred saves, then publish one durable candidate."""
    player = state.player
    if player is None or player.mode != 'live':
        raise ValueError('iOS battle settlement requires live persistence.')
    candidate = copy.deepcopy(player)
    dirty_before = state.state_dirty
    state.player, state.state_dirty = candidate, False
    try:
        result = run()
    finally:
        state.player, state.state_dirty = player, dirty_before
    if candidate.data != player.data:
        if not candidate.save(str(path)):
            raise OSError('The iOS battle result could not be saved; the previous attempt is preserved.')
        player.data, player.dirty = candidate.data, candidate.dirty
        state.state_dirty = False
    return result
