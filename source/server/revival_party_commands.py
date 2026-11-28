"""iOS Manage Party & Unit Equipment commands (CQRS write side).

Handles ``PartyDeckEditRequest`` (``TS5Dx9aZ``) and ``UnitEquipRequest``
(``pB3st6Tg``) for ``ios-revival``. Validated mutations stage against a
deep-copied candidate before replacing player state; pipeline-level
``revival_battle_commands.settle`` owns durable save/rollback.
"""
from __future__ import annotations

from collections import Counter
import copy
from dataclasses import dataclass
import json
import re
from typing import Callable, Iterator, Protocol

from ffbe_config import PARTY_DECK_GROUP
from revival_party_domain import (
    PARTY_KIND_MAP,
    default_materia_slots,
    ensure_deck_loadouts_initialized,
    owned_equipment_counts,
    owned_materia_counts,
    owned_vision_card_ids,
    sync_active_deck_to_roster,
)

_SLOT_TOKEN_SPECS: tuple[tuple[str, tuple[str, str], int | None, bool], ...] = (
    ('93Y6evuT', ('equipment', 'shift_equipment'), 6, True),
    ('80NUYFMJ', ('materia', 'shift_materia'), None, False),
)

_SCALAR_TOKEN_SPECS: tuple[tuple[str, str, bool], ...] = (
    ('w1JG7i9j', 'brave_shift', True),
    ('2c8nqLrM', 'skin_id', False),
)

_VISION_CARD_TOKEN = 'nQ1iAGf3'
_LOADOUT_TOKENS: tuple[str, ...] = (
    '93Y6evuT',
    '80NUYFMJ',
    'w1JG7i9j',
    '2c8nqLrM',
    _VISION_CARD_TOKEN,
)


@dataclass(frozen=True)
class DeckEquipSegment:
    """Decoded unit loadout delta for one party kind and one deck ID."""

    party_kind: str
    deck_id: str
    unit_loadouts: dict[str, dict]


@dataclass(frozen=True)
class ParsedEquipBatch:
    """Result of parsing an ``Er92Kdhm`` batch, including skipped-row warnings."""

    segments: tuple[DeckEquipSegment, ...]
    warnings: tuple[str, ...]


class EquipValidationError(ValueError):
    """Structured parse or ownership refusal identifying the exact offending field."""

    def __init__(self, party_kind: str, deck_id: str, iid: str, field: str, reason: str):
        self.party_kind = party_kind
        self.deck_id = deck_id
        self.iid = iid
        self.field = field
        self.reason = reason
        super().__init__(
            f"unit-equip: invalid {field} "
            f"(party_type={party_kind or '1'}, deck={deck_id}, unit={iid}): {reason}"
        )


def retain_owned_equipment(player) -> dict[str, int]:
    """Ensure starter gear inferred from worn slots exists in ``inventory.equipment``."""
    order, counts = owned_equipment_counts(player.data)
    equipment = player.data.setdefault('inventory', {}).setdefault('equipment', [])
    by_id = {str(entry['item_id']): entry for entry in equipment}
    for iid in order:
        count = int(counts[iid])
        if count <= 0:
            continue
        if iid in by_id:
            by_id[iid]['count'] = max(int(by_id[iid].get('count', 0)), count)
        else:
            entry = {'item_id': int(iid), 'count': count}
            equipment.append(entry)
            by_id[iid] = entry
    return counts


def _read_party_view(player, party_kind: str) -> tuple[str, set[str]]:
    """Read active deck ID and valid deck IDs without creating missing special blocks."""
    base = player.data['party']
    party = (base.get('special', {}).get(party_kind) or base) if party_kind else base
    decks = {str(d.get('id')) for d in party.get('decks') or [] if d.get('id') is not None}
    return str(party.get('active_deck', 0)), decks


def _iter_unit_entries(
    segment: str,
    token: str,
    party_kind: str,
    deck_id: str,
    roster: dict[str, dict],
) -> Iterator[tuple[str, str, dict]]:
    """Yield validated ``(iid, raw_value, unit)`` triples from one deck segment."""
    for entry in filter(None, segment.split(',')):
        if ':' not in entry:
            raise EquipValidationError(party_kind, deck_id, entry, token, "missing ':' separator")
        iid, raw = entry.split(':', 1)
        unit = roster.get(iid)
        if unit is None:
            raise EquipValidationError(party_kind, deck_id, iid, token, 'unit is not in roster')
        yield iid, raw, unit


