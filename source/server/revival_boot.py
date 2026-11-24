"""Explicit login/home receipts and a read-only early table projection."""
from dataclasses import dataclass
import hashlib
import json
import os

TABLE = 'F_FUNCTION_MST'
FUNCTION_TABLE = TABLE
RESOURCE_CATALOG_TABLES = (
    'F_RESOURCE_MST',
    'F_RESOURCE_VERSION_MST_LOCALIZE',
    'F_RESOURCE_CHECKSUM_MST',
)
LEDGER = 'ios_native_boot'
EARLY_RESOURCE_CATALOG = True
EARLY_REPLY = 'lEHBdOEf'
COMMAND_REPLIES = ('75fYdNxq', 'Daud71Hn')
MAX_LEDGER_ENTRIES = 8


@dataclass(frozen=True)
class EarlyCatalogPolicy:
    """Adapter-resolved flag controlling Launch-1 early resource catalog projection."""

    early_resource_catalog: bool = True


def resolve_early_catalog_policy(override=None) -> EarlyCatalogPolicy:
    """Resolve EarlyCatalogPolicy once at the adapter edge."""
    if isinstance(override, EarlyCatalogPolicy):
        return override
    if override is not None:
        return EarlyCatalogPolicy(early_resource_catalog=bool(override))
    if not EARLY_RESOURCE_CATALOG:
        return EarlyCatalogPolicy(early_resource_catalog=False)
    return EarlyCatalogPolicy(
        early_resource_catalog=os.environ.get('FFBE_IOS_EARLY_RESOURCE_CATALOG', '1') != '0',
    )


def _extract_device_hash(plaintext: str | None, expected_user_id: str) -> str | None:
    if not expected_user_id or expected_user_id == '0':
        return None
    try:
        req = json.JSONDecoder().raw_decode(plaintext or '{}')[0]
        row = (req.get('LhVz6aD2') or [{}])[0]
        user, device = str(row.get('9Tbns0eI') or ''), str(row.get('6e4ik6kA') or '')
    except (ValueError, AttributeError, IndexError, TypeError):
        return None
    if not device or len(device) > 512 or user in ('', '0') or user != str(expected_user_id):
        return None
    return hashlib.sha256(device.encode()).hexdigest()


def _expected_user_id(player) -> str:
    data = getattr(player, 'data', None)
    identity = data.get('identity') if isinstance(data, dict) else None
    return str(identity.get('user_id') or '') if isinstance(identity, dict) else ''


def build_early_version_rows(
    tables,
    held_version: str | None,
    *,
    early_resource_catalog: bool,
) -> list[dict[str, str]]:
    """Pure projection of early c1qYg84Q version rows for an initialized device."""
    if held_version is None or not isinstance(tables, dict):
        return []
    rows: list[dict[str, str]] = []
    fn_entry = tables.get(FUNCTION_TABLE)
    if isinstance(fn_entry, dict) and fn_entry.get('version') is not None:
        fn_version = str(fn_entry['version'])
        if held_version == fn_version:
            rows.append({'a4hXTIm0': FUNCTION_TABLE, 'wM9AfX6I': fn_version})
    if early_resource_catalog:
        catalog_entries = [tables.get(name) for name in RESOURCE_CATALOG_TABLES]
        if all(isinstance(entry, dict) and entry.get('version') is not None for entry in catalog_entries):
            for name, entry in zip(RESOURCE_CATALOG_TABLES, catalog_entries):
                rows.append({'a4hXTIm0': name, 'wM9AfX6I': str(entry['version'])})
    return rows


def project_early_versions(spec, prepared, ledger, device_hash, *, early_resource_catalog=None):
    """Read-only projection for lEHBdOEf: merge receipt-matched and catalog version rows."""
    if not isinstance(spec, dict):
        return spec
    policy = resolve_early_catalog_policy(early_resource_catalog)
    tables = (getattr(prepared, 'manifest', None) or {}).get('tables', {})
    held_map = ledger.get('held') if isinstance(ledger, dict) else None
    held_version = held_map.get(device_hash) if isinstance(held_map, dict) else None
    rows = build_early_version_rows(
        tables,
        held_version,
        early_resource_catalog=policy.early_resource_catalog,
    )
    if not rows:
        return spec
    existing = spec.get('c1qYg84Q')
    if not isinstance(existing, list):
        return {**spec, 'c1qYg84Q': rows}
    projected = {row['a4hXTIm0']: row for row in rows}
    seen = set()
    merged = []
    for entry in existing:
        if isinstance(entry, dict) and entry.get('a4hXTIm0') in projected:
            name = entry['a4hXTIm0']
            if name not in seen:
                merged.append({**entry, **projected[name]})
                seen.add(name)
        else:
            merged.append(dict(entry) if isinstance(entry, dict) else entry)
    for row in rows:
        if row['a4hXTIm0'] not in seen:
            merged.append(row)
    return {**spec, 'c1qYg84Q': merged}


