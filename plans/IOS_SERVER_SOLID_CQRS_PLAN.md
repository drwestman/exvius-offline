# Native iOS revival server for this Mac

## Summary and review findings

Add the iOS server to `exvius-offline`, using your installed Global FFBE app over home Wi-Fi. Start it manually when playing, configure DNS only on the iPhone, and create a fresh iOS campaign. Enable the full revival experience exclusively for this server.

Use revival commit `47a13c084f42cf1b83b53173d0c21065c78fc2de` as the reference.

The review identified three integration risks:

- **P1 — Unsafe CDN paths.** The fork decodes paths after stripping leading slashes, allowing an encoded absolute path to escape the content directory. Preserve the destination project's containment checks throughout iOS asset handling. [Source](/Users/david/Projects/Exvius-revival-ios/source/server/capture_server.py:581)
- **P1 — Engine regressions during import.** The fork removes existing save-corruption preservation and some battle/repeat handling. Port revival features into the current engine while retaining those fixes. [Save-loading example](/Users/david/Projects/Exvius-revival-ios/source/server/player_state.py:2186)
- **P2 — Container-dependent lifecycle.** DNS can fail while startup still reports readiness, and certificate renewal exits expecting Docker to restart the process. Both require native lifecycle management. [Source](/Users/david/Projects/Exvius-revival-ios/ios-server/serve.py:351)

## Architecture and revival integration

- Keep one canonical game engine. Introduce immutable `legacy` and `ios-revival` profiles, selected before engine modules load. Existing entrypoints retain `legacy`; the iOS launcher selects `ios-revival`.
- Apply SOLID through separate configuration, lifecycle, certificates, DNS, asset preparation, and engine adapters. Inject narrow filesystem, process, clock, random-number, and DNS-upstream dependencies for testing.
- Separate application commands from queries:
  - **Commands:** setup, data installation, asset preparation, start, stop, campaign initialization, gameplay mutations, and certificate maintenance.
  - **Queries:** doctor, status, data verification, rotation previews, and gameplay projections. These must not create directories, initialize saves, download assets, or start services.
- Move the fork's implicit writes—such as starting-friend creation and replay anchoring—into explicit campaign commands. Initialize them once during first gameplay initialization. Generate views from the resulting state.
- Port all revival feature families: historical replay, rotating summons/events/shops, notices, summon deals and guarantees, simulated friends, arena progression, economy changes, daily quests, weekly gifts, trust gains, and authored content.
- Preserve the existing encrypted request/response contract, locked JSON persistence, transaction protections, and repeat/reward handling. Isolate changed catalogs and response data behind the iOS profile.
- Adopt the pinned fork's settings as the iOS defaults, including December 2016 replay start, Sunday 10 PM Eastern rollover, and its pace change at the Neo Vision era. Calendar time continues while the server is stopped.

## Native hosting and interfaces

