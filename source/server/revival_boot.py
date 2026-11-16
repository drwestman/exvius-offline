"""Explicit login/home receipts and a read-only early table projection."""
import hashlib
import json

TABLE = 'F_FUNCTION_MST'
LEDGER = 'ios_native_boot'


def step(spec, reply_id, plaintext, state):
    player = state.player
    prepared = getattr(state, 'native_tables', None)
    if player is None or prepared is None or not isinstance(spec, dict):
        return spec
    from engine_profile import current_profile
    if current_profile().name != 'ios-revival' or reply_id not in ('75fYdNxq', 'Daud71Hn', 'lEHBdOEf'):
        return spec
    try:
        req = json.JSONDecoder().raw_decode(plaintext or '{}')[0]
        row = (req.get('LhVz6aD2') or [{}])[0]
        user, device = str(row.get('9Tbns0eI') or ''), str(row.get('6e4ik6kA') or '')
    except (ValueError, AttributeError, IndexError, TypeError):
        return spec
    if not device or len(device) > 512 or user in ('', '0') or user != str(player.data['identity']['user_id']):
        return spec
    device = hashlib.sha256(device.encode()).hexdigest()
    entry = prepared.manifest.get('tables', {}).get(TABLE)
    if entry is None:
        return spec
    version = str(entry['version'])
    ledger = player.data.get(LEDGER) or {}
    if reply_id == 'lEHBdOEf':
        if (ledger.get('held') or {}).get(device) == version:
            return dict(spec, c1qYg84Q=[{'a4hXTIm0': TABLE, 'wM9AfX6I': version}])
        return spec
    if player.mode != 'live':
        return spec
    ledger = {key: dict(ledger.get(key) or {}) for key in ('pending', 'held')}
    if reply_id == '75fYdNxq':
        ledger['pending'][device] = version
    elif ledger['pending'].get(device) == version:
        ledger['held'][device] = version
        ledger['pending'].pop(device)
    for rows in ledger.values():
        while len(rows) > 8:
            rows.pop(next(iter(rows)))
    if ledger != player.data.get(LEDGER):
        player.data[LEDGER] = ledger
        player.dirty = True
        state.state_dirty = True
    return spec


def synchronize(spec, reply_id, plaintext, state, path, persist):
    from engine_profile import current_profile
    if reply_id in ('75fYdNxq', 'Daud71Hn') and not persist:
        return spec
    if (current_profile().name != 'ios-revival' or reply_id not in ('75fYdNxq', 'Daud71Hn')
            or not persist or state.player is None or state.player.mode != 'live'
            or getattr(state, 'native_tables', None) is None):
        return step(spec, reply_id, plaintext, state)
    from revival_battle_commands import settle
    return settle(state, path, lambda: step(spec, reply_id, plaintext, state))