def project_for_reply(spec, reply_id, plaintext, state, *, early_resource_catalog=None):
    """Read-only pipeline entry point handling only lEHBdOEf early table projection."""
    if reply_id != EARLY_REPLY:
        return spec
    player = getattr(state, 'player', None)
    prepared = getattr(state, 'native_tables', None)
    if player is None or prepared is None or not isinstance(spec, dict):
        return spec
    from engine_profile import current_profile
    if current_profile().name != 'ios-revival':
        return spec
    device_hash = _extract_device_hash(plaintext, _expected_user_id(player))
    if device_hash is None:
        return spec
    data = getattr(player, 'data', None)
    ledger = (data.get(LEDGER) or {}) if isinstance(data, dict) else {}
    return project_early_versions(
        spec,
        prepared,
        ledger,
        device_hash,
        early_resource_catalog=early_resource_catalog,
    )


def _normalized_ledger(ledger) -> dict[str, dict[str, str]]:
    source = ledger if isinstance(ledger, dict) else {}
    return {
        key: dict(source[key]) if isinstance(source.get(key), dict) else {}
        for key in ('pending', 'held')
    }


def next_receipt_ledger(ledger, reply_id: str, device_hash: str, fn_version: str) -> dict:
    """Pure transition for ios_native_boot pending/held per-device receipts."""
    updated = _normalized_ledger(ledger)
    if reply_id == '75fYdNxq':
        updated['pending'][device_hash] = fn_version
    elif reply_id == 'Daud71Hn' and updated['pending'].get(device_hash) == fn_version:
        updated['held'][device_hash] = fn_version
        updated['pending'].pop(device_hash, None)
    for rows in updated.values():
        while len(rows) > MAX_LEDGER_ENTRIES:
            rows.pop(next(iter(rows)))
    return updated


def record_receipt(player, state, reply_id, device_hash, fn_version) -> bool:
    """Command-side receipt update on 75fYdNxq (pending) and Daud71Hn (held) for live players."""
    if player is None or player.mode != 'live' or reply_id not in COMMAND_REPLIES:
        return False
    current = player.data.get(LEDGER)
    baseline = _normalized_ledger(current)
    updated = next_receipt_ledger(current, reply_id, device_hash, fn_version)
    if updated == baseline:
        return False
    player.data[LEDGER] = updated
    player.dirty = True
    if state is not None:
        state.state_dirty = True
    return True


def _record_for_reply(spec, reply_id, plaintext, state):
    if reply_id not in COMMAND_REPLIES:
        return spec
    player = getattr(state, 'player', None)
    prepared = getattr(state, 'native_tables', None)
    if player is None or prepared is None or not isinstance(spec, dict):
        return spec
    from engine_profile import current_profile
    if current_profile().name != 'ios-revival':
        return spec
    device_hash = _extract_device_hash(plaintext, _expected_user_id(player))
    if device_hash is None:
        return spec
    tables = (getattr(prepared, 'manifest', None) or {}).get('tables', {})
    entry = tables.get(FUNCTION_TABLE)
    if not isinstance(entry, dict) or entry.get('version') is None:
        return spec
    record_receipt(player, state, reply_id, device_hash, str(entry['version']))
    return spec


def step(spec, reply_id, plaintext, state):
    """Backward-compatible facade routing lEHBdOEf queries vs 75fYdNxq/Daud71Hn commands."""
    if reply_id == EARLY_REPLY:
        return project_for_reply(spec, reply_id, plaintext, state)
    if reply_id in COMMAND_REPLIES:
        return _record_for_reply(spec, reply_id, plaintext, state)
    return spec


def synchronize(spec, reply_id, plaintext, state, path, persist):
    """Command-side pipeline step scoped exclusively to 75fYdNxq / Daud71Hn under atomic settle."""
    if reply_id not in COMMAND_REPLIES or not persist:
        return spec
    player = getattr(state, 'player', None)
    if player is None or player.mode != 'live' or getattr(state, 'native_tables', None) is None:
        return spec
    from engine_profile import current_profile
    if current_profile().name != 'ios-revival':
        return spec
    from revival_battle_commands import settle
    return settle(state, path, lambda: _record_for_reply(spec, reply_id, plaintext, state))