class WireLoadoutParser(Protocol):
    """Parser contract turning raw ``Er92Kdhm`` wire rows into typed segments."""

    def parse_rows(self, rows: list, player, roster: dict[str, dict]) -> ParsedEquipBatch:
        """Decode ``rows`` against ``player`` and ``roster``."""


class LoadoutValidator(Protocol):
    """Validator contract enforcing ownership invariants on decoded loadout segments."""

    def validate(self, player, segments: tuple[DeckEquipSegment, ...]) -> None:
        """Raise ``EquipValidationError`` if ``segments`` violate ownership."""


class EquipmentLoadoutStore(Protocol):
    """Persistence strategy interface for validated unit equipment segments."""

    def apply(
        self,
        player,
        segments: tuple[DeckEquipSegment, ...],
        *,
        on_materia_equipped: Callable[[], None] | None = None,
    ) -> list[str]:
        """Apply validated loadout updates onto ``player`` and return summary labels."""


class MultiDeckWireLoadoutParser:
    """Parses ``Er92Kdhm`` rows supporting ``;``-delimited multi-deck payloads."""

    def __init__(self, materia_slots_fn: Callable[[dict, bool], int] | None = None):
        self._materia_slots = materia_slots_fn or default_materia_slots

    def parse_rows(self, rows: list, player, roster: dict[str, dict]) -> ParsedEquipBatch:
        segments: list[DeckEquipSegment] = []
        warnings: list[str] = []
        for row in rows:
            row_segments, warning = self._parse_row(row, player, roster)
            if warning:
                warnings.append(warning)
            segments.extend(row_segments)
        return ParsedEquipBatch(segments=tuple(segments), warnings=tuple(warnings))

    def _parse_row(
        self,
        row: object,
        player,
        roster: dict[str, dict],
    ) -> tuple[list[DeckEquipSegment], str | None]:
        if not isinstance(row, dict):
            raise EquipValidationError('?', '?', '?', 'Er92Kdhm', 'row is not an object')
        wire_kind = str(row.get('xBi3L6yR', '1'))
        party_kind = PARTY_KIND_MAP.get(wire_kind)
        if party_kind is None:
            return (
                [],
                f"unit-equip: skipped unsupported party type xBi3L6yR={wire_kind!r} "
                f"r21y0YzS={row.get('r21y0YzS')!r}",
            )
        active_deck, valid_decks = _read_party_view(player, party_kind)
        deck_ids = self._parse_deck_ids(row.get('r21y0YzS'), active_deck, valid_decks, party_kind)
        split_fields = self._split_fields(row, deck_ids, party_kind)
        segments: list[DeckEquipSegment] = []
        for idx, deck_id in enumerate(deck_ids):
            loadouts: dict[str, dict] = {}
            for token, fields, fixed_cap, as_dict in _SLOT_TOKEN_SPECS:
                segs = split_fields[token]
                if idx < len(segs) and segs[idx]:
                    self._parse_slot_segment(
                        segs[idx], token, fields, fixed_cap, as_dict,
                        party_kind, deck_id, roster, loadouts,
                    )
            for token, field, binary_only in _SCALAR_TOKEN_SPECS:
                segs = split_fields[token]
                if idx < len(segs) and segs[idx]:
                    self._parse_scalar_segment(
                        segs[idx], token, field, binary_only,
                        party_kind, deck_id, roster, loadouts,
                    )
            vc_segs = split_fields[_VISION_CARD_TOKEN]
            if idx < len(vc_segs) and vc_segs[idx]:
                self._parse_vision_card_segment(
                    vc_segs[idx], party_kind, deck_id, roster, loadouts,
                )
            segments.append(DeckEquipSegment(
                party_kind=party_kind,
                deck_id=deck_id,
                unit_loadouts=loadouts,
            ))
        return segments, None

    @staticmethod
    def _parse_deck_ids(
        raw_decks: object,
        active_deck: str,
        valid_decks: set[str],
        party_kind: str,
    ) -> list[str]:
        if raw_decks in (None, ''):
            return [active_deck]
        if not isinstance(raw_decks, str):
            raise EquipValidationError(
                party_kind, str(raw_decks), '-', 'r21y0YzS',
                f'expected string, got {type(raw_decks).__name__}',
            )
        deck_ids = raw_decks.split(';')
        for did in deck_ids:
            if not did.isdigit() or did not in valid_decks:
                raise EquipValidationError(
                    party_kind, raw_decks, '-', 'r21y0YzS',
                    f'unknown or invalid deck id {did!r}',
                )
        return deck_ids

    @staticmethod
    def _split_fields(row: dict, deck_ids: list[str], party_kind: str) -> dict[str, list[str]]:
        deck_label = ';'.join(deck_ids)
        split_fields: dict[str, list[str]] = {}
        for token in _LOADOUT_TOKENS:
            raw_val = row.get(token)
            if raw_val in (None, ''):
                split_fields[token] = []
                continue
            if not isinstance(raw_val, str):
                raise EquipValidationError(
                    party_kind, deck_label, '-', token,
                    f'expected string, got {type(raw_val).__name__}',
                )
            segments = raw_val.split(';')
            if len(segments) > len(deck_ids):
                raise EquipValidationError(
                    party_kind, deck_label, '-', token,
                    f'segment count {len(segments)} exceeds deck count {len(deck_ids)}',
                )
            split_fields[token] = segments
        return split_fields

    def _parse_slot_segment(
        self,
        segment: str,
        token: str,
        fields: tuple[str, str],
        fixed_cap: int | None,
        as_dict: bool,
        party_kind: str,
        deck_id: str,
        roster: dict[str, dict],
        loadouts: dict[str, dict],
    ) -> None:
        for iid, raw, unit in _iter_unit_entries(segment, token, party_kind, deck_id, roster):
            forms = raw.split('|')
            if len(forms) > 2:
                raise EquipValidationError(party_kind, deck_id, iid, token, 'too many unit forms')
            for field, form in zip(fields, forms):
                capacity = (
                    fixed_cap
                    if fixed_cap is not None
                    else self._materia_slots(unit, field == 'shift_materia')
                )
                values = {str(n): '0' for n in range(1, capacity + 1)}
                seen: set[str] = set()
                for pair in filter(None, form.split('@')):
                    if '-' not in pair:
                        raise EquipValidationError(
                            party_kind, deck_id, iid, token, f'invalid slot pair {pair!r}',
                        )
                    position, item = pair.split('-', 1)
                    if position not in values:
                        raise EquipValidationError(
                            party_kind, deck_id, iid, token,
                            f'slot {position!r} out of range 1..{capacity}',
                        )
                    if position in seen:
                        raise EquipValidationError(
                            party_kind, deck_id, iid, token, f'duplicate slot {position!r}',
                        )
                    if not item.isdigit():
                        raise EquipValidationError(
                            party_kind, deck_id, iid, token, f'non-numeric item id {item!r}',
                        )
                    seen.add(position)
                    values[position] = item
                loadouts.setdefault(iid, {})[field] = values if as_dict else list(values.values())

    @staticmethod
    def _parse_scalar_segment(
        segment: str,
        token: str,
        field: str,
        binary_only: bool,
        party_kind: str,
        deck_id: str,
        roster: dict[str, dict],
        loadouts: dict[str, dict],
    ) -> None:
        for iid, value, _unit in _iter_unit_entries(segment, token, party_kind, deck_id, roster):
            if not value.isdigit() or (binary_only and int(value) not in (0, 1)):
                raise EquipValidationError(
                    party_kind, deck_id, iid, token, f'invalid value {value!r}',
                )
            loadouts.setdefault(iid, {})[field] = int(value)

    @staticmethod
    def _parse_vision_card_segment(
        segment: str,
        party_kind: str,
        deck_id: str,
        roster: dict[str, dict],
        loadouts: dict[str, dict],
    ) -> None:
        for iid, raw, _unit in _iter_unit_entries(
            segment, _VISION_CARD_TOKEN, party_kind, deck_id, roster,
        ):
            forms = raw.split('|')
            if len(forms) > 2 or any(not re.fullmatch(r'[0-9-]+', value) for value in forms):
                raise EquipValidationError(
                    party_kind, deck_id, iid, _VISION_CARD_TOKEN, f'invalid vision card {raw!r}',
                )
            for field, card in zip(('vision_card', 'shift_vision_card'), forms):
                loadouts.setdefault(iid, {})[field] = '' if card in ('0', '0-0') else card


