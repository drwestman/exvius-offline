# ADR-0001: Isolate iOS revival profiles and persist replay initialization with the campaign

## Status

accepted (auto-accepted, unreviewed)

**Domains**: server

## Context

Keep the current canonical engine and legacy defaults; select an immutable profile before engine imports, separate shared content from private runtime paths, and commit the replay anchor and initialization marker together in the existing atomic player save. Queries only inspect persisted state.

## Decision

Isolate iOS revival profiles and persist replay initialization with the campaign

## Consequences

Reviewed November 10, 2026 for native label/economy preparation. The profile and
private-runtime boundaries remain in force. Offline preparation reads only
recorded settings or validated provisional defaults; it does not import the
state loader, initialize/backfill campaigns, or modify shared source rewards.
Gameplay retains canonical unit lookup and purchase transactions through pure
helper adapters. See [ADR-0007](adr-0007-prepare-native-labels-and-economy-displays.md).

Reviewed again for complete table delivery: the prepared consumer requires current
recorded policy before state imports, keeps the private lock for its lifetime,
and binds its snapshot only in the iOS profile. Legacy routing and canonical
campaign saves retain their contracts. See
[ADR-0008](adr-0008-deliver-complete-registered-native-tables.md).

Reviewed for summon fitting: optional artwork is verified before state imports
and bound only to the prepared iOS engine. Legacy wire output and campaign
transactions remain canonical. See
[ADR-0010](adr-0010-prepare-summon-detail-artwork.md).

Reviewed for replay home banners: optional home images join the verified artwork
binding before state imports. Carousel policy is recorded or backfilled only in
the atomic campaign initialization command, preserving an existing replay anchor
and failed-save behavior. The prepared iOS adapter supplies its carousel flag
default while preserving explicit overrides and legacy defaults. See
[ADR-0013](adr-0013-prepare-replay-home-banners.md).


> Recorded by openlore decisions on 2026-11-09
> Decision ID: 381df222



Reviewed for managed-pack installation: commands do not import the engine or
initialize campaigns. Configuration pins a physical content generation while
retaining the logical data root as its containment boundary. Old prepared inputs
and all shared saves remain read-only. Native preparation remains explicit after
activation. See [ADR-0014](adr-0014-install-immutable-managed-packs.md).

Reviewed for gameplay hosting: start requires recorded campaign policy and current
prepared assets before state imports. Transport and engine share one held runtime
lease; shutdown drains native requests before asset unbinding and lease release.
The canonical handler, wire fields and campaign transactions remain unchanged.
See [ADR-0015](adr-0015-compose-prepared-native-gameplay-hosting.md).

Reviewed November 11 for native diagnostic uploads: only the prepared iOS engine
binds the report adapter, and close unbinds it. Uploads bypass the gameplay
pipeline and preserve campaign bytes. The adapter owns private bounded storage;
scheduling is a pure reply projection. An unbound canonical handler retains its
legacy behavior. The once-per-launch policy follows upstream 590d4fb, reviewed at
ae07888; other newer gameplay changes remain separately planned.
