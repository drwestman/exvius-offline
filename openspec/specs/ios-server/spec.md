# Native iOS Server Foundation

## Scope

This specification covers the profile/calendar foundation, replay-aware summons/events/exchanges/friends/arena,
and hello-only native connectivity checkpoint of
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
canonical player-save operation.
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
or download artwork. Additional authored campaigns SHALL remain closed until their
battle/art content is prepared. Legacy archive behavior SHALL remain unchanged.

#### Scenario: Project a new historical week

- Given a captured response includes a future event and the campaign is in replay week zero
- When the Vortex is projected
- Then only eligible archive gates remain alongside unrelated gate rows
- And the selected gates carry the current Eastern week's UTC bounds
- And player data and save bytes remain unchanged.

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
