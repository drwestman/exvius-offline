# ADR-0019: Store and project iOS Normal Party equipment loadouts per deck

## Status

Accepted for `ios-revival` after physical iPhone verification of Phase 1 (Track A).

## Context

Phase 1 device testing on iOS (`ver.9100`, build 1167) confirmed that leaving
`Manage Party` after editing Party 2 (`r21y0YzS="1"`) successfully saved Party 2's
equipment into state without `unit-equip: invalid equipment update`, **but immediately
erased Party 1 (`r21y0YzS="0"`) equipment in the UI**. Because `UnitEquipResponse::onReadStarted`
clears `UserUnitEquipInfoList` and rebuilds it strictly from `TJ9eL80N` rows keyed by
`(og2GHy49, r21y0YzS)`, emitting every roster row stamped with `str(party["active_deck"])`
dropped every other deck's rows as soon as `active_deck` changed to `"1"`.

Furthermore, `UnitEquipRequest` (`Er92Kdhm`) sends `;`-delimited per-deck equipment segments
(`r21y0YzS: "1;2"`), allowing the same roster unit or owned equipment item to appear across
multiple normal decks (`0..9`). Storing normal party equipment solely on `roster[i]` cannot
preserve independent per-deck loadouts or avoid conflating simultaneous deck wearers during
`MBPCGT84` (`equip_item_rows`) ownership projection.

## Decision

Under `ios-revival` only (`current_profile().name == 'ios-revival'`):

1. **Command side (`PerDeckLoadoutStore` in `revival_party_commands.py`)**:
   - Store Normal Party unit loadouts per `(deck_id, unit_instance_id)` under
     `party["deck_loadouts"][deck_id][iid]`.
   - On the first per-deck write to a pre-existing save lacking `party.deck_loadouts`,
     retain inferred starter equipment via `retain_owned_equipment` and snapshot non-starter-clone
     existing decks from `roster` into `party.deck_loadouts` before applying incoming deltas so
     Party 1 (and other customized decks) never lose pre-existing loadouts.
   - Mirror the currently active normal deck's entries back onto `roster[iid]` after writes
     and active-deck switches (`TS5Dx9aZ`) so battle, Arena, and shop consumers stay aligned.
   - Clean up per-deck loadout references on `PlayerState.drop_units` and validate them in
     `state_coherence_issues` when present.

2. **Query side (`PerDeckEquipmentStrategy` and count reconciliation in `revival_party_projections.py`)**:
   - Project `TJ9eL80N` (`UnitEquipResponse`) rows per `(unit_instance_id, deck_id)` across
     normal decks `0..9` (ordered numerically starting at `"0"`), plus active-deck fallback for
     any unassigned bench units, while leaving special-party modes (`7`, `8`, `11`) and `legacy`
     projections untouched.
   - Exclude unedited default starter-unit placeholder clones (`decks 3..9` still carrying the
     initial 2-member starter pair) from duplicating Party 1's starter/end-game gear across
     unused deck slots.
   - Reconcile `equip_item_rows()` (`MBPCGT84`) and `materia_rows()` (`rL81fVUI`) read-only as
     `max(inventory_count, max_single_deck_worn + untracked_roster_worn)` so sharing an owned
     item across two normal decks neither mints phantom copies nor undercounts simultaneous wearers
     in any single deck (`UnitEquipUtil::checkEquipCountAddUnitForParty`).

## Consequences

- `legacy` saves (Android, browser, macOS emulator) never write `party.deck_loadouts` and
  retain byte-for-byte identical global roster storage and `TJ9eL80N` projection.
- Existing `ios-revival` saves lacking `party.deck_loadouts` render both Party 1 and Party 2
  equipment immediately on boot (`X07iYtp5`) and migrate cleanly on the first `UnitEquipRequest`.
- Deleting/converting a unit removes its entries from `party.deck_loadouts`; awakening a unit
  (`renew_unit_instance`) migrates its instance key across `party.deck_loadouts` automatically.

Affected files: `source/server/revival_party_domain.py`,
`source/server/revival_party_commands.py`, `source/server/revival_party_projections.py`,
`source/server/revival_battle_commands.py`, `source/server/player_state.py`,
`source/server/exvius_actions.py`, `source/server/ffbe_player.py`,
`source/server/ffbe_pipeline.py`, `source/server/exvius_actions_expedition.py`,
`source/server/exvius_actions_shops.py`, `source/server/exvius_arena.py`,
`source/server/exvius_actions_arena.py`, `openspec/specs/ios-server/spec.md`,
`openspec/specs/server/spec.md`, and `source/exvius/test_ios_party_equipment.py`.
