# ADR-0008: Prepare and deliver every registered native table

## Status

Accepted for the complete registered-table and engine-delivery checkpoint.

## Context

The 35-table snapshot transforms labels and economy displays, but the stock client
also requests unchanged tables. Canonical forced versions and token fallbacks do
not guarantee that the advertised version names the delivered bytes. The local
Global-1167 corpus has 364 positive registrations and corroborated source files:
219 JSON masters (157 CBC, 62 ECB) and 145 ECB English localized tables.

## Decision

Package the corroborated name/token/key/cipher registry with the originating
native-library SHA-256. Require exact positive preference registrations, all native
sources and valid English index checksums. Reject unknown source tokens and
undeclared English index names. Preserve and report the five known unregistered
index rows without fabricating files or advertising their versions.

Normalize passthrough encrypted lines to LF without rewriting records. Retain
the existing core, label and economy transforms. Publish schema-3 snapshots with
registry provenance and source/registration version floors. Select a generation
that advances every previously published version, including after a floor drops.
Continue validating schema-1/2 artifacts for inspection and atomic upgrade.

Keep preparation independent of engine state loading. Add an explicit
Engine(config, prepared=True) consumer that verifies complete, current preparation
with recorded campaign economy settings while holding the runtime lock, before
binding engine modules. Bind that snapshot for the engine lifetime. Project its
364 identities after canonical versions and serve exact GET/HEAD bytes. Claimed
table paths cannot fall back to stock versions. Retain canonical path validation.

## Consequences

Initialize a campaign, explicitly prepare its tables, and start the prepared
consumer in a fresh process. Missing, partial, corrupt, stale or provisional
snapshots fail without implicit preparation or save repair. Query delivery never
writes files, downloads assets or changes campaign state. The default adapter and
hello-only LAN service are unchanged. Full gameplay hosting, native art/audio/story
preparation, managed installation and physical-iPhone acceptance remain pending.
