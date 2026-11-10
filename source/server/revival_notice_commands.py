"""Explicit native read-receipt command, called under the canonical STATE_LOCK."""
import copy

import revival_notices as policy


def serve(spec, req, reply_id):
    from ffbe_state import State, STATE_FILE, STATE_PERSIST
    player = State.player
    policy.settings(player.data)
    now = policy.clock()
    if reply_id == 'CQ4jTm2F':
        spec = policy.add_rows(spec, player.data, now)
    if reply_id != 'pC3a2JWU' or player.mode != 'live':
        return policy.project(spec, player.data)
    if not STATE_PERSIST:
        raise ValueError('iOS notice receipts require state persistence.')
    saved_index, marked = policy.ledger(player.data)
    known = dict(saved_index)
    for payload in State.replies.values():
        known.update(policy.catalogue(payload))
    known.update(policy.catalogue(spec))
    rows = req.get('p4U2NosZ', []) if isinstance(req, dict) else []
    requested = set()
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict):
            requested.update(str(row.get('goAiX84L') or '').split(','))
    accepted = {}
    for nid in requested - marked:
        replay = policy.replay_identity(player.data, nid, now)
        if replay:
            accepted[nid] = replay
        elif policy._digits(nid) and len(nid) <= 6 and policy.NOTICE_ID_BASE <= int(nid) <= policy.NOTICE_ID_BASE + policy.MAX_INDEX:
            continue  # A stale captured replay row cannot open a future/disabled week.
        elif nid in known:
            accepted[nid] = known[nid]
    if accepted:
        candidate = copy.deepcopy(player)
        candidate.data['notices'] = dict(candidate.data.get('notices', {}),
            index={**saved_index, **accepted}, read=sorted(marked | accepted.keys()))
        candidate.dirty = True
        out = policy.project(spec, candidate.data)
        if not candidate.save(str(STATE_FILE)):
            raise OSError('The iOS notice receipt could not be saved; the previous read state is preserved.')
        player.data, player.dirty = candidate.data, candidate.dirty
        return out
    return policy.project(spec, player.data)
