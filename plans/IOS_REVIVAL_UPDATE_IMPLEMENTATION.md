# Revival update implementation ledger

Reference: `d6e8858861969a2764e31345884453dde79fc71f` in the local
`Exvius-revival-ios` checkout; destination baseline `383814f`.
This is an **in-progress port**, not a full-parity or device-acceptance claim.

## Approved direction

Port all remaining iOS changes through the canonical engine. Adopt the latest
revival rules, preserve the existing isolated campaign and replay anchor, repair
confirmed defects, and pay historical rewards only with durable proof. Keep the
current owned-family companion policy and independent Arena rivals. Keep native
Mac hosting, existing Android/browser behavior, saves and release metadata.

## Implemented checkpoint

- Checksum-pinned update documents, separate source revision and saved update
  settings. Existing campaigns retain the original policy until explicitly upgraded.
- Pure full-run banner/event selection, corrected unit dates, late banners with
  unconfirmed entries excluded, held-ticket visibility, clone/later quest filtering,
  and optional all-banner summon listing.
- Mode-specific prism/fragment rules, native awakened-NV marker, normalized shift
  summon pools, Omniprism validation and request-local refusal envelopes.
- Candidate-save boundaries for roster, map-update, load and result commands;
  bulk fusion processes every row and refuses partial invalid batches.
- Quest completion switches and native Quest Report projection. Item bags exclude
  carried quantities; carried sets are bounded to ownership; attempt receipts
  protect consumption from retries after refilling.
- Recorded collection rolls, bounded collection settlement, per-entry first-clear
  claims, mission Gil without duplicating the existing Riches rule, quest LB EXP,
  forward story joins and Guide history. These reward additions require the saved
  update policy. Historical first clears remain an unknown baseline.
- Global random NV Vision Cards using the replay date and installed masters.
- One pure 5-star Select catalogue shared by commands and native preparation.
  Shipped masters produce 80 additions. Prepared transforms also repair 31 story
  sell prices, two Farplane placeholders and 12 restored ability descriptions.
- Native Convert bootstrap records bounded hashed device receipts through explicit
  login/home commands. Early table advertisement is read-only and version matched.
- Default iOS pack composition adds the pinned summon-art pack while preserving
  destination packs and Android app metadata. Explicit manifests remain complete
  overrides. The installer allowlist admits only the documented art directories.
- `plan-campaign-upgrade` is read-only. `upgrade-campaign` requires the preview's
  save digest, holds the instance lock, preserves a private backup, and publishes
  the candidate atomically. Unknown historical reward claims are listed unpaid.

## Still required for the approved plan

1. Complete replay quest/run rules, exchange scheduling and Captain menu snapshots;
   publish changing menus and their native resource/checksum tables together.
2. Port Global enemy/currency placement, currency sizing/backstops, lottery and
   encounter/scenario corrections, additional raid boxes, reward overrides and
   remaining scripted/tutorial gifts with recorded attempt facts.
3. Complete summon animation/buttons/descriptions, per-source artwork selection,
   finished summon-art pack consumption, illustrations, search/localization and
   coordinated prepared snapshot delivery. Installing the art pack alone does not
   integrate its images into the native projections.
4. Implement proven historical compensation delivery, including supported blocked
   receipts; the present planner deliberately grants no historical backpay.
5. Apply the complete default policy to newly initialized campaigns only after the
   remaining capabilities are implemented. Finish whole-feature encrypted and
   real-data acceptance, then upgrade a disposable clone before any live rollout.
6. Complete physical iPhone cold-start Convert, summon, awakening/refusal, carry,
   quest, audio/art and restart acceptance. No live campaign has been upgraded and
   no running host has been restarted during this checkpoint.

The settings record includes the approved future economy defaults; it does not
claim that every corresponding upstream capability has been implemented yet.

## Commands

Use the dedicated runtime and the same explicit private root/data/slot for both:

```sh
.venv-ios/bin/python -B source/exvius/macos_ios_server.py plan-campaign-upgrade --root PRIVATE_ROOT --data CONTENT_ROOT
.venv-ios/bin/python -B source/exvius/macos_ios_server.py upgrade-campaign --root PRIVATE_ROOT --data CONTENT_ROOT --expected-save-sha256 DIGEST_FROM_PREVIEW
```

The apply command performs this checkpoint's repairs and policy installation;
it does not implement the pending capabilities above. Both commands return JSON.
Preparation must be repeated after a saved policy changes; older immutable asset
generations are retained. Backups are under the selected private root's
`state/backups`, never in the shared content tree.

## Validation

The final full iOS suite passed 540 checks. A focused run after the final
Vision Card result-format refinement passed 25 checks including encrypted conversion,
save-failure rollback, multiple fusion rows, bootstrap receipts, carried-item
retry protection, bounded collection payment and native cipher preservation.
Canonical shop checks passed 65, canonical summon/completion/map/launcher checks
passed 97, and canonical Arena/social checks passed 23.
Real-master native transformation/decryption confirmed the 80/31/2/12 counts above.
An actual disposable upgrade against read-only shipped masters also confirmed
read-only preview without engine imports, exact backup retention, identity/anchor
preservation and repeat idempotency. Whitespace and changed Python/JSON parsing
checks passed. Tracked-file OpenLore drift has zero spec gaps/stale/uncovered
findings and four informational decision notices; its Git-based scan excludes
the new untracked modules, which have explicit implementation/spec anchors.
Physical device observations and live rollout remain pending.
