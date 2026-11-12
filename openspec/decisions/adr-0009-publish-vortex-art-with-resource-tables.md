# ADR-0009: Publish Vortex artwork with its resource tables

## Status

Accepted for the explicit native Vortex banner-pack checkpoint.

## Context

The stock iPhone mounts Vortex artwork from CPKs; Android's loose-image hooks are
unavailable. The pinned fork rebuilds the English spdungeon1.cpk during queries.
This conflicts with read-only asset delivery and can separate the pack's bytes
from its advertised resource version and size.

## Decision

Add prepare-data --vortex-art. Retain that choice on future ordinary refreshes.
Publish the rebuilt pack and all 364 tables as schema 4 under the existing atomic
generation pointer. Coordinate resource 6108101's upfront TUTO class, English
file version and exact size. Advance both table and pack versions monotonically;
retain schema-1/2/3 inspection and upgrades.

Separate the pure flat CPK codec, read-only artwork collection and artifact policy,
snapshot publication and exact delivery. Preserve original payload bytes,
compression metadata, IDs and duplicate names. Append available canonical archive
art without replacing existing names. Record source hashes, metadata and image
coverage. Reject unsupported layouts and invalid sources before publishing.

Preserve reserved UTF null-string offsets, including UserString's zero offset;
decoded text equality is insufficient to verify this binary contract. Artwork
pipeline revision 2 records the corrected encoder in freshness so existing
phones receive a new native pack version without altering source artwork.

Missing required artwork fails. The nine pinned added-event images can remain
reported gaps while gameplay retains its existing fallback from the common pack.
No remote art is fetched and no replacement images are invented. Future supplied
images change freshness and enter a new explicit generation.

Verification reads and validates without rebuilding; prepared-engine GET/HEAD uses
snapshot bytes and refuses old Vortex versions without token fallback. Default
and legacy consumers retain their existing routes. No new live service is started.

## Consequences

The complete registry, recorded economy policy and isolated engine contracts in
ADR-0008 remain in force. Request-time preparation, downloads and campaign writes
are excluded. The real corpus adds 692 images to 1,237 original entries; physical
iPhone mounting/visual acceptance is still required. Summon-banner fitting, other
art preparation, sound/story compatibility, managed installation and full gameplay
hosting remain later checkpoints.
