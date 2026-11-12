# ADR-0011: Prepare native sound banks in file-backed generations

## Status

Accepted for the explicit sound-preparation checkpoint.

## Context

The pinned revival fork removes keyless HCA type-1 frame encryption and changes
HCA-MX waveform flags to HCA during sound GETs. The destination requires explicit
preparation and read-only queries. The local corpus is 2.2 GB; retaining all banks
in an in-memory table snapshot would materially increase server memory use.

Resource metadata is also imperfect: all 782 sound references resolve to 735
unique exact-version banks, but 49 iOS size fields and 48 Android size fields
disagree with those source files. These include zero and stale positive sizes.
Bank structure and HCA CRCs can be checked independently of that metadata.

The pinned story_text rewrite is disabled by default because the actual iPhone
rejected its rebuilt scene packs with a CRI IFF-header error. Porting it as an
enabled compatibility transform would preserve a known failure.

## Decision

Add prepare-sounds and verify-sounds without binding sound delivery yet. Separate
pure bounded UTF/AFS2/HCA conversion, read-only resource/source collection, and
private snapshot commands. Use original encrypted resource, version and checksum
masters from both resource families. Require positive file versions and exact
source paths; prefer an available exact native iOS bank over Android sources.
Never substitute the highest bank version for a missing advertised version.

For Android banks, validate the complete archive, HCA headers and every frame
before converting. Apply the pinned keyless substitution, clear cipher type 1,
recompute checksums and reflag HCA-MX waveforms. Keep the byte length and every
unrelated byte. Reject keyed ciphers, unsupported encodings, invalid offsets,
external AWB dependencies and damaged streams visibly. Supported native iOS
banks retain every byte and still undergo structural/checksum validation.

Use the checksum-locked fastcrc CRC-16/UMTS implementation for polynomial 0x8005,
initial value zero, no reflection and no final xor. Verify it against an
independent bitwise oracle and compare complete converted banks against the
unmodified pinned implementation. The dependency belongs to .venv-ios only.

Hash original bytes and metadata, record original platform sizes, and measure
actual output sizes. Report disagreements without changing shared masters.
Process one bank at a time. Store content-addressed files and complete provenance
under private assets/sounds; replace current.json only after all outputs validate
and a second inventory confirms input freshness. Retain prior generations.
Queries validate one bank at a time without conversion, locks, repair or writes.

## Consequences

The prepared artifact registry records 735 banks, 782 resource references and
1,727 waveforms. Conversion decrypts 388 streams and reflags 816 waveform rows.
All 735 outputs match the pinned fork byte for byte, totaling 2,202,569,152 bytes.

Table versions/checksums and engine/CDN routing remain unchanged in this checkpoint.
The next step must coordinate sound resource versions and measured iOS byte sizes
with complete table publication, then bind exact file-backed GET/HEAD delivery.
The sound manifest explicitly reports delivery_ready false. No production cache
or campaign is created by the real-data validation, which uses a disposable root.

Story scene packs remain original. Their text repair needs a separately validated
native-compatible builder and physical-iPhone acceptance. Remaining artwork,
managed pack installation, gameplay hosting and actual-device audio acceptance
also remain pending.
