# Native iOS Server Foundation

## Scope

This specification covers the profile/calendar foundation, replay-aware summons,
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
the replay anchor and immutable settings in one canonical player-save operation.
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
