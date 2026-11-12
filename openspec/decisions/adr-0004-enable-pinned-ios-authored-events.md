# ADR-0004: Enable pinned iOS authored events through canonical battle paths

## Status

Accepted for the authored-content checkpoint.

## Context

The pinned history adds nine areas containing 118 missions. The current engine
already assembles 112 of them through its existing exploration, story, and battle
paths. Six Halloween Castle missions need the fork's local reconstruction packet.
The fork also changes unrelated encounters and cache paths; those changes are
outside this checkpoint.

## Decision

Validate and load the pinned reconstruction packet in an iOS-only content module.
Merge the nine history rows into the iOS catalogue; keep the public archive API
and legacy catalogue unchanged. Reuse canonical entry, battle, reward, repeat,
and persistence handlers. Return private copies of authored encounter packets.
For the ten added explorations, include an exact subset of the pinned finite
encounter plans and its two authored group formations. Preserve map-script boss
groups; roll future encounter drops without adding hypothetical fights to the
normal result ledger. Other explorations keep their canonical behavior.
Retain the shipped native fallback art until explicit asset preparation installs
the additional images; never fetch artwork while querying events.

## Consequences

Malformed authored packets fail visibly rather than opening incomplete content.
Existing identity checks, private cache rules, and atomic iOS settlement remain
authoritative. Original reward and skill-set masters are reused. Read-only
inspection does not install assets or initialize campaign state. Native data/asset
preparation and physical-device play remain separate acceptance milestones.

Affected files: `revival_content.py`, `event_encounters_added.json`,
`revival_events.py`, `event_archive.py`, `battle_content.py`, `ffbe_battle.py`,
`revival_exploration.py`, and `exploration_encounters_added.json`.
