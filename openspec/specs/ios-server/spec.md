# Native iOS Server Foundation

## Scope

This specification covers the profile/calendar foundation, replay-aware summons,
events, exchanges, friends, arena, reward mail, daily economy, quest trust, replay notices,
pinned exploration encounters and rare quest loot,
complete registered native-table preparation, managed-pack installation,
opt-in engine delivery, native gameplay hosting and independent hello-only connectivity of
[plans/IOS_SERVER_SOLID_CQRS_PLAN.md](../../../plans/IOS_SERVER_SOLID_CQRS_PLAN.md).
Physical iPhone gameplay acceptance remains pending. Reference commit:
`47a13c084f42cf1b83b53173d0c21065c78fc2de`.

## Requirements

### Requirement: SelectImmutableEngineProfile

The engine SHALL select `legacy` or `ios-revival` before binding engine modules.
Existing LocalGame entrypoints SHALL select legacy. A bound interpreter SHALL
reject switching profiles. Both profiles SHALL retain the canonical handler,
cipher, save format, and corruption-preservation behavior.

#### Scenario: Reject profile mixing

- Given an interpreter bound to one engine profile
- When a caller selects the other profile
- Then selection fails before rebinding any paths or loading another campaign.

### Requirement: IsolateIosRuntime

The iOS adapter SHALL use separate shared content and private runtime trees.
It SHALL accept prepared host data and managed static/native layouts, use private
state and runtime policies, and hold an exclusive instance lock while initialized.
Initialization failure SHALL release the lock.

#### Scenario: Reuse data without importing its campaign

- Given prepared content containing an unrelated save
- When an iOS campaign initializes
- Then content and the unrelated save remain unchanged
- And the new campaign is stored under the private runtime root.

### Requirement: KeepDiagnosticsReadOnly

Doctor, status, rotation, verify-data, plan-data and verify-packs SHALL neither
import the engine state loader nor create files, initialize campaigns, download
assets, or start services. Malformed
saved data SHALL be reported without repair, quarantine, or replacement.

#### Scenario: Inspect an unconfigured installation

- Given missing data and no private runtime directory
- When diagnostics or calendar previews run
- Then missing prerequisites and a provisional calendar are reported
- And the filesystem remains unchanged.

### Requirement: InitializeCampaignExplicitly

The first InitializeRequest, or the explicit init-campaign command, SHALL persist
the replay anchor, immutable settings, and starting simulated friendships in one
canonical player-save operation. Reward-mail settings SHALL be recorded in that
candidate; mail delivery SHALL use a separate explicit synchronization command.
Home-carousel settings SHALL be recorded or backfilled in that same transaction
without changing an existing replay anchor.
It SHALL publish candidate state only after a successful save. Projections SHALL
read recorded facts without creating an anchor. Frozen or disabled persistence
SHALL not initialize a campaign.

#### Scenario: Retry after initialization

- Given an initialized campaign
- When initialization repeats after a request retry or process restart
- Then the original anchor and settings remain unchanged.

#### Scenario: Fail the initialization save

- Given a loaded campaign
- When its candidate initialization cannot save
- Then initialization reports failure
- And the original player and previous save remain authoritative.

### Requirement: PreserveReplayCalendar

The calendar SHALL start at December 16, 2016, roll over Sunday at 22:00 Eastern,
advance three historical weeks per real week until the historical week's start
reaches August 20, 2020, and advance two thereafter. Stopped-server time SHALL
count. Recorded settings SHALL take precedence over future default changes.

#### Scenario: Cross daylight saving time

- Given a week containing an Eastern DST transition
- When the next rotation boundary is computed
- Then the boundary remains Sunday at 22:00 local time.

### Requirement: ShareReplaySummonPolicy

The iOS rotation query, encrypted summon catalogue, drop-rate pages, and summon
commands SHALL use the same persisted calendar and banner selection policy.
They SHALL select Global release sets in the historical window, retain permanent
families with the pinned NV-era/dated-period gates, deduplicate calendar aliases,
and use the pinned holiday catch-up and deterministic post-history rotation rules.
The legacy catalogue SHALL retain its existing behavior.

#### Scenario: Inspect future summons before initialization

- Given no initialized iOS campaign
- When rotation previews several weeks
- Then all weeks use one provisional anchor and list their actual banner sets
- And no campaign, directories, counters, or runtime state are created.

#### Scenario: Submit an expired banner

- Given a client opened a banner before the Eastern weekly boundary
- When it submits the encrypted purchase request after the boundary
- Then the current catalogue contains the next historical release sets
- And the old request returns no award without changing balances, roster, or save bytes.

### Requirement: LimitHistoricalSummonPools

The iOS engine SHALL apply pinned unit-release metadata before distributing tier
weights and to explicit, step, secondary, mixed-reward, and guaranteed-slot pools.
Holiday featured units and one-off ticket pools SHALL retain the pinned exceptions.
Unavailable forced rewards SHALL decline before spending. Finite boxes and select
summons SHALL enforce the same eligibility. Missing/corrupt metadata SHALL fail
visibly rather than open future pools. A summon command SHALL require an already
initialized campaign; a query SHALL not initialize it.

#### Scenario: Guarantee cannot be fulfilled

- Given an eligible banner whose guaranteed reward is outside its allowed historical pool
- When a pull is attempted
- Then no currency or ticket is spent and no counter, box, or roster is changed.

#### Scenario: Filter a tier without changing its printed share

- Given a tier contains both released and future units
- When its pool is expanded
- Then future units are excluded before dividing that tier's rate among eligible units.

### Requirement: PreserveOneOffTicketExceptions

The iOS SP ticket bundles 990000108 and 990000109 SHALL be limited to one purchase
per campaign. Bundle 990000107 SHALL be unavailable. Already held plain SP tickets
SHALL retain the replay cutoff. Legacy bundle definitions SHALL remain unchanged.

#### Scenario: Retry a one-off ticket purchase after restart

- Given a campaign has purchased one of the one-off SP ticket bundles
- When the campaign reloads and the purchase is submitted again
- Then it is rejected before charging or granting another ticket.

### Requirement: SelectReplayVortexEvents

The iOS Vortex and archive menu SHALL use the saved replay calendar and pinned
event run/window metadata. Selection SHALL include the first-week 14-day lookback,
historical reruns, holiday event years, ranked periods, and deterministic recurring
and permanent dungeon rotations. Known closed captured gates SHALL be removed;
selected gates SHALL use the actual weekly bounds. Queries SHALL not create state
or download artwork. Additional authored areas SHALL require validated encounter
content and prepared native art or the shipped safe fallback. Legacy archive
behavior SHALL remain unchanged.

#### Scenario: Project a new historical week

- Given a captured response includes a future event and the campaign is in replay week zero
- When the Vortex is projected
- Then only eligible archive gates remain alongside unrelated gate rows
- And the selected gates carry the current Eastern week's UTC bounds
- And player data and save bytes remain unchanged.

### Requirement: LoadPinnedAuthoredEventAreas

The iOS catalogue and archive facade SHALL include the nine pinned history
additions, containing 118 unique missions, without altering the legacy catalogue.
Area/mission identities, first entries, and complete content inventories SHALL
be validated before gates are advertised. Their ordinary releases, reruns, and
Halloween windows SHALL use the same replay policy as existing events. News SHALL
deduplicate the two Halloween areas into one campaign announcement while Vortex
retains both distinct gates. Missing new art SHALL use the existing native fallback;
queries SHALL not fetch or install artwork.

#### Scenario: Open the Halloween Vortex

- Given an initialized iOS campaign whose saved history has reached the Halloween events
- When the real holiday window is active
- Then both Halloween gates appear with valid native art references
- And their News campaign is announced once without campaign or save writes.

### Requirement: IsolateAuthoredBattleReconstructions

Only the iOS profile SHALL load the pinned six-mission Halloween reconstruction
packet. Version, exact mission inventory, original wave count, phase identities,
battle groups, monster definitions, and positive HP SHALL be validated. Bad or
missing packets SHALL fail visibly without partially publishing content. Returned
bundles SHALL be private copies. Unrelated mission lookups and legacy paths SHALL
not require the new reconstruction packet. Existing canonical reconstructions,
original reward masters, and cache rules SHALL remain unchanged.

All 118 added missions SHALL retain the canonical exploration, non-combat story,
or battle-load path. Halloween results SHALL use canonical completion, challenge,
reward, switch, trust, and atomic iOS settlement handlers. Closed new entries SHALL
be refused before opening an attempt or spending; a pending attempt MAY resume and
settle after rollover. Retries/reloads SHALL not duplicate grants, and failed saves
SHALL preserve the original attempt and rewards.

#### Scenario: Finish a Halloween battle after rollover

- Given an authorized pending Halloween battle persisted before its week closed
- When the campaign reloads, resumes, and settles it
- Then original supported rewards are granted once
- And a repeated result grants nothing and a new closed entry remains unavailable.

### Requirement: ServePinnedExplorationEncounters

The iOS profile SHALL use all 248 finite exploration plans and 285 authored group
formations from the pinned source. Its five partial lineups SHALL retain their
declared omissions; 189 unresolved mission descriptions SHALL not acquire
invented plans. Unplanned missions SHALL use their canonical path. Map-script
boss groups and explicit group bindings SHALL remain present. Native encounter
rows SHALL carry per-field/per-group occurrence indexes and the referenced
monster/skill data without creating an opening combat phase. Budgets SHALL use
the pinned field-to-zone mapping, including Crystal Tower fields 70–75. The legacy
profile SHALL retain its existing behavior.

Future field battles SHALL roll their own drop candidates with the canonical
keep-one rule. Served drops SHALL retain at least four fields; empty drops SHALL
be omitted. Invalid candidates SHALL fail before an attempt is opened. Hypothetical
field fights SHALL not populate the normal drop ledger or grant inventory. Only
the client's reported completed fights/loot SHALL be credited by canonical
settlement, with existing completion/retry guards. Loading and deriving encounter
data SHALL not create disk caches or modify pinned source metadata.
Doctor SHALL report plan coverage and declared gaps without initializing state.

#### Scenario: Load an exploration before fighting

- Given a valid finite field encounter plan
- When its mission resource command runs
- Then map/script groups remain alongside the finite encounter rows, without an opening battle
- And no hypothetical enemy drops enter inventory or the normal result ledger.

#### Scenario: Load a partial multi-zone plan

- Given a pinned plan with distinct zone budgets or declared missing monsters
- When its field bundle is derived
- Then each native field receives only its matching zone's finite encounters
- And declared gaps remain visible without replacing scripted bosses.

### Requirement: RecordIosLootPolicyAndFixedBonuses

