"""Pure domain rules and ownership accounting for iOS per-deck party loadouts.

This module sits beneath both ``revival_party_commands`` (write side) and
``revival_party_projections`` (query side) so neither layer depends on the
other. It contains zero wire-token formatting, zero ``State`` globals, and zero
filesystem I/O.
"""
from __future__ import annotations

from collections import Counter
import copy
from typing import Callable


PARTY_KIND_MAP: dict[str, str] = {
    '1': '',
    '7': '7',
    '8': '8',
    '11': '11',
    '50': '11',
}

LOADOUT_FIELDS: tuple[str, ...] = (
    'equipment',
    'shift_equipment',
    'materia',
    'shift_materia',
    'vision_card',
    'shift_vision_card',
    'skin_id',
    'brave_shift',
)

SHIFT_LOADOUT_FIELDS: tuple[str, ...] = (
    'shift_equipment',
    'shift_materia',
    'shift_vision_card',
)

STARTER_MASTER_PAIR: frozenset[str] = frozenset({'100000102', '100000202'})


def default_materia_slots(unit: dict, shifted: bool = False) -> int:
    from player_state import unit_materia_slots
    return unit_materia_slots(unit, shifted=shifted)


def normal_deck_order_key(deck: dict) -> tuple[int, str]:
    """Deterministic sort key placing numeric deck IDs ``0..9`` in numerical order."""
    did = str(deck.get('id', ''))
    return (0, did.zfill(6)) if did.isdigit() else (1, did)


def is_untouched_starter_deck(data: dict, deck: dict) -> bool:
    """Return True if ``deck`` is an unedited default starter-unit placeholder deck.

    ``default_state`` populates decks 1..9 with the two starter units so no deck
    slot is empty. Excluding untouched placeholders keeps legacy-to-per-deck
    fallback/migration from cloning starter or Party 1 Rain/Lasswell gear onto
    unused decks 3..9.
    """
    party = data.get('party') or {}
    did = str(deck.get('id', ''))
    active_did = str(party.get('active_deck', 0))
    deck_loadouts = party.get('deck_loadouts') or {}
    if did == '0' or did == active_did or did in deck_loadouts:
        return False
    members = deck.get('members') or []
    if len(members) != 2:
        return False
    default_name = f'Party {int(did) + 1}' if did.isdigit() else ''
    if default_name and deck.get('name') != default_name:
        return False
    roster_by_id = {str(u.get('instance_id')): u for u in data.get('roster') or []}
    member_mids = {
        str((roster_by_id.get(str(m.get('instance_id'))) or {}).get('master_id', ''))
        for m in members
    }
    return member_mids == STARTER_MASTER_PAIR


def resolve_normal_deck_unit_loadouts(
    data: dict,
    deck: dict,
    roster_by_id: dict[str, dict],
) -> list[tuple[str, dict, bool, bool]]:
    """Resolve ``(uid, saved_loadout, fallback_to_unit, is_member)`` tuples for one normal deck."""
    party = data.get('party') or {}
    did = str(deck.get('id', ''))
    deck_loadouts = party.get('deck_loadouts')
    has_per_deck_state = isinstance(deck_loadouts, dict)
    per_deck = (deck_loadouts.get(did) or {}) if has_per_deck_state else {}

    member_ids = [
        str(m.get('instance_id'))
        for m in (deck.get('members') or [])
        if str(m.get('instance_id')) in roster_by_id
    ]
    seen = set(member_ids)
    extra_ids = [uid for uid in per_deck if uid in roster_by_id and uid not in seen]

    untouched_starter = (not has_per_deck_state) and is_untouched_starter_deck(data, deck)
    resolved: list[tuple[str, dict, bool, bool]] = []
    for uid, is_member in [(uid, True) for uid in member_ids] + [(uid, False) for uid in extra_ids]:
        if has_per_deck_state:
            saved = per_deck.get(uid)
            resolved.append((uid, saved if isinstance(saved, dict) else {}, False, is_member))
        elif untouched_starter:
            resolved.append((uid, {}, False, is_member))
        else:
            resolved.append((uid, {}, True, is_member))
    return resolved


def _unit_combined_item_counts(
    unit: dict,
    saved: dict,
    normal_key: str,
    shift_key: str,
    *,
    is_dict: bool,
    fallback: bool,
) -> Counter[str]:
    """Count items worn by one unit, sharing copies between normal and shift forms."""
    base_vals = saved.get(normal_key, unit.get(normal_key)) if fallback else saved.get(normal_key)
    shift_vals = saved.get(shift_key, unit.get(shift_key)) if fallback else saved.get(shift_key)
    base_iter = (base_vals or {}).values() if is_dict else (base_vals or [])
    shift_iter = (shift_vals or {}).values() if is_dict else (shift_vals or [])
    combined = Counter(str(v) for v in base_iter) | Counter(str(v) for v in shift_iter)
    return Counter({iid: qty for iid, qty in combined.items() if iid and iid != '0' and qty > 0})