class OwnershipValidator:
    """Read-only ownership validator for decoded equipment, materia, and vision cards."""

    @staticmethod
    def validate(player, segments: tuple[DeckEquipSegment, ...]) -> None:
        _, gear = owned_equipment_counts(player.data)
        _, materia = owned_materia_counts(player.data)
        cards = owned_vision_card_ids(player.data)
        for segment in segments:
            for iid, fields in segment.unit_loadouts.items():
                for field, values in fields.items():
                    if field in ('equipment', 'shift_equipment', 'materia', 'shift_materia'):
                        owned = materia if 'materia' in field else gear
                        counts = Counter(values if 'materia' in field else values.values())
                        for item, count in counts.items():
                            if item != '0' and count > owned.get(item, 0):
                                raise EquipValidationError(
                                    segment.party_kind,
                                    segment.deck_id,
                                    iid,
                                    field,
                                    f'unowned or insufficient item {item} '
                                    f'(need {count}, owned {owned.get(item, 0)})',
                                )
                    elif field in ('vision_card', 'shift_vision_card') and values:
                        ids = {part for part in values.split('-') if part not in ('', '0')}
                        if ids and not ids.intersection(cards):
                            raise EquipValidationError(
                                segment.party_kind,
                                segment.deck_id,
                                iid,
                                field,
                                f'unowned vision card {values!r}',
                            )


