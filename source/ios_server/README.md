# Native iOS connection check

The iPhone-to-Mac connection checkpoint of
[the iOS plan](../../plans/IOS_SERVER_SOLID_CQRS_PLAN.md) is available. It serves a
setup page, a certificate profile, and an HTTPS hello page over the home network.
It does not load the game engine or a campaign. Complete registered-table preparation is
also available. Gameplay hosting and full native asset installation remain pending.

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
python3 source/exvius/macos_ios_server.py verify-data --data source/out/browser-data
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

All **248 pinned exploration plans** and **285 authored group formations** are now
included. Native field IDs select their original zone budgets, including Crystal
Tower's extra fields. Map-script bosses remain, and explorations open without a
battle. Five plans retain declared missing monsters (Fledgling Rukh, Roborg, or
Will O' Wisp); 189 unresolved descriptions remain unplanned. Doctor reports this
coverage. Unplanned missions retain their canonical path. Field drops retain
native four-field formatting, and planned fights never grant loot. All derivation
stays in memory.

Initialization records `EXVIUS_FIELD_ENCOUNTERS=1` and
`EXVIUS_CALAMITY_WRIT_DROP=0.5` once. Each wave or future field encounter rolls a
0.5% chance for one additional Calamity Writ after the ordinary keep-one drop roll.
The chance accepts finite percentages from 0 to 100; zero disables it. Set field
encounters to `0`, `off`, `false`, or `no` to retain canonical scripted fields.
Missing settings backfill atomically; saved settings survive environment edits.
An installation missing the Writ item master offers no bonus.

Normal and field settlement credits reported loot with the existing completion
guards. Capture and fixed Enlightenment missions record their native drop rows
and Writ count with the pending attempt; reloads reuse that roll. A clear pays
the recorded bonus alongside original captures or fixed stone quantities,
ignoring client-supplied bonus counts. Failed grants/saves roll back the result,
and retries preserve inventory and saved result echoes. Older pending attempts
without a receipt gain no retroactive bonus. Diagnostics validate saved facts
without repair. Legacy loot and field behavior are unchanged.

Native preparation now covers all 364 registered tables in the supported client
corpus, including the pinned English labels and converted challenge/Arena displays.
An opt-in engine consumer delivers their exact versions and an explicitly prepared
Vortex banner pack. Remaining art/audio/story compatibility, full gameplay hosting
and physical-device acceptance remain pending.

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

## Offline native table preparation

From the repository root, using existing prepared content:

```sh
python3 source/exvius/macos_ios_server.py prepare-data --data source/out/browser-data
python3 source/exvius/macos_ios_server.py verify-data --data source/out/browser-data
```

Preparation uses the same exclusive runtime lock as hosting and campaign commands.
Stop the connection service before preparing its runtime, or select a separate
private root with `--root /path/to/private-ios-runtime`. Verification is read-only
and may run while the service is active. Both commands use the dedicated Python
environment and emit one JSON document. Neither starts services, downloads packs,
loads the engine/player aggregate, or changes the shared content tree. Managed `static/native`
data layouts are also supported.

Snapshots contain all 364 registered native files for the supported Global-1167
corpus: 219 JSON masters (157 CBC and 62 ECB) and 145 English ECB localized tables.
The packaged client registry records corroborated names, filename tokens, keys,
cipher modes and native-library SHA-256. Missing/unknown positive preference
registrations, unmapped source tokens, missing files or bad English checksums fail
before publication. Five known English index entries have no registered mappings
or files: `F_TEXT_CRAFT`, `F_TEXT_DESCRIPTION_FORMAT`, `F_TEXT_EXCHANGE_SHOP`,
`F_TEXT_TITLE` and `F_TEXT_URL`. They remain unchanged and appear under
`preparation.coverage.unregistered_localized`; no files or advertised versions are
invented for them. Passthrough tables retain encrypted records with outer LF lines.

Transforms still cover resource definitions/versions, quest rewards, WebView URLs,
the localized-text index, all 25 pinned English label families and five economy masters.
It moves `resources_common.cpk` and `resources.cpk` into the tutorial download,
removes resource rows without a base or English file version, reveals quest
rewards with their original quantities, and sets the Drop Rates URL to the v910
route. English labels include all canonical revival bundles, ticket names and
descriptions, summon names/details, reconstructed abilities/monsters/skills,
native event modes, exchange products, items/equipment/materia, and all 22 custom
daily quests. The pinned fallback file supplies 44 recoverable item names;
unresolved exchange products are reported rather than invented. Append-only
text preserves existing records, hook fills retain usable English, and explicit
overrides replace only the intended keys. English versions, MD5s and byte sizes
update together. Padding/column shapes, other languages and unrelated records
remain intact; encrypted lines use LF endings.

Master reward displays use the selected `--slot` campaign's saved economy settings.
Environment changes cannot override those recorded settings. Before settings
exist, preparation reports `preparation.economy.source: provisional` and uses
validated defaults without creating/backfilling a save. After initialization or
changing saved settings, run preparation again. Unrelated campaign progress does
not invalidate a snapshot. Conversion starts from the original source rows, so
re-preparation never multiplies a previously converted reward. Source quantities,
unit metadata, purchases, balances and reward receipts remain unchanged.

Files are staged under the private `assets/tables/` directory. An atomic
`current.json` pointer selects one validated generation. Identical inputs reuse
it; changed source files, registrations or preparation revisions publish higher versions and
retain the previous files. Failed publication leaves the active pointer intact.
Each version exceeds both the native source and persisted registration version.
If either floor decreases, generation selection still advances every prior version.
Existing seven- and 35-table snapshots validate and upgrade atomically to schema 3,
keeping their old files and versions. Missing new inputs leave the old
snapshot available.
Malformed sources or corrupt published snapshots fail visibly without repair.
`verify-data` detects stale inputs as well as damaged output bytes and unsafe paths.

New results explicitly report `scope: native-tables` and `gameplay_ready: false`.
The current hello service does not serve these files. Managed-pack downloading/
installation, remaining art, sound/story compatibility, full gameplay hosting and
physical iPhone acceptance remain pending.

### Native Vortex artwork

To include the stock iPhone's English Vortex banner pack:

```sh
python3 source/exvius/macos_ios_server.py prepare-data --vortex-art --data source/out/browser-data
python3 source/exvius/macos_ios_server.py verify-data --data source/out/browser-data
```

This upgrades to schema 4 and publishes `spdungeon1.cpk` with all 364 tables under
one atomic pointer. Resource 6108101 gets upfront download class `TUTO`, the pack's
new English file version and exact byte size. Once enabled for the runtime,
ordinary `prepare-data` refreshes keep Vortex art enabled. The option applies only
to preparation. Older schema-1/2/3 generations remain readable and intact.

Preparation preserves original payloads, compression metadata, IDs and duplicate
shipped names, appending available canonical event/dungeon/raid images without
replacing names already in the pack. The archive keeps masked native UTF metadata,
case-insensitive TOC ordering, aligned payloads and correct header/content sizes.
Source versions/sizes, source hashes, PNG chunks, paths and the supported CPK layout
are validated before publication. Missing required images or corrupt sources fail
without changing the current generation. Unsupported pack layouts fail visibly.

The current corpus adds 692 images to 1,237 original entries. Nine authored-event
images remain unavailable: areas 703, 711, 712, 746, 747, 749, 797, 919 and 921.
`preparation.art.missing_added` reports them; their existing gameplay fallback is
mounted from the common pack. This command downloads or invents no artwork.
Supplying an image and explicitly preparing again clears its gap. Changes to art
bytes, even at the same size, or metadata make verification stale. Verification
validates published bytes and resource-table agreement without rebuilding a pack.

The prepared engine serves exact Vortex GET/HEAD bytes and returns 404 for old pack
versions without falling back to stock files. Both prepared and managed data
layouts are supported. Physical-iPhone mounting/visual acceptance, missing artwork
and sound/story compatibility remain separate checkpoints.

### Summon detail fitting

Update the dedicated runtime dependencies with `setup`, then prepare available
summon detail images explicitly:

```sh
python3 source/exvius/macos_ios_server.py setup
python3 source/exvius/macos_ios_server.py prepare-banners --data source/out/browser-data
python3 source/exvius/macos_ios_server.py verify-banners --data source/out/browser-data
```

This uses checksum-locked [Pillow 13.0.0](https://pypi.org/project/pillow/13.0.0/).
Both prepared-host and managed static/native layouts are supported. Use the same
`--root` and `--data` as the prepared engine. Artwork uses the private runtime lock;
stop its service before preparation. Verification is read-only. Stdout is one
JSON document; diagnostics use stderr. No command downloads missing artwork or
initializes a campaign.

For each available source PNG, prepare both paid/step-up (640:183) and layout-0/base
(640:392) frame variants. The pinned fitting policy keeps the source at native
scale, centered over a blurred/darkened copy; art already within six percent of
the frame ratio retains its exact bytes. Bare list images stay unchanged.
Each fitted filename contains its output's full SHA-256, so changed bytes get a
new native cache identity. The current corpus has 487 available sources and 307
missing detail names. Missing names appear in the report and remain unrenamed;
supplying them and preparing again clears their gaps.

An independent atomic pointer under private `assets/banners/` selects the artwork
generation. Image changes do not rebuild native tables or the Vortex CPK. Repeated
inputs reuse a generation; failed rendering/writes/pointer replacement preserve
the active one, and old generations remain intact. Source bytes, current catalogue
documents and renderer policy/version determine freshness, including same-size
edits. Corrupt PNGs, unsafe paths and damaged published facts fail without repair.
`verify-banners` checks hashes, content filenames, PNGs, dimensions and freshness
without fitting images or writing files.

The prepared engine binds a current artwork snapshot if present and rejects stale
or corrupt artwork before loading campaign state. Native entry, step/result and
box refreshes share the same detail/carousel projection and select the frame from
actual wire layouts. GET/HEAD returns verified PNG bytes for the content name,
including the supported native language/path prefixes. Unknown fitted names get
404 without source fallback. Reads do not resize, download, write asset caches or
change campaigns. Canonical POST request recording retains its existing path.
Restart the prepared engine after publishing a new artwork generation.

The default/legacy adapters and hello service retain their behavior. Local native-
size review and parity checks cover the prepared outputs; actual iPhone visual
acceptance, missing art and sound/story compatibility remain pending.

### Prepared engine consumer

Development consumers can explicitly construct `Engine(config, prepared=True)` in
a fresh Python 3.12 process after running `init-campaign`, `prepare-data` and
`verify-data` for the same root, data and slot. The adapter holds the runtime lock
and validates complete, current preparation with recorded campaign settings before
loading engine state. Missing, old partial, corrupt, stale or provisional snapshots
fail without automatic preparation or campaign initialization. Default engine
construction retains its existing behavior; `serve` remains the connection check.
Use `prepare-banners` and `verify-banners` to include optional summon detail fitting.

The prepared engine projects exactly 364 unique published table versions after canonical
version handling. Table GET/HEAD requests return exact snapshot bytes and lengths;
HEAD has no body. Unknown or old versions under `mst/` and `localized_texts/en/`
return 404 without falling back to stock files. Schema-4 snapshots apply the same
exact-version rule to the prepared Vortex pack. Path validation runs before lookup.
Reads do not write caches, refresh inputs, download or change the campaign. Closing
the engine unbinds its snapshot. This adapter is ready for the later gameplay host.

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
hashes or establish gameplay completeness; `verify-data` checks the prepared native
table snapshot and its input freshness, rather than all resource packs.

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
.venv-ios/bin/python -B source/exvius/test_ios_full_tables.py
.venv-ios/bin/python -B source/exvius/test_ios_vortex_art.py
.venv-ios/bin/python -B source/exvius/test_ios_banner_fitting.py
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