def compute_worn_item_counts(
    data: dict,
    normal_key: str,
    shift_key: str,
    *,
    is_dict: bool,
) -> tuple[Counter[str], list[str], Counter[str]]:
    """Compute simultaneous worn copies across normal decks plus untracked roster copies.

    Only actual ``deck['members']`` are summed together as simultaneous wearers in
    a deck. Non-member ``extra_ids`` retained in ``deck_loadouts[did]`` (e.g., a
    unit swapped out of a party without clearing its slots) contribute at most
    their own per-unit count so swapping members cannot mint phantom duplicates.
    """
    party = data.get('party') or {}
    roster = data.get('roster') or []
    roster_by_id = {str(u.get('instance_id')): u for u in roster}
    deck_loadouts = party.get('deck_loadouts') or {}

    max_per_deck: Counter[str] = Counter()
    max_extra: Counter[str] = Counter()
    order: list[str] = []
    seen: set[str] = set()
    governed_units: set[str] = {
        str(uid)
        for entries in (deck_loadouts.values() if isinstance(deck_loadouts, dict) else ())
        if isinstance(entries, dict)
        for uid in entries
    }

    for deck in sorted(party.get('decks') or [], key=normal_deck_order_key):
        deck_counts: Counter[str] = Counter()
        for uid, saved, fallback, is_member in resolve_normal_deck_unit_loadouts(data, deck, roster_by_id):
            governed_units.add(uid)
            combined = _unit_combined_item_counts(
                roster_by_id[uid], saved, normal_key, shift_key, is_dict=is_dict, fallback=fallback,
            )
            for item_id, qty in combined.items():
                if item_id not in seen:
                    seen.add(item_id)
                    order.append(item_id)
                if is_member:
                    deck_counts[item_id] += qty
                elif qty > max_extra[item_id]:
                    max_extra[item_id] = qty
        for item_id, qty in deck_counts.items():
            if qty > max_per_deck[item_id]:
                max_per_deck[item_id] = qty

    simultaneous: Counter[str] = Counter()
    for item_id in seen:
        simultaneous[item_id] = max(max_per_deck[item_id], max_extra[item_id])

    untracked_roster: Counter[str] = Counter()
    for unit in roster:
        uid = str(unit.get('instance_id'))
        if uid in governed_units:
            continue
        combined = _unit_combined_item_counts(
            unit, {}, normal_key, shift_key, is_dict=is_dict, fallback=True,
        )
        for item_id, qty in combined.items():
            untracked_roster[item_id] += qty
            if item_id not in seen:
                seen.add(item_id)
                order.append(item_id)

    return simultaneous, order, untracked_roster


def owned_equipment_counts(data: dict) -> tuple[list[str], dict[str, int]]:
    """Compute authoritative equipment ownership counts from state + worn loadouts."""
    party = data.get('party') or {}
    if isinstance(party.get('deck_loadouts'), dict):
        simultaneous, order, untracked = compute_worn_item_counts(
            data, 'equipment', 'shift_equipment', is_dict=True,
        )
        counts: dict[str, int] = {
            iid: max(1, simultaneous[iid] + untracked[iid])
            for iid in order
        }
    else:
        counts = {}
        order = []
        for unit in data.get('roster') or []:
            combined = _unit_combined_item_counts(
                unit, {}, 'equipment', 'shift_equipment', is_dict=True, fallback=True,
            )
            for iid, qty in combined.items():
                if iid not in counts:
                    order.append(iid)
                    counts[iid] = 0
                counts[iid] += qty
    for it in (data.get('inventory') or {}).get('equipment') or []:
        iid = str(it.get('item_id', ''))
        qty = int(it.get('count', 0) or 0)
        if iid and qty > 0:
            if iid not in counts:
                order.append(iid)
                counts[iid] = 0
            counts[iid] = max(counts[iid], qty)
    return order, counts


def owned_materia_counts(data: dict) -> tuple[list[str], dict[str, int]]:
    """Compute authoritative materia ownership counts from inventory + worn loadouts."""
    order: list[str] = []
    counts: dict[str, int] = {}
    for it in (data.get('inventory') or {}).get('items') or []:
        if str(it.get('item_type')) == '22':
            iid = str(it.get('item_id', ''))
            qty = int(it.get('count', 0) or 0)
            if iid and qty > 0:
                if iid not in counts:
                    order.append(iid)
                    counts[iid] = 0
                counts[iid] = max(counts[iid], qty)
    party = data.get('party') or {}
    if isinstance(party.get('deck_loadouts'), dict):
        simultaneous, extra_order, untracked = compute_worn_item_counts(
            data, 'materia', 'shift_materia', is_dict=False,
        )
        for iid in extra_order:
            needed = simultaneous[iid] + untracked[iid]
            if needed > counts.get(iid, 0):
                if iid not in counts:
                    order.append(iid)
                counts[iid] = needed
    return order, counts