class GlobalRosterLoadoutStore:
    """Track A store: normal party loadouts live on roster units; special modes use party overrides."""

    def apply(
        self,
        player,
        segments: tuple[DeckEquipSegment, ...],
        *,
        on_materia_equipped: Callable[[], None] | None = None,
    ) -> list[str]:
        roster = {str(unit['instance_id']): unit for unit in player.data['roster']}
        normal_loadouts: dict[str, dict] = {}
        special_loadouts: dict[str, dict[str, dict]] = {}
        for segment in segments:
            target = (
                normal_loadouts
                if segment.party_kind == ''
                else special_loadouts.setdefault(segment.party_kind, {})
            )
            for iid, fields in segment.unit_loadouts.items():
                target.setdefault(iid, {}).update(fields)

        applied: list[str] = []
        if any(
            any(roster[iid].get(key) != value for key, value in fields.items())
            for iid, fields in normal_loadouts.items()
        ):
            retain_owned_equipment(player)
            for iid, fields in normal_loadouts.items():
                _notify_materia_equipped(roster[iid], fields, on_materia_equipped)
                roster[iid].update(copy.deepcopy(fields))
            player._mutate()
            applied.append(f'normal:{len(normal_loadouts)}')

        applied.extend(
            _apply_special_loadouts(
                player, roster, special_loadouts, on_materia_equipped=on_materia_equipped,
            )
        )
        return applied


def _notify_materia_equipped(
    current: dict,
    fields: dict,
    on_materia_equipped: Callable[[], None] | None,
) -> None:
    if on_materia_equipped is None:
        return
    for field in ('materia', 'shift_materia'):
        if (
            field in fields
            and fields[field] != current.get(field)
            and any(item != '0' for item in fields[field])
        ):
            on_materia_equipped()


def _apply_special_loadouts(
    player,
    roster: dict[str, dict],
    special_loadouts: dict[str, dict[str, dict]],
    *,
    on_materia_equipped: Callable[[], None] | None = None,
) -> list[str]:
    del on_materia_equipped  # Quest action 13 triggers on normal party materia edits.
    applied: list[str] = []
    special_map = player.data.get('party', {}).get('special', {})
    for party_kind, changes in special_loadouts.items():
        existing = special_map.get(party_kind) or {}
        stored_existing = existing.get('loadouts') or {}
        changed_units = [
            (iid, fields)
            for iid, fields in changes.items()
            if any(
                {**roster[iid], **stored_existing.get(iid, {})}.get(k) != v
                for k, v in fields.items()
            )
        ]
        if not changed_units:
            continue
        party = player.special_party(party_kind)
        stored = party.setdefault('loadouts', {})
        for iid, fields in changed_units:
            stored.setdefault(iid, {}).update(copy.deepcopy(fields))
        player._mutate()
        applied.append(f'special-{party_kind}:{len(changed_units)}')
    return applied