Campaign initialization SHALL record `EXVIUS_FIELD_ENCOUNTERS=1` and
`EXVIUS_CALAMITY_WRIT_DROP=0.5` defaults once. Missing settings SHALL backfill
atomically without changing the replay anchor. Writ chance SHALL be finite and
between zero and 100; field enablement SHALL be boolean. Existing settings SHALL
survive environment edits, and malformed settings or receipts SHALL fail without
repair. Disabling field plans SHALL retain the canonical scripted field path.

Each ordinary wave or planned future field drop row MAY append one supported
Calamity Writ, using an injected RNG and the recorded strict percentage chance
after the canonical keep-one roll. Missing policy, unsupported item masters,
non-live players, disabled persistence, and zero chance SHALL offer no bonus.
Forecast field rows SHALL never grant inventory or populate the normal drop ledger.

For capture and fixed Enlightenment missions, the resource-load command SHALL
record native drop rows and their Writ count with the existing pending attempt.
Reload SHALL reuse those recorded facts. A pre-port pending attempt without a
receipt SHALL not acquire a retroactive bonus. Successful settlement SHALL grant
exactly the recorded bonus alongside original capture/fixed rewards, ignoring
client-supplied Writ counts. Incomplete grants or save failures SHALL roll back
the entire result. Uncleared attempts SHALL grant no protected bonus. Retries
SHALL project the recorded result without changing saved echoes or paying again.
Normal and field loot SHALL retain canonical reported-loot settlement.

#### Scenario: Retry a protected chamber after reload

- Given a loaded capture or Enlightenment attempt with recorded rare loot
- When the campaign reloads, resumes, clears, and retries its result
- Then resume performs no new rare-loot roll, and the original bonus pays once
- And capture rewards and fixed stone quantities remain authoritative.

### Requirement: AuthorizeReplayEventEntry

New iOS event entries SHALL revalidate eligibility before opening an attempt or
spending stamina/orbs. A pending previously authorized attempt SHALL remain
resumable after rollover and retain the canonical settlement/retry protections.
An event command SHALL not initialize a missing replay anchor. Unrelated story
missions SHALL retain their existing entry behavior.

#### Scenario: Resume across rollover

- Given an event battle began before rollover
- When its pending resource load repeats after the event closes
- Then the same attempt can resume without creating another attempt
- And after settlement, another entry into the closed event is refused without save changes.

### Requirement: ApplyReplayExchangeEligibility

Custom exchange listings, labels, and purchases SHALL use current historical unit
eligibility. Native medal and Trust Coin purchases SHALL enforce that eligibility
before payment. A mixed batch containing an ineligible reward SHALL be refused
atomically. Event exchanges SHALL remain available while their event is active or
the campaign holds their currency. Summon-ticket exemptions SHALL not open future
exchange rewards. Weekly rollovers and restarts SHALL preserve stock receipts;
monthly resets SHALL use the campaign's recorded timezone. Refused purchases SHALL
not return a recorded success row or initialize a campaign.

#### Scenario: Reject an unreleased exchange reward

- Given a client requests an unreleased unit with sufficient payment
- When the encrypted exchange command executes
- Then the purchase is refused before charging or granting
- And the eligible listing, labels, and stock counts remain consistent.

#### Scenario: Redeem leftover currency

- Given an event has closed and its currency remains in the campaign
- When exchanges are projected
- Then that event's exchange remains available
- And spending the last currency leaves the closed exchange unavailable.

### Requirement: InitializeVortexSwitchesExplicitly

Campaign initialization SHALL persist the mission-switch container and the Vortex
unlock resolved from the shipped function/switch masters. An older initialized
campaign missing those switches SHALL be upgraded atomically by initialization
without replacing its replay anchor. Failed saves SHALL preserve the original
campaign. Projections SHALL derive a fresh empty mission container without writing.

#### Scenario: Backfill an older campaign

- Given an existing replay anchor without the Vortex unlock
- When initialization saves successfully
- Then only the missing initialization facts are persisted and the anchor is unchanged
- And repeated initialization does not save again.

### Requirement: LoadPinnedIosSummonDeals

The iOS catalogue SHALL merge pinned deal definitions and printed banner bonuses
before replay selection. Existing authored bonuses and stronger guarantees SHALL
be retained. Metadata loading and rotation previews SHALL not import engine state,
download artwork, or create files. The legacy catalogue SHALL remain unchanged.

#### Scenario: Add a printed multi-summon bonus

- Given an eligible banner whose secondary offer lacks a printed bonus
- When the iOS catalogue is projected and the secondary offer is purchased
- Then the printed bonus is listed and granted by that offer
- And its cost is charged once without changing the source banner definition.

### Requirement: ShareDealOfferAndPoolRules

iOS purchases and drop-rate pages SHALL resolve the same effective step/offer,
including pool overrides, weighted choices, counted guarantees, and extra slots.
Printed date ranges and limited/collaboration exclusions SHALL filter ordinary
pools before distributing rates. Explicitly named guarantees SHALL retain their
printed units while respecting the replay cutoff. Invalid or zero-weight mandatory
pools SHALL decline before spending. Daily limits and served bounds SHALL follow
the recorded timezone, including daylight-saving transitions.

#### Scenario: Keep an explicitly printed step guarantee

- Given a step-up's ordinary pool ends the day before its featured units arrived
- And a later step explicitly guarantees one of those units
- When the campaign has reached that release and the step is purchased
- Then the named guarantee is fulfilled while ordinary draws keep their printed cutoff.

### Requirement: StageIosSummonAwardsAtomically

The iOS command boundary SHALL stage payment, main rewards, bonuses, and counters
on a candidate player. Only a successful complete transaction SHALL publish the
candidate. A refused or failed grant SHALL preserve the original data and dirty
flag. Persistence SHALL retain the canonical save path and locking contract.

#### Scenario: Fail after granting a candidate unit

- Given an affordable iOS summon
- When granting a candidate unit or bonus fails after partial candidate changes
- Then the original balances, roster, stock counters, and save remain unchanged.

### Requirement: BoundResummonReplacement

iOS re-summon deals SHALL persist their remaining redos and the main result's
identity/snapshots. A free redo SHALL replace only unchanged, unused main units,
retain the paid-pull bonus, and leave the paid-purchase count and payment unchanged.
Missing, changed, or deployed main units SHALL prevent replacement. Native detail
and user rows SHALL project remaining redos without writes and refresh after a
purchase. Each accepted redo request consumes one attempt; no request nonce is
available for distinguishing a retransmission from another choice.

#### Scenario: Redo after a campaign reload

- Given a paid re-summon result and remaining free redos
- When the campaign reloads and an eligible redo is purchased
- Then the previous main units are replaced without accumulating results or bonuses
- And exhaustion prevents further redos or another paid purchase.

### Requirement: RedeemDealSelectTickets

NV select-ticket bonuses SHALL expose their native-master exchanges while tickets
are held. Exchange IDs, prices, purchase limits, and historical reward checks SHALL
remain stable across reloads. Spending the last ticket SHALL hide its exchange.
Ticket ownership SHALL not bypass the historical unit cutoff.

#### Scenario: Earn and redeem a select ticket

- Given an affordable deal whose printed bonus includes a select ticket
- When its encrypted purchase succeeds and that ticket is redeemed
- Then the ticket is granted once, spent at the master price, and the selected unit is credited
- And a paid-purchase retry or exhausted-stock redemption does not grant again.

### Requirement: InitializeSimulatedFriendsExplicitly

The iOS initialization command SHALL create the pinned deterministic crowd's
starting friendships once. Defaults SHALL be 200 generated accounts, 15 starting
friends, and 10 daily suggestions, in addition to configured YAML helpers. The
command SHALL record crowd size and suggestion count so later environment edits
cannot change an existing campaign. Initialization SHALL preserve previous
friend removals, favorites, replay anchors, and the canonical capacity limit.
An older campaign missing this checkpoint SHALL be backfilled atomically.

#### Scenario: Fail a friend backfill

- Given an existing replay anchor and a removed friend
- When the friend initialization candidate cannot save
- Then the original player and save remain unchanged
- And a successful retry preserves the anchor and the removal.

### Requirement: ProjectSimulatedFriendsWithoutWrites

Friend lists, search, details, suggestions, and companion lists SHALL be read-only.
Generated handles and ranks SHALL retain the pinned deterministic seeds. Helpers
SHALL rotate with the saved calendar's real week and use named, renderable shipped
forms from character families currently owned in the roster, including storage.
Family identity SHALL use `F_UNIT_MST.woghJa61`, not display names; separately
released variants SHALL remain separate families. Temporary guests, material units,
standalone Brave Shift rows, and statless placeholder masters SHALL be excluded.
Forms SHALL respect the historical cutoff, using their own release date or the
family root's date when no form date exists. Rank SHALL NOT restrict eligible
rarities. Generated levels SHALL use the existing rarity suggestions (otherwise
the form maximum), capped by the form maximum and the highest owned family level.
Duplicate copies SHALL NOT weight selection. Daily suggestions SHALL exclude
existing relationships and use the saved calendar timezone, including DST.
Projections SHALL neither seed missing friendships nor consume global gameplay RNG.
Every projection SHALL reflect the current roster and levels without a migration.
Curated friends SHALL keep eligible configured units at their configured level,
capped by the same form and owned-family limits. Otherwise their identities SHALL
receive deterministic weekly eligible replacements with bare equipment, abilities,
card and esper slots, and valid default Limit Burst levels. Cached YAML SHALL NOT
be changed. With no eligible forms, projections SHALL emit empty friend/companion
rows without an unowned fallback or changes to stored relationships or gift receipts.

#### Scenario: Read native social pages

- Given an initialized campaign
- When encrypted friend, suggestion, search, and reinforcement requests run
- Then they return complete native rows for the current relationships
- And campaign data and save bytes remain unchanged.

#### Scenario: Borrow another form of an owned character

- Given a lower-rarity owned unit and a higher-level stored copy in the same family
- When friend lists, search, details, suggestions, boot and companion lists are projected
- Then every helper belongs to an owned family and respects its highest owned level
- And eligible forms vary deterministically by friend and week without duplicate-copy weighting.

#### Scenario: Lose the last owned copy

- Given friends lending units from an owned family
- When the last copy is sold or consumed and the next projection runs
- Then that family is absent, including after reload
- And an empty eligible pool clears display rows while preserving stored friendships.

### Requirement: PersistIosFriendCommands

iOS requests and agreements with known local players SHALL accept immediately,
subject to the canonical capacity limit. Favorites and removal tombstones SHALL
persist across reloads. Retried commands SHALL not duplicate relationships or
invite quest progress. Each command SHALL stage and save its candidate before
publishing it. Frozen, unknown, self, invalid-category, and over-capacity commands
SHALL leave the campaign unchanged. Legacy friendship behavior SHALL be retained.

#### Scenario: Remove a generated or curated helper

