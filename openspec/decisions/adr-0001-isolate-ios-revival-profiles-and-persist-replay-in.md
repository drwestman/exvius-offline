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


> Recorded by openlore decisions on 2026-11-09
> Decision ID: 381df222


