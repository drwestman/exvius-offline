# ADR-0005: Complete iOS exploration plans and rare quest loot

## Status

Accepted for the exploration/loot checkpoint.

## Context

The pinned source contains 248 finite exploration plans, including five declared
partial monster lineups, plus 189 unresolved mission descriptions. The ten-mission
subset is already ported. The fork's rare Calamity Writ rule appends a 0.5-percent
bonus to each ordinary wave/field drop roll, but the destination protects capture
and fixed-reward chambers by ignoring client-supplied ordinary loot there.

## Decision

Use the full pinned exploration file without inventing missing lineups. Extend
the existing adapter with the pinned field/zone mapping and Crystal Tower fields;
preserve scripted bosses and leave unplanned missions on their canonical path.
Record field enablement and Writ chance once during campaign initialization.
Keep bonus rolling separate from reward crediting and use injectable RNG.

For protected capture/fixed-reward missions, record native drop rows and their
Writ count in the existing loaded-attempt receipt. Reuse those facts on reload;
credit the bonus on a successful clear alongside original protected rewards.
Normal and field loot retain canonical reported-loot settlement. No new query
initializes state, grants items, writes caches, or repairs content gaps.

## Consequences

Legacy gameplay and fixed reward quantities remain unchanged. Writ settings and
receipts survive environment edits and retries. Malformed settings, packets, or
recorded facts fail visibly. Partial/unresolved content remains explicitly reported
by diagnostics. Native asset installation and device acceptance remain separate.

Affected files: `revival_exploration.py`, `exploration_encounters.json`,
`revival_loot.py`, `revival_campaign.py`, `battle_content.py`, `ffbe_battle.py`,
`exvius_repeat.py`, and `ios_server/queries.py`.
