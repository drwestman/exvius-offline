# ADR-0010: Prepare immutable summon-detail images before projecting their names

## Status

Accepted for the explicit summon-banner fitting checkpoint.

## Context

The stock client stretches detail images into paid or base frames and retains
downloaded filenames. The pinned fork fits images and creates caches during GETs.
The destination requires explicit preparation and read-only asset delivery.
The existing gacha group builder serves entry, step/result and box refreshes;
changing only the opener would leave later views inconsistent.

## Decision

First extract the existing master/layout and offer/detail blocks from gacha_groups.
Gate each extraction with summon/deal/completion tests and full catalogue wire
characterization. The two extractions preserve all 1,053 banners and 1,708 detail
rows while reducing structural risk from 81 to 67 before the feature is added.

Add prepare-banners and verify-banners. Publish a separate artwork generation
under private assets/banners/current.json, using the same atomic publisher and
exclusive runtime lock as table preparation. Banner URLs are content-addressed;
there is no need to rebuild 364 tables or a large CPK when an image changes.

Prepare paid 640:183 and base 640:392 variants for each available source PNG,
following the pinned blur2 algorithm and six-percent unchanged-ratio tolerance.
Keep source pixels at their native scale. Pin Pillow and its wheel hashes in the
isolated iOS runtime. Hash source bytes, current catalogue metadata and renderer
policy/version. Unknown source artwork stays reported without invented images.

Bind current artwork only through the explicitly prepared iOS engine. Refuse stale
or corrupt snapshots before engine imports. Project detail/carousel names after
the shared group builder using its actual native layout facts. Preserve bare list
names, costs, rewards, steps, boxes and legacy/unprepared projections.

Serve only verified snapshot bytes for fitted names; unknown names return 404.
Verification and delivery never render, download or create caches. Canonical POST
request recording remains controller telemetry and retains its existing behavior.

## Consequences

Artwork and table generations have independent freshness checks and retain prior
files. Identical inputs reuse a generation; failed rendering/publication preserves
the active pointer. A prepared engine keeps one verified artwork binding for its
lifetime. The live LAN service remains hello-only. Missing artwork, sound/story
compatibility, managed installation, full hosting and physical-iPhone visual/gameplay
acceptance remain later work.