def _current_normal_unit_loadout(player, deck_id: str, unit: dict) -> dict:
    party = player.data.get('party') or {}
    deck_loadouts = party.get('deck_loadouts')
    if isinstance(deck_loadouts, dict):
        saved = (deck_loadouts.get(deck_id) or {}).get(str(unit['instance_id']))
        return saved if isinstance(saved, dict) else {}
    return unit


class PerDeckLoadoutStore:
    """Track B store: normal loadouts live per ``(deck_id, iid)`` under ``party.deck_loadouts``."""

    def __init__(self, materia_slots_fn: Callable[[dict, bool], int] | None = None):
        self._materia_slots = materia_slots_fn

    def apply(
        self,
        player,
        segments: tuple[DeckEquipSegment, ...],
        *,
        on_materia_equipped: Callable[[], None] | None = None,
    ) -> list[str]:
        roster = {str(unit['instance_id']): unit for unit in player.data['roster']}
        normal_segments = [seg for seg in segments if seg.party_kind == '']
        special_loadouts: dict[str, dict[str, dict]] = {}
        for seg in segments:
            if seg.party_kind != '':
                target = special_loadouts.setdefault(seg.party_kind, {})
                for iid, fields in seg.unit_loadouts.items():
                    target.setdefault(iid, {}).update(fields)

        applied: list[str] = []
        changed_normal = [
            seg
            for seg in normal_segments
            if any(
                any(
                    _current_normal_unit_loadout(player, seg.deck_id, roster[iid]).get(k) != v
                    for k, v in fields.items()
                )
                for iid, fields in seg.unit_loadouts.items()
            )
        ]
        if changed_normal:
            retain_owned_equipment(player)
            deck_loadouts = ensure_deck_loadouts_initialized(player.data, roster)
            changed_decks: list[str] = []
            for seg in changed_normal:
                deck_map = deck_loadouts.setdefault(seg.deck_id, {})
                for iid, fields in seg.unit_loadouts.items():
                    entry = deck_map.setdefault(iid, {})
                    _notify_materia_equipped(entry, fields, on_materia_equipped)
                    entry.update(copy.deepcopy(fields))
                if seg.deck_id not in changed_decks:
                    changed_decks.append(seg.deck_id)
            sync_active_deck_to_roster(player.data, materia_slots_fn=self._materia_slots)
            player._mutate()
            applied.append(f'normal:{len(changed_decks)}decks')

        applied.extend(
            _apply_special_loadouts(
                player, roster, special_loadouts, on_materia_equipped=on_materia_equipped,
            )
        )
        return applied


DEFAULT_LOADOUT_PARSER: WireLoadoutParser = MultiDeckWireLoadoutParser()
DEFAULT_OWNERSHIP_VALIDATOR: LoadoutValidator = OwnershipValidator()
DEFAULT_LOADOUT_STORE: EquipmentLoadoutStore = PerDeckLoadoutStore()


def apply_unit_equip(
    player,
    req: object,
    *,
    parser: WireLoadoutParser = DEFAULT_LOADOUT_PARSER,
    validator: LoadoutValidator = DEFAULT_OWNERSHIP_VALIDATOR,
    store: EquipmentLoadoutStore = DEFAULT_LOADOUT_STORE,
    on_materia_equipped: Callable[[], None] | None = None,
    note_fn: Callable[[str], None] = lambda _msg: None,
    atomic: bool = True,
) -> bool:
    """Validate and apply ``UnitEquipRequest`` (``Er92Kdhm``) to ``player``."""
    if player is None or player.mode == 'frozen' or not isinstance(req, dict):
        return False
    rows = req.get('Er92Kdhm')
    if not isinstance(rows, list):
        return False

    roster = {str(unit['instance_id']): unit for unit in player.data['roster']}
    try:
        batch = parser.parse_rows(rows, player, roster)
        for warning in batch.warnings:
            note_fn(warning)
        if not batch.segments:
            return False
        validator.validate(player, batch.segments)
    except EquipValidationError as exc:
        note_fn(str(exc))
        return False

    target = copy.deepcopy(player) if atomic else player
    applied = store.apply(target, batch.segments, on_materia_equipped=on_materia_equipped)
    if atomic:
        if applied or target.data != player.data:
            player.data, player.dirty = target.data, target.dirty
            return True
        return False
    return bool(applied)


