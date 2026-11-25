# ADR-0013: Prepare replay home banners before carousel projection

## Status

Accepted for replay home-carousel preparation and native delivery.

## Context

The pinned fork selects current replay-week Vortex art for the home carousel and
maps HomeBanner filenames to event art during GETs. The destination still used
legacy era selection; its canonical default deliberately keeps the promotional
strip off. The iOS profile needs the pinned replay behavior while retaining the
legacy selection and flag controls.

The local artwork inventory covers 766 areas and 701 source PNG names. There are
692 available sources and nine missing added-event images. Multiple names contain
identical PNG bytes. Missing sources must remain visible gaps rather than being
replaced with unrelated or invented images.

## Decision

Add prepare-home-banners and read-only verify-home-banners independently of native
table, sound and summon-detail generations. Read event_art.json and event_history.json
with the same original-event precedence as the pinned fork. Prefer exact native
overlay art, enforce containment, validate PNGs, and keep every source byte.
Publish content-addressed PNG files and complete provenance through a private
assets/home-banners/current.json pointer using the existing atomic publisher.

Record enabled, limit and tap settings in ios_marquee during the existing atomic
campaign initialization command. Defaults match the fork: enabled, six images,
and eligible event taps. Bound the configurable limit to 1 through 52. Existing
anchored campaigns backfill settings without changing their anchor; queries never
initialize settings or repair malformed state.

Select active historical events through the canonical iOS event policy. Match the
pinned release/area descending order, filename deduplication, permanent-event
exclusion and limit. Omit missing art. Disabled, unanchored, unprepared and finished
replay selection uses the existing era path; an active replay week without usable
art yields no replay rows. Native-mode events retain their normal Vortex link;
eligible events use the pinned type-6 area/dungeon/mission link.

Preserve native banner IDs as 7000000 plus the area, and use the immutable snapshot
generation as the cache version. Keep HomeBanner_<id>.png as the URL basename under
an ios-home-<full SHA-256> directory. Use local game-host URLs and the existing
rebased display window. The available artwork is not resized or re-encoded.

Bind current home and optional summon artwork together before engine-state imports.
The small artwork binding forwards the existing summon projection unchanged and
routes exact home URLs through the existing PNG GET/HEAD adapter. Enable the iOS
marquee flag by default only when home artwork is bound, respecting explicit
MARQUEE_FLAG overrides. Existing legacy/default consumers keep their prior behavior.

## Consequences

Repeated preparation reuses a generation, source changes advance cache identity,
and failed publication preserves the current pointer. Verification validates
bytes, paths, PNG dimensions, identities and freshness without writes. Unknown
prepared home URLs return 404; queries do not download, fit, index or write caches.
The prepared engine retains its verified image binding for its lifetime.

The real corpus publishes 692 source names as 628 unique files. Selection matched
the pinned algorithm over 201 replay weeks, including era fallback after history.
Physical-iPhone display/tap acceptance remains pending. Managed-pack installation,
remaining source-art gaps, story repair if needed and full gameplay hosting remain
later work. The live LAN service remains the connection check.
