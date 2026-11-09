# Native iOS Server Foundation

## Scope

This specification covers the first profile/calendar checkpoint of
[plans/IOS_SERVER_SOLID_CQRS_PLAN.md](../../../plans/IOS_SERVER_SOLID_CQRS_PLAN.md). It does not claim native hosting or complete
revival gameplay support. Reference commit:
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