- Given an accepted friend
- When the friend is removed and the campaign reloads or initializes again
- Then the friend remains absent from accepted and companion lists
- And a later explicit request may restore the friendship.

### Requirement: GiftAcceptedIosFriends

The canonical gift transaction SHALL accept currently accepted iOS friends,
including generated accounts. Removed or unknown recipients SHALL be refused.
Existing per-friend UTC-day reciprocal limits, receipt ownership, atomic batch
validation, quest/archive progress, and one-time collection SHALL be preserved.

#### Scenario: Retry a generated friend's gift

- Given an accepted generated friend
- When a gift is sent repeatedly and its reciprocal receipt collected after reload
- Then one send and one reciprocal receipt are recorded for the UTC day
- And collecting the same receipt again grants no additional reward.

### Requirement: ProjectHistoricalArenaLadder

With the simulated crowd enabled, iOS Arena SHALL use the shipped weekly season
running at the start of the historical slice, or the last shipped season after
history finishes. Rival teams SHALL contain up to five distinct, named,
renderable, historically eligible base units from the original rank-based pool,
independent of companion ownership and level restrictions. When the generated
crowd is disabled, accepted curated rivals SHALL retain their original configured
units and levels, including during matching and battle startup.
The pinned strength, gear, weekly target, pace, tie ordering, and Global placement
scale SHALL be preserved. Ratios SHALL range from 0.50 to 1.50 in steps of 0.05.
Five opponents SHALL refresh every ten minutes by default; ranking SHALL show
the top 100 accounts and the player's own row. Global gameplay RNG SHALL be untouched.
Elapsed-time scoring and displayed week boundaries SHALL account for Eastern DST.

#### Scenario: Change owned units without changing Arena rivals

- Given generated opponents or the curated fallback roster
- When owned families or levels change
- Then Arena retains its original rival units and levels
- And friend/companion projections independently apply ownership and family level caps.

#### Scenario: Inspect a moving leaderboard

- Given an initialized Arena week
- When ranking or restart is requested, including after the week ends
- Then the recorded week and points are projected without rewards, rollover, or save writes
- And pending battle snapshots retain their original season and opponents.

### Requirement: SettleArenaWeeksExplicitly

RbEntryRequest SHALL be the explicit Arena initialization and rollover command.
It SHALL record ladder configuration once, with default top score 12000 and five
rivals. A completed played week SHALL settle against its own season and final
leaderboard, map local placement onto Global's 300000-rank scale, and credit the
original master rewards once. The settled points SHALL move into lifetime totals
before weekly points reset. Empty skipped weeks SHALL not grant rewards. Missing
or unsupported rewards SHALL preserve the unpaid week for retry. An active battle
SHALL delay rollover until it settles. Clock rollback or malformed recorded week
data SHALL not reset or repair the campaign.

#### Scenario: Return after several weeks away

- Given a played week with positive points
- When a later Arena entry occurs after several weeks away
- Then only the recorded played week receives its placement reward
- And repeated entry or reload neither grants it again nor changes the saved configuration.

### Requirement: CommitArenaBattlesAtomically

Matching SHALL persist rival members, ratio, AI, and initiative before starting.
Repeated matching, starting, and settlement SHALL reuse the recorded battle.
Full-team settlement and retirement SHALL validate every started member. The
canonical streak, bonus, medal, daily reward, archive, and all-orb consumption
rules SHALL be retained, with wins using the snapshotted ratio as base points.
iOS initialization, rollover, matching, start, end, and medal-board mutations SHALL
save a staged candidate before publishing changes. Save failures SHALL preserve
the previous campaign, balances, orbs, rewards, and pending battle. Existing
pre-ladder pending battles SHALL finish before their all-time points migrate.
Legacy Arena behavior SHALL remain unchanged; disabled iOS crowds SHALL retain
curated single-unit opponents and the existing participation reward policy.

#### Scenario: Fail a battle settlement save

- Given a started five-unit rival battle
- When settlement cannot save
- Then the original pending battle and campaign remain authoritative
- And a successful retry grants its result once.

### Requirement: DeliverIosRewardMailExplicitly

The iOS profile SHALL mail the pinned weekly summon gift (ten Rare Summon Tickets
and one Guaranteed Ticket) once per saved-calendar rotation week. Returning after
several weeks SHALL deliver the current week's gift only. The four pinned Global
replay mails SHALL become due when their dates fall before the historical window's
exclusive end. Appreciation quantities SHALL use the pinned inclusive days-played
brackets measured from the saved replay start. Configuration SHALL be recorded
once and retained across process-default changes.

InitializeRequest and RoutineHomeUpdateRequest SHALL explicitly synchronize due
mail with a staged save before publishing it. MailListRequest, diagnostics, and
reward previews SHALL never initialize settings, issue mail, or grant attachments.
Delivery SHALL add inbox entries only; inventory SHALL change on receipt.
The native inbox counters SHALL reflect committed mail on login/home replies.
Frozen, ephemeral, or disabled-persistence commands SHALL not grant rewards.

#### Scenario: Return after several weeks

- Given a previously synchronized campaign
- When a later login or home synchronization reaches additional history
- Then one current weekly gift and all unissued due historical mails are delivered
- And repeated synchronization leaves the inbox, issue ledger, and save bytes unchanged.

### Requirement: PreserveRewardMailIdentity

Reward issue keys SHALL be durable independently of inbox entries. Claiming,
deleting, reloading, or rolling the clock back SHALL not reissue delivered gifts.
The original replay mail IDs SHALL remain logical content keys. Numeric inbox
IDs SHALL avoid both canonical catch-up mail IDs and future automatic allocations.
Malformed settings, conflicting/missing delivery facts, and unsupported or
invisible native attachments SHALL be refused without resetting the ledger.
Diagnostics SHALL report malformed saved delivery data without repair.

#### Scenario: Mix reward and existing mail

- Given catch-up mail and automatically numbered Arena mail
- When weekly and replay gifts are delivered, received, and deleted
- Then every native mail ID remains distinct
- And issue records prevent duplicate delivery even when the inbox is empty.

### Requirement: CommitIosMailReceiptsAtomically

iOS mail receipt and deletion SHALL reuse the canonical parsing, inventory,
metadata, and ownership rules, but stage changes and save before publishing them.
Duplicate receipts SHALL grant nothing. Delivery or receipt save failures SHALL
preserve the previous inbox, issue ledger, and inventory so retry can succeed.
Legacy mail behavior SHALL remain unchanged.

#### Scenario: Fail a receipt save

- Given an unreceived gift
- When receipt cannot save
- Then neither its attachments nor its received marker are published
- And a successful retry grants the attachments once.

### Requirement: RecordIosEconomyAndDailyFacts

The iOS profile SHALL record the earned-Lapis multiplier, original daily reward,
completion bonus, custom-quest switch, and selection count in the campaign.
Defaults SHALL be 5, 150, 200, true, and 5 respectively. Recorded settings SHALL
survive environment changes. Invalid saved settings or daily snapshots SHALL fail
visibly without reset. Initialization MAY backfill missing settings while preserving
the replay anchor and existing daily receipts.

Daily selection SHALL match the pinned day-seeded pool shuffle, with distinct
actions and five quests by default. An explicit daily update, login/home, or relevant
gameplay command SHALL freeze the selected definitions, native reward metadata,
actual reward amounts, and completion bonus. Selection SHALL not consume gameplay
RNG. A same-day pre-port set and its claims SHALL be retained.

#### Scenario: Restart after changing defaults

- Given a recorded daily set and economy
- When the process restarts with different environment defaults
- Then the day's displayed rewards and claim amounts remain the recorded amounts
- And selection and diagnostics do not mutate the campaign.

### Requirement: SeparateDailyQueriesAndClaims

Daily screens SHALL project recorded progress and rewards without rolling a day
or granting inventory. Days and countdowns SHALL use the saved campaign timezone
and actual seconds across DST. Queries after midnight SHALL report an expired set
without rewriting it. Clock rollback SHALL not recreate an earlier day. Gameplay
SHALL score successful canonical actions using their existing completion/receipt
guards, rather than merely receiving a request.

Claims SHALL require current-day completed, unclaimed quests and live persistence.
They SHALL stage all grants and receipts, including the once-per-day completion
bonus, and save before publishing. Unsupported rewards, incomplete grants, or save
failures SHALL preserve the prior campaign. Rewards SHALL retain trust-moogle
metadata. Duplicate, unknown, incomplete, stale, frozen, or ephemeral claims SHALL
grant nothing. Claims SHALL not implicitly roll to a new day.

#### Scenario: Fail the completion bonus

- Given all selected quests are complete
- When claim-all cannot grant or save the completion bonus
- Then no daily reward or claim marker is published
- And retry can grant the entire set and bonus once.

### Requirement: ConvertEarnedLapisAtCreditAndProjection

Earned Lapis SHALL use the recorded multiplier. Purchases, refunds, direct balance
edits, and already-normalized daily grants SHALL bypass conversion. Canonical
reward return values and receipt rows SHALL retain their source denomination.
Native earned-reward projections SHALL display the converted amounts without
changing source payloads or multiplying retries again. Mission reward wrappers
and unit metadata SHALL survive projection. Item-drop channels SHALL retain their
existing interpretation. Legacy grants and projections SHALL remain unchanged.

Native master conversion and custom daily text SHALL be pure preparation inputs;
queries SHALL not write shared tables. Explicit preparation SHALL install custom
daily text and converted challenge/Arena master displays into a private snapshot.
Gameplay asset routing and visual device acceptance remain later checkpoints.

#### Scenario: Buy Lapis while earned Lapis is boosted

- Given a saved multiplier of five
- When an earned 100-Lapis mail and a purchased 5,000-Lapis bundle are claimed
- Then the mail displays and credits 500 Lapis once
- And the bundle credits exactly 5,000 Lapis with its original charge and stock limit.

### Requirement: RevalidateIosDatedBundles

The iOS catalogue SHALL use the pinned bundles, including Bonus Present Ticket
and twelve Hill of Fortune runs. Historical sale periods SHALL overlap the saved
replay window using its exclusive end. Expired dated runs SHALL not return after
history ends. Lists and purchases SHALL apply the same availability and stock
rules, removing stale captured rows. Daily stock dates SHALL use the saved timezone.
Purchase commands SHALL stage the original contents, charge, and stock receipt and
save before publishing. Failures and stale/sold-out selections SHALL not spend.
Legacy bundle definitions SHALL remain unchanged.

#### Scenario: Submit a stale bundle purchase

- Given a previously visible dated bundle
- When replay rollover closes its sale period before purchase
- Then purchase is refused without changing the balance, inventory, limit, or save.

### Requirement: RecordIosQuestTrust

