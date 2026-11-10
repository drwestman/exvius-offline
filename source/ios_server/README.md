# Native iOS connection check

The iPhone-to-Mac connection checkpoint of
[the iOS plan](../../plans/IOS_SERVER_SOLID_CQRS_PLAN.md) is available. It serves a
setup page, a certificate profile, and an HTTPS hello page over the home network.
It does not load the game engine or a campaign. Gameplay, data installation, and
the remaining revival ports are still pending.

The reference is revival commit `47a13c084f42cf1b83b53173d0c21065c78fc2de`.

## Available commands

First-time setup, from the repository root:

```sh
python3 source/exvius/macos_ios_server.py setup
python3 source/exvius/macos_ios_server.py serve
```

`setup` requires [uv](https://docs.astral.sh/uv/) and creates a separate Python
3.12 `.venv-ios` using the checksum-locked requirements. It reuses an available
Python 3.12 or lets uv install one. It creates a private CA and server certificate
under the iOS runtime root. It does not change the Mac’s DNS, trust store, firewall,
or Android setup. After setup, the entrypoint reuses the dedicated environment;
`serve` does not install packages or initialize a campaign.

For subsequent sessions, double-click
[Check Exvius iPhone Connection.command](../../Check%20Exvius%20iPhone%20Connection.command).
Keep the Mac awake and leave its terminal open. Ctrl+C stops all listeners.

The foreground server prints the Mac’s setup URL and HTTPS hello URL only after
UDP/TCP DNS, HTTP, HTTPS, and the private control socket have all bound. The
defaults are ports 53, 80, and 443. It accepts loopback and the selected home
subnet. If a port is occupied, acquired listeners close and startup fails.

Address discovery uses the default Mac interface and its upstream IPv4 DNS resolver.
Overrides are available when needed:

```sh
python3 source/exvius/macos_ios_server.py serve --lan-address 192.168.86.40 --upstream-dns 192.168.86.1
```

Use the addresses printed by your current server; DHCP can change them. Advanced
`--dns-port`, `--http-port`, and `--https-port` overrides support diagnostics.
iPhone manual DNS requires port 53. HTTP and HTTPS links include custom ports.
Repeated `serve` with the same configuration reports the existing instance;
conflicting configurations require stopping that instance first.
The stop command waits for both listener shutdown and release of the runtime
lock before returning, so an immediate restart can safely reuse the ports.

Read-only diagnostics and the explicit stop command:

```sh
python3 source/exvius/macos_ios_server.py doctor
python3 source/exvius/macos_ios_server.py status
python3 source/exvius/macos_ios_server.py rotation --weeks 8
python3 source/exvius/macos_ios_server.py stop
```

Doctor, status, and rotation print JSON without initializing the engine, creating
a save, downloading data, writing caches, or starting services. Status reads the
private control socket when a service is running. It reports `mode: connectivity-check`,
`hosting: running` and `ready: true`, or `hosting: stopped`. Doctor reports whether
Python, dependencies and certificates are prepared. `missing_data`/`game_data_ok`
are informational for the later gameplay milestone and do not prevent hello hosting.

## On the iPhone

1. Connect the iPhone to the same home Wi-Fi as the Mac.
2. Open the printed `http://<Mac address>/` setup URL in Safari. If this fails,
   check the Mac firewall allows incoming connections for this Python runtime,
   and that the Wi-Fi network does not isolate devices from each other.
3. Download the certificate profile from the page. Open Settings → General →
   VPN & Device Management and install **Exvius Offline iPhone Connection**.
4. Open Settings → General → About → Certificate Trust Settings and enable full
   trust for **Exvius Offline iOS Root**. Installing a downloaded profile alone
   does not enable TLS trust. [Apple instructions](https://support.apple.com/en-us/102390).
5. In Settings → Wi-Fi → your network’s ⓘ → Configure DNS, choose Manual and
   use the printed Mac address as the **only** DNS server. Save it.
   [Manual Wi-Fi DNS instructions](https://developers.cloudflare.com/1.1.1.1/setup/ios/).
6. Open **https://v900-lapis.gumi.sg/__exvius/hello** in Safari. Success is the
   **Secure connection successful** page loading without a certificate warning.
   This confirmation view differs from the HTTP setup guide. Also open an ordinary
   website to verify DNS forwarding.

The service answers `gumi.sg`, `exvius.com`, and their subdomains locally and
forwards ordinary queries to the Mac’s upstream resolver. Game-domain AAAA
queries return no IPv6 answer. Upstream failures return SERVFAIL and are logged.
Only the public CA/profile and hello pages are served; game POSTs return 503.

When finished, stop the server and restore Configure DNS to **Automatic** on
the iPhone. Manual DNS applies to this Wi-Fi network, not cellular service.
Physical iPhone reachability and warning-free HTTPS were confirmed by the user
on November 9, 2026. Ordinary browsing and gameplay remain separate device checks.

`rotation --weeks 8` previews the actual iOS summon catalogue: permanent banners,
release sets, holiday selections, and ticket-pool exemptions for each calendar
window (`to` is exclusive). Before initialization it reports `anchored: false`
and uses one provisional anchor for the whole preview; viewing it does not begin
the campaign. Each window also lists the selected Vortex events and available
event exchanges, including exchanges retained for leftover currency.

The engine uses the same policy for encrypted summon lists, purchases, and drop
rates. Historical pools include units released before the window's end, with the
pinned fork's featured-holiday and one-off-ticket exceptions. NV permanent
summons appear at the NV era. After history ends, a deterministic weekly shuffle
selects one special and two featured release sets. Purchases recheck eligibility
before spending, so a banner opened before rollover cannot be pulled afterward.
Unavailable guaranteed rewards also decline without spending. The two SP ticket
bundles are one-off purchases on iOS; the plain SP ticket bundle is removed, while
already held plain SP tickets retain the historical pool limit.

The iOS catalogue also includes the pinned **311 deal banners** and **107 printed
bonus definitions**. Step costs, counted guarantees, separate NV slots, paid-pull
bonuses, weighted bonus choices, and daily/weekly/lifetime/lap limits use the
canonical transaction code. Printed pool dates and limited/collaboration exclusions
apply to ordinary draws and extra slots; an explicitly named guarantee keeps its
printed units while still respecting the campaign's historical cutoff. Rate pages
use the same effective step/offer definitions as purchases.

The seven NV select-ticket currencies earned by these deals expose their exchanges
while tickets are held. Redemption keeps the existing master prices and stock
limits, checks historical eligibility, and removes the exchange after the last
ticket is spent. Paid-pull bonuses belong to that purchase and are not repeated by
free re-summons.

The six re-summon deals let a paid result be replaced a bounded number of times.
The current result remains owned if you stop. A free redo replaces only unchanged,
unused main units; it keeps the paid bonus and does not charge again or advance the
paid-purchase count. Training, removing, or assigning those units prevents a redo.
Remaining attempts persist across reloads and are projected on the secondary offer.
As with the existing protocol, each accepted redo request consumes an attempt;
the client supplies no distinct operation nonce for distinguishing a retry from a
new choice. iOS daily limits reset at midnight in the saved campaign timezone.

iOS draws stage their payments, units, bonuses, and counters before publishing to
the live player. A refused or failed grant preserves the original state. The native
gameplay host and deal-art preparation remain later checkpoints; importing these
definitions does not download their generated artwork.

Vortex events follow that calendar too: the first week includes the preceding
14 days, reruns retain their own run dates, ranked events use their original
periods, and recurring dungeons rotate deterministically. Closed captured gates
are removed and selected gates carry the actual weekly bounds. New entries after
rollover are refused before creating an attempt or spending stamina/orbs. A pending
battle can still resume and settle through the existing reward/raid ledger.

Exchange listings and purchases share historical unit eligibility. This includes
the native medal and Trust Coin purchase paths. Event exchanges stay open while
the event is active or the campaign holds its currency; spending the last currency
after the event closes removes the exchange. Stock receipts persist across weekly
rollovers and restarts; monthly resets follow the recorded campaign timezone.
Summon-ticket full-pool exemptions do not apply to exchange rewards.

The Vortex unlock and initial mission-switch container are now persisted by the
explicit campaign-initialization command. Initializing an older iOS campaign
backfills missing switches atomically while preserving its replay anchor. Views
do not create them. The nine additional event areas declared by the pinned history
metadata are now included for iOS, with 118 original missions. They retain the
same historical and holiday entry guards. No art is downloaded by previews or
gameplay projections; new images use the shipped native fallback until prepared.

This is engine integration; the running native service still serves the connection
check. Full iPhone gameplay hosting and the remaining revival ports are pending.

The iOS economy now records its settings with the campaign. Earned Lapis defaults
to **5×**; purchases, refunds, and direct balance edits retain their original
amounts. Native mail, login calendars, quest replies, Arena results, and mission
repeat rewards project converted amounts. The canonical reward receipts retain
source amounts, so completeness checks and repeat guards keep their contracts.

Daily updates, login/home commands, and relevant gameplay commands explicitly
freeze the day's selection and actual rewards before scoring activity. The default
mix contains five different actions from the original quests and 22 pinned custom
quests. Rewards vary by day; trust-moogle metadata is retained. Original quests
default to 750 Lapis each, with a 1,000-Lapis bonus for claiming the entire set.
Claims stage all rewards and save before publishing; retries pay nothing extra.
Screens and diagnostics never roll the day forward. An expired screen reports no
current rows until an explicit update, and an expired claim grants nothing.
Midnight and its countdown follow the saved campaign timezone, including DST.

The initialization defaults are `EXVIUS_LAPIS_MULTIPLIER=5`,
`EXVIUS_DAILY_QUEST_LAPIS=150`, `EXVIUS_DAILY_ALL_BONUS=200`,
`EXVIUS_DAILY_CUSTOM=1`, and `EXVIUS_DAILY_QUEST_COUNT=5`. Existing recorded settings
survive changes to those environment variables. Missing settings can be backfilled
by initialization without moving the replay anchor; malformed saved facts are
reported without repair.

Quest trust uses the pinned revival rule: each eligible own-party unit has a 30%
chance per cleared quest to gain 1% trust; 5% of those hits give 5% instead. Gains
cap at the unit's requirement and use the canonical one-time mastery reward.
The native result shows actual before/after trust even when no EXP was earned.
Failed battles, exploration exits, zero-wave story scenes, mastered units, and
friend helpers earn none. Fusion and expedition trust retain their existing rules.

Initialization records `EXVIUS_QUEST_TRUST=1`, `EXVIUS_QUEST_TRUST_CHANCE=30`,
`EXVIUS_QUEST_TRUST_POINTS=10`, `EXVIUS_QUEST_TRUST_BIG_CHANCE=5`, and
`EXVIUS_QUEST_TRUST_BIG_POINTS=50` once. Points are tenths of one percent; chance
settings accept decimals. Invalid settings fail visibly. Existing campaigns can
backfill settings through initialization; diagnostics never backfill or repair.

iOS normal-battle results now stage the full canonical settlement after the
explicit daily update. Trust, original rewards, quest progress, completion
receipts, and result echoes save together before publication. Failed grants,
projections, or saves retain the previous campaign for retry. Repeated results
after reload grant no additional trust or mastery items. The existing limitation
remains: the client supplies no nonce to distinguish a delayed result after a new
mission load from another legitimate clear.

The iOS bundle catalogue now includes the pinned Bonus Present Ticket and twelve
dated Hill of Fortune runs. Lists and purchases share historical availability;
expired or sold-out offers cannot be bought from a stale screen. Purchases save
the charge, original contents, and stock receipt atomically. Bundle daily limits
use the campaign timezone. Legacy bundles and economy retain their existing paths.

The added content comprises Memories from the Aquapolis, The Auracite Chosen,
Guardian of the Order, The Web-Weaving Princess, King of Darkness, Dracotaur
Lancer, Orbonne Monastery Vaults, and the two Return to the Halloween Castle
areas. Six Halloween battles use the pinned original-Global reconstruction;
the other missions retain canonical battle/story paths. Bad content packets fail
visibly rather than exposing incomplete battles. Legacy content is unchanged.

The ten added explorations include their pinned finite encounter plans and two
authored enemy formations. Map-script bosses remain, and no opening battle is
invented for an exploration. Field drops retain native four-field formatting;
planned fights never grant loot. Canonical settlement pays only reported loot
and completed quest rewards, preserving reload/retry and failed-save protections.
All derivation stays in memory. The pinned pack's broader exploration plans and
rare Calamity Writ rule remain a follow-up engine slice.

Native asset preparation is still pending. Pure preparation helpers provide
converted master rewards and custom daily text; these are not yet installed into
the phone's served tables. Daily names/details, master-based challenge displays,
and additional bundle artwork still need that preparation and device acceptance.

An explicit development command can initialize a campaign using already prepared
data. Setup prepares its Python 3.12 dependencies. Stop the connection service
first; this command shares the same exclusive runtime lock:

```sh
python3 source/exvius/macos_ios_server.py init-campaign --data source/out/browser-data
```

Use `--root /path/to/private-ios-runtime` to select an alternate private root and
`--slot NAME` for a save slot. Initialization acquires the instance lock, loads
the existing canonical engine without listeners, and persists the calendar once.
Engine diagnostics go to stderr; stdout remains one JSON document. A failed
initialization releases the lock. Use a fresh process to reconfigure engine paths.

## Replay notices

The iOS News board now lists the current and seven previous replay weeks by
default. Each notice summarizes the canonical historical summons, deals, Vortex
events, dated bundles, and enabled replay gifts. Holiday and post-history
rotations follow the same policies as gameplay. Dated bundle/mail announcements
use the historical window's exclusive end; appreciation quantities use the
campaign's saved start. Viewing gifts in News never delivers or grants them.

Initialization records `EXVIUS_REPLAY_NOTICES=1` and
`EXVIUS_REPLAY_NOTICE_WEEKS=8` once. Retention accepts 1–52 weeks. Missing settings
can be backfilled without moving the replay anchor or changing read receipts.
News, native user-state projections, diagnostics, and detail pages do not write
catalogue indexes or saves. Invalid saved settings/receipts fail without reset.

Notice read requests explicitly save their native year/index coordinates before
publishing a read mask. Retries after reload make no extra writes. Old read masks
remain valid after year rollover or leaving the retained list, and unrelated
captured read flags are cleared from the response copy. Legacy behavior keeps its
existing path.

The canonical engine content adapter serves `/exvius/notices/<week>.html` for
elapsed weeks, including those outside the News list. Future/disabled pages
return 404. Pages escape text and reference local prepared artwork; missing art
leaves readable text. No remote sprite fallback, download, or cache creation runs
on a page read. Missing-art preparation and replay home banners remain part of
the later asset/hosting stage. The running native service still serves only the
accepted connection check.

## Profiles and storage

`LocalGame` explicitly selects the immutable `legacy` profile. The iOS adapter
selects `ios-revival` before importing engine modules. A bound interpreter cannot
switch profiles. Both use the same encrypted handler and `PlayerState` save code.
The iOS profile defaults the daily anniversary ticket to off, as in the pinned fork.

Shared inputs can use either layout:

| Layout | Decoded tables and art | Native resources |
| --- | --- | --- |
| Prepared host data | `mst_decoded/`, `text_decoded/`, `cpk_extract/` | `client/files/`, with `overlay/` taking precedence |
| Managed packs | `static/mst_decoded/`, `static/text_decoded/`, `static/cpk_extract/` | `native/` |

The version registry is `client/shared_prefs/gamedata.xml` under the prepared
root, or under `static/` for managed packs. Presence checks do not verify pack
hashes or establish gameplay completeness; the planned `verify-data` command
will perform content verification.

The default private root is
`~/Library/Application Support/Exvius Offline/iOS`. Campaigns use
`state/<slot>.json`, request records use `requests/`, certificates use
`certs/`, and battle caches use `cache/battles/`. Runtime and shared-content trees
must be separate, including after symlink resolution. Saves and policies under
the shared data root are ignored.

The CA identity is stored atomically in private `certs/identity.json`; the leaf
certificate/key pair is one private `certs/leaf.pem` file. Keys use mode 0600,
certificate storage uses 0700, and the profile contains only the public CA.
Repeating setup or renewing the leaf retains the root and profile UUIDs. A corrupt
or lost CA fails visibly rather than silently replacing the phone’s trust identity.
The running service renews and reloads a due leaf without restarting listeners.
The root is issued with name constraints for `gumi.sg` and `exvius.com`.

Lifecycle commands use `control.sock` under the private runtime root and an
exclusive `instance.lock`, shared with the engine adapter. Public HTTP exposes
no stop endpoint or filesystem browsing. Logs rotate at 1 MiB with two backups
under `logs/connectivity.log`; DNS errors are logged without ordinary browsing
history or request bodies.

For canonical engine consumers, `data_paths.DATA_ROOT` continues to locate
runtime policies; in iOS mode `CONTENT_ROOT` separately identifies shared inputs.
Legacy path/environment precedence remains unchanged. iOS battle views derive
cache misses in memory. Explicit preparation code can call
`battle_content.assemble(..., write_cache=True)` to build a disk cache.

The replay anchor and its settings are stored together in the campaign's
`ios_revival` record. The first `InitializeRequest` creates that record as an
explicit command before the reply's projections. Candidate state becomes live
only after its atomic save succeeds. Repeated initialization and restarts retain
the anchor. Invalid anchor data is reported without a silent reset.

Defaults match the fork: December 16, 2016; Sunday at 10 PM in
`America/New_York`; three historical weeks per real week, then two when the
historical week's start reaches August 20, 2020. Elapsed calendar weeks count
while the server is stopped. The time-zone rules retain 10 PM across DST changes.

## Validation

```sh
.venv-ios/bin/python -B source/exvius/test_ios_connectivity.py
.venv-ios/bin/python -B source/exvius/test_ios_server.py
.venv-ios/bin/python -B source/exvius/test_ios_summons.py
.venv-ios/bin/python -B source/exvius/test_ios_events.py
.venv-ios/bin/python -B source/exvius/test_ios_deals.py
.venv-ios/bin/python -B source/exvius/test_ios_daily_economy.py
.venv-ios/bin/python -B source/exvius/test_ios_trust.py
.venv-ios/bin/python -B source/exvius/test_ios_notices.py
.venv-ios/bin/python -B source/exvius/test_ios_authored_content.py
```

Use Python 3.12 with the engine dependencies for the subprocess integration
checks. Tests create synthetic masters and temporary private saves. They cover
encrypted initialization, restart/retry persistence, write failure, canonical
corruption preservation, both data layouts, instance-lock conflicts and cleanup,
read-only diagnostics, DST transitions, cache behavior, and CDN traversal and
symlink rejection. Valid resource and art fallbacks are also checked.

The summon suite covers historical/holiday selection, pool and guarantee limits,
one-off ticket purchases across reloads, Eastern weekly limits, read-only summon
views, and encrypted catalogue/purchase requests before and after rollover.
The event/exchange suite also covers event run windows, pending-battle resumes,
expired entry rejection, atomic native medal batches, persistent exchange stock,
monthly reset boundaries, and atomic Vortex-unlock backfills. The legacy event,
repeat, raid, mode, and shop checks retain their existing contracts.
The deal suite covers printed pool rules, offer-specific bonus choices, staged
grant failure, counted/NV guarantees, mixed-pool overrides, encrypted ticket award
and exchange, bounded re-summons, changed-unit rejection, native limit refreshes,
and daily reset timing. The pinned JSON files are copied unchanged; their authoring
source is retained in `source/server/content/deal_specs.json`.
The daily/economy suite covers frozen settings and daily rewards, deterministic
selection, read-only screens, DST/midnight, metadata, claims and completion bonuses,
save failures, successful-action scoring, earned/purchased Lapis, and atomic bundle
purchases. It uses disposable roots and synthetic masters. Real-data smoke checks
also exercised encrypted daily claims, mail receipts, bundles, mission repeats,
and 365 days of selection parity against the pinned fork without shared-data writes.
The trust suite covers recorded settings and atomic backfills, fractional and
large-hit boundaries, read-only planning, disabled/ineligible units, zero-EXP
clears, native result fields, mastery items, daily scoring, retry/reload behavior,
and grant, projection, and save failures. A disposable real-data smoke check also
completed Ignis's mastery via an encrypted clear and preserved the save on retry.

The notice suite covers historical selection, DST/year boundaries, retention,
local-only escaped HTML, native GET/HEAD pages, durable read masks, reloads,
failed saves/projections, disabled settings, unknown IDs, and legacy behavior.
A real-data sweep rendered 201 weeks, covering 557 summon entries, 360 deals,
1,498 event entries, 13 dated bundles, and all four historical mails without
network use, campaign changes, gameplay RNG changes, or shared-content writes.

The authored-content suite covers pinned packet validation, source-copy isolation,
replay/holiday selection, six encrypted battle loads, closed-entry refusal,
rollover resumes, reward retries, save failures, archive/News projections, finite
field rows, native-safe drops, and legacy compatibility. A disposable real-data
sweep loaded all 118 missions (34 story, ten field, 74 battle), checked 5,057 field
encounter rows and native skill references, settled all six Halloween battles
without blocked rewards, and retried a field-loot receipt after reload. No network,
shared-content writes, or disk battle caches were used.

Legacy summon and shop checks can also use the prepared data without loading a save:

```sh
FFBE_DATA=source/out/browser-data PYTHONPATH=source/server:source/exvius .venv-ios/bin/python -B -m unittest test_summon_transactions
FFBE_DATA=source/out/browser-data PYTHONPATH=source/server .venv-ios/bin/python -B source/exvius/test_actions_shops.py
```

The connectivity suite uses temporary loopback listeners, disposable certificates
and a fixture upstream. It requires permission to bind sockets; a restricted
sandbox cannot run those wire checks. It covers UDP/TCP forwarding, malformed
packets and split TCP prefixes, suffix boundaries, upstream failures, subnet
restrictions, TLS trust, CA/leaf renewal, port conflicts, lock/control cleanup,
SIGTERM, status, and idempotent startup. The foundation suite still covers the
canonical encrypted initialization/save behavior. Real game downloads, gameplay,
APK builds, and physical iPhone acceptance remain separate validation steps.
