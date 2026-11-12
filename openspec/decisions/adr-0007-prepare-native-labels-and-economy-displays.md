# ADR-0007: Prepare native labels and economy displays from pure catalogues

## Status

Accepted for the expanded native-table preparation checkpoint.

## Context

The core snapshot covers seven files. The stock iPhone has no Android text hooks
for reconstructed names, local summons/bundles or generated exchanges. Earned
Lapis uses saved campaign settings, so native master displays must use that same
policy without rewriting canonical source rewards or loading a player aggregate.

## Decision

Expand preparation to 35 outputs: five core masters, all 25 pinned English label
families, and five economy masters. Four additional native tables supply product
stock and unit/card/recipe names. Keep codecs, label policy, source collection and
snapshot publication separate. Use canonical revival bundle/summon definitions
and the pinned 44-item English fallback file.

Extract the existing exchange catalogue calculation and reward tuple decoder into
pure helpers. Gameplay supplies its original unit-master lookup; preparation
supplies content without binding the engine. Preserve product identities, prices,
stock limits and reward metadata.

Preparation reads only the selected campaign's recorded economy settings. If
missing, it validates provisional environment defaults without initializing or
backfilling a save. Fingerprint the effective policy, slot, label projections and
source provenance. Unrelated campaign progress does not invalidate a snapshot.
Convert master displays once from original shared source rows.

Publish schema-2 snapshots while retaining strict schema-1 validation. An explicit
upgrade advances versions atomically and preserves old generations. Missing new
inputs or corrupt facts must not discard the usable core snapshot.

## Consequences

English append/fill/override behavior follows the pinned text rules; usable text,
native column/padding shape and other languages remain authoritative. Unnameable
products are reported rather than invented. Saved economy changes require explicit
re-preparation; environment edits cannot override recorded settings. Neither
preparation nor verification imports the state loader, repairs saves, grants loot,
or changes hosting. Full table coverage, art/audio/story packs and device gameplay
acceptance remain later checkpoints.