Campaign initialization SHALL record the pinned quest-trust settings once:
enabled, 30 percent hit chance, 10 points per hit, 5 percent chance of upgrading
a hit, and 50 points for an upgraded hit. Percentages SHALL support hundredths;
1000 trust points SHALL represent 100 percent. Saved settings SHALL survive
environment changes. Missing settings MAY be backfilled atomically without
moving the replay anchor. Invalid defaults or saved settings SHALL fail visibly
without reset. Diagnostics and planning SHALL neither initialize nor save.

#### Scenario: Backfill an existing campaign

- Given an anchored campaign without recorded trust settings
- When explicit initialization succeeds
- Then trust settings are saved without changing the replay anchor or previous rewards
- And later initialization retains those settings despite changed process defaults.

### Requirement: RollTrustOncePerClearedAttempt

An eligible own-party unit SHALL roll independently once per successfully cleared
loaded attempt, including a clear granting zero EXP. A large hit SHALL replace
the normal gain and cap at the unit's own trust requirement. Mastered units,
Trust Moogles, missing units/descriptors, and nonpositive requirements SHALL not
roll. Defeats, exploration exits, zero-wave story scenes, and duplicate result
requests SHALL not roll. Friend helpers SHALL not gain. Planning SHALL not mutate
the campaign or consume global gameplay RNG. Disabled trust, zero ordinary gain,
or zero hit chance SHALL grant nothing. Legacy master-defined rates and expedition
and fusion trust rules SHALL remain unchanged.

The canonical trust operation SHALL credit original mastery rewards once using
the existing shared fusion/quest receipt. Native result field nine SHALL show
the actual capped before/after trust, including when EXP is zero. Daily trust
progress SHALL count units that actually gained trust once per attempt.

#### Scenario: Cap a large hit at mastery

- Given an own-party unit with 995 of 1000 trust points
- When a cleared attempt rolls a 50-point hit
- Then the unit reaches 1000, the native result shows 995 to 1000, and its original mastery item is granted
- And retrying after reload neither rolls again nor grants another item.

### Requirement: CommitIosNormalBattleResultsAtomically

After explicit daily synchronization, MissionEndRequest SHALL stage the canonical
result pipeline on a candidate player. Trust, mastery rewards, quest progress,
other completion effects, the attempt receipt, and the source-denomination result
echo SHALL save together once before publication. Grant, later projection, or
save failures SHALL preserve the previous player, dirty flags, and campaign save.
Frozen/ephemeral players and disabled persistence SHALL be refused without
mutations. The existing mission-load attempt identity and delayed-retry limits
SHALL remain the wire contract.

#### Scenario: Fail after planning a mastery award

- Given a pending battle that will reach mastery
- When a reward, later result projection, or final save fails
- Then the previous trust, inventory, daily counters, attempt, and echo remain authoritative
- And a successful retry may settle that attempt once.

### Requirement: RecordReplayNoticeSettings

Explicit campaign initialization SHALL record notice enablement and retained-list
length once, defaulting to enabled and eight weeks. Retention SHALL be bounded
to 1–52 weeks. Existing campaigns MAY backfill missing settings atomically without
changing their replay anchor or read receipts. Saved settings SHALL take precedence
over process defaults; malformed settings or receipts SHALL fail visibly without
reset. Diagnostics SHALL validate without repair or engine imports.

#### Scenario: Backfill notice configuration

- Given an anchored campaign with existing native read receipts and no notice settings
- When initialization saves successfully
- Then it adds only the missing settings without changing the anchor or receipts
- And a failed save preserves the previous campaign.

### Requirement: ProjectReplayNewsWithoutWrites

NoticeUpdateRequest SHALL list the current and previous retained replay weeks,
using pinned notice IDs starting at 880000 and native read indexes starting at
500. The display date's UTC year SHALL namespace read masks. Wire dates SHALL
represent saved-timezone rollover and actual DST duration. Captured replay rows
SHALL be replaced, including when notices are disabled. Missing initialization
or a clock before the anchor SHALL not create notices or state.

Each week's summary SHALL use the same canonical iOS summon and event policies
as gameplay, including holiday and post-history rotation. Deals, newly opened
dated permanent offers, dated bundles, and enabled historical mails SHALL use the
historical window's exclusive end. Gift quantities SHALL use the saved replay
start. Queries SHALL not consume gameplay RNG, grant inventory, initialize saves,
record catalogue indexes, or deliver mail. Only validated authored additions
SHALL be included in the canonical catalogue.

#### Scenario: Inspect News after rollover

- Given a saved campaign with a read notice older than the retained list
- When encrypted News and native user-state queries run after rollover
- Then the board lists the current retained weeks and preserves the old read mask
- And the campaign and save bytes remain unchanged.

### Requirement: PersistIosNoticeReadsExplicitly

NoticeReadUpdateRequest SHALL stage accepted read IDs and their native year/index
coordinates, validate the response projection, and save before publication.
Known static notice identities and existing read receipts SHALL be preserved.
Unknown, malformed, future, and disabled replay IDs SHALL not accumulate receipts.
Frozen/ephemeral players SHALL not record reads; disabled persistence SHALL be
refused. Duplicate reads and reloads SHALL not create additional writes. Saved
coordinates SHALL take precedence over later captured catalogue changes. Wire
read masks SHALL reflect the campaign, clearing unrelated captured flags.
Save or projection failures SHALL preserve the previous player, receipts, and
save. Legacy catalogue indexing and read-mask behavior SHALL remain unchanged.

#### Scenario: Retry a read after a failed save

- Given an unread replay notice
- When its read-receipt save fails
- Then its read marker is not published
- And retrying successfully records it once, surviving reload and year rollover.

### Requirement: RenderReplayNoticePagesLocally

The canonical content adapter SHALL serve `/exvius/notices/<week>.html` for elapsed
iOS replay weeks, including weeks outside the retained list. Future, negative,
malformed, uninitialized, disabled, and legacy requests SHALL not reveal a replay
page. GET and HEAD SHALL share content length, with HEAD returning no body.
Pages SHALL escape catalogue text, summarize native offer facts and original
rewards, and use local artwork URLs only. Unsafe artwork names SHALL be omitted;
missing images SHALL retain readable text. Page requests SHALL not fetch or cache
art, write saves, mark notices read, or grant gifts. Existing CDN containment
checks SHALL remain authoritative for the referenced artwork. Preparing missing
art and replay home banners remains a later asset/hosting task.

#### Scenario: Open an archived notice

- Given an elapsed notice outside the eight-week News list
- When its page is opened or requested with HEAD
- Then it shows that week's canonical content with local artwork references
- And neither the campaign nor shared content changes.

### Requirement: SeparateViewCachingFromPreparation

iOS battle views SHALL read existing caches or derive in memory without writing
disk caches. Explicit preparation MAY persist under the private cache root.
Legacy callers SHALL retain their existing cache behavior.

### Requirement: PrepareCoreNativeTablesExplicitly

The prepare-data command SHALL reuse prepared or managed static/native inputs
read-only, without loading an engine/campaign or starting services/downloads.
It SHALL acquire the private runtime's exclusive instance lock and publish a
364-table snapshot for the supported Global-1167 corpus: 219 JSON masters and
145 English localized tables. The packaged registry SHALL record corroborated
names, filename tokens, keys and cipher modes. Positive native preference
registrations SHALL match this complete inventory. Missing/unknown registrations,
unmapped source tokens or missing sources SHALL fail before publication.
Earlier seven- and 35-table snapshots SHALL remain valid for inspection and
atomic upgrade; incomplete new inputs SHALL preserve them.

Preparation SHALL use each registered CBC/ECB master or ECB localized-text format,
preserve source padding layers and text columns, and emit LF between encrypted
lines. Passthrough tables SHALL retain their encrypted records. Invalid encryption, unsupported row shapes, missing required tables, or
English source checksum/size mismatches SHALL fail before publication. Existing
shipped text records, including duplicate keys, SHALL remain unless explicitly
replaced by a declared native label rule.

Both tutorial resource packs SHALL download up front; resource rows with no base
or English file version SHALL be excluded. Quest reward visibility SHALL be shown
without changing amounts or extra metadata. The Drop Rates URL SHALL point to
the pinned v910 WebView route while preserving unrelated URLs and empty values.
All 22 custom daily quest names/details SHALL be added to their English tables.
The localized index SHALL advertise their final versions, MD5s, and byte sizes
while preserving other languages and unrelated rows.

The command SHALL validate staged outputs, persist checksums/provenance, and
atomically replace one active-generation pointer. Files SHALL remain inside the
private runtime. Identical inputs SHALL reuse the current generation; changed
inputs or transformation revisions SHALL advance versions monotonically.
Each version SHALL exceed its source and persisted registration floor. If a floor
decreases, generation selection SHALL still exceed the prior published versions.
Interrupted writes SHALL leave the previous generation available; retries MAY
reuse a matching complete unpublished generation. Corrupt published facts SHALL
fail visibly without repair. No source data, real save, or active service SHALL
be changed by preparation.

#### Scenario: Interrupt snapshot publication

- Given a valid prepared generation and changed preparation inputs
- When a table write or active-pointer replacement fails
- Then the old generation remains available with its original versions and bytes
- And a retry can publish the new generation without rewriting the old one.

#### Scenario: Preserve unregistered localized metadata

- Given the five declared English index names without registered client mappings or files
- When the complete snapshot is prepared
- Then those original index rows remain unchanged and are reported as unregistered
- And they acquire no invented table files or advertised prepared versions.

### Requirement: VerifyNativeTableBytesReadOnly

The verify-data query SHALL validate the active pointer/manifest, exact table
paths, versions, byte sizes, SHA-256/MD5 checksums, native decoding, and localized
index references. It SHALL detect changed source inputs or preparation rules
without rewriting files, creating directories/caches, or initializing campaigns.
Missing and corrupt preparation SHALL be reported distinctly.

Verified snapshots SHALL provide exact published-path lookup and a private
version-response projection. Complete snapshots SHALL advertise each published
identity once and omit unknown identities; older partial snapshots SHALL retain
their existing overlay behavior.
New preparation and verification SHALL report scope native-tables and
gameplay_ready false. Full native gameplay hosting, remaining art/audio/story
compatibility and device acceptance are pending.

#### Scenario: Inspect prepared native files

- Given a valid snapshot whose source inputs are unchanged
- When verify-data runs and its versions are projected for an asset consumer
- Then every advertised snapshot version resolves to its validated bytes
- And text MD5s/sizes agree with the localized index without filesystem writes.

### Requirement: DeliverPreparedNativeTablesExplicitly

An explicit Engine(config, prepared=True) consumer SHALL require a current complete
snapshot and the selected campaign's recorded economy policy before importing
the state loader. Missing, partial, corrupt, stale or provisional preparation SHALL
fail and release the runtime lock without initializing a campaign. The running
hello service and default engine adapter SHALL retain their existing behavior.

