# ADR-0012: Bind sound generations to native table publication

## Status

Accepted for coordinated native sound versions, sizes and delivery.

## Context

ADR-0011 prepares verified sound artifacts independently of table snapshots.
The client fetches sound through common file versions and platform-specific byte
sizes in both resource families. Publishing those values independently from the
artifact binding could serve different bytes under an advertised version.
The 2.2 GB corpus also makes in-memory retention or per-table-generation copies
unnecessary costs. Existing table schemas and optional Vortex assets must remain
inspectable and compatible.

## Decision

Add prepare-data --sounds, requiring current explicit prepare-sounds output.
Publish schema 5 with all 364 tables and an immutable sound-generation reference
containing its directory and manifest SHA-256. The sound bytes stay under their
existing content-addressed paths. Only the table current.json replacement selects
the coordinated client versions, measured sizes and artifact binding.

Advance each sound file's common version using the source version, existing
version offset and table generation step. Raise the generation as necessary when
a source version decreases; reject signed-32-bit overflow. Project common sound
versions and measured iOS byte sizes into both ordinary and map resource tables.
Keep Android size fields, all other language fields and unrelated rows intact.
Validate every referenced resource/path and both table projections before publish
and when loading a snapshot. The sound and native source-table provenance must
agree exactly.

Remember enabled sound and Vortex options on ordinary refreshes. Schema 5 can
include the Vortex pack; schemas 1 through 4 retain their inspection and upgrade
contracts. Extract source-policy validation from the existing table loader to
keep the new artifact policy in its own module.

The prepared engine binds the table snapshot's pinned sound generation, never
substituting the mutable sound current pointer. Startup also checks freshness
against current explicit preparation before importing campaign state. Reads from
an already bound engine retain that generation for its lifetime.

Claim the iOS sound namespace only when sound delivery is bound. Read one exact
bank at a time, recheck containment, length and SHA-256 before responding, and
retain existing octet-stream GET/HEAD headers. HEAD has no body. Unknown or old
versions return 404 without source/token fallback. Damaged or missing bound files
return an empty 500 response; no conversion, repair or fallback runs in a query.

## Consequences

prepare-sounds and verify-sounds keep their artifact-only delivery_ready false
report. A coordinated table report exposes sound_delivery_ready true. Sound
preparation alone does not activate delivery; default/unprepared engines and
schema-3/4 consumers retain their existing behavior.

Repeat preparation reuses a generation. Failure before pointer replacement leaves
the previous table/sound binding authoritative; a retry can reuse a complete
unpublished table generation. Old table and sound artifacts must remain available.
Explicit table refreshes that change the generation advance sound client versions
even when a bank's bytes are unchanged; ordinary reads never refresh versions.

The live native service remains the connection check. Full gameplay hosting,
managed-pack installation, remaining art, a validated story repair if needed, and
physical-iPhone audio/gameplay acceptance remain pending.