def _parse_deck_members(
    raw_members: object,
    slots: int,
    known: set[str],
) -> tuple[list[dict] | None, list[str]]:
    members: list[dict] = []
    unknown: list[str] = []
    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    for tri in str(raw_members or '').split(','):
        if not tri:
            continue
        parts = [x.strip() for x in tri.split(':')]
        if len(parts) != 3 or not all(parts):
            return None, []
        mtype, order, iid = parts
        if not (mtype.isdigit() and order.isdigit()):
            return None, []
        if int(mtype) < 0 or int(mtype) > 1 or int(order) < 0 or int(order) >= slots:
            return None, []
        order_i = int(order)
        if order_i in seen_orders or iid in seen_ids:
            return None, []
        seen_orders.add(order_i)
        seen_ids.add(iid)
        if iid not in known:
            unknown.append(iid)
            continue
        members.append({'member_type': int(mtype), 'disp_order': order_i, 'instance_id': iid})
    if unknown or not members or len(members) > slots:
        return None, unknown
    return members, []


def _parse_deck_shift_updates(
    raw_shift: object,
    deck_id: str,
    known: set[str],
    note_fn: Callable[[str], None],
) -> dict[str, int]:
    updates: dict[str, int] = {}
    if not isinstance(raw_shift, str) or not raw_shift:
        return updates
    for entry in filter(None, raw_shift.split(',')):
        if ':' not in entry:
            note_fn(f"apply_party_edit: deck {deck_id} malformed w1JG7i9j entry {entry!r}; ignored")
            continue
        iid, flag = entry.split(':', 1)
        if iid not in known or flag not in ('0', '1'):
            note_fn(f"apply_party_edit: deck {deck_id} invalid w1JG7i9j entry {entry!r}; ignored")
            continue
        updates[iid] = int(flag)
    return updates