Only the iOS profile with the bound verified snapshot SHALL project its complete
versions after canonical forced-version handling. GET/HEAD under mst/ and
localized_texts/en/, for a prepared Vortex pack, and for bound iOS sounds, SHALL return exact published bytes and sizes. An absent version
SHALL return 404 without a stock/token fallback. HEAD SHALL omit the body. Path
validation SHALL precede lookup. Delivery SHALL not write files, refresh sources,
download assets or change campaign facts. Closing the engine SHALL unbind it.

#### Scenario: Deliver every encrypted initialization version

- Given an initialized campaign and current schema-3 preparation
- When the opt-in engine answers encrypted initialization and table GET/HEAD requests
- Then all 364 unique table versions resolve to the snapshot bytes
- And canonical global master/resource/app version rows retain their original values
- And stale/unknown paths return 404 and traversal returns 400 without query writes.

### Requirement: PrepareVortexArtworkExplicitly

The prepare-data command with --vortex-art SHALL build the English spdungeon1.cpk
from shared native inputs and available canonical event, dungeon, added-event and
raid artwork. Later refreshes SHALL retain that enabled feature. Collection SHALL
hash source bytes and metadata, enforce containment and validate image structure.
Missing required art SHALL fail; missing added-event images SHALL remain reported
gaps using the existing common-pack fallback without invented art or downloads.

- **Implementation**: `collect::source/ios_server/vortex_art.py`

#### Scenario: Add an image after a reported gap

- Given an added-event image was unavailable during preparation
- When that image becomes available and preparation runs again
- Then its content enters the new pack and the reported gap clears
- And old generations remain unchanged.

### Requirement: PreserveNativeBannerPackLayout

The pure CPK builder SHALL preserve every original file payload, compression
metadata, ID and duplicate shipped filename. Additions SHALL not replace names
already present case-insensitively. Rebuilt archives SHALL use masked native UTF
tables, sorted TOC names, TOC-relative offsets, eight-byte payload alignment and
correct file/content sizes. UTF null-string cells SHALL retain the reserved
string-pool offset zero, including the TOC's constant UserString field. Encoder
revisions SHALL invalidate artwork provenance so explicit preparation publishes
a new native pack version even when source images are unchanged.
Truncation, directories, unsupported indexes or CRC
layouts SHALL fail visibly before publication.

- **Implementation**: `rebuild::source/ios_server/cpk.py`
- **Implementation**: `inspect::source/ios_server/cpk.py`
- **Implementation**: `encode_table::source/ios_server/cpk.py`

#### Scenario: Preserve compressed original entries

- Given a flat source pack with compressed entries and duplicate original names
- When archive images are appended
- Then original payload bytes, IDs and extract sizes remain intact
- And the rebuilt pack has valid masked metadata, sizes and aligned offsets.

#### Scenario: Preserve reserved null-string cells

- Given a native UTF table with constant and per-row null-string cells
- When the table is encoded
- Then those cells reference string-pool offset zero
- And ordinary filenames reference their own nonzero offsets.

### Requirement: PublishVortexPackWithItsResourceTables

Schema-4 preparation SHALL atomically publish the pack with all 364 tables.
Resource 6108101 SHALL have upfront class TUTO, the pack's English file version
and its exact byte size. Pack and table versions SHALL advance monotonically,
including after a source version decreases; overflow SHALL fail. Schema-1/2/3
snapshots SHALL remain inspectable and upgrade without losing prior generations.
Failed builds or publication SHALL preserve the active pointer.

- **Implementation**: `prepare::source/ios_server/vortex_art.py`

#### Scenario: Interrupt pack publication

- Given a valid table snapshot and Vortex preparation enabled
- When writing the pack or replacing the pointer fails
- Then the old generation remains authoritative
- And a retry can reuse complete unpublished files and publish consistent tables and pack.

### Requirement: VerifyAndDeliverVortexWithoutPreparation

Verification SHALL validate pack paths, bytes, hashes, layout and agreement with
the recorded resource tables, and detect stale source art or metadata without
building a pack, writing files or importing the engine. The prepared engine SHALL
serve exact Vortex GET/HEAD bytes and refuse unpublished versions without stock
fallback. Hello-only hosting, unrelated assets and legacy behavior SHALL remain.

- **Implementation**: `load::source/ios_server/vortex_art.py`

#### Scenario: Request a stock Vortex version

- Given an opt-in iOS engine bound to a schema-4 snapshot and a stock pack on disk
- When the client requests the old pack version
- Then it receives 404 rather than stock bytes
- And exact GET/HEAD requests match the snapshot without filesystem or campaign writes.

### Requirement: PrepareSummonDetailArtworkExplicitly

The prepare-banners command SHALL use the private runtime lock and publish a
separate immutable artwork generation without changing native table/CPK versions.
It SHALL collect current catalogue overrides, locale variants and step extras
without engine imports, downloads or campaign writes. Exact native URLs SHALL
precede contained extracted/community basename sources. Missing art SHALL be
reported and remain unrenamed; corrupt or escaping sources SHALL fail visibly.

- **Implementation**: `collect::source/ios_server/banner_inputs.py`
- **Implementation**: `prepare::source/ios_server/banner_snapshots.py`

#### Scenario: Supply an unavailable banner image

- Given a detail image is missing and listed in the preparation report
- When that image arrives and prepare-banners runs
- Then both frame variants are published and its gap clears
- And unrelated content filenames and prior generations remain intact.

### Requirement: FitSummonImagesToNativeFrames

Fitting SHALL use the pinned blur2 policy, preserving native source scale on a
centered blurred/darkened canvas. Paid/layout-1/2 frames SHALL use 640:183;
layout-0/base frames SHALL use 640:392. Images within six percent of the target
ratio SHALL retain their exact input bytes. Both variants SHALL be prepared for
each available source PNG. Output names SHALL contain the complete output SHA-256;
list artwork SHALL remain unchanged.

- **Implementation**: `render::source/ios_server/banner_fit.py`

#### Scenario: Keep lettering at native scale

- Given a 640 by 392 detail image for a paid summon
- When it is prepared
- Then the image is centered without scaling in a 1371 by 392 canvas
- And its base-frame variant retains the original bytes.

### Requirement: VerifySummonSnapshotsWithoutRendering

Artwork verification SHALL validate the pointer, manifest, complete variant
inventory, output content names, PNGs, dimensions and hashes without rendering or
writing. Source bytes, catalogue documents, pipeline and renderer version SHALL
participate in freshness. Corrupt facts SHALL not be repaired. Failed preparation
or pointer publication SHALL preserve the active generation and support retry.

- **Implementation**: `load::source/ios_server/banner_snapshots.py`
- **Implementation**: `verify::source/ios_server/banner_snapshots.py`

#### Scenario: Detect a same-size source edit

- Given a valid artwork generation
- When a source PNG changes without changing its byte size
- Then verification reports staleness without changing files
- And explicit preparation publishes new content names only for changed outputs.

### Requirement: DeliverPreparedSummonNamesReadOnly

An opt-in prepared engine SHALL bind current artwork if present and refuse stale
or corrupt artwork before state imports, releasing its lock on failure. Summon
entry, step/result and box refreshes SHALL use actual wire layouts to rename only
prepared detail/carousel references. Missing names and bare list fields SHALL
remain unchanged. Closing SHALL clear the binding. Legacy and unprepared paths
SHALL retain their wire and gameplay behavior.

- **Implementation**: `Banners::source/ios_server/banner_snapshots.py`

#### Scenario: Use the same image on different summon layouts

- Given a source image is used by both a base and a paid summon
- When their native groups are projected
- Then each detail references the correct prepared frame variant
- And costs, rewards, counters, layouts and list images remain unchanged.

### Requirement: ServeFittedImagesWithoutPreparation

Prepared artwork GET/HEAD SHALL use only the bound snapshot bytes for its
content-addressed filenames and supported native URL prefixes. HEAD SHALL omit
the body; unknown prepared names SHALL return 404 without stock fallback. Path
validation SHALL run first. Reads SHALL not fit images, download, write caches or
change campaigns. Canonical API request recording SHALL retain its existing path.

- **Implementation**: `serve::source/ios_server/banner_delivery.py`

#### Scenario: Request an unknown fitted image

- Given a prepared engine with verified artwork
- When a client requests an unpublished fitted filename
- Then it receives 404 without fallback or source lookup
- And valid GET/HEAD requests match the published bytes, length and PNG type.

### Requirement: PrepareSoundBanksExplicitly

The system SHALL provide prepare-sounds independently from native table and
artwork preparation. It SHALL read the original encrypted resource/version/size
masters for both resource families, require positive exact file versions, prefer
supported native iOS banks and record all source hashes and identities. Missing
exact versions SHALL fail without highest-version substitution. Original zero
or stale size metadata SHALL remain recorded alongside measured bank lengths.

- **Implementation**: `collect::source/ios_server/sound_inputs.py`

#### Scenario: Reuse an exact sound bank

- Given two resource records naming the same exact sound bank
- When sound preparation resolves them
- Then it records both resource identities and one source bank
- And reports size discrepancies without changing shared masters.

### Requirement: ConvertPinnedSoundWithoutReencoding

Android sound preparation SHALL remove keyless HCA type-1 encryption and change
HCA-MX waveform flags to HCA, preserving byte lengths and unrelated bytes.
It SHALL validate bounded UTF and AFS2 structures and all HCA header/frame CRCs
before mutation. Unsupported keyed ciphers, encodings, external AWB dependencies
or corrupt streams SHALL fail visibly. Supported native iOS banks SHALL remain
byte-identical. Accelerated CRCs SHALL match an independent bitwise oracle.

- **Implementation**: `prepare::source/ios_server/sound_codec.py`

#### Scenario: Encounter a damaged last frame

- Given a bank with valid earlier streams and a corrupt final frame
- When sound preparation runs
- Then it rejects the bank without publishing or mutating the source
- And a valid bank converts to the pinned fork's exact output bytes.

### Requirement: PublishFileBackedSoundGenerations

Sound commands SHALL process one bank at a time under the exclusive private
runtime lock and publish immutable files through assets/sounds/current.json.
All outputs and a second input inventory SHALL validate before pointer replacement.
Repeated inputs SHALL reuse the generation. Build or publication failure SHALL
preserve the previous pointer, and complete unpublished generations SHALL support
retry. Shared data, campaigns, table versions and engine routing SHALL remain.

- **Implementation**: `prepare::source/ios_server/sound_snapshots.py`

#### Scenario: Interrupt sound publication

- Given an existing sound generation and changed source bytes
- When pointer replacement fails
- Then the old generation remains authoritative
- And retry can validate and reuse complete unpublished artifacts.

### Requirement: VerifySoundsWithoutPreparation