- Add a dedicated macOS entrypoint supporting `setup`, `fetch-data`, `verify-data`, `start`, `serve`, `stop`, `status`, `doctor`, and `rotation`. Provide a double-click launcher for foreground operation.
- Use an isolated Python 3.12 environment with locked dependencies. Setup prepares dependencies and certificates; starting the server uses already prepared data.
- Store iOS saves, configuration, certificates, caches, and logs under `~/Library/Application Support/Exvius Offline/iOS`. Use a private control socket and instance lock for lifecycle operations.
- Support both managed `static/native` packs and the existing prepared host-data layout. Reuse suitable prepared assets read-only, excluding their saves. Download missing managed packs explicitly, with resumable downloads, SHA-256 checks, ordered extraction, and atomic installation records.
- Retain the destination manifest's Android application metadata; both repositories currently list identical pack IDs, sizes, and hashes.
- Implement DNS on UDP and TCP 53 using [dnslib's server framework](https://pypi.org/project/dnslib/). Resolve `gumi.sg`, `exvius.com`, and their subdomains to the selected Mac IPv4 address. Return empty IPv6 answers for those names and forward ordinary DNS queries to the Mac's upstream resolver. Reject forwarding loops and report upstream timeouts.
- Serve HTTP on 80 and HTTPS on 443. Use wildcard bindings as verified on this Mac, with access restricted to loopback and the selected LAN subnet. Expose explicit LAN-address and upstream-DNS overrides.
- Bind all required listeners before reporting readiness. A required listener failure closes the others and returns an actionable error. Start is idempotent for the same configuration; conflicting instances fail clearly.
- Reuse the private CA and stable profile identity. Renew and reload leaf certificates without exiting. Keep private keys inaccessible through HTTP and enforce content-root containment after every path rewrite.
- Preserve the iOS compatibility transformations: table versions and LF endings, early battle resources, localized text, banner packs, sound conversion, story fixes, and WebView routes. Build disk caches through preparation commands rather than view queries.
- Provide bounded logs and request-report retention, graceful shutdown, and diagnostics for address changes, missing data, TLS failures, and port conflicts.

Document the iPhone setup: select the Mac as the sole manual DNS server for home Wi-Fi, install the certificate profile, enable full certificate trust, and verify the HTTPS hello page. Restore DNS to Automatic when the server is off. Manual DNS applies per Wi-Fi network, and downloaded certificate profiles require a separate trust step. [DNS instructions](https://developers.cloudflare.com/1.1.1.1/setup/ios/), [Apple certificate instructions](https://support.apple.com/en-ie/102390).

## BDD validation and delivery

Implement in three stages: profile and engine integration, native hosting, then device acceptance.

- **Given an unconfigured installation**, when any diagnostic or preview query runs, then it reports missing prerequisites without filesystem writes, downloads, save initialization, or service startup.
- **Given occupied ports or failed initialization**, when startup runs, then it reports failure, closes acquired resources, and never reports readiness.
- **Given iPhone DNS points to the Mac**, when game and ordinary domains are queried, then game traffic reaches the local server and ordinary browsing continues. Cover TCP, malformed packets, suffix boundaries, upstream failures, and subnet restrictions.
- **Given encoded paths or symlinks outside permitted content roots**, when assets are requested, then access is rejected. Verify transformed tables, advertised versions, checksums, and delivered bytes agree.
- **Given repeated requests, restarts, and weekly rollovers**, then gifts, rewards, trust gains, friendships, and replay progress persist without duplicate grants. Cover Eastern daylight-saving transitions and save-write failures.
- **Given the legacy profile**, then existing gameplay fixtures, save-corruption protection, transaction/repeat tests, and emulator/browser-streaming tests retain their behavior.
- **On the actual iPhone**, verify certificate trust, initial downloads, the documented first-login relaunch, tutorial battle, audio, summons, shops, friends, arena, and save persistence after server restart.

The reference client is Global build 1167 (`ver.9100`); record your installed build during device acceptance.

Validation before implementation: **30 existing Mac launcher tests passed**. iOS gameplay was unverified. At that point no implementation changes had been made to `exvius-offline`; OpenLore's automatic indexing added an `.openlore/` ignore entry to the reference checkout's `.gitignore`.

## Implementation review and checkpoint — November 9, 2026

The reference checkout is at the pinned commit. The staged delivery remains appropriate; copying the fork's engine wholesale would replace current save, transaction, and repeat fixes.

The source review tightened three requirements:

- Store the replay anchor **inside the campaign save**, alongside its settings and initialization marker. The fork's separate `replay.json` is not an atomic campaign transaction. Corrupt anchor data must fail visibly rather than silently restart history.
- Separate shared content from **all** runtime state, including event/raid policies and battle caches. Merely moving the player JSON leaves other canonical readers looking under the shared root.
- Revalidate **every** CDN fallback. A regression test exposed an existing destination bug: an exact lookup rejected an escaping symlink, then its version-token fallback reopened the same file. Indexed artwork also lacked a final containment check. Both fallbacks are now checked, with positive tests for valid assets.

First checkpoint implemented:

- Immutable `legacy` and `ios-revival` profiles selected before engine imports; legacy LocalGame selection remains explicit.
- A native application package and entrypoint with read-only `doctor`, `status`, and `rotation`, plus the explicit development command `init-campaign`.
- Separate private runtime paths and prepared/managed content layouts, with an instance lock and failure cleanup.
- The pinned historical calendar, including the December 2016 start, Eastern Sunday rollover, Neo Vision pace change, and stopped-server elapsed time.
- Atomic first-gameplay replay initialization through the existing encrypted pipeline, preserving retry/restart behavior and canonical save-corruption recovery.
- iOS battle views derive cache misses in memory; disk cache creation requires an explicit preparation call. Legacy caching retains its behavior.
- CDN token/artwork fallback containment fixes.

Validation: **24 new iOS behavior checks and 59 existing checks passed** on Python 3.12.13. Existing checks comprise 30 Mac emulator/browser-launcher tests, 10 raid-ledger tests, and 19 event/repeat/title-menu tests. Synthetic masters were used for the latter and for the new engine integration checks. Prepared host data was subsequently found at `source/out/browser-data`; a disposable-save initialization/restart smoke test also passed against it. The full summon-transaction/gameplay suites, packaged Android build, and real iPhone acceptance have not been validated.

**Stage 1 remains in progress.** Next, port the actual replay-filtered summons/events/shops and the remaining revival feature families behind the iOS profile, with explicit starting-friend and reward commands. Calendar preview currently reports date windows only. The locked Python environment, setup/data installer, asset transformations/preparation, DNS/TLS/HTTP hosting, lifecycle control socket, double-click launcher, retention, and device acceptance remain outstanding. Status explicitly reports that hosting is not implemented.

See [the implementation notes](../source/ios_server/README.md) and [foundation BDD specification](../openspec/specs/ios-server/spec.md).

## Connectivity checkpoint brought forward — November 9, 2026

The user prioritized a minimal physical iPhone-to-Mac connection check before
the remaining revival gameplay ports. This checkpoint implements:

- `setup` for a dedicated Python 3.12 environment with checksum-locked dependencies and a private, stable CA/profile.
- Foreground `serve` with home-network discovery, UDP/TCP DNS forwarding, HTTP/HTTPS hello routes, an exclusive instance lock, and a private status/stop socket. All required listeners bind before readiness. Matching startup is idempotent; conflicts fail and close acquired resources.
- Read-only status and certificate diagnostics, explicit `stop`, SIGINT/SIGTERM cleanup, bounded logs, and leaf certificate renewal/reload without changing the trusted root.
- Public certificate/profile and setup routes only. No engine imports, game data, saves, game asset serving, or gameplay mutation. The mode is explicitly `connectivity-check`.
- A double-click [connection launcher](../Check%20Exvius%20iPhone%20Connection.command) and [iPhone setup instructions](../source/ios_server/README.md#on-the-iphone).

Verification so far: **26 connectivity tests, 24 foundation tests, and 40 existing Mac launcher/raid-ledger tests passed**. Native tests use disposable roots and loopback sockets. Physical iPhone trust, firewall/Wi-Fi reachability, and the phone's ordinary browsing remain device acceptance checks. The full game's DNS/TLS transport will reuse this lifecycle after the remaining engine and asset compatibility work.

Live Mac verification also passed on `192.168.86.40`: DNS over UDP and TCP 53,
empty game AAAA answers, forwarding ordinary queries to `192.168.86.1`, profile
download over HTTP 80, and hostname-validated HTTPS on 443 using the private CA.
The real setup command was tested twice with a disposable root; CA/profile
identity stayed stable. The persistent hello service was then prepared and
started for iPhone acceptance. No campaign was created.

The user subsequently confirmed that the HTTPS hello page loaded on the physical
iPhone **without a certificate warning**. Home-Wi-Fi reachability, game-hostname
DNS resolution, HTTPS, and the installed certificate's trust therefore passed
this device checkpoint. Ordinary browsing from the iPhone and actual gameplay
remain separate acceptance checks. The HTTPS confirmation view now differs
clearly from the HTTP setup instructions.

The page refresh exposed a stop/restart race: the control socket could close
before the final listener and instance lock were released. Stop now waits for
the lock as well, with a regression exercising delayed listener cleanup and an
immediate restart. All **27 connectivity tests** pass after this fix.

## Replay-aware summons checkpoint — November 9, 2026

The next Stage 1 slice implements the pinned replay selection rules against the
existing canonical summon catalogue, exclusively for `ios-revival`:

- One read-only policy selects historical Global release sets, permanent summons,
  holiday catch-up years, NV-era gates, dated permanent periods, and the deterministic
  weekly rotation after history ends. It uses the campaign's saved settings and anchor.
- `rotation --weeks 8` now lists actual banner names/IDs, release sets, holidays,
  and full-pool ticket exceptions. An uninitialized preview uses one provisional
  anchor across all weeks and creates no state.
- Encrypted catalogue requests, drop-rate pages, and purchase commands share the
  policy. Purchases revalidate after rollover before spending. Unit-release metadata
  is copied unchanged from the pinned commit; unavailable units are removed before
  tier rates are distributed, including nested guaranteed pools. Unfulfillable
  forced/bonus rewards, finite boxes, and select purchases decline without spending.
- Summon projections no longer initialize iOS banner counters. Weekly iOS limits
  use the saved Eastern rotation bounds. Legacy catalogue, counters, and transaction
  behavior retain their existing paths.
- The two full-pool SP ticket exceptions carry their required one-purchase bundle
  limits on iOS, and the cheap plain SP ticket bundle is removed. Other shop/economy
  changes remain for the later port.

Validation: **18 replay-summon BDD checks, 24 foundation checks, 22 existing summon
transaction checks, and 65 existing shop-action checks passed** (129 distinct checks).
The new checks include real encrypted catalogue/purchase requests with synthetic
masters, stale requests preserving save bytes, read-only projections, nested
guarantees, finite boxes, select summons, and bundle retries after reload. A separate
comparison against the pinned fork agreed on all **201 weekly banner selections**
using the destination catalogue, including holidays, NV transition, and post-history
rotation. An encrypted smoke test with `source/out/browser-data` listed eight active
banners and completed a Noctis-banner pull for 500 Lapis using only a disposable
private save and no network.

**Stage 1 remains in progress.** Next are replay-aware events and exchange shops,
followed by the remaining deals, friends, arena, rewards, and economy ports. The
native service still hosts the accepted connection check; routing the complete
game engine/assets to the iPhone and full gameplay acceptance remain pending.

## Replay-aware events and exchanges checkpoint — November 9, 2026

The next Stage 1 slice applies the campaign calendar to the existing playable
Vortex archive and exchange commands, exclusively for `ios-revival`:

- A read-only event policy uses the pinned run/window metadata, first-week 14-day
  lookback, reruns, holiday catch-up years, ranked-event periods, and deterministic
  recurring/permanent dungeon rotations. The Vortex and archive menu share it;
  closed captured gates are removed and active gates use the real weekly bounds.
- New event entry is checked before opening an attempt or spending stamina/orbs.
  A pending battle can resume after rollover; completion keeps the existing
  repeat/raid settlement protections. Settled attempts cannot reopen a closed event.
- Exchange catalogues and labels exclude unreleased units and refresh across
  rollover. Custom, native medal, and Trust Coin commands enforce eligibility before
  payment. Event exchanges remain redeemable while their event is active or the
  campaign holds its currency. Stock counters retain their IDs across rollover and
  reload; monthly resets use the recorded campaign timezone.
- Pinned Skeleton Key exchange definitions are included. The nine added campaigns
  declared by `event_history.json`, including the Halloween Castle, remain closed
  pending their separate authored battle/art content port. No query downloads art.
- The real-data read-only check found that `serve_switches` implicitly granted the
  Vortex unlock. iOS initialization now persists it and the initial mission-switch
  container atomically. Older anchors can receive missing switches through the same
  command without restarting history. Views project missing containers in memory.
- `rotation --weeks 8` now lists actual events and event exchanges alongside summons.

Validation: **18 event/exchange BDD checks, 42 existing iOS foundation/summon checks,
48 legacy summon/event/repeat/raid checks, 65 shop-action checks, and 18 mode checks
passed** (191 distinct checks). The new scenarios include encrypted requests,
read-only projections, expired entries, pending resumes, persistent exchange stock,
atomic mixed medal batches, Eastern monthly reset boundaries, and failed/successful
Vortex-switch backfills. A comparison with the pinned fork agreed on all **201 weekly
event selections** using the destination catalogue and pinned run/window metadata.
The real prepared-data smoke test projected **18 events, 450 gate rows, and 1,901
exchange products/labels**, then completed an encrypted 200-Lapis exchange purchase.
It used a disposable private save, denied network access, and verified projection
state/save immutability.

**Stage 1 remains in progress.** Next are the remaining summon deals/guarantees and
their exchange sources, followed by friends, arena, rewards, economy, and added
authored content. Native gameplay routing, asset preparation/installation, and full
iPhone gameplay acceptance remain pending; the native service is still the accepted
connection check.

## Summon deals, guarantees, and ticket exchanges checkpoint — November 9, 2026

The iOS profile now includes the pinned **311 deal banners**, **107 printed bonus
definitions**, and the corresponding seven select-ticket exchange currencies:

- Deal definitions override the same catalogue IDs as the fork; printed bonuses
  fill missing terms while retaining authored bonuses and stronger guarantees.
  The generated definitions, bonus metadata, and `content/deal_specs.json` authoring
  source are copied unchanged from the reference commit.
- Ordinary pools enforce printed date ranges and limited/collaboration exclusions.
  Step/secondary pool overrides, weighted bonus choices, counted guarantees, and
  extra NV slots share effective definitions with the rate page. Explicitly named
  step guarantees keep their printed units under the campaign's historical cutoff.
- The iOS command boundary stages canonical payments, units, bonuses, and counters
  before publishing the result. Refused, partial, or exceptional grants preserve
  the original player. The legacy transaction path and wire contract remain intact.
- Six re-summon deals persist bounded free replacements, keep the paid bonus, and
  do not charge or increment the paid-purchase counter again. Changed, missing, or
  deployed main units prevent replacement. Secondary limits refresh in the native
  reply. Each accepted redo consumes an attempt; the protocol has no operation nonce.
- NV select-ticket exchanges use the shipped master prices and limits, appear while
  tickets are held, and preserve stock receipts across reloads. Historical unit
  filtering applies independently of summon-ticket pool exemptions.
- Daily deal counters and native date bounds use the recorded campaign timezone,
  including 23-hour and 25-hour days at Eastern daylight-saving transitions.

Validation: **16 new deal checks, 60 existing iOS foundation/summon/event checks,
48 legacy summon/event/repeat/raid checks, 65 shop-action checks, and 18 mode checks
passed** (207 distinct checks). A real-data sweep at each deal's historical release
age, with selection held open to isolate transactions, completed **533 primary/step
pulls across all 311 definitions** and rendered **311 rate pages without state
writes**. A separate comparison agreed with the fork on **201 weekly summon and
event selections** using the expanded catalogue.

Real encrypted flows also passed for a printed 10+1 bonus (800440), the NV
select-ticket award/redemption (9503462, ticket 1209001554), and a free result
replacement without a second charge (9503300). These checks used disposable private
saves, denied network access, and confined writes to those disposable roots.

**Stage 1 remains in progress.** Next are explicit simulated-friend initialization
and friend behavior, followed by arena progression, remaining rewards/economy, and
added authored content. Native gameplay routing, data/asset preparation (including
generated deal artwork), and full iPhone gameplay acceptance remain pending. The
native service continues to serve the accepted connection check.

## Simulated friends checkpoint — November 9, 2026

Ported the pinned crowd's deterministic handles, ranks, weekly helpers, and daily
suggestions into the iOS profile. The default crowd has 200 accounts, with 15
starting friendships and 10 daily suggestions, alongside the curated YAML helpers.
Helpers use the saved replay calendar, historical release eligibility, shipped
names, valid stats, and each form's level cap. Suggestions use the saved timezone.

Campaign initialization now saves starting friendships and crowd settings in the
same atomic candidate as the replay anchor and Vortex unlock. Existing campaigns
receive an explicit backfill without resetting their anchors, favorites, or
removal tombstones. Reads never initialize or migrate friendships. Configuration
is recorded once; changing process defaults does not resize an existing crowd.

Extended the canonical relationship model rather than importing the fork's
parallel state store. iOS friend requests accept immediately; search, details,
favorites, removal, counts, capacity checks, and invite quest progress use the
existing native rows. Relationship commands save their candidate before publishing
it and preserve the previous campaign on save failure. Duplicate requests do not
repeat progress or rewrite the save. Legacy behavior remains unchanged.

Generated and curated accepted friends share the canonical gift transaction:
one reciprocal delivery per friend per UTC day, persistent receipts, one-time
collection, and existing quest/archive accounting. Removed recipients are refused.

Validation: **14 new BDD scenarios, 76 existing iOS checks, 23 legacy arena/social
checks, and 65 shop/gift checks passed (178 distinct checks).** They cover read-only
encrypted pages, deterministic initialization, timezone/DST suggestions, historical
helper eligibility, malformed settings, backfill/save failures, retries, capacity,
frozen players, favorites, curated/generated removals, reloads, and gifts.
A disposable real-data campaign exercised encrypted social and gift flows with
17 accepted helpers; a 201-week sweep checked 40,200 generated helper projections.
All writes stayed within the disposable root; no network was used. This sweep
found statless master placeholders, now excluded from helpers.

**Stage 1 remains in progress.** Next is arena progression, followed by remaining
rewards/economy and added authored content. Native gameplay routing, data/asset
preparation, and full iPhone gameplay acceptance remain pending. The running
native service continues to serve the accepted connection check.

## Arena progression checkpoint — November 9, 2026

Ported the pinned arena ladder into the iOS profile using the campaign calendar
and simulated-friend unit pool. Arena selects the shipped historical season,
generates teams of up to five distinct eligible units, and offers five opponents
per ten-minute window. Strength, gear, 0.50–1.50 ratios, weekly target scores,
score growth, standings, and Global placement brackets follow the pinned policy.
Ranking includes the top 100 accounts and the player. Scoring uses actual elapsed
UTC time across Eastern daylight-saving transitions.

Arena entry is the explicit initialization/rollover command. It records ladder
configuration once, settles the last played week using that week's final standings
and original season rewards, moves points into lifetime totals, and resets weekly
points. Empty skipped weeks grant nothing. Missing rewards preserve the unpaid
week. Ranking and restart are read-only; they continue to show an unsettled old
week until entry rolls it forward. Pending battles delay rollover and retain their
season, opponents, ratio, AI, initiative, and orb reservation.

Extended the canonical battle and medal-board handlers with staged iOS saves.
Matching/start/end retries reuse recorded state; full-team results and retirement
account for every enemy. Wins use the recorded ratio, while existing streak,
bonus, medal, daily reward, archive, and all-orb rules remain intact. Save failures
publish no partial battle, charge, reward, or board purchase. Pre-ladder pending
battles can finish before their old totals migrate. Legacy behavior remains
unchanged, including curated single-unit opponents when the iOS crowd is disabled.

Validation: **18 new arena BDD scenarios, 90 existing iOS checks, and 23 legacy
arena/social checks passed (131 distinct checks).** Coverage includes native
encrypted requests, read-only rankings/restarts, ten-minute refreshes, DST,
retries/reloads, full-team wins/losses/retirement, all-orb accounting, stale
selections, settings persistence, save failures, old pending battles, medal boards,
missed weeks, missing rewards, and malformed recorded state.

A disposable real-data campaign completed an encrypted five-unit battle in
historical season 6, credited ratio-based points, and settled a top-bracket weekly
reward with four original reward units. A 201-week sweep validated **1,005 rival
teams and 5,025 units**, including historical eligibility, level caps, ratios,
season selection, and native serialization. All writes remained in the disposable
root; no network was used.

**Stage 1 remains in progress.** Next are the remaining rewards/economy ports
(daily quests, weekly gifts, trust gains, replay mail/notices), followed by added
authored content. Native gameplay routing, data/asset preparation, and full iPhone
gameplay acceptance remain pending. The native service still serves the accepted
connection check.

## Weekly gifts and replay mail checkpoint — November 9, 2026

Ported the pinned weekly gift and four historical Global mail campaigns into the
iOS profile. The default weekly gift contains ten Rare Summon Tickets and one
Guaranteed Ticket (4★/5★/NV). Historical mail follows the saved replay window's
exclusive end, including the original appreciation-ticket quantities based on
inclusive days played from the campaign's saved historical start.

Campaign initialization records delivery settings once. Login and routine home
updates explicitly synchronize due mail using a staged atomic save; inbox reads,
diagnostics, and previews do not deliver or grant anything. Returning after time
away delivers the current weekly gift, plus all unissued historical mail. Delivery
adds inbox entries; attachments enter inventory only through the native receipt
command. Login/home inbox counters project the committed mailbox.

The pinned fixed mail IDs overlap the canonical catch-up ranges. Original replay
IDs are retained as logical issue keys, while numeric inbox IDs are allocated
downwards in a private range, avoiding both catch-up IDs and future automatic
Arena mail IDs. The issue ledger survives deletion and reload. Missing/conflicting
delivery facts and malformed settings fail visibly without resetting receipts.
Attachments must be creditable and displayable by the native mail class.

iOS receipt and deletion now stage the canonical handler's changes and save before
publishing them. Save or partial-delivery failures preserve the previous inbox,
ledger, and inventory. Duplicate receipts, deleted gifts, and clock rollback cannot
repeat a reward. Legacy mail behavior remains unchanged. Frozen/ephemeral players
and disabled persistence do not receive new grants.

Validation: **21 new policy, native-mail, and legacy compatibility scenarios;
108 existing iOS checks; 65 shop/gift checks; and 32 feature-completion checks
passed (226 distinct checks).** Coverage includes read-only inboxes, initialization
and backfill, DST, missed weeks, appreciation tiers, ID collisions, retries,
deletion, save/delivery failures, unusable attachments, and malformed ledgers.

A disposable real-data campaign claimed the weekly tickets and spent one rare
ticket on banner 9. It delivered all four historical mails, claimed their original
1/15/15/15 ticket quantities, and spent the Guaranteed NV ticket on banner 9200026.
Automatic mail remained distinct, retries preserved save bytes, and 201 weekly
previews were read-only. Pinned mail metadata was copied byte-for-byte. All writes
stayed within the disposable runtime; no network was used.

**Stage 1 remains in progress.** Next are the earned-Lapis economy and daily quests,
then trust gains, replay notices, and added authored content. Native gameplay
routing, data/asset preparation, and full iPhone gameplay acceptance remain pending.
The native service continues to serve the accepted connection check.

## Daily quests and earned-Lapis checkpoint — November 9, 2026

Ported the pinned earned-Lapis economy, 22 custom daily quests, and dated revival
bundles into the iOS profile. Campaign initialization records economy settings once:
five times earned Lapis, 150 base Lapis for original dailies, a 200-base-Lapis
completion bonus, and five varied quests by default. Existing campaigns backfill
missing settings without changing their replay anchor. Purchases, refunds, direct
balance edits, and already-normalized daily rewards bypass the multiplier.

Daily update, login/home, and relevant gameplay commands explicitly freeze the
day's set, quest definitions, actual rewards, trust-moogle metadata, and bonus.
Selection follows the pinned deterministic pool shuffle without consuming gameplay
RNG. Successful battle, summon, fusion, expedition, Arena, and gift activity uses
canonical completion/receipt guards. Views and diagnostics do not select or grant;
an expired set is empty until an explicit update. Midnight and countdowns use the
saved campaign timezone, including 23/25-hour DST days. Same-day pre-port selections
and claims are preserved. Claims never implicitly reset the day.

Daily claims and completion bonuses stage and save before publication. Duplicate,
incomplete, stale, frozen, and ephemeral claims pay nothing. Failed grants or saves
preserve inventory and receipts. Earned mail/login/quest/Arena/result projections
show converted amounts; canonical grant return values and receipts keep their
source denomination. Native result reward wrappers and unit metadata are retained.
Purchased Lapis remains the bundle's listed quantity. Legacy paths are unchanged.

The pinned bundle catalogue adds Bonus Present Ticket and twelve Hill of Fortune
runs, using the replay window for both listing and purchase. Stale captured rows
are removed; expired and sold-out requests cannot spend. Purchases save original
contents, payment, and stock together, with daily limits in the saved timezone.

Validation: **22 new daily/economy BDD scenarios, 129 existing iOS checks, 65 legacy
shop/gift checks, and 85 legacy trust/completion/summon/Arena checks passed (301
distinct checks).** Coverage includes read-only views, fixed settings, selection,
DST/midnight, claim and purchase retries/reloads, reward metadata, successful versus
refused action scoring, partial grants, failed saves, and malformed saved facts.

A disposable real-data campaign claimed 750 daily Lapis plus its 1,000-Lapis
completion bonus once, received a displayed 500-Lapis earned mail once, and bought
Early Bird with exactly 5,000 purchased Lapis. Its 35 cactuars followed canonical
conversion into 3.5 million enhancement EXP. Encrypted story clears/retries retained
single-attempt accounting and projected boosted repeat Lapis. A 365-day sweep
matched every daily selection to the pinned fork and checked all selected rewards
against real masters. Pinned custom/bundle JSON is byte-identical. All writes stayed
in the disposable runtime; no network was used.

**Stage 1 remains in progress.** Next are trust gains, replay notices, and added
authored content. Pure helpers now supply native master-reward conversions and
custom daily text, but installing these into served assets, bundle artwork, native
gameplay routing, and full iPhone gameplay acceptance remain pending. The running
native service continues to serve the accepted connection check.

## Quest trust checkpoint — November 10, 2026

Ported the pinned quest-trust policy into the iOS profile. Campaign initialization
records the enabled switch, 30% hit chance, 10-point normal gain, 5% large-hit
chance, and 50-point large gain once. Existing campaigns can backfill missing
settings atomically without changing their replay anchor. Invalid saved settings
and defaults fail visibly; diagnostics never initialize or repair them.

Each eligible own-party unit rolls independently for a cleared loaded attempt.
Large hits replace ordinary gains and cap at the unit's own requirement. The pure
planner accepts an injected random source and leaves the campaign and global
gameplay RNG untouched. Failed battles, exploration exits, zero-wave story scenes,
mastered units, Trust Moogles, and friend helpers earn no quest trust. Canonical
mastery receipts remain shared with fusion. Native results show capped before/
after trust even with zero EXP; daily progress counts actual unit gains.

The source review exposed a persistence gap: ordinary pipeline saves tolerate
failure and precede the result echo. iOS normal-battle results now stage the
canonical pipeline after explicit daily synchronization, deferring those saves.
Trust, original mastery rewards, quest progress, all completion effects, the
attempt receipt, and the raw result echo save together once before publication.
Grant, later projection, and final-save failures preserve the prior player and
save for retry. Legacy settlement, fusion, and expedition trust retain their
existing paths. The client's lack of an attempt nonce still limits delayed
retries after a new mission load.

Validation: **17 new trust BDD scenarios, 151 existing iOS engine checks,
27 connectivity checks, and 172 legacy gameplay checks passed**. Another
30 Mac launcher, 18 mode, 14 event, 10 raid-progress, 7 endpoint, and 6 decode
checks passed. Coverage includes encrypted results, zero-EXP gains, fractional
odds, large-hit boundaries, mastery and daily receipts, reloads/retries,
backfills, corrupt settings, and partial-grant/projection/save failures.

A disposable real-data campaign completed Ignis's trust from 995 to 1000 through
an encrypted clear, displayed the capped gain, and awarded original item
`21:409020400:1` once. Retrying after reload preserved save bytes. An audit guard
rejected network use and writes outside the disposable runtime.

The broader repository suite could not fully run: Android fixture paths,
`libgame.so`, a pinned pipeline bundle, Windows Java tools, and optional
`cricodecs` are unavailable in this environment. No packaged Android build or
new physical iPhone gameplay acceptance is claimed.

**Stage 1 remains in progress.** Next are replay notices and added authored
content. Native data/asset preparation, gameplay routing, and full iPhone gameplay
acceptance remain pending. The running native service continues to serve the
accepted connection check.

## Replay notices checkpoint — November 10, 2026

Ported the pinned weekly News board into the iOS profile. Initialization records
notice enablement and eight retained weeks once. Existing campaigns can backfill
missing settings atomically without changing their anchor or native read receipts.
Malformed settings and receipt indexes fail visibly; diagnostics do not repair.

Weekly summaries share the canonical iOS summon and event policies, including
holiday catch-up and post-history rotation. They include deals, newly opened
dated permanent offers, dated bundles, and enabled historical replay gifts.
Historical date filters retain exclusive window ends, and appreciation quantities
use the saved campaign start. Unported authored events remain closed.

News and native user-state projections derive indexes without saving them. Read
requests explicitly stage and save accepted IDs and their native year/index
coordinates before publication. Unknown, future, and disabled replay IDs are
ignored. Receipt save/projection failures preserve the prior campaign; retries
and reloads do not repeat writes. Existing static notice receipts retain their
recorded identities, and response copies clear unrelated captured read flags.
Legacy catalogue indexing and read masks retain their existing behavior.

The canonical content adapter serves elapsed-week detail pages at
`/exvius/notices/<week>.html`, including weeks outside the retained list. Native
dates use UTC representations of the saved local rollover, including DST.
Future and disabled pages return 404; HEAD returns the same content length
without a body. Pages escape text, show offer terms and original rewards, and
reference local prepared artwork only. Missing images retain readable text.
The fork's query-time sprite download/cache and remote fallbacks were excluded.
No notice query initializes, grants, delivers mail, writes shared content, or
consumes global gameplay RNG.

Validation: **21 new notice BDD scenarios, 195 existing iOS checks (including
27 connectivity checks), and 172 legacy gameplay checks passed.** Coverage
includes encrypted News/read requests, native GET/HEAD pages, retention,
exclusive historical bounds, DST, year rollover, saved settings, atomic
backfills, corrupt receipts, failed saves/projections, HTML escaping, local
art paths, unknown IDs, frozen/disabled persistence, and legacy compatibility.

A disposable real-data campaign read the Noctis-era News page, retained read
masks across the 2026/2027 boundary, and preserved save bytes on retry/reload.
A read-only 201-week sweep rendered **557 summon entries, 360 deals, 1,498 event
entries, 13 dated bundles, and all four historical mails**, matching the canonical
summon selection. An audit guard rejected network access and writes outside the
disposable runtime; campaign state, save bytes, and gameplay RNG remained unchanged.

**Stage 1 remains in progress.** Next is added authored content. Missing-art and
replay home-banner preparation, native gameplay routing, and full iPhone gameplay
acceptance remain pending. The running native service still serves the accepted
connection check. The previously recorded Android fixture/tooling limitations
still prevent claiming a complete repository or packaged-build validation.

## Added event content checkpoint — November 10, 2026

Enabled the nine pinned history additions for the iOS profile: Memories from the
Aquapolis, The Auracite Chosen, Guardian of the Order, The Web-Weaving Princess,
King of Darkness, Dracotaur Lancer, Orbonne Monastery Vaults, and both Return to the
Halloween Castle areas. The catalogue validates all 118 unique missions before
advertising their gates. Existing historical/holiday policies, weekly bounds,
archive selection, and News deduplication remain authoritative. Legacy catalogue
and gameplay paths retain their behavior.

The initial source inventory assembled 112 missions using the existing canonical
paths. Ported the six missing Halloween reconstructions byte-for-byte from the
pinned fork, with validation for mission/wave identity, group/enemy completeness,
and native packet shape. The iOS adapter returns private copies. It preserves the
original monster/skill and reward masters, including the 48,750,000-HP Skeleton
King. An unrelated changed encounter and the fork's shared cache path were not
imported. Missing new artwork uses the existing shipped native fallback; queries
do not fetch or prepare images.

The review also identified the ten added explorations' finite encounter plans.
Ported an exact subset of the pinned source, retaining its two authored enemy
formations and source hash. Native per-field occurrence rows coexist with
map-script boss groups without an opening combat phase. Each future encounter
rolls native-safe drop candidates; hypothetical fights do not populate the normal
drop ledger or grant inventory. Canonical settlement credits reported loot and
completed quest rewards once. Other explorations retain their existing behavior.

Validation: **18 new authored-content BDD scenarios; 207 iOS engine checks in total;
and 186 legacy gameplay/event checks passed.** Coverage includes malformed packet
and metadata rejection, private copies, historical/holiday selection, all six
encrypted Halloween loads, closed-entry refusal, resume after rollover, reward
retry/reload, failed result saves, read-only gates/News, finite field indexes,
empty/four-field drop safety, and legacy isolation.

A disposable real-data campaign loaded all **118 missions: 34 story scenes, ten
explorations, and 74 battles**. It validated **5,057 finite encounter rows**, native
monster/skill references, and preservation of script-bound groups. All six
Halloween battles settled with no unsupported rewards; retries after reload
preserved save bytes. One exploration's reported loot was also credited exactly
once. An audit guard rejected network operations and writes outside the disposable
runtime. No disk battle caches were created. The reconstruction packet's SHA-256
is `0d1d58af0b9f9740c37062d9469e313a5addb886d2d6205aedbf4de8344cbe0e`;
the field subset's missions/formations matched the pinned source exactly.

**Stage 1 remains in progress.** The source comparison identified the broader
exploration plans (238 missions beyond this checkpoint) and the fork's rare
Calamity Writ loot rule as remaining engine work. Native asset preparation,
missing artwork and replay home banners, gameplay hosting, and physical iPhone
acceptance remain pending. The running service still serves the accepted
connection check. Earlier Android fixture/tooling validation limitations remain.

## Full exploration and rare-loot checkpoint — November 10, 2026

Completed the broader exploration/loot engine slice identified above. The full
pinned packet now supplies **248 finite exploration plans and 285 authored group
formations**, retaining the approved ten-mission subset. Native fields receive
their own zone budgets and occurrence indexes, including Crystal Tower fields
70–75. Script-bound bosses and explicit group bindings remain present without
an opening combat phase. Unplanned missions retain the canonical path; derivation
creates no disk caches.

The source declares five partial lineups: Fledgling Rukh is missing from missions
`7840101`, `11310505`, and `11430201`; Roborg and Will O' Wisp are missing from
`41930101` and `41930102`. Those omissions remain explicit. The 189 unresolved
mission descriptions do not gain invented plans. Doctor reports coverage and
partial lineups without changing content or campaign state.

Campaign initialization records `EXVIUS_FIELD_ENCOUNTERS=1` and
`EXVIUS_CALAMITY_WRIT_DROP=0.5` once. Missing settings backfill atomically without
moving the replay anchor. Existing settings survive environment changes; invalid
saved settings/receipts fail without repair. Field enablement is boolean and Writ
chance is a finite percentage from zero to 100. Disabled fields retain canonical
scripted encounters. Legacy behavior remains unchanged.

The rare-loot policy adds a supported Calamity Writ after the canonical keep-one
roll, independently per wave/future field encounter row. Forecasts never grant
inventory or populate the normal drop ledger. Capture and fixed Enlightenment
loads record their native rows and bonus count with the existing pending attempt;
reload reuses those facts. Clears pay the recorded bonus alongside original
captures/fixed stone quantities, ignoring client-supplied bonus counts. Old pending
attempts receive no retroactive bonus. Failed grants or saves roll back the whole
result; retries project the saved result echo without changing save bytes.

Validation: **22 new BDD scenarios; 229 iOS engine checks, 27 native connectivity
checks, and 186 legacy gameplay/event checks passed.** Coverage includes pinned
inventory/gaps, zone budgets, policy backfill, malformed facts, strict chance
boundaries, disabled/missing policy, old pending attempts, protected reloads,
uncleared results, incomplete grants, save failures, read-only diagnostics, and
normal/protected result retries. Python syntax and whitespace checks passed.

A disposable real-data sweep derived all **248 plans and 60,444 native encounter
rows**, validating group/skill references and preservation of scripted groups.
Eight representative encrypted loads covered single/multi-zone fields, Crystal
Tower, a partial lineup, an unplanned scripted boss, normal waves, capture, and
Enlightenment. Four reward settlements verified normal/field/protected Writs,
the original 350-stone reward, and byte-stable retries after reload. Event checks
used eligible replay windows rather than bypassing entry policy. The audit guard
rejected network access and writes outside the disposable runtime; no shared
data, real campaign, or live service was changed. The full packet matches the
pinned source byte-for-byte, with SHA-256
`4e6f41a9f1cd45382c21fb6360e996aeee8f42f6fb6e917f0f300ade69a4ecd2`.

**Stage 1 engine feature ports have reached the asset-preparation boundary.** Next
is native data preparation/installation: master/version and text compatibility,
banner packs and missing artwork, replay home banners, sound/story resources,
and served-byte verification. Gameplay routing/hosting and full physical-iPhone
acceptance remain pending. The running native service still serves the accepted
connection check. Earlier Android fixture/tooling limitations still prevent a
complete repository or packaged-build validation claim.

## Core native-table preparation checkpoint — November 10, 2026

Started the asset-preparation stage with explicit `prepare-data` and read-only
`verify-data` commands. Both reuse the prepared or managed static/native layout;
neither loads the engine/campaign, downloads packs, starts listeners, or changes
shared content. Preparation takes the existing private instance lock. The running
connection service remains unchanged.

The first snapshot contains seven encrypted native files: `F_RESOURCE_MST`,
`F_RESOURCE_VERSION_MST_LOCALIZE`, `F_QUEST_MST`, `F_URL_MST`,
`F_LOCALIZED_TEXT_MST`, and daily quest names/details. It ports the pinned core
compatibility transforms: move `resources_common.cpk` and `resources.cpk` into
the upfront tutorial download, omit resources with no base/English version,
reveal quest rewards without changing quantities/extra metadata, and use the
v910 Drop Rates WebView URL. All 22 custom daily quest names/details enter the
English native tables, with matching localized versions, MD5s and sizes.

Separate pure CBC/ECB codecs and table policies from filesystem publication.
Preserve source padding layers, text column counts, existing duplicate text keys,
other languages and unrelated records. Encrypted lines use LF endings. Bad
base64, malformed records, missing required tables and inconsistent source text
checksums fail before publication.

Prepare validated generations under the private `assets/tables/` tree and select
one with an atomic `current.json` pointer. Identical inputs reuse the snapshot;
changed source bytes or preparation revisions advance all snapshot versions.
Previous generations remain intact. Failed table writes or pointer replacement
preserve the active snapshot; retries can reuse a matching complete unpublished
generation. Verification checks provenance/input freshness, exact paths, versions,
native decoding, SHA-256/MD5/size, and localized index agreement without writes.
Corrupt published facts fail visibly without repair.

Validation: **19 new preparation BDD scenarios; 248 iOS engine/preparation checks,
27 native connectivity checks, and 186 legacy gameplay/event checks passed.**
Coverage includes both layouts, padding/columns, original duplicate text keys,
malformed sources, source/output checksum failures, stale inputs, exact-version
lookup/projection, private copies, idempotence, monotonic revisions, interrupted
writes, pointer failure/retry, busy locks, symlinks, path tampering, and real CLI
JSON output. Python syntax and whitespace checks passed.

A disposable real-data run prepared **949,830 bytes across seven files**. All
seven outputs matched the pinned fork's corresponding pure transformations
byte-for-byte (with banner/art preparation disabled for this slice). It moved
both tutorial packs, omitted seven unversioned resource rows, updated 239 quest
rows, one URL row and two localized-index rows, and added 22 names plus 22 details.
The read-only verifier and exact-version projection agreed with the prepared
bytes. Repeated preparation preserved the pointer and file inventory. An audit
guard rejected networking, writes outside the disposable runtime, and all writes
during verification. Shared source hashes stayed unchanged; no engine state
loader was imported and no campaign was created.

**This is the first preparation slice, not complete native asset installation.**
Next are the remaining English labels and earned-Lapis master display conversion,
followed by full table coverage, native banner/art packs, sound/story compatibility,
managed-pack download/installation, and gameplay asset/API routing. Prepared
snapshots expose a version projection and exact-path lookup for that later host;
the current hello service does not consume them. Commands report
`scope: core-native-tables` and `gameplay_ready: false`. Full physical-iPhone
gameplay acceptance and earlier Android tooling/fixture limitations remain.

## Native English labels and economy displays checkpoint — November 10, 2026

Expanded explicit preparation to **35 output tables**: five core masters, all
25 pinned English label families, and five economy masters. Four additional
native inputs provide exchange stock and original unit/card/recipe names.
English source versions/checksums remain authoritative. The five economy-table
filename/key mappings were recovered from the literal-returning ARM64 getters
in the local v0.1.25 client artifact and corroborated by decrypting all five
prepared source files.

Ported the pinned append/fill/override rules for bundles, tickets, summons,
reconstructed abilities/monsters/skills, native event modes, item/equipment/materia
and important-item text, generated exchange products, and custom dailies. The
canonical revival bundle catalogue includes all 13 additions absent from the
legacy catalogue. Usable English, native columns/padding, duplicate shipped keys,
other languages and unrelated records remain intact except for declared
overrides. The pinned 44-item fallback file matches its source byte-for-byte;
SHA-256 is `178159ec91405a700bb161600c56ed3a9ee1a82469261a83fd96fbbed9e4b5b6`.
Unresolved product names are reported without invented translations.

Extracted the existing exchange calculation and reward tuple decoder into pure
helpers shared with gameplay. The engine still supplies its canonical unit-master
lookup. Product IDs, prices, currencies, stock limits, receipts, event associations
and unit reward metadata retain their existing meaning. Native preparation uses
the state-free summon catalogue and performs no gameplay writes or RNG rolls.

Challenge/panel/special-challenge and both Arena masters use the canonical earned-
Lapis display conversion. Preparation reads the selected slot's recorded economy
settings without loading an aggregate or repairing a save. Missing settings use
validated provisional defaults. Recorded settings ignore later environment edits;
unrelated campaign progress does not invalidate preparation. Changed settings
require an explicit new generation. Every conversion starts from original native
rows, so repeated preparation does not multiply a converted display again.

Schema-2 manifests record effective policy, slot, label coverage and source
provenance. Valid schema-1 seven-table snapshots remain readable and upgrade
atomically with higher versions. Missing new inputs, malformed metadata/settings,
or publication failures leave the prior snapshot available. Queries still perform
no writes, downloads, campaign initialization, grants, or service changes.

Validation: **16 new BDD scenarios; 264 iOS engine/preparation checks, 27 native
connectivity checks, and 186 legacy gameplay/event checks passed.** Coverage
includes English preservation/overrides, all item families and revival bundles,
unresolved references, injected unit metadata, stable exchange contracts, saved
versus provisional settings, raw-source conversion, unchanged progress, corrupt
settings/metadata, and successful/refused seven-table upgrades. Existing snapshot
failure/containment and CLI checks remain green.

The server and iOS specs document the new boundaries, with exact implementation
anchors for the extracted helpers. Strict OpenSpec validation was run against
both the working tree and an isolated HEAD baseline: both retain **417 existing
errors and three warnings**, with no new findings. Those pre-existing generated-
spec structure issues (including the iOS spec's missing Purpose header) remain
unresolved; this is not a claim that repository-wide spec validation passed.

A guarded disposable real-data upgrade produced **62,481,210 bytes across 35
files**, retaining the prior seven-table generation. All **25 English files and
the localized index matched the pinned patcher byte-for-byte**, using destination
catalogues and native English inputs. It covered **1,053 summon definitions,
2,079 exchange products with no unresolved names, and 52 bundle name/detail keys**.
All **20,307 positive Lapis reward entries** in the five economy masters converted
correctly, preserving other fields and padding. The pure exchange calculation
matched the checked-in prior calculation in both profiles. All 39 native source
hashes, the source metadata and gameplay RNG stayed unchanged. The guard rejected
networking, writes outside the disposable runtime and all verification writes;
no engine state loader was imported or campaign created.

**Next is full native-table coverage and version delivery**, followed by native
banner/art packs, sound/story compatibility, managed-pack installation and
gameplay asset/API routing. Results now report `scope: native-tables` and
`gameplay_ready: false`. Prepared bytes remain offline; the live service still
serves the accepted connection check. Physical-iPhone gameplay acceptance and
the earlier Android fixture/tooling limitations remain pending.

## Complete registered tables and version delivery checkpoint — November 10, 2026

Preparation now publishes every table in the supported Global-1167 native corpus:
**364 files: 219 JSON masters and 145 English localized tables**. The packaged
registry records names, filename tokens, keys, cipher modes and the originating
native-library SHA-256. Mappings were corroborated against all available encrypted
sources and positive client preference registrations. JSON masters comprise
**157 CBC and 62 ECB tables**; English files use ECB. Passthrough tables preserve
their encrypted records with LF outer lines; the prior core, label and economy
transformations remain in place.

Source collection rejects missing/unknown positive registrations, duplicate or
malformed preference entries, unmapped source tokens, missing sources, and English
index/checksum disagreements before publication. Five index names have positive
English metadata without registered mappings/files: `F_TEXT_CRAFT`,
`F_TEXT_DESCRIPTION_FORMAT`, `F_TEXT_EXCHANGE_SHOP`, `F_TEXT_TITLE` and `F_TEXT_URL`.
Their original rows remain untouched and are reported as unregistered; no table
files or advertised prepared versions are invented for them.

Schema-3 manifests record complete registry provenance and per-table version
floors. Published versions exceed both original source and persisted registration
versions. Generation selection advances all prior published versions even if a
source/registration floor decreases. Valid schema-1/2 seven- and 35-table snapshots
remain inspectable and upgrade atomically while retaining their original bytes.
Failures preserve the active generation.

Added an explicit `Engine(config, prepared=True)` consumer. While holding the
private runtime lock, it requires a current complete snapshot and the selected
campaign's recorded economy policy before importing engine state. Missing,
partial, corrupt, stale or provisional preparation fails without implicit
preparation or campaign initialization; failure releases the lock. Initialize the
campaign, prepare its data, and construct the prepared consumer in a fresh process.

The bound snapshot projects exactly **364 unique table identities** after canonical
version/forced-version handling. GET/HEAD returns their exact bytes and lengths;
HEAD omits the body. Owned master/English paths with unknown or stale versions
return 404 without stock/token fallback. Existing traversal validation precedes
lookup. Reads create no files/caches, download nothing, and change no campaign
facts. Closing the adapter clears its snapshot binding. Default construction,
legacy routing, unrelated assets and the live hello service keep their contracts.

Validation: **16 new BDD scenarios; 280 iOS engine/preparation checks, 27 native
connectivity checks, 186 legacy gameplay/event checks and six client-decoder checks
passed.** Coverage includes mixed CBC/ECB padding, passthrough preservation,
registration/source failures, version floors and decreases, overflow refusal,
old-snapshot upgrades, recorded-policy freshness, pre-import startup refusal and
lock release, exact encrypted initialization versions, GET/HEAD, stale refusal,
traversal and write-free queries. Python syntax and CRLF-aware whitespace checks
passed.

A guarded disposable real-data upgrade retained the old 35-table generation and
published **367,946,588 bytes across 364 files**. All 329 passthrough outputs kept
their encrypted source records, all 145 English index references verified, and
all five unregistered index rows stayed unchanged. Encrypted initialization
advertised the complete inventory; **728 GET/HEAD checks** returned exact snapshot
bytes and **364 old source-version paths** returned 404. Repeated preparation was
idempotent. The guards rejected networking, writes outside the disposable runtime,
and all verification/delivery writes. Shared source/metadata hashes remained
unchanged. Only an isolated disposable campaign was initialized.

Strict OpenSpec validation against an isolated HEAD baseline retains **417 existing
errors and three warnings**, with no added findings. The generated-spec structure
issues remain unresolved; repository-wide strict validation does not pass.
Updated the iOS/server/battle contracts and ADR-0008 for this checkpoint.

**Next are native banner/art packs and sound/story compatibility**, followed by
managed-pack installation, full gameplay hosting and physical-iPhone acceptance.
Results retain `scope: native-tables` and `gameplay_ready: false`; the live native
service remains the accepted connection check. The known Android fixture/tooling
limitations remain pending.

## Native Vortex banner pack checkpoint — November 10, 2026

Added explicit `prepare-data --vortex-art` for the English `spdungeon1.cpk`.
The stock iPhone loads Vortex textures from mounted CPKs, without Android's
loose-image hooks. Schema-4 generations publish the rebuilt pack with all 364
tables through the existing atomic pointer. Resource 6108101 is marked `TUTO`
for upfront download, its English file version names the prepared pack, and its
English checksum size matches the exact delivered bytes. Ordinary preparation
refreshes retain the enabled feature. Schema-1/2/3 snapshots remain inspectable
and upgrade without rewriting old generations.

Separate the pure flat CPK codec, read-only source/art collection and artifact
policy, atomic publication and exact delivery. Preserve all original payload
bytes, compression metadata, IDs and duplicate shipped names. Append available
canonical event, dungeon and raid images without replacing existing names.
Keep native masked UTF metadata, sorted TOC entries, TOC-relative offsets and
eight-byte payload alignment. Header `FileSize` and `TotalDataSize` are populated
with the rebuilt facts, including when the source used zero-storage cells.
Unsupported directories, indexed/CRC layouts, TOC storage or truncated data fail
before publication. PNG chunks/CRCs and source resource versions/sizes validate.

Fingerprint source bytes, image bytes and all four artwork metadata documents;
same-size changes invalidate freshness. Source and private paths retain containment
checks and overlay precedence. Missing required images fail preparation. The nine
added-area images for **703, 711, 712, 746, 747, 749, 797, 919 and 921** remain
reported in `preparation.art.missing_added`, retaining the existing fallback mounted
from the common pack. No art is invented or downloaded. Supplying a missing image
and explicitly preparing again adds it and clears its gap.

Pack/table versions advance monotonically, including after source-version
decreases; overflow fails before building. Build, table/pack writes and pointer
failures retain the active generation. Retries can reuse complete unpublished
files. Verification validates pack bytes, hashes, layout and resource-table
agreement without rebuilding, writing or importing engine state. The prepared
engine serves exact Vortex GET/HEAD bytes and refuses old versions without a
stock/token fallback. Request paths are validated first. No query creates caches,
downloads or changes campaign facts. Legacy/default adapters and hello hosting
retain their behavior.

Validation: **19 new BDD scenarios; 299 iOS engine/preparation checks, 27 native
connectivity checks, 186 legacy gameplay/event checks and six decoder checks
passed.** Tests cover native UTF storage, original compressed/duplicate entries,
unsupported and malformed archives, both layouts, source/PNG failures, image
arrival and same-size edits, monotonic versions/overflow, atomic schema upgrades,
write/pointer failures and retry, locks, symlink containment, corrupt published
facts, table/pack disagreement, real CLI JSON, encrypted initialization, exact
GET/HEAD and write-free delivery.

A guarded disposable real-data upgrade retained the old **364-table** generation
and published **610,430,498 bytes** across the tables and one **242,483,910-byte**
pack. It preserves **1,237 original entries** and appends **692 images**, for
**1,929 entries**. The rebuilt inventory and every file payload match the pinned
builder; native header sizes, sort order and offsets also verify independently.
All **730 GET/HEAD checks** matched snapshot bytes and **365 old source-version
paths** returned 404. Repeated preparation was idempotent. Shared source/metadata
hashes and gameplay RNG stayed unchanged; guards rejected networking, writes
outside the disposable runtime and all verification/delivery writes. Only an
isolated disposable campaign was initialized.

Strict OpenSpec validation retains **417 existing errors and three warnings**
against an isolated HEAD baseline, with no new findings. The generated-spec
structure issues remain unresolved; this does not claim repository-wide strict
validation passed. Updated the iOS/server contracts and ADR-0009 for this slice.

**Next are summon-banner fitting, remaining art and sound/story compatibility**,
followed by managed-pack installation and full gameplay hosting. Physical-iPhone
mounting, artwork review and full gameplay acceptance remain pending. Results
retain `scope: native-tables` and `gameplay_ready: false`; the live native service
remains the accepted connection check. Earlier Android fixture/tooling limitations
remain pending.

## Summon detail fitting checkpoint — November 10, 2026

Added explicit `prepare-banners` and read-only `verify-banners`. Separate immutable
artwork generations under private `assets/banners/` reuse the exclusive runtime
lock and atomic publisher. Their content-addressed URLs do not require rebuilding
the 364 native tables or Vortex CPK. Both prepared-host and managed static/native
layouts are supported. No source data or campaign is changed by these commands;
missing art is not downloaded or invented.

The pinned blur2 fitting policy prepares both **640:183 paid/step-up** and
**640:392 layout-0/base** variants. Each source remains at native scale, centered
over blurred/darkened padding. Images within six percent of the target ratio keep
their exact bytes. Output filenames include their full SHA-256, giving changed
pixels new native cache identities. Source PNG structure, path containment,
catalogue override order, locale variants and step extras are validated. Exact
native URL sources precede extracted/community basename fallbacks. Hash source
bytes and six current catalogue documents, plus renderer policy/version; same-size
edits invalidate freshness. Pillow 13.0.0 and wheel hashes are pinned in the
isolated iOS environment and the locked sync was exercised.

Before adding the projection, extracted the existing gacha master/layout and
detail/offer blocks. Each extraction passed an **88-test** gate. All **1,053
catalogue banners and 1,708 detail rows**, including box groups, matched the
captured baseline. Structural risk dropped from **81 to 67** before the feature.
The shared builder remains the projection point for entry, step/result and box
refreshes; signatures, costs, rewards, counters, layouts and offer shapes retain
their contracts. Legacy and unprepared paths do not acquire fitted names.

The explicitly prepared engine binds current artwork if available and refuses
stale/corrupt artwork before state imports, releasing its lock on failure. It
selects variants from actual wire layout facts and renames only known detail and
carousel fields. Bare list names and missing image names remain unchanged.
Closing clears the binding. GET/HEAD uses only the verified snapshot; supported
native path prefixes share the same content identity. Unknown fitted names return
404 without stock fallback and traversal is rejected first. Queries do not fit
images, download, write artwork caches or change campaign facts. Canonical POST
request recording remains controller telemetry and retains its existing behavior.

Artwork validation checks the pointer, manifest, complete two-frame inventory,
PNG bytes, dimensions, names and hashes without rendering. Identical inputs reuse
the generation. Invalid renders, image writes, pointer failures, damaged snapshots
and unsafe paths preserve the active generation without repair. Old files remain
intact; retries can reuse complete unpublished outputs. Table and artwork pointers
remain independent.

Validation: **19 new BDD scenarios; 318 iOS engine/preparation checks, 27 native
connectivity checks, 186 legacy gameplay/event checks and six decoder checks
passed.** Coverage includes frame/tolerance behavior and native source pixels,
locale/override precedence, both layouts, same-size changes and image arrival,
source/render failures, locks, unsafe paths, corruption, publication failure/retry,
private-copy/idempotent projections, native aliases and GET/HEAD, CLI JSON,
encrypted entry, step/box refreshes, stale startup and lock release.

A guarded real-data preparation produced **974 variants from 487 available
sources**, stored as **972 unique PNGs totaling 203,750,954 bytes**. All 974 outputs
matched the pinned renderer **byte-for-byte**. Full catalogue projection renamed
**2,166 detail/carousel references**. **307 missing names** remain explicit gaps
and stay unrenamed. All **1,944 image GET/HEAD checks** returned matching bytes,
lengths and PNG type; unknown names returned 404 and traversal returned 400.
Representative paid/base outputs passed local native-size visual review. Shared
source/metadata hashes, gameplay RNG and campaign facts stayed unchanged. Audit
guards rejected network use and asset/campaign writes during reads; canonical POST
request records were allowed. Only a disposable campaign was initialized.

Strict OpenSpec validation against an isolated HEAD baseline retains **417
existing errors and three warnings**, with no new findings. Syntax and CRLF-aware
whitespace checks passed. Updated the iOS/server contracts and ADR-0010; structural
drift reports no spec gaps. Existing generated-spec structure issues remain
unresolved, so repository-wide strict validation does not pass.

**Next are sound/story compatibility and remaining missing artwork**, followed by
managed-pack installation and full gameplay hosting. Physical-iPhone visual and
gameplay acceptance remain pending. Results retain `gameplay_ready: false`; the
live native service remains the accepted connection check. Earlier Android
fixture/tooling limitations remain pending.

## Native sound preparation checkpoint — November 10, 2026

Implemented explicit `prepare-sounds` and read-only `verify-sounds`. This checkpoint
prepares sound artifacts independently; coordinated native resource tables and
sound delivery are the next slice.

The pinned fork enables keyless HCA type-1 decryption and HCA-MX-to-HCA waveform
flags by default. Its story-text CPK rewrite is disabled because the actual iPhone
rejected both rebuilt scene-pack versions with an invalid CRI IFF-header error.
That rewrite remains disabled here; original story packs remain in use.

Sound preparation now:

- Reads the six original encrypted resource, version and checksum masters for
  the ordinary and map resource families. Requires positive, exact file versions;
  native iOS sources take precedence. Missing versions never use stock token or
  highest-version fallback.
- Separates read-only source collection, pure bounded UTF/AFS2/HCA codecs, and
  private snapshot commands. Supports both prepared and managed content layouts.
  Reuses the validated UTF schema codec and checksum-locks fastcrc in `.venv-ios`.
- Validates archive offsets, waveform encodings, HCA layouts and every header/frame
  CRC before converting. Removes cipher type 1, rewrites checksums and reflags
  HCA-MX without decoding/re-encoding audio or changing file lengths. Supported
  native iOS sources remain byte-identical. Corrupt or unsupported streams fail
  visibly, including keyed ciphers and external AWB dependencies.
- Processes one bank at a time and publishes content-addressed files through an
  atomic private `assets/sounds/current.json` pointer. Full provenance includes
  source hashes, resource identities, original platform sizes, measured lengths
  and transformation counts. A second inventory rejects changes during the build.
  Repeated inputs reuse the generation; failed builds/publication preserve the
  active pointer and complete interrupted builds can be reused on retry.
- Verifies output hashes, formats, lengths, waveform counts and current inputs
  without conversion, cache writes, locking, engine imports or campaign creation.
  The launcher dispatches all artwork/sound commands through the isolated runtime.

All **782 resource references** resolve to **735 unique banks**, totaling
**2,202,569,152 bytes** and **1,727 waveforms**. The source size masters contain
**49 iOS size discrepancies** and **48 Android size discrepancies**, including
zero and stale positive values. These are recorded rather than silently patched
or trusted as an integrity check. Bank structure/CRCs and source SHA-256 provide
independent validation; the next resource-table integration must use measured
output lengths.

Validation: **380 iOS checks passed**, including **35 new sound checks** and the
27 connectivity checks. **203 legacy/decoder checks passed** with disposable
fixtures where required. An additional legacy event-archive audit was unavailable
because its decoded memorial-data fixture is absent; no archive code changed.
The guarded real-data run prepared and verified all 735 banks in a disposable
runtime, compared every output byte with the unmodified pinned converter, and
confirmed idempotency. It decrypted **388 streams** and reflagged **816 waveform
rows**. Source files stayed unchanged; verification made zero writes, with no
network use or engine imports. Actual iPhone audio playback remains unverified.

Updated the iOS and launcher contracts, command documentation and ADR-0011.
Strict OpenSpec validation adds no findings to the existing **417 errors and
three warnings**. Static drift reports no code/spec gaps for tracked changes;
two informational decision-freshness notices remain. The new sound files have
explicit implementation anchors and BDD coverage; the drift tool's Git-based
change scan excludes untracked files until they are checked in.

**Next is coordinated sound resource-version/size table publication and exact
file-backed GET/HEAD delivery.** The sound manifest reports `delivery_ready: false`;
this checkpoint does not change native table versions or engine/CDN routing.
Remaining artwork, a validated story repair if needed, managed pack installation,
full gameplay hosting, and physical-iPhone acceptance remain pending.

## Coordinated sound delivery checkpoint — November 10, 2026

Implemented `prepare-data --sounds` and exact, file-backed sound delivery through
the explicitly prepared engine. Sound conversion remains in `prepare-sounds`;
table preparation requires current, verified sound artifacts and does not build
or repair them.

Schema 5 now publishes all 364 native tables with a pinned sound-generation
directory and manifest SHA-256. Both ordinary and map resource families advertise
new common sound file versions and measured iOS byte sizes. This repairs all
49 stale/zero iOS size entries in the prepared outputs while preserving Android
size fields, other languages, unrelated rows and shared source files. Source table
hashes must agree between native and sound preparation, and every resource/path
binding is checked before publication and on load.

The table pointer atomically selects the complete version/size/artifact binding.
Sound banks remain under their immutable content-addressed sound generation;
they are neither copied into table generations nor retained as a 2.2 GB memory
cache. Sound and Vortex features stay enabled on later ordinary refreshes. Schema
5 supports both together, and schemas 1 through 4 remain inspectable and upgradeable.
Versions advance above prior published identities even when source versions
fall; signed-32-bit overflow fails before publication. Repeated inputs reuse a
generation. Interrupted publication preserves the old binding and complete
unpublished table generations can be reused on retry.

The prepared engine binds the table snapshot's recorded sound generation rather
than following the mutable sound pointer. Startup requires current preparation
before importing state and releases the runtime lock on failure. Exact iOS sound
GET/HEAD reads one pinned bank at a time and rechecks containment, byte length and
SHA-256 before sending a response. HEAD has no body. Old and unknown sound versions
return 404 without stock/token fallback; damaged or missing bound files return
an empty 500 response. Reads do not convert, repair, refresh inputs, download,
write caches or change campaign facts. Existing engines without a sound binding
retain their previous behavior.

Artifact-only sound reports still use `delivery_ready: false`; coordinated table
reports now expose `sound_delivery_ready: true`. The live LAN service remains
the connection check and does not yet host gameplay.

Validation: **399 iOS checks passed**, including **19 new sound/table/delivery
checks** and the 27 connectivity checks. **203 legacy/decoder checks passed**.
BDD covers both content layouts, schema-4/Vortex coexistence, exact source
provenance, monotonic versions after source decreases, overflow, publication
failure/retry, immutable bindings after pointer replacement, damaged or escaping
banks, read-only verification, startup failure cleanup, CLI behavior, and encrypted
initialization with native delivery.

A guarded real-data run upgraded a complete schema-3 snapshot to schema 5 with
Vortex and sound enabled. It retained old generations, verified idempotency and
freshness, advertised all **364 unique table versions** through encrypted
initialization, and delivered every table plus the Vortex pack. All **735 sound
GETs and 735 HEADs** matched published hashes and lengths; all **735 stock sound
URLs** were refused. The **782 sound resource references** bind **2,202,569,152
bytes**. The disposable campaign's normal first-login daily initialization ran
in the explicit setup phase. During the subsequent audited queries, guards
rejected asset/campaign writes and network use; canonical POST request records
were allowed. Shared sources and campaign bytes stayed unchanged. The disposable
runtime was removed after validation.

Strict OpenSpec validation retains the existing **417 errors and three warnings**
with no added findings. Static drift reports no tracked code/spec gaps, stale
anchors or uncovered files; informational decision-freshness notices remain.
As before, Git-based drift excludes new untracked files until check-in; the new
sound-binding module has explicit implementation anchors and BDD coverage.
Updated the iOS/server contracts, command documentation and ADR-0012. CRLF-aware
whitespace checks passed.

**Next are remaining artwork/source gaps and managed-pack installation**, followed
by full gameplay hosting and physical-iPhone acceptance. The pinned story-text
rewrite remains disabled; any future repair needs a validated native scene-pack
builder. Actual iPhone audio playback is still unverified.