def _apply_deck_rows(
    candidate,
    party: dict,
    rows: list,
    decks: dict[str, dict],
    roster: dict[str, dict],
    slots: int,
    special: str | None,
    target_active_did: str,
    note_fn: Callable[[str], None],
) -> tuple[list[str], bool]:
    known = set(roster)
    changed: list[str] = []
    dropped: list[str] = []
    rejected_decks: list[str] = []
    pending_shifts: list[tuple[str, dict[str, int]]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        deck = decks.get(str(row.get('r21y0YzS')))
        if deck is None:
            continue
        members, row_unknown = _parse_deck_members(row.get('2A6fYiEC'), slots, known)
        if members is None:
            dropped.extend(row_unknown)
            rejected_decks.append(str(row.get('r21y0YzS')))
            continue
        touched = False
        if members != deck.get('members'):
            deck['members'] = members
            touched = True
        new_name = row.get('G4L0YIB2')
        if isinstance(new_name, str) and new_name and new_name != deck.get('name'):
            deck['name'] = new_name
            touched = True
        did = str(deck['id'])
        shift_updates = _parse_deck_shift_updates(row.get('w1JG7i9j'), did, known, note_fn)
        if shift_updates:
            pending_shifts.append((did, shift_updates))
        if touched:
            candidate._mutate()
            if did not in changed:
                changed.append(did)

    shift_touched = _apply_deck_shift_updates(
        candidate, party, roster, pending_shifts, changed, special, target_active_did,
    )

    if rejected_decks:
        reason = f"unknown unit id(s) {','.join(dropped)}" if dropped else 'malformed/duplicate slot data'
        note_fn(
            f"apply_party_edit: rejected deck row(s) {','.join(rejected_decks)} ({reason}); "
            'no partial deck was applied'
        )
    return changed, shift_touched


def _apply_deck_shift_updates(
    candidate,
    party: dict,
    roster: dict[str, dict],
    pending_shifts: list[tuple[str, dict[str, int]]],
    changed: list[str],
    special: str | None,
    target_active_did: str,
) -> bool:
    if not pending_shifts:
        return False
    shift_touched = False
    if special:
        loadouts = party.setdefault('loadouts', {})
        for did, updates in pending_shifts:
            deck_changed = False
            for iid, flag in updates.items():
                entry = loadouts.get(iid) or {}
                current = int(entry.get('brave_shift', roster[iid].get('brave_shift', 0)))
                if current != flag or entry.get('brave_shift') != flag:
                    if current != flag:
                        deck_changed = True
                        shift_touched = True
                    loadouts.setdefault(iid, {})['brave_shift'] = flag
            if deck_changed:
                candidate._mutate()
                if did not in changed:
                    changed.append(did)
        return shift_touched

    deck_loadouts = party.get('deck_loadouts')
    seen_flags: dict[str, set[int]] = {}
    for _did, updates in pending_shifts:
        for iid, flag in updates.items():
            seen_flags.setdefault(iid, set()).add(flag)
    updated_iids = set(seen_flags)
    multi_deck_units = {
        iid
        for iid in updated_iids
        if sum(
            1
            for d in (party.get('decks') or [])
            if any(str(m.get('instance_id')) == iid for m in (d.get('members') or []))
        ) > 1
    }
    needs_per_deck = (
        isinstance(deck_loadouts, dict)
        or any(len(flags) > 1 for flags in seen_flags.values())
        or bool(multi_deck_units)
        or any(
            did != target_active_did and int(roster[iid].get('brave_shift', 0)) != flag
            for did, updates in pending_shifts
            for iid, flag in updates.items()
        )
    )
    if needs_per_deck:
        if not isinstance(deck_loadouts, dict):
            retain_owned_equipment(candidate)
            deck_loadouts = ensure_deck_loadouts_initialized(candidate.data, roster)
        for did, updates in pending_shifts:
            deck_map = deck_loadouts.setdefault(did, {})
            deck_changed = False
            for iid, flag in updates.items():
                entry = deck_map.get(iid)
                current = int(
                    entry.get('brave_shift', 0) if isinstance(entry, dict) else 0
                )
                if current != flag:
                    if entry is None:
                        entry = deck_map[iid] = {}
                    entry['brave_shift'] = flag
                    deck_changed = True
                    shift_touched = True
            if deck_changed:
                candidate._mutate()
                if did not in changed:
                    changed.append(did)
        return shift_touched

    for did, updates in pending_shifts:
        deck_changed = False
        for iid, flag in updates.items():
            if int(roster[iid].get('brave_shift', 0)) != flag:
                roster[iid]['brave_shift'] = flag
                deck_changed = True
                shift_touched = True
        if deck_changed:
            candidate._mutate()
            if did not in changed:
                changed.append(did)
    return shift_touched


def _apply_beast_rows(
    candidate,
    party: dict,
    beast_rows: object,
    decks: dict[str, dict],
    slots: int,
    special: str | None,
    on_beast_linked: Callable[[], None] | None,
    note_fn: Callable[[str], None],
) -> bool:
    if not isinstance(beast_rows, list):
        return False
    state = candidate.data
    owned_beasts = {str(b.get('esper_id')) for b in state.get('beasts') or []}
    beast_changed = False
    for brow in beast_rows:
        if not isinstance(brow, dict) or str(brow.get('r21y0YzS')) not in decks:
            continue
        parsed: dict[int, str] = {}
        bad = False
        for pair in str(brow.get('XZ4Kh7Ic') or '').split(','):
            bits = pair.split(':')
            if len(bits) != 2 or not bits[0].isdigit() or not bits[1].isdigit():
                bad = True
                break
            slot, esper = int(bits[0]), bits[1]
            if slot >= slots or slot in parsed or (esper != '0' and esper not in owned_beasts):
                bad = True
                break
            parsed[slot] = esper
        if bad or set(parsed) != set(range(slots)):
            note_fn(f"apply_party_edit: beast deck {brow.get('r21y0YzS')} malformed/unowned; ignored")
            continue
        did = str(brow['r21y0YzS'])
        target_slots = [int(parsed[n]) for n in range(slots)]
        if special:
            beast_decks = party.setdefault('beast_decks', {})
            if beast_decks.get(did) != target_slots:
                beast_decks[did] = target_slots
                candidate._mutate()
                beast_changed = True
        else:
            previous = state.get('beast_decks', {}).get(did, [0] * slots)
            if did not in state.get('beast_decks', {}) or list(previous) != target_slots:
                if (
                    on_beast_linked is not None
                    and any(
                        int(esper) and (slot >= len(previous) or int(esper) != int(previous[slot]))
                        for slot, esper in parsed.items()
                    )
                ):
                    on_beast_linked()
                for slot, esper in parsed.items():
                    candidate.link_beast(did, slot, int(esper))
                beast_changed = True
    return beast_changed


def apply_party_deck_edit(
    player,
    plaintext: str | None,
    *,
    on_beast_linked: Callable[[], None] | None = None,
    note_fn: Callable[[str], None] = lambda _msg: None,
    atomic: bool = True,
    materia_slots_fn: Callable[[dict, bool], int] | None = None,
) -> bool:
    """Validate and apply ``PartyDeckEditRequest`` (``5Eb0Rig6``) to ``player``."""
    if not plaintext or player is None:
        return False
    if player.mode == 'frozen':
        note_fn('apply_party_edit: frozen state policy -- deck edit not applied')
        return False
    try:
        req = json.JSONDecoder().raw_decode(plaintext)[0]
    except Exception:  # noqa: BLE001 - malformed request body must never break the reply
        note_fn('apply_party_edit: request body did not parse as JSON; deck edit dropped')
        return False
    rows = req.get(PARTY_DECK_GROUP) if isinstance(req, dict) else None
    if not isinstance(rows, list):
        return False

    candidate = copy.deepcopy(player) if atomic else player
    state = candidate.data
    settings = req.get('CN92arJK')
    setting = settings[0] if isinstance(settings, list) and settings and isinstance(settings[0], dict) else {}
    kind = str(setting.get('xBi3L6yR', '1'))
    mapped = PARTY_KIND_MAP.get(kind)
    special = mapped or None
    party = candidate.special_party(special) if special else state['party']
    slots = 6 if special else 5
    roster = {str(u.get('instance_id')): u for u in state.get('roster') or []}
    decks = {str(d.get('id')): d for d in party.get('decks') or []}

    active_tok = 'b61ICxJk' if special == '8' else 'r21y0YzS'
    cand_id = str(setting.get(active_tok, ''))
    target_active_did = cand_id if cand_id in decks else str(party.get('active_deck', 0))

    changed, shift_touched = _apply_deck_rows(
        candidate, party, rows, decks, roster, slots, special, target_active_did, note_fn,
    )

    active_changed = cand_id in decks and cand_id != str(party.get('active_deck'))
    if active_changed:
        if special:
            party['active_deck'] = int(cand_id)
            candidate._mutate()
            if special == '11':
                candidate.set_active_deck(cand_id)
        else:
            candidate.set_active_deck(cand_id)
        if cand_id not in changed:
            changed.append(f'active={cand_id}')

    if not special and (active_changed or shift_touched):
        sync_active_deck_to_roster(candidate.data, materia_slots_fn=materia_slots_fn)

    beast_changed = _apply_beast_rows(
        candidate, party, req.get('49rQB3fP'), decks, slots, special, on_beast_linked, note_fn,
    )
    if atomic:
        if candidate.data != player.data:
            player.data, player.dirty = candidate.data, candidate.dirty
            return True
        return False
    return beast_changed or bool(changed)


def _run_staged_command(fn: Callable[[object], bool]) -> None:
    """Execute ``fn(player)`` against a candidate copy unless already inside ``settle``."""
    from ffbe_state import State
    from revival_battle_commands import in_transaction

    player = State.player
    if player is None:
        return
    if in_transaction():
        fn(player)
        return
    candidate = copy.deepcopy(player)
    State.player = candidate
    try:
        changed = fn(candidate)
    finally:
        State.player = player
    if changed or candidate.data != player.data:
        player.data, player.dirty = candidate.data, candidate.dirty


def handle_unit_equip(spec, req) -> dict:
    """Action handler adapter for ``UnitEquipRequest`` (``pB3st6Tg``) on ``ios-revival``."""
    from exvius_actions import _refresh
    from ffbe_player import score_quest_action
    from ffbe_state import _note

    _run_staged_command(
        lambda target: apply_unit_equip(
            target,
            req,
            on_materia_equipped=lambda: score_quest_action('13'),
            note_fn=_note,
            atomic=False,
        )
    )
    return _refresh(spec)


def handle_party_deck_edit(plaintext: str | None) -> None:
    """Pipeline adapter for ``PartyDeckEditRequest`` (``TS5Dx9aZ``) on ``ios-revival``."""
    from ffbe_player import score_quest_action
    from ffbe_state import _note

    _run_staged_command(
        lambda target: apply_party_deck_edit(
            target,
            plaintext,
            on_beast_linked=lambda: score_quest_action('49'),
            note_fn=_note,
            atomic=False,
        )
    )