verify-sounds SHALL validate recorded paths, hashes, lengths, waveform counts,
native format checks and current input freshness without conversion, writes,
locks, downloads, engine imports or campaign initialization. Missing and corrupt
snapshots SHALL be distinct visible failures. Escaping source/output symlinks
SHALL be rejected. The artifact-only sound report SHALL declare delivery_ready
false; coordinated native table reports SHALL expose sound_delivery_ready true.
The pinned disabled story-text rewrite SHALL remain disabled.

- **Implementation**: `verify::source/ios_server/sound_snapshots.py`

#### Scenario: Verify a same-size source edit

- Given a prepared sound generation and changed source bytes of the same length
- When verification runs
- Then it reports stale inputs without creating or repairing files
- And no engine or campaign state is loaded.

### Requirement: CoordinateSoundVersionsAndSizesAtomically

prepare-data --sounds SHALL require current explicit sound preparation and publish
schema 5 with all 364 native tables and a pinned sound-generation directory and
manifest SHA-256. Both resource families SHALL advertise common sound versions and
measured iOS sizes. Other languages, Android size fields and unrelated rows SHALL
remain intact. Native/sound source table provenance and every resource/path binding
SHALL agree. Optional Vortex and sound features SHALL persist on later refreshes.
Earlier schemas SHALL remain inspectable. Failed publication SHALL retain the
previous binding, and complete interrupted table generations SHALL support retry.

- **Implementation**: `prepare::source/ios_server/native_sounds.py`
- **Implementation**: `prepare_data::source/ios_server/preparation.py`

#### Scenario: Decrease a source file version

- Given sound and table versions were already published
- When sound inputs use a lower source version and are explicitly prepared again
- Then the new table generation publishes higher sound and table client versions
- And overflow fails before replacing the active pointer.

### Requirement: BindSoundFilesWithoutCopyingTheCorpus

The coordinated table manifest SHALL reference immutable prepared sound files
without copying them into table generations or retaining all banks in memory.
Loading SHALL validate the pinned reference and coordinated resource tables,
independently from the mutable current sound pointer. Startup freshness SHALL
still require current sound preparation before state imports. Failure SHALL
release the runtime lock and preserve campaign facts. A bound engine SHALL keep
its sound generation for its lifetime. Sound preparation alone SHALL not enable
delivery in unbound snapshots or default engines.

- **Implementation**: `load::source/ios_server/native_sounds.py`
- **Implementation**: `open_prepared::source/ios_server/preparation.py`

#### Scenario: Replace the current sound pointer

- Given a coordinated table snapshot pins a valid immutable sound generation
- When the mutable sound pointer changes or becomes corrupt
- Then inspection still validates the pinned files and resource tables
- And freshness verification reports the changed preparation without substitution.

### Requirement: DeliverExactSoundBanksReadOnly

A prepared sound binding SHALL claim the iOS sound namespace and deliver only
exact published GET/HEAD paths. Reads SHALL check containment, file length and
SHA-256 before replying, processing one bank at a time. HEAD SHALL omit the body.
Unknown or old versions SHALL return 404 without stock/token fallback; damaged,
missing or escaping bound files SHALL return an empty 500 response. Delivery
SHALL not convert, refresh sources, repair, download, write caches or change
campaign facts. The live hello service and legacy behavior SHALL remain.

- **Implementation**: `Delivery::source/ios_server/native_sounds.py`
- **Implementation**: `serve::source/ios_server/table_delivery.py`

#### Scenario: Corrupt a bank after binding

- Given an initialized engine with a verified sound binding
- When a bound file changes or escapes its generation before GET or HEAD
- Then delivery fails visibly with an empty 500 response
- And no source fallback, conversion or filesystem mutation occurs.

### Requirement: PrepareReplayHomeArtworkExplicitly

prepare-home-banners SHALL read event-art/history mappings and available exact
native PNGs, preserve every image byte, and publish a private immutable generation
through assets/home-banners/current.json. It SHALL validate names, identities,
containment and PNGs, deduplicate identical files, report missing sources, reuse
identical inputs and preserve the active pointer on publication failure.

- **Implementation**: `prepare::source/ios_server/home_banners.py`

#### Scenario: Supply previously missing event art

- Given a home artwork snapshot reports a missing source PNG
- When the PNG becomes available and preparation runs again
- Then a new immutable generation includes its original bytes and clears the gap
- And no campaign or shared source file changes.

### Requirement: SelectReplayHomeRowsFromRecordedPolicy

The home carousel SHALL use recorded enabled/limit/tap policy and prepared art.
Defaults SHALL be enabled, six images and eligible taps; limits SHALL be 1 to 52.
Historical selection SHALL use active replay events, descending release/area,
filename deduplication and available art. Disabled, unprepared, unanchored or
finished replay SHALL use era fallback; an active week without art SHALL yield
no replay rows. Queries SHALL not initialize policy or mutate campaign facts.

- **Implementation**: `entries::source/server/revival_marquee.py`
- **Implementation**: `rows::source/server/revival_marquee.py`

#### Scenario: Roll the replay week forward

- Given recorded policy and immutable prepared images
- When the campaign enters another replay week
- Then rows reflect the active event policy without a retained week-selection cache
- And missing images and duplicate filenames consume no extra slots.

### Requirement: PreserveNativeHomeCacheAndTapContracts

Rows SHALL use banner ID 7000000 plus area and the snapshot generation as cache
version, local content-addressed URLs ending in HomeBanner_<id>.png, and a rebased
UTC display window. Eligible taps SHALL use the pinned type-6 stage-list link;
native modes or disabled taps SHALL retain the Vortex link. Both reply carriers
SHALL share selection and explicit MARQUEE_FLAG controls. Legacy behavior SHALL
remain unchanged.

- **Implementation**: `event_link::source/server/revival_marquee.py`
- **Implementation**: `marquee_rows::source/server/ffbe_banner.py`

#### Scenario: Return the home flag and carousel rows

- Given a prepared iOS engine with active available replay art
- When native GameSetting and home-marquee replies are projected
- Then the enable flag and rows agree and every image URL resolves to bound bytes
- And an explicit MARQUEE_FLAG override retains its effect.

### Requirement: VerifyAndDeliverHomeArtworkWithoutPreparation

verify-home-banners SHALL validate recorded PNGs, hashes, lengths, dimensions,
paths and input freshness without writes or engine imports. The prepared engine
SHALL bind current home and optional summon art before state imports. GET/HEAD
SHALL deliver exact bound PNGs, omit HEAD bodies and return 404 for unknown
prepared URLs, without downloads, resizing, input refresh or cache writes.

- **Implementation**: `current::source/ios_server/home_banners.py`
- **Implementation**: `serve::source/ios_server/banner_delivery.py`

#### Scenario: Change artwork after publication

- Given a valid home snapshot and changed same-size source bytes or metadata
- When verification runs or a prepared engine starts
- Then stale inputs fail visibly without automatic preparation or save changes
- And an existing bound engine retains its verified image generation.

### Requirement: PreparePinnedEnglishLabels

Preparation SHALL apply the pinned English text rules to all 25 localized label
families: bundles, items/equipment/materia/important items, summon names/details,
reconstructed abilities/monsters/skills, area/dungeon labels, generated exchanges,
and custom dailies. All canonical revival bundles SHALL have labels, including
the 13 additions absent from the legacy bundle catalogue. Append-only bundle,
ticket and summon-detail rules SHALL preserve existing text. Hook fills SHALL
replace missing, raw-key, TFA or Japanese placeholders while preserving usable
English. Explicit summon name overrides, generated product labels, native mode
names and custom dailies MAY replace existing records.

The state-free summon catalogue and one pure exchange calculation SHALL supply
label identities. Gameplay SHALL retain the same product IDs, prices, limits,
currencies and reward metadata. Preparation SHALL name products from original
English reward names or the pinned 44-item fallback file. Unresolved products
SHALL be listed without invented translations. Text generation SHALL not alter
catalogue selection, payments, rewards, RNG, historical eligibility or stock.

#### Scenario: Preserve usable English

- Given shipped English names and missing or placeholder hook text
- When native labels are prepared
- Then existing usable English remains unless a declared override applies
- And required additions retain native columns/padding and matching index checksums.

### Requirement: PrepareRecordedEconomyDisplays

Native preparation SHALL read the selected slot's recorded economy policy without
loading a player aggregate, initializing/backfilling settings, or repairing saves.
If no recorded policy exists, validated environment defaults SHALL be marked
provisional. Recorded settings SHALL take precedence over later environment edits.
Malformed save/settings or required metadata SHALL fail without replacing the save
or active snapshot.

The canonical pure conversion SHALL normalize Lapis reward fields in
F_CHALLENGE_MST, F_PANEL_QUEST_MST, F_SP_CHALLENGE_MST, F_RB_SS_MST and
F_RB_SS_REWARD_MST. Conversion SHALL start from original native source rows on
every generation, preserve unit/other-item metadata and all unrelated fields,
and leave canonical source rewards unchanged. Slot, effective policy, label
projections and source provenance SHALL participate in snapshot freshness;
unrelated campaign progress SHALL not. Changed settings SHALL require explicit
re-preparation and monotonically higher versions.

#### Scenario: Rebuild after an economy edit

- Given a snapshot prepared with a recorded multiplier of five
- When that slot records three and prepare-data runs again
- Then an original 20-Lapis master reward displays 60 in the new generation
- And the previous 100-Lapis display remains in the old generation without any grant.

### Requirement: ContainCdnFallbackPaths

CDN exact lookups, version-token fallbacks, and indexed artwork fallbacks SHALL
validate resolved paths against permitted content roots before opening files.

#### Scenario: Reject a symlink fallback

- Given a resource or artwork index pointing to a private file outside content
- When the client requests that resource, including through a version fallback
- Then the file is not returned
- And valid public resources and artwork remain available.

### Requirement: HostConnectivityWithoutGameplay

The connectivity service SHALL serve public setup/profile and hello routes on
HTTP and HTTPS, without importing the engine, creating saves, or serving game
assets. Unknown paths SHALL return 404; gameplay POSTs SHALL return 503.

#### Scenario: Reach the Mac from Safari

- Given the iPhone uses the Mac for home-Wi-Fi DNS and trusts the installed CA
- When Safari opens the canonical HTTPS hello URL
- Then the page loads without a certificate warning
- And a distinct secure-connection confirmation replaces the HTTP setup steps
- And the page identifies the connection-check scope.

### Requirement: ForwardOrdinaryDns

UDP and TCP DNS SHALL answer game-domain IPv4 queries with the selected Mac
address, return empty IPv6 game answers, and forward ordinary domains to the
Mac’s upstream IPv4 resolver. Domain suffix matching SHALL respect label
boundaries. Local upstream loops SHALL be rejected. Failed/mismatched upstream
responses SHALL return SERVFAIL. Malformed requests SHALL not stop listeners.

