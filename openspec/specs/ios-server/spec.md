# Native iOS Server Foundation

## Scope

This specification covers the profile/calendar foundation, replay-aware summons,
events, exchanges, friends, arena, reward mail, daily economy, quest trust, replay notices,
pinned exploration encounters and rare quest loot,
and hello-only native connectivity of
[plans/IOS_SERVER_SOLID_CQRS_PLAN.md](../../../plans/IOS_SERVER_SOLID_CQRS_PLAN.md).
Full revival gameplay hosting and physical iPhone acceptance remain pending. Reference commit:
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

Doctor, status, and rotation SHALL neither import the engine state loader nor
create files, initialize campaigns, download assets, or start services. Malformed
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
base units available in the historical window, within their form's level cap.
Statless placeholder masters SHALL be excluded. Daily suggestions SHALL exclude
existing relationships and use the saved calendar timezone, including DST.
Projections SHALL neither seed missing friendships nor consume global gameplay RNG.

#### Scenario: Read native social pages

- Given an initialized campaign
- When encrypted friend, suggestion, search, and reinforcement requests run
- Then they return complete native rows for the current relationships
- And campaign data and save bytes remain unchanged.

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
renderable, historically eligible units from the same pool as simulated helpers.
The pinned strength, gear, weekly target, pace, tie ordering, and Global placement
scale SHALL be preserved. Ratios SHALL range from 0.50 to 1.50 in steps of 0.05.
Five opponents SHALL refresh every ten minutes by default; ranking SHALL show
the top 100 accounts and the player's own row. Global gameplay RNG SHALL be untouched.
Elapsed-time scoring and displayed week boundaries SHALL account for Eastern DST.

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
queries SHALL not write shared tables. Installation into the served native assets
and visual device acceptance remain part of the later preparation stage.

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
readiness. Failure SHALL close acquired listeners and release the instance lock.
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
