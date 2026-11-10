# ADR-0006: Prepare native iOS tables as private snapshots

## Status

Accepted for the core native-table preparation checkpoint.

## Context

The pinned fork transforms tables and localized text during CDN requests. The
native plan requires explicit preparation, shared content reuse without writes,
and agreement between advertised versions and delivered bytes. The hello service
does not yet host gameplay or assets.

## Decision

Add `prepare-data` and read-only `verify-data` for an initial seven-table snapshot.
Keep CBC/ECB codecs, compatibility transformations, and filesystem publication in
separate modules. Read the prepared or managed static/native layout without
loading an engine or campaign. Validate English source checksums before patching.

Stage LF-terminated encrypted files and a provenance/checksum manifest in the
private runtime. Publish the immutable generation through one atomic pointer
under the existing instance lock. Changed inputs advance all snapshot versions;
identical inputs reuse the existing generation. Preserve previous generations
and refuse corrupt published facts rather than silently repairing them.

Expose exact-version byte lookup and a private version-response projection for
the later gameplay host. That host must verify preparation inputs before use.
No current service or engine route consumes these files yet.

## Consequences

Tutorial resource flags, hidden quest rewards, the Drop Rates URL, and custom
daily text are reproducible offline. The localized index records the final text
versions, MD5s and sizes. Failed writes cannot replace the active snapshot;
interrupted pointer replacement can reuse a complete unpublished generation.
Queries perform no writes, downloads, campaign initialization, or service starts.

Remaining English text, earned-Lapis master displays, full table coverage, art,
audio/story preparation, pack installation, and gameplay hosting stay on later
checkpoints. `gameplay_ready` remains false.

Affected files: `ios_server/table_codec.py`, `ios_server/native_tables.py`,
`ios_server/preparation.py`, `ios_server/cli.py`, and `exvius/macos_ios_server.py`.