### Requirement: RestrictHomeNetworkAccess

Public HTTP/HTTPS and DNS SHALL accept only loopback and the selected home
subnet. Certificates and private keys SHALL not be served through filesystem
paths. A private, user-owned control socket SHALL provide status and stop.

### Requirement: BindBeforeReady

The service SHALL bind TCP/UDP DNS, HTTP, HTTPS and control before announcing
readiness. Gameplay mode SHALL initialize the prepared engine only after binding
and before starting listeners. Failure SHALL close acquired resources and release
the instance lock.
Matching startup commands SHALL reuse the instance; conflicts SHALL fail.
SIGINT, SIGTERM and explicit stop SHALL close listeners and the control socket.
Explicit stop SHALL wait for the runtime lock to be released before reporting
completion, including when the control socket closes before other listeners.

### Requirement: PreserveCertificateIdentity

Setup SHALL prepare a dedicated checksum-locked Python 3.12 environment and
private CA. The root identity and each leaf key/certificate pair SHALL be
atomic files. Repeated setup and leaf renewal SHALL retain the CA and profile
UUIDs. Root corruption/loss SHALL fail without implicit replacement. Leaf
renewal SHALL reload TLS without requiring listener restart. Diagnostic queries
SHALL not generate or repair certificates. Logs SHALL have bounded retention.


### Requirement: ReadLocalManagedPackManifest

Managed-pack commands SHALL validate a local schema-1 manifest, preserve its exact
bytes and Android application metadata, skip only client-assets, and retain pack
order. plan-data SHALL report missing-layer sizes without transfer or writes.

- **Implementation**: `read::source/ios_server/pack_manifest.py`, `plan::source/ios_server/pack_install.py`

#### Scenario: Preview the bundled release

- Given the bundled manifest and an empty separate data directory
- When plan-data runs
- Then it reports 18 selected packs and their compressed and expanded sizes
- And the manifest, data directory, campaign and runtime remain unchanged.

### Requirement: ResumeVerifiedPackTransfers

Explicit fetch-data SHALL resume partial ZIPs, restart when ranges are ignored,
and require exact length and SHA-256 before promotion. Invalid ranges, oversized
responses and unsafe redirects SHALL fail. Interrupted transfers SHALL remain
available for a later explicit retry.

- **Implementation**: `fetch::source/ios_server/pack_download.py`

#### Scenario: Resume an interrupted transfer

- Given a partial archive and a server supporting HTTP ranges
- When fetch-data is retried
- Then the request starts at the saved byte offset
- And only a complete checksum-verified archive is promoted.

#### Scenario: Use existing archives

- Given archive-dir contains a ZIP named by digest, pack ID or published basename
- When fetch-data needs that layer
- Then it validates and extracts the ZIP without modifying it or transferring bytes.

### Requirement: ValidateManagedZipLayers

Extraction SHALL restrict paths to supported content and registry destinations,
reject traversal, links, special entries, duplicates and case/Unicode collisions,
and enforce expanded sizes. A complete verified layer SHALL be published by
archive hash and reused without extraction. Saves and APK resources SHALL be excluded.

- **Implementation**: `members::source/ios_server/pack_layers.py`, `extract::source/ios_server/pack_layers.py`

#### Scenario: Refuse an unsafe later pack

- Given a valid first pack and a later unsafe ZIP
- When fetch-data runs
- Then the completed first layer is retained for retry
- And no incomplete generation becomes active.

### Requirement: RebuildOrderedManagedOverlay

Each managed generation SHALL rebuild the full overlay from verified immutable
layers in manifest order, with later exact paths winning. Removing or reordering
a pack SHALL restore the appropriate earlier file and omit removed-only files.
Unchanged layers SHALL require neither download nor extraction.

- **Implementation**: `merge::source/ios_server/pack_layers.py`

#### Scenario: Remove an override

- Given a patch overrides a base file and adds another file
- When a replacement manifest removes both patch entries
- Then the new generation contains the base version and omits the patch-only file
- And the old generation retains its original bytes.

### Requirement: ProjectFinalNativePackRegistry

The final overlay SHALL project validated registry.json versions into a sanitized
gamedata.xml before publication, matching the Android bootstrap's post-extraction
update. Source archives, immutable layer XML and previous generations SHALL retain
their original bytes.

- **Implementation**: `project_registry::source/ios_server/managed_content.py`

#### Scenario: Apply a later registry update

- Given a base XML version of one and a later registry version of two
- When the ordered installation is built
- Then the active native XML reports two
- And the base layer XML and previous generation still report one.

### Requirement: ActivateManagedInstallationAtomically

fetch-data SHALL hold private-runtime and shared-install locks, reject existing
prepared or flat managed trees, check free space, and verify the complete staged
payload before replacing its pointer. Failure SHALL preserve the previous active
generation. Previous layers and generations SHALL be retained.

- **Implementation**: `fetch::source/ios_server/pack_install.py`

#### Scenario: Retry a failed activation

- Given a complete new generation whose pointer replacement failed
- When fetch-data runs again
- Then the old pointer remains authoritative until successful replacement
- And completed layers and the matching unpublished generation can be reused.

### Requirement: PinManagedContentGeneration

Configuration SHALL resolve a managed pointer once, retain the logical data root
as its containment boundary, and bind engine paths to that physical generation.
Prepared host and flat managed inputs SHALL remain supported. New generations
SHALL invalidate earlier prepared provenance until explicit re-preparation.

- **Implementation**: `resolve::source/ios_server/managed_content.py`, `Configuration::source/ios_server/config.py`

#### Scenario: Update after preparing native assets

- Given an engine configuration pinned to a prepared managed generation
- When a new manifest becomes active
- Then the old configuration retains its original content paths
- And a fresh configuration detects stale assets until prepare-data runs.

### Requirement: VerifyManagedInstallationReadOnly

verify-packs SHALL check pointer, manifest and installation identities, exact file
inventory, payload lengths, hashes and native layout without engine imports or
writes. Missing, stale or corrupt installations SHALL fail without repair.
Successful raw installation SHALL continue reporting gameplay_ready false.

- **Implementation**: `verify::source/ios_server/pack_install.py`, `load::source/ios_server/managed_content.py`

#### Scenario: Detect a damaged payload

- Given an active generation with missing or changed bytes
- When verify-packs runs
- Then it reports failure
- And neither the installation nor the campaign is repaired or replaced.


### Requirement: StartPreparedNativeGameplayExplicitly

start SHALL require an initialized private campaign, current complete schema-5
tables with Vortex and sound bindings, and current summon/home snapshots before
state imports. It SHALL perform no download, preparation or campaign initialization.
serve SHALL retain its independent connection-only behavior.

- **Implementation**: `Gameplay::source/ios_server/hosting.py`

#### Scenario: Refuse missing prepared artwork

- Given a campaign and coordinated tables but no home snapshot
- When gameplay preflight runs
- Then it reports the explicit preparation command without importing engine state
- And no source, campaign or preparation record changes.

#### Scenario: Launch with prepared host assets and release metadata

- Given checkout data/ contains only release metadata and source/out/browser-data/ has a native registry
- When Play Exvius on iPhone.command runs without an explicit data selection
- Then it selects the prepared host assets and retains the private iOS campaign
- And explicit --data or FFBE_IOS_DATA selections take priority
- And an existing repository installation, including an incomplete one, is never silently replaced by another data selection.

### Requirement: ShareHostingRuntimeLease

The prepared engine SHALL accept only a held InstanceLock for its own private
root when hosting supplies a lease. It SHALL retain standalone lock ownership
otherwise. Hosting SHALL keep that lease through active request drainage and
engine shutdown, avoiding a second lock acquisition.

- **Implementation**: `Engine::source/ios_server/engine.py`, `Service::source/ios_server/service.py`

#### Scenario: Share the transport lease

- Given bound native listeners and one held private runtime lease
- When the prepared engine initializes under hosting
- Then initialization succeeds without reacquiring the lock
- And a competing instance remains refused until all requests and engine resources close.

### Requirement: ComposeNativeGameplayTransport

Gameplay mode SHALL preserve canonical encrypted API, transaction and prepared
asset handling behind the existing restricted HTTP/HTTPS listeners. Public setup,
profile and hello GET/HEAD SHALL remain available. Native hosting SHALL refuse
engine debug/status/new-game routes. HEAD SHALL omit bodies.

- **Implementation**: `handler::source/ios_server/game_http.py`

#### Scenario: Initialize over TLS and fetch native content

- Given a prepared host or managed corpus and a trusted local certificate
- When encrypted InitializeRequest runs over HTTPS
- Then its 364 native versions name the exact published table bytes
- And GET/HEAD delivers tables, Vortex, sound and artwork with correct lengths.

#### Scenario: Damage a bound sound after startup

- Given a running prepared host whose sound bank bytes change
- When GET or HEAD requests that bank through HTTPS
- Then it receives an empty 500 without stock fallback
- And the private campaign remains unchanged.

### Requirement: BoundNativePostFraming

Native gameplay POST SHALL require one nonnegative decimal Content-Length no
larger than 4 MiB, except the dedicated native report upload route, which SHALL
allow at most 64 MiB while a native report adapter is bound. It SHALL reject
transfer encoding before canonical dispatch. The
same check SHALL guard Expect: 100-continue. Connections SHALL close after their
response and game sockets SHALL have a bounded I/O timeout.

- **Implementation**: `handler::source/ios_server/game_http.py`, `Server::source/ios_server/http.py`

#### Scenario: Reject oversized or ambiguous framing

- Given missing, duplicate, negative or oversized Content-Length, or transfer encoding
- When a native gameplay POST arrives
- Then it receives 400 or 413 without canonical action dispatch or a campaign mutation.

### Requirement: ReuseOnlyMatchingHostingConfiguration

Repeated starts SHALL reuse only the same mode, logical data root, pinned content
generation, slot and network configuration. Changing those inputs SHALL require
explicit stop. status SHALL read actual service mode without loading the engine.
Foreground readiness SHALL remain one JSON document; request diagnostics SHALL use stderr.

- **Implementation**: `serve::source/ios_server/cli.py`, `Service::source/ios_server/service.py`

#### Scenario: Change mode or campaign while running

- Given active gameplay hosting
- When serve or a start with another data root or slot is requested
- Then it reports a configuration conflict
- And a matching start reports the current instance without another engine.

### Requirement: DrainNativeGameplayBeforeUnlocking

Shutdown SHALL stop accepts and wait for active game requests before unbinding
engine assets or releasing its runtime lease. Startup failure SHALL close bound
listeners and the application. Signal and control shutdown SHALL use this same
lifecycle; stop SHALL wait for socket and lock release before success.

- **Implementation**: `Service::source/ios_server/service.py`, `lifecycle::source/ios_server/commands.py`

#### Scenario: Stop during a response

