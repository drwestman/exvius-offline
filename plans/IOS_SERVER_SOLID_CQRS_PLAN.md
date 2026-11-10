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
