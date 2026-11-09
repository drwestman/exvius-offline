# Native iOS server foundation

This is the first implementation checkpoint of
[the iOS plan](../../plans/IOS_SERVER_SOLID_CQRS_PLAN.md). It does **not** host an iPhone
session yet. DNS, HTTP/HTTPS listeners, certificates, data installation, and the
remaining revival gameplay ports are pending.

The reference is revival commit `47a13c084f42cf1b83b53173d0c21065c78fc2de`.

## Available commands

Run from the repository root:

```sh
python3 source/exvius/macos_ios_server.py doctor
python3 source/exvius/macos_ios_server.py status
python3 source/exvius/macos_ios_server.py rotation --weeks 8
```

These commands print JSON. They do not initialize the engine, create a save,
download data, write caches, or start services. `doctor` exits 1 for missing
prerequisites. `status` explicitly reports `hosting: not-implemented`.

`rotation` currently previews calendar windows, with `to` exclusive. It does not
select banners, events, or shops. Before initialization it reports
`anchored: false`; previewing does not begin the campaign.

An explicit development command can initialize a campaign using already prepared
data. It requires Python 3.12 with the canonical engine's PyYAML and cryptography
dependencies available. The dedicated environment installer and dependency lock
are a later checkpoint. In that environment:

```sh
python source/exvius/macos_ios_server.py init-campaign --data /path/to/prepared-data
```

Use `--root /path/to/private-ios-runtime` to select an alternate private root and
`--slot NAME` for a save slot. Initialization acquires the instance lock, loads
the existing canonical engine without listeners, and persists the calendar once.
Engine diagnostics go to stderr; stdout remains one JSON document. A failed
initialization releases the lock. Use a fresh process to reconfigure engine paths.

## Profiles and storage

`LocalGame` explicitly selects the immutable `legacy` profile. The iOS adapter
selects `ios-revival` before importing engine modules. A bound interpreter cannot
switch profiles. Both use the same encrypted handler and `PlayerState` save code.
The iOS profile defaults the daily anniversary ticket to off, as in the pinned fork.

Shared inputs can use either layout:

| Layout | Decoded tables and art | Native resources |
| --- | --- | --- |
| Prepared host data | `mst_decoded/`, `text_decoded/`, `cpk_extract/` | `client/files/`, with `overlay/` taking precedence |
| Managed packs | `static/mst_decoded/`, `static/text_decoded/`, `static/cpk_extract/` | `native/` |

The version registry is `client/shared_prefs/gamedata.xml` under the prepared
root, or under `static/` for managed packs. Presence checks do not verify pack
hashes or establish gameplay completeness; the planned `verify-data` command
will perform content verification.

The default private root is
`~/Library/Application Support/Exvius Offline/iOS`. Campaigns use
`state/<slot>.json`, request records use `requests/`, certificates will use
`certs/`, and battle caches use `cache/battles/`. Runtime and shared-content trees
must be separate, including after symlink resolution. Saves and policies under
the shared data root are ignored.

For canonical engine consumers, `data_paths.DATA_ROOT` continues to locate
runtime policies; in iOS mode `CONTENT_ROOT` separately identifies shared inputs.
Legacy path/environment precedence remains unchanged. iOS battle views derive
cache misses in memory. Explicit preparation code can call
`battle_content.assemble(..., write_cache=True)` to build a disk cache.

The replay anchor and its settings are stored together in the campaign's
`ios_revival` record. The first `InitializeRequest` creates that record as an
explicit command before the reply's projections. Candidate state becomes live
only after its atomic save succeeds. Repeated initialization and restarts retain
the anchor. Invalid anchor data is reported without a silent reset.

Defaults match the fork: December 16, 2016; Sunday at 10 PM in
`America/New_York`; three historical weeks per real week, then two when the
historical week's start reaches August 20, 2020. Elapsed calendar weeks count
while the server is stopped. The time-zone rules retain 10 PM across DST changes.

## Validation

```sh
python -B source/exvius/test_ios_server.py
```

Use Python 3.12 with the engine dependencies for the subprocess integration
checks. Tests create synthetic masters and temporary private saves. They cover
encrypted initialization, restart/retry persistence, write failure, canonical
corruption preservation, both data layouts, instance-lock conflicts and cleanup,
read-only diagnostics, DST transitions, cache behavior, and CDN traversal and
symlink rejection. Valid resource and art fallbacks are also checked.

Checkpoint validation on this Mac: 24 iOS checks plus 30 existing Mac launcher
checks, 10 raid-ledger checks, and 19 existing event/repeat/title-menu checks
(the latter with synthetic masters). Full-corpus gameplay, summon transaction
coverage, APK builds, and actual iPhone acceptance remain unverified.