- Given an active game request is still running
- When shutdown begins
- Then the application and runtime lease remain held until the response completes
- And the control socket and lease are released before a new instance can start.

### Requirement: BoundOwnedPrivateRequestRecords

Explicit gameplay startup and maintenance SHALL prune recognized canonical request
JSON records older than three days, then oldest-first above 300 MiB, under the
engine state lock. Other names and symlinks SHALL be excluded. Missing directories
SHALL remain absent. Queries SHALL not perform retention writes.

- **Implementation**: `prune::source/ios_server/request_retention.py`, `Gameplay::source/ios_server/hosting.py`

#### Scenario: Retain unrelated files

- Given old and oversized canonical records alongside unrelated files and links
- When maintenance runs
- Then only eligible owned records are removed to meet the limits
- And unrelated files and link targets retain their bytes.


### Requirement: InspectBoundStartupWithoutFalseReadiness

A control probe that times out while engine activation is pending SHALL report no
ready service and leave the held lease intact. A queued explicit stop SHALL set
shutdown intent even if its client disconnects before the response is written.
Neither condition SHALL permit a competing runtime instance.

- **Implementation**: `read_service::source/ios_server/runtime.py`, `ControlHandler::source/ios_server/http.py`

#### Scenario: Poll and stop during slow activation

- Given the control socket is bound while engine activation waits
- When status and stop probes time out before listeners start
- Then readiness remains false and the runtime stays exclusively locked
- And the queued stop is honored after activation even though its client disconnected.


### Requirement: PreserveGlobalVersionRowsInPreparedReplies

Prepared version projection SHALL retain existing F_MST_VERSION, F_RSC_VERSION,
F_APP_VERSION_IOS and F_APP_VERSION_AND rows unchanged. These bootstrap counters
SHALL not be treated as downloadable tables, inflated or synthesized. Only known
published native table identities SHALL receive prepared file versions.

- **Implementation**: `PreparedTables::source/ios_server/preparation.py`

#### Scenario: Project a mixed bootstrap version carrier

- Given canonical global counters, known table rows and an unknown table row
- When complete prepared versions are projected
- Then global rows retain their original values and extra fields
- And all 364 native tables advertise published versions while the unknown table is omitted
- And the input reply and campaign remain unchanged.

<!-- manual -->
### Known Invariants

- The iPhone gameplay launcher must distinguish release metadata from installed
  content when selecting its default data directory. A metadata-only data/ folder
  must not hide existing prepared host assets; explicit selections and existing
  installations remain authoritative. Discovered November 12, 2026: unconditional
  selection of data/ failed on its missing client/shared_prefs/gamedata.xml.

- PreparedTables.project_versions must distinguish global bootstrap/version
  metadata from downloadable native table rows. A file-publication allowlist must
  not remove F_MST_VERSION or F_RSC_VERSION from canonical initialization replies.
  Discovered November 11, 2026 during physical-iPhone MST_LOAD_FAILED diagnosis:
  the complete-table filter dropped both original counters. Counter preservation
  is verified by regression tests; physical recovery requires an iPhone retry.

- iOS upfront resource sizes must describe the exact files selected by CDN overlay
  precedence. Repacked assets can retain their filename/version while changing
  length; trusting stale platform-size metadata then disagrees with downloaded
  bytes. Discovered November 11, 2026 during a physical 98%-download failure:
  three of 57 served upfront packs differed from their iOS size fields.

- Native diagnostic uploads must bypass gameplay commands, keep their bodies out
  of ordinary records, and be requested only on GameSetting while explicitly
  enabled. Periodic Home polling must never repeatedly request a whole device log.
  Discovered November 11, 2026 while porting the upstream 590d4fb diagnostic fix:
  the prior adapter neither acknowledged queued reports nor retained device errors.

- Synchronous summon detail dependencies must not remain solely in the bulk
  background queue. The native client loads gacha UI textures and the default
  monster preview immediately when entering detail. Discovered November 11, 2026:
  the crashed session reported missing gacha button textures and Ochu CSV/animation
  data while their intact packs were scheduled only as background downloads.

- cpk.encode_table must reuse string-pool offset zero for the native null
  sentinel. Comparing decoded text alone cannot distinguish a reserved null cell
  from an ordinary string containing the same characters. Discovered November
  11, 2026 while investigating Vortex GateScene's event_1115.png load failure:
  the original TOC used zero while the prepared TOC used offset 82. The encoding
  mismatch is reproduced by a binary-cell regression. The device later opened
  Vortex after a Home wait for background data; the encoding repair's causal
  contribution to that recovery was not isolated.

- The Drop Rates URL published in F_URL_MST must resolve the stock WebView's
  own gacha_id form request to the existing replay-aware rates renderer.
  Testing only an alternate browser/hook URL does not establish that contract.
  Discovered November 12, 2026: the advertised sg_summons_list.php route returned
  an empty 404 while the existing banner-specific HTML route returned valid rates.
<!-- /manual -->

### Requirement: ReconcileUpfrontIosResourceSizes

Preparation SHALL measure available TUTO/PRE_TUTO CPKs, both early resource packs
and the required summon menu packs from exact overlay-first CDN paths. It SHALL record contained paths, byte
lengths and SHA-256s, and correct only common/English iOS size fields. Other
platform fields and source files SHALL remain unchanged. Missing files SHALL be
reported without invented sizes; escaping paths SHALL fail.

- **Implementation**: `collect::source/ios_server/upfront_resources.py`, `project::source/ios_server/upfront_resources.py`

#### Scenario: Serve a patched upfront pack

- Given a served pack has a different length than its original iOS size row
- When native tables are prepared
- Then the iOS size row matches the selected pack's actual bytes
- And exact overlays take precedence without changing base or overlay files.

### Requirement: BindUpfrontCpkFactsToPreparedGeneration

Upfront CPK provenance and coverage SHALL participate in the preparation identity.
Published size rows SHALL agree with recorded facts. Source edits, including
same-length changes, SHALL make verification stale until explicit preparation.
Failed collection/publication SHALL preserve the active pointer and campaign.

- **Implementation**: `prepare_data::source/ios_server/preparation.py`, `coverage::source/ios_server/upfront_resources.py`

#### Scenario: Change an upfront source after preparation

- Given a current prepared size table and its source inventory
- When the selected source changes bytes without changing length
- Then read-only verification reports stale preparation
- And a failed preparation never replaces the prior snapshot or repairs shared inputs.

### Requirement: CollectNativeReportsWithoutGameplayWrites

The prepared iOS engine SHALL bind a private diagnostic adapter. Explicit
EXVIUS_CLIENT_REPORTS=1 SHALL request a log on GameSetting only; all other replies
SHALL omit report-back instructions. Uploads SHALL bypass gameplay commands and
return the encrypted report-state acknowledgment. When disabled, queued uploads
SHALL be acknowledged without saving. Undecryptable uploads and invalid or unsaved
uploads while enabled SHALL not claim success. Closing the engine SHALL unbind
the adapter.

- **Implementation**: `ClientReports::source/ios_server/client_reports.py`, `project::source/ios_server/client_reports.py`

#### Scenario: Receive a queued log with diagnostics disabled

- Given a native campaign and disabled diagnostic storage
- When an encrypted queued report arrives
- Then the reply acknowledges it without saving its body or changing campaign bytes
- And periodic home replies never request another log.

### Requirement: BoundAndKeepNativeReportsPrivate

Native report storage SHALL be atomic, contained in the private runtime, mode
0600 under a 0700 directory, and bounded to three reports and 128 MiB. Retention
SHALL ignore symlinks and unrelated files. Report bodies SHALL be omitted from
ordinary request records and diagnostic output. A read-only decoder SHALL decrypt
the report lines without loading gameplay state. Public asset routes SHALL never
serve report files.

- **Implementation**: `save::source/ios_server/client_reports.py`, `prune::source/ios_server/client_reports.py`, `decode::source/ios_server/client_reports.py`

#### Scenario: Save a report larger than an ordinary gameplay request

- Given opt-in diagnostics and a valid encrypted report larger than 4 MiB
- When it arrives on the dedicated report route within its 64 MiB bound
- Then it is saved privately and acknowledged without a campaign write
- And its body is absent from ordinary records and cannot be fetched as an asset.

### Requirement: PreloadSynchronousSummonDependencies

Native preparation SHALL classify gacha1_common.cpk, gacha1.cpk and
monster3_common.cpk for upfront TUTO download when present in the resource list.
Existing TUTO/PRE_TUTO classifications SHALL be retained. Unversioned resources
SHALL remain omitted, and unrelated background packs SHALL keep their class.
Exact file provenance and iOS sizes SHALL be bound through upfront collection
without changing source files, summon costs, pools, awards or legacy projections.

- **Implementation**: `build::source/ios_server/native_tables.py`, `collect::source/ios_server/upfront_resources.py`

#### Scenario: Open summon detail before the bulk movie queue finishes

- Given the summon UI and default preview packs have background classifications
- When native tables are prepared
- Then those three dependencies are advertised for upfront download with exact iOS sizes
- And an unrelated background pack, source files and campaign remain unchanged.

### Requirement: ServeNativeDropRatesWebView

The iOS gameplay handler SHALL serve the exact published GACHA_RATE_URL path for
GET, HEAD and URL-encoded POST fields. A numeric gacha_id SHALL select the existing
rates renderer and its effective replay pool/guarantees; requests without an ID
SHALL list the current replay catalogue with links to banner-specific rates.
Form fields SHALL be read afresh for each request, independent of MIME labels,
bounded to 64 KiB and 128 fields per query/body. Conflicting or invalid IDs SHALL
return 400, oversized forms 413 and unknown banners 404 with readable content.

Delivery SHALL run under the canonical state lock, return UTF-8 HTML with exact
Content-Length and no-store caching, and omit the body for HEAD. It SHALL bypass
encrypted command dispatch and ordinary gameplay request recording, preserve
campaign/save bytes and RNG state, and log no form bodies or identity fields.
Existing banner-specific HTML and legacy resource routes SHALL retain behavior.

- **Implementation**: `owns::source/ios_server/rates_delivery.py`, `banner_id::source/ios_server/rates_delivery.py`, `serve::source/ios_server/rates_delivery.py`
- **Implementation**: `index_page::source/server/gacha_rates.py`

#### Scenario: Open native banner rates

- Given a prepared native Drop Rates URL and a replay-eligible summon
- When the stock WebView posts its gacha_id and localization fields
- Then the response matches the existing banner-specific rates HTML
- And a later request can select another banner without retained form fields
- And GET/HEAD query requests agree without commands, saves or RNG changes.

#### Scenario: Recover a request without a banner ID

- Given the WebView requests the native rates path without gacha_id
- When the page is served
- Then it lists eligible replay summons with local rates links
- And future summons and unescaped catalogue text are absent.
