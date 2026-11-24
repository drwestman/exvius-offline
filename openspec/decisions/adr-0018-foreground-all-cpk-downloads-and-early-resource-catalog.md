# ADR-0018: Foreground all versioned CPK downloads and advertise resource catalog early for returning devices

## Status

Phase 1 and Phase 2 implemented and verified by offline automated tests; Phase 0 (`ResourceAllDownloadRequest` / `i0d5n1Dp` wire-contract verification), Phase 3, and physical-iPhone acceptance remain pending.

## Context

Physical iPhone diagnostic reports (`report-99c095bf8d4e45c1a59ec64b79f9408a.json`) and the November 18 Vortex investigation (`docs/reviews/2026-11-18-ios-vortex-crash.md`) established two causes for `.cpk` archives continuing to download in the background (`MODE=bg`) on `HomeScene` instead of blocking in `InitialDownloadScene` (`MODE=fore`):

1. **Background CPK classification (`F_RESOURCE_MST.81fTkEDP == ''`)**:
   Only `EARLY_PACKS`, `MENU_PACKS`, `spdungeon1.cpk`, and `UNIT_ART_PACK` were promoted to `'TUTO'` and audited by `upfront_resources.collect`. The remaining 349 empty-phase `.cpk` packs (`monster*`, `battlebg*`, `area*`, `beast*`, `item*`, `visioncard*`, `LBMovie*`, `movie_sg*`, etc.) remained `''` (background) and bypassed upfront size/drift auditing (leaving 16 additional drifted packs un-reconciled).
2. **Launch-1 resource-catalog ordering gap (`lEHBdOEf` vs. `LoginScene::STATE_MST_DL`)**:
   `revival_boot` only advertised `F_FUNCTION_MST` on `lEHBdOEf` when a returning device's receipt matched the exact current `F_FUNCTION_MST` version. On the first launch after `prepare-data` published updated resource tables, `PostStartupScene` (`PRE_TUTO`) and `LoginScene::STATE_INIT` (`TUTO`/`tuto`) evaluated stale cached `F_RESOURCE_*` tables and skipped `InitialDownloadScene` until a second cold launch.

## Decision

1. **Pure CPK foreground classification policy (`source/ios_server/cpk_foreground_policy.py`, `PIPELINE_VERSION = 7`)**:
   - Extract `ForegroundCpkPolicy` with explicit frozen descriptors `ALL_CPKS` (active default: `promote_empty_phase=True`, `promote_define_phase=False`) and `LEGACY_MENU_AND_UNITS`.
   - In `native_tables.build_masters` (`PIPELINE_VERSION = 7`, retaining manifest schema `version = 6`), promote all `''` `.cpk` rows to `'TUTO'` while preserving `'PRE_TUTO'`, `'TUTO'`, `'tuto'`, `'DEFINE'` (banner packs), and `.acb` audio rows.
   - In `upfront_resources.collect`, audit all non-Vortex versioned `.cpk` rows (`should_audit_upfront`), automatically versioning and staging all drifted packs via `version_policy.resolve_upfront` and `upfront_store.BlobStore` while keeping unchanged tables, sound banks, `spdungeon1.cpk`, and previously bumped CPKs at their carried-forward versions.
2. **Segregated Launch-1 early resource-catalog projection (`source/server/revival_boot.py`)**:
   - Separate read-only `project_early_versions` (`lEHBdOEf`) from command-side `record_receipt` (`75fYdNxq`, `Daud71Hn`).
   - For returning initialized devices (`device_hash in ledger['held']`), advertise `F_RESOURCE_MST`, `F_RESOURCE_VERSION_MST_LOCALIZE`, and `F_RESOURCE_CHECKSUM_MST` at their current prepared versions alongside receipt-matched `F_FUNCTION_MST`, even when `F_FUNCTION_MST` or `F_RESOURCE_*` versions changed since the last boot.
   - Gate behind `EARLY_RESOURCE_CATALOG` / `FFBE_IOS_EARLY_RESOURCE_CATALOG=0` for zero-code rollback if physical-device testing exposes `PostStartupScene` incompatibility.
3. **Server-only scope & Phase-0 wire gate**:
   - Non-startup `mst/*.dat` master tables and `sound/bgm` `.acb` tracks remain unchanged under server-only boundaries.
   - `ResourceAllDownloadRequest` (`i0d5n1Dp`) remains deferred until Phase-0 binary (`libgame.so`) or live physical-iPhone capture verifies its exact response schema.

## Consequences

- Fresh preparation on `PIPELINE_VERSION = 7` promotes all empty-phase `.cpk` archives to foreground `'TUTO'` and reconciles all drifted `.cpk` packs while reusing unchanged tables, sounds, Vortex pack, and prior bumped CPKs.
- Returning devices receive updated `F_RESOURCE_*` versions on Launch 1 `lEHBdOEf` without mutating `player.data` or `dirty`; uninitialized devices and non-`ios-revival` profiles retain prior behavior.
- Manifest schema 6 remains backward-compatible with prior schema 1–6 artifacts; `verify-data` and `open_prepared` enforce `PIPELINE_VERSION = 7`.
