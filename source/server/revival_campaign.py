"""Explicit first-gameplay initialization; no writes in replay projections.

The anchor and initialization marker share the canonical PlayerState atomic
save. Publish the candidate only after it saves successfully. Call under the
engine's existing STATE_LOCK (the CLI also takes an exclusive instance lock).
"""
import copy
from datetime import datetime, timezone

from engine_profile import current_profile
from replay_calendar import new_anchor, read_anchor


INITIALIZE_REPLY = '75fYdNxq'  # InitializeRequest, the first gameplay initialization.


def initialize_campaign(state, state_file, *, now=None, profile=None) -> bool:
    profile = profile or current_profile()
    if profile.replay is None:
        return False
    player = state.player
    if player is None:
        raise ValueError('A player must be loaded before campaign initialization.')
    anchored = read_anchor(player.data) is not None
    from revival_friends import settings as friend_settings, initialize as initialize_friends
    needs_friends = friend_settings(player.data) is None
    from player_state import _load_ndjson, switch_position
    from ffbe_config import SWITCH_TYPE_MISSION, SWITCH_BASE_INDICES
    vortex = _load_ndjson('F_FUNCTION_MST.ndjson', 'G1nfeht7').get('FUNCTION_REEL_DIMENSION', {})
    unlock = switch_position(vortex.get('juA0Z4m7'))
    needs_container = SWITCH_TYPE_MISSION not in player.switches
    needs_unlock = unlock is not None and unlock[1] not in player.switches.get(unlock[0], set())
    if anchored and not needs_container and not needs_unlock and not needs_friends:
        return False
    if player.mode != 'live':
        raise ValueError('iOS campaign initialization requires live persistence.')
    moment = now if now is not None else datetime.now(timezone.utc)
    candidate = copy.deepcopy(player)
    if not anchored:
        candidate.data['ios_revival'] = {'version': 1, 'replay': new_anchor(moment, profile.replay),
                                         'initialized_utc': moment.astimezone(timezone.utc).isoformat()}
    candidate.switches.setdefault(SWITCH_TYPE_MISSION, set(SWITCH_BASE_INDICES))
    if unlock:
        candidate.grant_switch(*unlock)
    initialize_friends(candidate.data)
    candidate.data.setdefault('meta', {})['engine_profile'] = profile.name
    candidate.dirty = True
    if not candidate.save(str(state_file)):
        raise OSError('The iOS campaign could not be initialized; the previous save is preserved.')
    state.player = candidate
    state.state_dirty = False
    return True


def initialize_for_reply(spec, reply_id, state, state_file, *, persist=True):
    if reply_id == INITIALIZE_REPLY and current_profile().replay is not None:
        if not persist:
            raise ValueError('The iOS campaign requires state persistence.')
        initialize_campaign(state, state_file)
    return spec
