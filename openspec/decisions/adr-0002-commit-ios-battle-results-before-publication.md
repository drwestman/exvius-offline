# ADR-0002: Commit iOS battle results before publication

## Status

Accepted for the trust-gain implementation.

## Context

The pinned revival trust policy adds rare large gains. The destination already
owns mastery grants, native result rows, and durable per-attempt reward guards.
Its legacy pipeline tolerates save failures and saves before recording the result
echo, which cannot guarantee an atomic iOS trust reward and completion receipt.

## Decision

Record trust settings once through campaign initialization. Keep trust planning
read-only with an injectable random source, and retain canonical trust grants.
After the existing explicit daily synchronization, run the iOS mission-result
pipeline on a candidate player. Defer its ordinary saves until the result echo
and all completion effects are ready, then save once before publishing.

## Consequences

Legacy settlement and master-defined trust rates retain their current path.
iOS grant or save failures preserve the previous player and attempt for retry.
Daily synchronization remains its own explicit transaction before settlement.
The existing wire contract has no attempt nonce: retries after a new mission
load cannot be distinguished from another legitimate clear.

Affected files: `revival_trust.py`, `revival_battle_commands.py`,
`revival_campaign.py`, `ffbe_battle.py`, and `ffbe_pipeline.py`.