def owned_vision_card_ids(data: dict) -> set[str]:
    """Return all owned user vision-card instance IDs."""
    return {str(card['user_vc_id']) for card in (data.get('vision_cards') or [])}


def worn_counts_for_sale(data: dict) -> tuple[Counter[str], Counter[str]]:
    """Return simultaneous worn equipment and materia counts across normal decks."""
    sim_eq, _ord_e, untracked_eq = compute_worn_item_counts(
        data, 'equipment', 'shift_equipment', is_dict=True,
    )
    sim_mat, _ord_m, untracked_mat = compute_worn_item_counts(
        data, 'materia', 'shift_materia', is_dict=False,
    )
    return sim_eq + untracked_eq, sim_mat + untracked_mat


def snapshot_unit_loadout(unit: dict) -> dict:
    """Copy persisted loadout fields from a roster unit dict."""
    return {
        field: copy.deepcopy(unit[field])
        for field in LOADOUT_FIELDS
        if field in unit
    }


def ensure_deck_loadouts_initialized(data: dict, roster: dict[str, dict]) -> dict[str, dict]:
    """Migrate pre-Track-B normal deck loadouts from ``roster`` on first per-deck write."""
    party = data['party']
    existing = party.get('deck_loadouts')
    if isinstance(existing, dict):
        return existing

    deck_loadouts: dict[str, dict] = {}
    for deck in party.get('decks') or []:
        did = str(deck.get('id', ''))
        if not did or is_untouched_starter_deck(data, deck):
            continue
        entries: dict[str, dict] = {}
        for member in deck.get('members') or []:
            uid = str(member.get('instance_id', ''))
            unit = roster.get(uid)
            if unit is not None:
                entries[uid] = snapshot_unit_loadout(unit)
        deck_loadouts[did] = entries
    party['deck_loadouts'] = deck_loadouts
    return deck_loadouts


def sync_active_deck_to_roster(
    data: dict,
    *,
    materia_slots_fn: Callable[[dict, bool], int] | None = None,
) -> None:
    """Mirror the currently active normal deck's loadouts onto ``roster`` for battle/Arena.

    Every unit in ``active_deck`` (or in ``deck_loadouts[active_deck]``) is
    synchronized completely so absent fields in the newly active deck do not
    retain stale gear, materia, vision cards, skins, or Brave Shift flags from
    a previously active deck.
    """
    party = data.get('party') or {}
    deck_loadouts = party.get('deck_loadouts')
    if not isinstance(deck_loadouts, dict):
        return

    active_did = str(party.get('active_deck', 0))
    active_deck = next(
        (d for d in (party.get('decks') or []) if str(d.get('id')) == active_did),
        None,
    )
    active_member_ids = {
        str(m.get('instance_id'))
        for m in (active_deck or {}).get('members') or []
        if m.get('instance_id') is not None
    }
    raw_active_map = deck_loadouts.get(active_did)
    active_map = raw_active_map if isinstance(raw_active_map, dict) else {}
    sync_ids = active_member_ids | {str(uid) for uid in active_map}
    if not sync_ids:
        return

    slots_fn = materia_slots_fn or default_materia_slots
    roster = {str(unit['instance_id']): unit for unit in (data.get('roster') or [])}
    for uid in sync_ids:
        unit = roster.get(uid)
        if unit is None:
            continue
        raw_saved = active_map.get(uid)
        saved = raw_saved if isinstance(raw_saved, dict) else {}
        unit['equipment'] = copy.deepcopy(saved['equipment']) if 'equipment' in saved else {}
        if 'materia' in saved:
            unit['materia'] = copy.deepcopy(saved['materia'])
        else:
            unit['materia'] = ['0'] * slots_fn(unit, False)
        unit['vision_card'] = copy.deepcopy(saved['vision_card']) if 'vision_card' in saved else ''
        unit['brave_shift'] = int(saved['brave_shift']) if 'brave_shift' in saved else 0
        if 'skin_id' in saved:
            unit['skin_id'] = copy.deepcopy(saved['skin_id'])
        else:
            unit.pop('skin_id', None)
        for key in SHIFT_LOADOUT_FIELDS:
            if key in saved:
                unit[key] = copy.deepcopy(saved[key])
            else:
                unit.pop(key, None)
