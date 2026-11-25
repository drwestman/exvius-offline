# ADR-0017: Preserve unchanged native versions and re-version drifted upfront CPKs

## Status

Accepted for native iOS preparation schema 6; physical-iPhone download and gameplay acceptance pending.

## Context

After generation 8 was published, device crash diagnosis (`crash_diagnosis.md`, 2026-11-21) identified two defects in native table/asset versioning:

1. **Unconditional re-versioning across generations**:
   `native_tables.build`, `native_sounds.inventory`, and `vortex_art.prepare` unconditionally assigned `floor + 200000 + generation * 10000` to every table, sound bank, and pack on every generation, and schema 1–5 validators enforced that formula. Advancing from generation 7 to generation 8 re-versioned 239 byte-identical tables (138 MB) and all 735 byte-identical sound banks (2.2 GB), forcing the iPhone to discard its intact local cache and re-download ~2.6 GB in the background. While that background download ran, Home icon/master lookups missed and `GateEntryScene` / World map dereferenced null master rows (`EXC_BAD_ACCESS` at `0x60`/`0x90`).

2. **In-place upfront CPK edits without version bumps**:
   Upstream v0.1.35 modified four upfront CPKs (`Ver36_monster3_common.cpk`, `Ver26_item2_common.cpk`, `Ver25_battleEffect4_common.cpk`, `Ver13_effectResource1_common.cpk`) in place without bumping their native version numbers. Generation 8 updated `F_RESOURCE_CHECKSUM_MST` (advertised sizes) while leaving the stock versions (`36`, `26`, `25`, `13`) unchanged, allowing an iPhone with previously cached bytes for those versions to retain stale data or reject the size mismatch.

## Decision

Introduce **manifest schema version 6** (`PIPELINE_VERSION = 6`) with a pure monotonic version-resolution policy (`version_policy.py`) and an immutable content-addressed upfront CPK store (`upfront_store.py`), while preserving strict validation and loading for schemas 1–5:

1. **Pure monotonic carry-forward (`version_policy.py`)**:
   - Resolve leaf artifacts before dependent master tables in a five-stage pipeline:
     1. Upfront CPKs (`resolve_upfront`)
     2. Vortex pack (`build_pack` -> `resolve_managed`)
     3. Sound banks (matched by `Ver0_` identity -> `resolve_managed`)
     4. Localized text tables (`patch_text` -> `resolve_managed`), then `F_LOCALIZED_TEXT_MST` and master tables, then projections, then final master table version resolution (`resolve_masters`).
   - Any managed artifact whose output SHA-256 matches the previous generation and whose carried version satisfies `version >= floor` and `version >= 210000` retains its existing `version` and `version_generation`. Only artifacts whose output bytes changed or whose floor rose above their carried version receive `floor + 200000 + generation * 10000` with `version_generation = generation`.
   - `next_generation` advances `generation` above all prior managed versions and runs `check_bounds` before expensive builds (such as `cpk.rebuild`).

2. **Upfront CPK drift detection, private blob store, and delivery (`upfront_store.py`, `upfront_resources.py`, `table_delivery.py`)**:
   - Bump any upfront CPK whenever `size != advertised` (stock drift against `F_RESOURCE_CHECKSUM_MST`) or `sha256 != previous_sha256` (catches same-size edits and future changes) or `prior.version < source_version`, carrying forward the bumped version while its SHA-256 remains identical.
   - Exclude `vortex_art.RESOURCE_ID` (`6108101`) from `upfront_resources.collect` when `vortex_art` is enabled so ownership never overlaps.
   - Stage bumped upfront CPKs by streamed `O_NOFOLLOW` copy (never hardlinked) into `assets/upfront/blobs/<sha256>.cpk` (`0o700` dir, `0o600` file) before atomic generation directory and `current.json` publication. Shared `CDN_ROOT`/`CDN_OVERLAY` files remain untouched.
   - Serve bumped upfront CPKs via `UpfrontDelivery` in `table_delivery.serve` (containment + `O_NOFOLLOW` + per-request 256 KiB chunked SHA-256 verification before HTTP 200 headers; 404 for stock/superseded versions without stock fallback; 500 on corrupt/missing/escaping blobs; unbumped stock upfront CPKs pass through to `capture_server.py`).

3. **Stateless freshness & CQRS separation**:
   - Keep `fingerprint`, `sources`, and `preparation` 100% pure functions of current inputs (`upfront` provenance upgraded to `policy = 2` recording `source_version` and `relative`, with `preparation.upfront` remaining input-derived).
   - Keep `verify-data`, `load_prepared`, `open_prepared`, and `table_delivery.serve` strictly read-only.

## Alternatives Considered

- **Per-generation CPK copies inside `assets/tables/<gen>-<fp>/`**: Duplicates large upfront CPKs across generations whenever any table changes. Content-addressed `assets/upfront/blobs/<sha256>.cpk` deduplicates unchanged bumped CPKs with zero extra disk writes.
- **Mutating `CDN_ROOT` / `CDN_OVERLAY` or creating CDN version aliases**: Violates shared-data immutability and risks breaking stock/browser/Android paths or hardlink isolation.
- **Continuing unconditional re-versioning**: Directly causes multi-gigabyte background cache invalidation and mid-download null-row crashes on physical devices.

## Consequences

- Routine single-table, sound, or artwork updates only re-version the changed artifacts and their direct index/resource tables (`version_reuse` diagnostics exposed in `PreparedTables.describe()`).
- Upgrading from generation 8 (schema 5) to generation 9 (schema 6) preserves gen-8 versions for all unchanged tables, sound banks, and `spdungeon1.cpk`, while immediately bumping and privately serving the stock-drifted upfront CPKs.
- Schema 1–5 snapshots remain readable and strictly validated under their original rules; `Engine.initialize(prepared=True)` accepts both schema 5 and schema 6.
