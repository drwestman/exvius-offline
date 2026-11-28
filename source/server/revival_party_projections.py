"""Read-only iOS party and equipment projections (CQRS query side).

This module performs zero state mutations and zero filesystem writes. Legacy
projections in ``player_state.py`` remain untouched; ``ios-revival`` delegates
action-scoped group filtering, per-deck ``UnitEquipResponse`` projection, and
inventory ownership count reconciliation here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from revival_party_domain import (
    default_materia_slots,
    is_untouched_starter_deck as _domain_is_untouched_starter_deck,
    normal_deck_order_key,
    owned_equipment_counts,
    owned_materia_counts,
    resolve_normal_deck_unit_loadouts,
)


@dataclass(frozen=True)
class ActionProjectionPolicy:
    """Reply-boundary policy declaring which clear-and-rebuild groups to omit."""

    reply_id: str
    suppress_all_player_groups: bool = False
    suppressed_tags: frozenset[str] = frozenset()


# Client clear-and-rebuild response tags split by domain so a sequential
# Manage Party exit chain (mRPo5n2j -> TS5Dx9aZ -> pB3st6Tg, or reverse)
# cannot wipe pending edits in the sibling domain before its request serializes.
_UNIT_AND_EQUIP_REBUILD_TAGS = frozenset({
    'B71MekS8',  # UserUnitInfoResponse
    'TJ9eL80N',  # UnitEquipResponse (normal party)
    'DW7uH6Mn',  # UnitEquipResponse (party type 7)
    'VE7KZ8CY',  # UnitEquipResponse (party type 8 / Dark Visions)
    'wc8vSHPS',  # UnitEquipResponse (party type 11 / Clash of Wills)
    'IqkX0gV1',  # UnitEquipResponse (Arena equipment list 2)
})

_PARTY_AND_BEAST_REBUILD_TAGS = frozenset({
    '5Eb0Rig6',  # UserPartyDeckInfoResponse (normal party)
    'fqTUI1z6',  # UserPartyDeckInfoResponse (party type 7)
    'GV7Ej6n0',  # UserPartyDeckInfoResponse (party type 8)
    'zeucwm6H',  # UserPartyDeckInfoResponse (party type 11)
    '49rQB3fP',  # UserBeastDeckInfoResponse (normal party)
    'REbh19u0',  # UserBeastDeckInfoResponse (party type 7)
    'qVX5Lab8',  # UserBeastDeckInfoResponse (party type 8)
    'g8ZuTVvQ',  # UserBeastDeckInfoResponse (party type 11)
    '8PEB5o7G',  # UserActualInfo (active deck)
})

IOS_ACTION_PROJECTIONS: dict[str, ActionProjectionPolicy] = {
    'mRPo5n2j': ActionProjectionPolicy(
        reply_id='mRPo5n2j',
        suppress_all_player_groups=True,
    ),
    'TS5Dx9aZ': ActionProjectionPolicy(
        reply_id='TS5Dx9aZ',
        suppressed_tags=_UNIT_AND_EQUIP_REBUILD_TAGS,
    ),
    'pB3st6Tg': ActionProjectionPolicy(
        reply_id='pB3st6Tg',
        suppressed_tags=_PARTY_AND_BEAST_REBUILD_TAGS,
    ),
}


def filter_reply_groups(reply_id, out: dict, groups: dict) -> dict:
    """Return a copy of ``out`` merged with ``groups`` under the action boundary policy."""
    result = dict(out)
    policy = IOS_ACTION_PROJECTIONS.get(str(reply_id))
    if policy is None:
        result.update(groups)
        return result
    if policy.suppress_all_player_groups:
        for tag in policy.suppressed_tags:
            result.pop(tag, None)
        return result
    for tag, rows in groups.items():
        if tag not in policy.suppressed_tags:
            result[tag] = rows
    for tag in policy.suppressed_tags:
        result.pop(tag, None)
    return result


def is_untouched_starter_deck(player, deck: dict) -> bool:
    """Read-only check for an unedited default starter-unit placeholder deck."""
    return _domain_is_untouched_starter_deck(player.data, deck)


def iter_normal_deck_unit_loadouts(
    player,
    deck: dict,
    roster_by_id: dict[str, dict],
) -> list[tuple[str, dict, bool]]:
    """Resolve ``(uid, saved_loadout, fallback_to_unit)`` pairs for one normal deck."""
    return [
        (uid, saved, fallback)
        for uid, saved, fallback, _is_member in resolve_normal_deck_unit_loadouts(
            player.data, deck, roster_by_id,
        )
    ]


def format_equip_row(
    unit: dict,
    saved: dict | None,
    deck_id,
    *,
    materia_slots_fn: Callable[[dict, bool], int] | None = None,
    fallback_to_unit: bool = True,
) -> dict:
    """Project one ``UnitEquipResponse`` wire row without mutating state."""
    slots_fn = materia_slots_fn or default_materia_slots
    saved = saved or {}
    src = (
        (lambda key, default=None: saved.get(key, unit.get(key, default)))
        if fallback_to_unit
        else (lambda key, default=None: saved.get(key, default))
    )
    equip = src('equipment') or {}
    has_shift = bool(
        src('shift_equipment') or src('shift_materia') or src('shift_vision_card')
    )
    slots = '@'.join(
        f"{slot}-{equip.get(str(slot), equip.get(slot, '0'))}"
        for slot in range(1, 7)
    )
    if has_shift:
        shift = src('shift_equipment') or {}
        slots += '|' + '@'.join(
            f"{n}-{shift.get(str(n), shift.get(n, '0'))}" for n in range(1, 7)
        )
    materia = src('materia') or []
    mat = '@'.join(
        f"{i + 1}-{materia[i] if i < len(materia) else '0'}"
        for i in range(slots_fn(unit, False))
    )
    if has_shift:
        shift_materia = src('shift_materia') or []
        mat += '|' + '@'.join(
            f"{i + 1}-{shift_materia[i] if i < len(shift_materia) else '0'}"
            for i in range(slots_fn(unit, True))
        )
    card = src('vision_card') or src('shift_vision_card') or '0-0'
    if not str(card).startswith('0-'):
        card = '0-' + str(card)
    row = {
        'og2GHy49': str(unit['instance_id']),
        'r21y0YzS': str(deck_id),
        '93Y6evuT': slots,
        '80NUYFMJ': mat,
        'nQ1iAGf3': card,
    }
    has_skin = ('skin_id' in saved) or (fallback_to_unit and 'skin_id' in unit)
    if has_skin:
        row['2c8nqLrM'] = str(saved.get('skin_id', unit.get('skin_id')))
    return row


def build_global_equip_rows(
    data: dict,
    party: dict | None = None,
    *,
    materia_slots_fn: Callable[[dict, bool], int] | None = None,
) -> list[dict]:
    """Project one global ``UnitEquipResponse`` row per roster unit."""
    normal_party = data.get('party') or {}
    target_party = normal_party if party is None else party
    saved_loadouts = (
        (target_party.get('loadouts') or {}) if target_party is not normal_party else {}
    )
    return [
        format_equip_row(
            unit,
            saved_loadouts.get(str(unit.get('instance_id'))) or {},
            target_party.get('active_deck', 0),
            materia_slots_fn=materia_slots_fn,
            fallback_to_unit=True,
        )
        for unit in (data.get('roster') or [])
    ]


class EquipmentProjectionStrategy(Protocol):
    """Strategy interface for projecting ``UnitEquipResponse`` rows."""

    def project(self, player, party=None) -> list[dict]:
        """Return read-only ``UnitEquipResponse`` rows for ``player``."""


class GlobalRosterEquipmentStrategy:
    """Track A strategy: project one global equipment row per roster unit."""

    def __init__(self, materia_slots_fn: Callable[[dict, bool], int] | None = None):
        self._materia_slots = materia_slots_fn

    def project(self, player, party=None) -> list[dict]:
        return build_global_equip_rows(
            player.data, party=party, materia_slots_fn=self._materia_slots,
        )


class PerDeckEquipmentStrategy:
    """Track B strategy: project ``UnitEquipResponse`` rows per ``(unit_id, deck_id)``."""

    def __init__(self, materia_slots_fn: Callable[[dict, bool], int] | None = None):
        self._materia_slots = materia_slots_fn

    def project(self, player, party=None) -> list[dict]:
        data = player.data
        normal_party = data.get('party') or {}
        if party is not None and party is not normal_party:
            return build_global_equip_rows(
                data, party=party, materia_slots_fn=self._materia_slots,
            )

        roster = data.get('roster') or []
        roster_by_id = {str(u.get('instance_id')): u for u in roster}
        decks = sorted(normal_party.get('decks') or [], key=normal_deck_order_key)
        rows: list[dict] = []
        covered_units: set[str] = set()

        for deck in decks:
            did = str(deck.get('id', ''))
            for uid, saved, fallback, _is_member in resolve_normal_deck_unit_loadouts(
                data, deck, roster_by_id,
            ):
                covered_units.add(uid)
                rows.append(
                    format_equip_row(
                        roster_by_id[uid],
                        saved,
                        did,
                        materia_slots_fn=self._materia_slots,
                        fallback_to_unit=fallback,
                    )
                )

        active_did = str(normal_party.get('active_deck', 0))
        for unit in roster:
            uid = str(unit.get('instance_id'))
            if uid not in covered_units:
                rows.append(
                    format_equip_row(
                        unit,
                        {},
                        active_did,
                        materia_slots_fn=self._materia_slots,
                        fallback_to_unit=True,
                    )
                )
        return rows


DEFAULT_EQUIPMENT_STRATEGY: EquipmentProjectionStrategy = PerDeckEquipmentStrategy()


def project_equip_rows(
    player,
    party=None,
    *,
    strategy: EquipmentProjectionStrategy = DEFAULT_EQUIPMENT_STRATEGY,
) -> list[dict]:
    """Project ``UnitEquipResponse`` rows read-only using the selected strategy."""
    return strategy.project(player, party=party)


def reconcile_equipped_counts(player) -> list[dict]:
    """Reconcile ``UserEquipItemInfoResponse`` (``MBPCGT84``) across per-deck loadouts."""
    order, counts = owned_equipment_counts(player.data)
    return [{'J1YX9kmM': iid, 'Qy5EvcK1': str(max(1, counts[iid]))} for iid in order]


def reconcile_materia_counts(player) -> list[dict]:
    """Reconcile ``UserMateriaInfoResponse`` (``rL81fVUI``) across per-deck loadouts."""
    order, counts = owned_materia_counts(player.data)
    return [{'H5jBL0Vf': iid, 'Qy5EvcK1': str(counts[iid])} for iid in order]
