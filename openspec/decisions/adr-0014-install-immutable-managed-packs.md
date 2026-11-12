# ADR-0014: Install managed packs through immutable layers and generations

## Status

Accepted for explicit managed-pack installation; full gameplay hosting remains pending.

## Context

The native iOS adapter already consumes prepared host data and flat static/native
content. It still needs an independent installer for the pinned release packs.
Android and iOS use the same pack identities, but their application metadata
belongs to the destination checkout. Shared Android/browser saves and existing
host data must remain untouched.

The release is an ordered overlay. Updating the final tree in place cannot
correctly remove an override or reveal a file from an earlier pack. Downloads and
extraction can also fail partway through a large release, so completed work must
be reusable without activating incomplete content.

## Decision

Separate manifest policy, resumable transfer, immutable layer extraction,
read-only content records and installation orchestration into small modules.
Expose read-only plan-data and verify-packs separately from explicit fetch-data.
Commands use the dedicated iOS runtime and emit one JSON result; progress uses
stderr. None imports the engine or initializes a campaign.

Read a local schema-1 manifest, defaulting to data/latest.json. Preserve its exact
bytes and app metadata. Skip only client-assets. Validate declared sizes, hashes,
URLs and ZIP destinations. Existing local archives are read-only inputs; missing
archives are downloaded only by fetch-data, using bounded reads and resumable
partials. Require complete length and SHA-256 before extraction.

Store immutable payloads in .ios-layers keyed by archive SHA-256. Record every
file's length and digest, reject unsafe ZIPs and Mac case/Unicode collisions, and
verify reused layers. Build each complete .ios-generations tree in manifest
order using hard links. Later exact paths override earlier files; rebuilding from
layers restores earlier files when a later override disappears or order changes.

After overlay composition, build a sanitized gamedata.xml from the final
registry.json. This mirrors Android's post-extraction registry update: the real
preserved registry is newer than XML for three tables. Replace the XML hard link
with a new file so archived layers and previous generations remain unchanged.

Keep exact manifest bytes and a payload/layer inventory in the generation.
Verify the complete payload and required layout before atomically replacing
ios-current.json. Hold the private runtime lock and a shared-data installation
lock throughout the command. Retain old generations and verified layers. A failed
activation can reuse a matching complete unpublished generation on retry.

Configuration keeps the logical data root for containment and pins the selected
physical content generation once. Engine paths and content provenance use that
pinned generation. Existing prepared/flat layouts still resolve directly.
fetch-data refuses to adopt or overwrite either layout; installation uses a
separate managed directory. Native compatibility preparation remains explicit.

## Consequences

Raw installation can be resumed independently of campaign or asset preparation.
Repeated manifests need no transfer or extraction. Missing, stale and corrupt
installations fail visibly; diagnostic queries do not repair them. Retained layers
and generations require disk space, while hard links avoid duplicating bulk
payloads. Old configurations retain their original paths after activation.

BDD covers transfers, ZIP policy, overlay updates, activation failures, locks,
read-only queries, source preservation and engine/native-table integration.
Two published patch archives passed transfer/hash/extraction checks, and the real
364-table registry projection passed against disposable copies. A complete
14.58 GB download/installation and physical-iPhone gameplay remain unverified.
The live LAN listener continues to serve only the accepted connection check.
