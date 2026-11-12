# Native iPhone gameplay acceptance

This record follows the [server plan](IOS_SERVER_SOLID_CQRS_PLAN.md) and
[setup/launch guide](../source/ios_server/README.md). Mac preparation and local
probes do not establish physical-iPhone gameplay acceptance.

## Current core-flow checkpoint — November 12, 2026

The exercised iPhone flows now pass: Home/audio, reward mail, a ticket summon
and Drop Rates, the native unit list, Vortex/Enhance navigation, an easy quest
with a borrowed companion, bundle and exchange purchases, and a fresh login
after clean server stop/start. The latest save has rank 3, 1,347 free Lapis,
zero paid Lapis, Gil 1,000,013 and one NRG Restore 10. The two original units
are level 11 and Strago is level 1.

This is a core-flow checkpoint, not full-catalogue acceptance. Arena remains
behind its legitimate story unlock; installed-build/manual-DNS recording,
initial-download/relaunch details and remaining artwork/menu breadth retain
their individual statuses below. The host remains running for play.

## Session baseline

Recorded November 11, 2026 at 15:57 UTC, against hosting commit `0742b7f`.

| Setting | Observed value |
| --- | --- |
| Target client | Global build 1167 (`ver.9100`) |
| Installed iPhone build | User is unsure; observed request AppVersion: 1167 (not independently confirmed as installed build) |
| Private runtime | `~/Library/Application Support/Exvius Offline/iOS` |
| Save slot | `campaign`, newly initialized for iOS on November 11 |
| Shared inputs | Checkout `source/out/browser-data`, read-only |
| Mac address / subnet | `192.168.86.40` / `192.168.86.0/24` |
| Upstream DNS | `192.168.86.1` |
| Listeners | UDP/TCP DNS 53, HTTP 80, HTTPS 443 |
| Service at this checkpoint | `mode: gameplay`, `ready: true` |
| Setup URL | <http://192.168.86.40/> |
| Secure hello URL | <https://v900-lapis.gumi.sg/__exvius/hello> |

The existing trusted CA was retained. Its SHA-256 is
`48be4374d955142bd5cf41b55dfd71ae942438bec065c9a13758d0a19a3674f6`.
Preparation left all existing certificate bytes and the shared registry unchanged;
an audit guard refused writes to the repository/shared corpus. No APK, client
package, Android/browser save or Mac DNS/trust setting was changed.

## Mac results

| Check | Result | Evidence |
| --- | --- | --- |
| Fresh private campaign | Passed | Explicit init-campaign; no previous campaign existed |
| Native sound preparation / verification | Passed | 735 banks, 2,202,569,152 bytes |
| Summon artwork preparation / verification | Passed | 974 fitted images, 972 unique files; 307 sources remain missing |
| Home artwork preparation / verification | Passed | 692 source names, 628 unique files; nine sources remain missing |
| Coordinated table preparation / verification | Passed | Schema 5, 364 tables, Vortex pack, 735 sound bindings |
| Gameplay startup | Passed | Persistent runtime, original CA, actual ports 53/80/443 |
| Game-domain IPv4 and empty IPv6 | Passed on Mac | UDP and TCP probes against the running server |
| Ordinary DNS forwarding | Passed on Mac | UDP and TCP example.com lookups |
| HTTP setup and public profile | Passed on Mac | Setup GET and profile HEAD returned 200 |
| Trusted HTTPS hello | Passed on Mac | GET/HEAD returned 200; GET identified gameplay readiness |
| Query isolation | Passed | Campaign bytes unchanged across all ten transport probes |
| Device gameplay traffic | Not yet observed | Zero canonical gameplay request records at this checkpoint |

All five explicit initialization/preparation commands and four read-only asset
verification commands succeeded. No synthetic InitializeRequest was sent to the
persistent campaign; its first native login remains for the iPhone.

## Device results

Work through these checks one at a time and record actual observations. Keep the
Mac awake and the foreground server running. The previously accepted certificate
and DNS setup can be reused, but current gameplay reachability needs a fresh test.

| Check | Result | Evidence to record |
| --- | --- | --- |
| Installed client | Request version observed | AppVersion 1167; installed build remains unconfirmed |
| Current Wi-Fi DNS | Pending | iPhone uses 192.168.86.40 as its only manual DNS server on the same home Wi-Fi |
| Secure Safari hello | Passed on iPhone | User confirmed the gameplay-ready page loads without a certificate warning on November 11 |
| Ordinary Safari browsing | Passed on iPhone | User confirmed example.com loads with Wi-Fi DNS unchanged on November 11 |
| Initial native downloads/login | Reached gameplay on iPhone | User reports passing the tutorial after a restart with generation 2; earlier failures are retained below |
| First-login relaunch | Restart reported | Exact restart timing and full app-switcher close remain unconfirmed |
| Tutorial battle | Completion reported after restart | User reports passing the tutorial; independent settlement and duplicate-reward checks remain pending |
| Vortex quest battle | Passed on iPhone and saved | Chamber of Experience 2110401 completed with a borrowed unit, rewards and durable settlement |
| Home navigation | Home, Summon, Units, Shop, Friends and Vortex/Enhance observed working | Enhance displays its banner; Back returns to Home with the footer restored |
| Audio | Passed on iPhone | User confirms music and button sound effects sound normal on the Summon page |
| Reward mail | Passed on iPhone and saved | Weekly Summon Gift claimed; ten Rare Summon Tickets and one Guaranteed Ticket saved with the receipt |
| Summons | Ticket draw and native Drop Rates passed | Guaranteed-ticket draw awarded Strago; user confirms unit names and probabilities display after the native-route repair |
| Native unit list | Passed on iPhone | User sees Strago under Home → Units → List after the summon |
| Shops/exchanges | Bundle and exchange purchase passed on iPhone and saved | NRG Restore 10 cost 3 Lapis, granted one item and saved stock count 1; bundle charge/reward was previously verified |
| Friends | List, companion selection and battle use passed on iPhone | User confirms the borrowed unit fights normally and the Chamber of Experience battle/rewards complete |
| Arena | Expected story lock observed; gameplay deferred | Home button is dark/inert; its unlock comes from Grandshelt Castle – Throne Room, not yet cleared |
| Artwork and taps | Vortex/Enhance banner and return navigation passed; other artwork/taps pending | User confirms Back returns to Home with its footer; no footer repair was needed for this flow |
| Restart persistence | Passed on iPhone and saved | After clean server stop/start and fresh login, user confirms rank 3, 1,350 Lapis and Strago; saved settlement remains completed |

The first-login relaunch comes from the pinned fork's play instructions: patched
download lists arrive during login, after the client has made its initial upfront
download selection. Its physical behavior here still needs confirmation.

Do not mark a device row passed from a Mac loopback probe, successful server
reply, or existing automated test alone. Record failures before changing code.
Keep full campaign saves, request payloads and client identifiers in the private
runtime; commit only the minimum acceptance evidence.

## Manual lifecycle

From the checkout, use the same content path on later launches:

```sh
./"Play Exvius on iPhone.command" --data source/out/browser-data
python3 source/exvius/macos_ios_server.py status --data source/out/browser-data
python3 source/exvius/macos_ios_server.py stop
```

The launch command is for a stopped service. Do not initialize or reset the
campaign between acceptance checks. Stop the server when finished and restore
the iPhone's Wi-Fi DNS to Automatic while it is off. Recheck the Mac address after
network changes; this record is a dated observation, not a fixed-address promise.

Full 18-pack bulk-install validation, the documented missing artwork, and story
repair remain separate open work. The unvalidated story rewrite stays disabled.


## MST_LOAD_FAILED investigation — November 11

The iPhone reported MST_LOAD_FAILED during its first download/login flow. Nine
requests reached the canonical engine, with AppVersion 1167 and no request
decryption errors, including initialization and user/home requests. The server
had no corresponding failed prepared-MST request detail in its existing log.

A concrete response defect was reproduced: PreparedTables.project_versions
removed canonical F_MST_VERSION and F_RSC_VERSION rows when restricting the
carrier to published table identities. These are bootstrap metadata, not files.
The fix preserves existing global master/resource/app version rows unchanged,
while keeping exact published versions for all 364 native tables and excluding
unknown table names. Initialization now carries 364 table rows plus the two
original global counters, rather than only 364 rows.

The new regression failed before the fix and passed afterward. All 474 iOS checks
and 200 legacy/decoder checks passed. A read-only projection audit against the
actual snapshot confirmed all 366 rows without a campaign write. Strict OpenSpec
adds no findings to the existing baseline; mapping has no stale anchors and
tracked static drift has no code/spec gaps.

The host was stopped cleanly and restarted with the fix. Its original CA identity,
replay record and table-generation pointer are unchanged; all ten Mac transport
probes passed again. No campaign reset, asset regeneration or synthetic native
login was performed. The observed client failure is not marked resolved until
the iPhone is fully closed/reopened and its download/login flow succeeds.

Device retry update: after the counter-preservation fix and app relaunch, the user reports downloading at 98% with apparent stalled progress. Completion and disappearance of MST_LOAD_FAILED are not yet confirmed.

At the apparent 98% pause, Mac network counters showed 35,751,186 additional outgoing bytes over five seconds. An iPhone HTTPS connection remained established, and no transfer exceptions were recorded. Logged ordinary assets included a 166,054,264-byte movie pack. The percentage pause was therefore not treated as proof of a stalled transfer; device completion remains pending.

Device retry outcome: after the active 98% transfer, the user reports a generic error and return to the title screen. Native download/login acceptance remains failed; investigating the subsequent failure rather than treating the counter fix as device recovery.

## Upfront resource-size correction — November 11

Audited the 57 upfront CPKs requested by the device against their iOS size fields.
Three disagreed with the exact files selected by CDN overlay precedence:

| Resource | Advertised bytes | Served bytes |
| --- | ---: | ---: |
| common map `SP4/Ver11_700010300.cpk` (127030) | 674,944 | 678,256 |
| common event `SP4/Ver5_700010308.cpk` (127038) | 18,707 | 22,160 |
| English `Ver112_resources_pretutorial.cpk` (9200402) | 7,544,683 | 7,568,144 |

Preparation now records selected paths, byte lengths and SHA-256s, corrects only
the common/English iOS size fields, and binds those facts to snapshot freshness.
The regression failed before the fix and passed afterward. The full 475-test iOS
suite and 200 legacy/decoder checks passed; two additional overlay/escape guards
also passed. Strict OpenSpec adds no findings to its 417-error/three-warning
baseline; tracked static drift has no code/spec gaps or stale anchors.

Stopped the host cleanly, explicitly prepared and verified generation 2 with its
existing Vortex/sound features, then restarted it. Coverage reports 57 checked,
three corrected and no missing upfront packs. Source writes were guarded; shared
CPK bytes, CA identity and campaign replay facts remain unchanged. All ten Mac
transport probes pass and gameplay readiness is true. No campaign reset or
synthetic native login was used. The invariant and AP-004 document the mismatch.

Physical recovery remains pending a full app close/reopen and completed download.
The size mismatch is confirmed; whether it caused the generic client error still
requires the device retry.

## Device progress and download observation — November 11

The user now reports passing the tutorial, with a restart required. This confirms
that the device reached gameplay after the metadata corrections; it does not
establish a seamless first login or explain the remaining restart requirement.
Audio, reward correctness and the remaining acceptance flows need separate checks.

At the subsequent live check, gameplay hosting remained ready on generation 2.
Recent successful requests included switch updates, summon entry and banner
images; no new host-log activity appeared during a six-second sample and no
transfer exceptions were recorded. Total Mac Wi-Fi outgoing traffic grew only
21,649 bytes over five seconds, so no bulk download was observed during that
interval. This is a momentary observation, not proof that every asset is cached;
new screens may request further assets.

## Home navigation failure — November 11

The user reports that Home renders after the tutorial/restart but none of its
icons work. Treat Home navigation as failed rather than inferring usability from
successful login. Later logs show additional unit/movie-pack downloads after the
earlier idle observation; that observation did not establish complete caching.

At the failure checkpoint, canonical initialization, all three user-info requests,
reinforcement, marquee, home/event polls and offerwall replies were answered
without request decryption errors. Two completed missions and the reported hint
switches are persisted; the saved active deck exists. Switch projection retains
the tracked types, so a dropped saved-hint container has not been reproduced.
An eight-second sample showed no new CDN or API requests and 393,657 outgoing Mac
Wi-Fi bytes. No code defect explaining the blocked taps is confirmed yet.

Requested a single Summon tap and its visible behavior to distinguish a blocked
client input layer from a pending menu transition. No player flags, saves or
client caches were changed during this investigation.

## Summon clarification and updated-reference review — November 11

The user clarifies that Summon opens but its loading indicator is a blank square,
and has updated the local revival reference. This refutes the earlier interpretation
of a global Home input failure. The reference is now ae07888, 15 commits beyond
the pinned baseline; [IOS_UPSTREAM_UPDATE_REVIEW.md](IOS_UPSTREAM_UPDATE_REVIEW.md)
records the selective review and remaining update slices.

No matching general loading-indicator repair was identified upstream. Ported the
latest native diagnostic protocol, including 590d4fb's off-by-default,
GameSetting-only request policy. A wire regression reproduced the original lack
of an encrypted acknowledgment for queued reports. The adapter now acknowledges
them without storage while off and saves bounded private reports while enabled,
without gameplay commands or ordinary-record copies. The root cause of the blank
square remains unconfirmed until a real report arrives.

The old gameplay host was stopped at the operational checkpoint. Restarted the
same runtime with temporary EXVIUS_CLIENT_REPORTS=1; generation 2 and the original
CA remain selected. All ten Mac transport probes pass with unchanged campaign
bytes. Requested a full app close/reopen and Summon retry to capture device errors.
No synthetic login or report was sent to the persistent campaign.

Final validation: all 483 iOS checks pass, plus 125 decoder/summon/completion/shop
checks and three canonical login checks with isolated state. The final host loads
the route/request-ID guard and reports ready with diagnostics enabled. One
ordinary example.com DNS lookup returned SERVFAIL after restart; subsequent direct
router and forwarded UDP/TCP checks succeeded, then all ten transport probes passed
on retry. Campaign bytes and CA identity are unchanged; no actual
device report has arrived at this checkpoint. Strict OpenSpec adds no baseline
findings; static drift has no tracked gaps or stale anchors. Physical loading
recovery remains pending the device retry.

## First summon-banner crash — November 11

The user opened Summon and tapped its first banner; the app crashed. The blank
loading square was not observed in this attempt. The server answered GachaEntry
at 19:32:06 local time, with no request decryption error, subsequent summon command
or corresponding server exception. No draw or reward outcome is claimed.

Two real startup reports arrived at 19:31, before this crash (10,481 and 1,664,127
stored bytes). Decoding works. The older-session report confirms missing summon
UI textures, including gacha_top_banner_light.png, gacha_top_textarea.png and gold
button images. Both exact source CPKs pass structural inspection: common
Ver19_gacha1_common.cpk has 31 entries and English Ver58_gacha1.cpk has 190; the
named textures are present, and their lengths match the iOS size rows. They were
scheduled as background downloads in that earlier session, without matching GETs
in the retained host log. Download/mount timing or cached state remains a
hypothesis, not a confirmed cause of the new crash. Older audio/MST/DNS errors in
these reports are not attributed to the latest attempt without fresh evidence.

Requested one relaunch stopping at Home, so the next diagnostic upload includes
the crashed session. No report for that session has arrived at this checkpoint.
No game code, campaign flags, asset files or client caches were changed during
this investigation. Physical recovery remains pending.

## Post-crash report and summon prerequisite fix — November 11

The requested relaunch reached Home and uploaded the crashed session at 19:39.
Its 1,882,991-byte report records GachaPayDetailScene at 00:32:20 UTC, missing
gold summon-button textures, monster_anime_3110010.png and
monster_cgg_3110010.csv, followed by the next startup. This is fresh evidence from
the reported attempt, rather than an error inferred from an older session.

The resource table schedules the common/English gacha1 packs and monster3_common
only in the background, behind the movie queue. The detail scene loads their
assets synchronously. Exact source-pack inspection confirms the UI textures in
the two gacha packs and the default Ochu texture/CSV in Ver36_monster3_common.cpk.
Their combined size is 17,682,014 bytes. This confirms a prerequisite-delivery
defect; physical proof that it resolves the crash still requires a retry.

Pipeline revision 5 classifies these three dependencies as TUTO while preserving
existing TUTO/PRE_TUTO classes and unrelated background packs. Their source paths,
hashes and measured iOS sizes join the upfront provenance. The regression failed
before the fix and passed afterward; all 484 iOS tests pass. Read-only inspection
of the real inputs reports 60 upfront packs checked, three corrected sizes and
none missing. No draw rules, source packs, legacy projections or campaign facts
are changed. The invariant and AP-006 document the dependency-ordering boundary.

Published and verified generation 3 with the existing Vortex/sound features, then
restarted gameplay with diagnostic capture still enabled. The guarded operation
preserved full campaign bytes and CA identity and refused shared/source writes.
The running snapshot advertises all three dependencies as TUTO. Ten Mac transport
probes and exact HTTPS GET/HEAD checks for each pack passed, including byte lengths
and GET hashes; campaign bytes remained unchanged. These six asset probes use
User-Agent Exvius-Acceptance-ReadOnly and are not device download evidence.

Requested a close/reopen with completed startup downloads, one further relaunch
to apply the updated list, then the first Summon banner retry. The host is ready;
physical recovery remains pending that result. No campaign reset or synthetic
gameplay login was performed.

## Generation-3 retry and required-data dialog — November 11

The user reports that the banner still crashes and that every launch shows
Downloading Required Data with Download before tutorial / Download after tutorial.
Neither choice visibly shows progress. Generation 3 has not resolved physical
acceptance. Asked whether the dialog displays a nonzero size, zero, or no size.

The latest uploaded report covers the 20:06 local-time crash: it still reports the
two gacha packs and monster3_common as absent. The host's ordered log shows the
first real iPhone GETs for those three exact packs only after the subsequent
20:12 initialization. Those GETs returned 200, but do not prove installation or
mounting. This report predates those transfers; a report following the latest
failed attempt is needed to establish whether the same absence persists afterward.

Read-only validation of the running snapshot finds 521 resource rows, no entries
with both iOS common/English versions zero, and all three menu rows marked TUTO.
This rules out reintroducing the seven known unversioned resources in the current
prepared table. Upstream documents both TUTO and PRE_TUTO as blocking classes;
changing the class name again is not justified by the available evidence.
No campaign/cache reset or speculative code change was made during this check.

## Client installation confirmed — November 11

The next relaunch reached Home and uploaded a 2,589,829-byte report at 20:24:59.
It confirms foreground installation of the required packs during the preceding
20:12 login: common gacha1 completed at 01:12:50 UTC, English gacha1 and
monster3_common at 01:12:53. All 12 files in that login download completed by
01:13:49, including the prepared Vortex pack. This is client installation evidence,
beyond the earlier server GET observations.

The banner crash recorded in this report remains the 01:06:46 attempt, before
those installs; no newer banner attempt is recorded after installation. The user
is now on Home. Requested one first-banner retry to test the installed assets.
Installation is confirmed; banner recovery and the recurring required-data dialog
remain unconfirmed. No additional code, data or campaign changes were made.

## Banner-opening recovery confirmed — November 11

After the reported prerequisite installs and subsequent relaunch, the user opened
the first Summon banner and confirmed that it displays without crashing. The
corresponding GachaEntry request arrived at 20:27:23 local time. Physical recovery
of this banner-opening failure is now passed; this result is based on the user
observation, supported by the earlier client installation report.

No summon was executed by the agent. Draw/rates/cost/ownership, audio, other menus
and restart persistence remain separate checks. Background downloads continue
(recent requests include esper movie packs), so completion of the whole asset
queue is not inferred from the usable banner page. Next is the audio check.

Audio check passed: the user confirms normal music and button sound effects on
the Summon page after the prerequisite downloads. This confirms that screen's
audio, not every track in the continuing background queue. Next is one actual
summon with its animation, result, charge and saved ownership checked.

Read-only campaign inspection shows no held Rare/Guaranteed summon tickets and
one unclaimed Weekly Summon Gift containing ten Rare Summon Tickets and one
Guaranteed Ticket. Requested claiming that mail as the prerequisite for the
ticket-summon check. The agent did not claim mail or spend currency.

The user claimed the gift. MailReceiptRequest at 20:33:06 local time completed
without a decryption error; read-only inspection confirms its received marker and
saved balances of ten Rare Summon Tickets and one Guaranteed Ticket. Pre-draw
baseline: 250 free Lapis, zero paid Lapis, two unit instances. Requested one
Rare-ticket summon on the first banner, followed by its animation/result check.
No summon was submitted by the agent.

The user completed a draw and reports receiving Strago. GachaExeRequest at
20:35:33 local time succeeded without a decryption error. The request selects
banner 9/detail 9001 and native ticket ID 18; the saved receipt awards one
level-1, rarity-5 unit 206000905, whose shipped English name is Strago. Read-only
inspection confirms three saved unit instances, zero Guaranteed Tickets (one
spent), ten Rare Summon Tickets (unchanged), and 250 free/zero paid Lapis
(unchanged). This was a Guaranteed-ticket draw rather than the requested Rare
ticket; record the actual selection and debit. No agent draw/retry was sent.

The user-confirmed animation/result and saved award/charge pass this draw's
acceptance. Native roster display, restart persistence and broader rate/pool
presentation remain separate checks. Next is finding Strago in the Units list.

Native roster display passed: the user finds Strago under Home → Units → List.
Requested a full app-switcher close/reopen, then the same list, to verify app
restart persistence. The server remains running for this check; clean server
restart persistence will need a separate observation.

App-restart persistence passed: the user confirms Strago is still listed after
fully closing and reopening FFBE. Clean server stop/start persistence remains
pending. Next is opening the Shop listings without making a purchase.

Shop listing check passed: the user confirms names, images and prices display.
Read-only state still has 250 free Lapis, zero paid Lapis and 13 Gil. The native
bundle catalogue offers Bundle of Riches (990000105) for 100 Lapis, granting
1,000,000 Gil, once per day. Requested one purchase as the transaction check;
expected balances are 150 free Lapis and 1,000,013 Gil if this exact offer is used.
No purchase was submitted by the agent.

The user completed the Bundle of Riches purchase. BundlePurchaseRequest at
20:48:28 local time succeeded without a decryption error. Read-only saved-state
inspection confirms free Lapis 250 → 150, paid Lapis unchanged at zero, and Gil
13 → 1,000,013, matching one 100-Lapis charge and one 1,000,000-Gil reward.
Physical bundle purchase and its saved balance changes are passed. Exchange-shop
transactions remain separate. Next is opening the Friends list.

The saved bundle receipt also records count 1 for 990000105 on 2026-11-11.

Friends-list check passed: the user confirms the offline friends and their units
appear. Companion selection and use in battle remain unverified. Next is opening
the Arena screen to check availability, or its legitimate progression lock.

Arena is dark and tapping has no effect, as reported by the user. Read-only
verification finds FUNCTION_REEL_COLOSSEUM requires switch 10010300, mapped by
F_SWITCH_MST to type 101/index 26. F_MISSION_MST grants it on mission 1110703;
the shipped English name is Grandshelt Castle - Throne Room. The current save is
rank 1, has cleared only 1110100/1110101, and lacks that bit. The observed disabled
entry therefore matches the story gate. Arena entry/battle acceptance is deferred
until natural progression; no unlock or campaign change was applied. Next is
Vortex event-list/artwork navigation, whose explicit initialization unlock exists.

Vortex navigation failed on the device: the user sees only the blue background,
header and footer, with music continuing and footer taps ineffective. The
21:34 diagnostic upload contains a GateEntryScene → GateScene transition at
21:32:04, successful Vortex BGM installation, then a texture-load failure for
event_1115.png at 21:32:07. LayoutUtils immediately reports that it cannot create
the sprite batch node for that missing texture. No server exception accompanies
the attempt.

Read-only inspection confirms the Chamber of Supercite image is present in the
generation-3 English Vortex CPK, with valid PNG bytes and the recorded source
SHA-256. A second parser from the reference repository agrees on its TOC entry
and payload offset. Earlier client logs confirm installation of both that
prepared English pack and the common Vortex pack. This narrows the failure to
native texture availability/loading; it does not establish why the client cannot
use the packed image. No speculative pack, gate or save change was applied.
Requested a full app close/reopen and remaining on Home to capture the latest
failed session and verify recovery of ordinary navigation. Vortex remains failed.

The user confirms Home loads normally after the full client restart. Its new
report retains a second GateScene failure for the same event_1115.png texture;
there is still no accompanying server exception. The image is valid and packed,
so installation evidence alone does not establish native loading compatibility.

Binary comparison found a concrete encoding mismatch: the original native TOC
and reference builder encode UserString with reserved null-string offset zero,
whereas our prepared pack used offset 82 to a second literal '<NULL>' string.
The decoder renders both as identical text, so the earlier round-trip tests did
not detect it. A new BDD test fails on the old encoder and passes after preserving
offset zero. Artwork pipeline revision 2 invalidates the old provenance and
publishes a new pack version with unchanged source images. Whether this encoding
repair resolves the phone's freeze remains unconfirmed until the next retry.

All 486 iOS tests pass, including 21 Vortex/CPK tests. Strict OpenSpec validation
adds no findings to the 417-error/three-warning baseline, and static drift for
the diff reports zero issues. Added the format invariant to the iOS spec and
AP-007; repository-wide mapping still reports an existing diagnostic-helper
anchor issue outside this repair.

Generation 4 is prepared, verified and hosted with 364 tables, one Vortex pack,
735 sound bindings, and temporary client diagnostics. A write guard protected
the shared corpus and source; full campaign and CA-identity hashes are unchanged.
Ten transport probes and eight exact asset GET/HEAD checks pass, including the
new en/sd/area/Ver240461_spdungeon1.cpk (242,483,910 bytes). The served pack has
UserString offset zero and the exact event_1115.png source hash. Requested a full
client close/reopen, completion of downloads, one further relaunch, then Vortex
banner display and footer-Home navigation. Physical recovery remains pending.

November 12 retry remains failed: the user reports Vortex still crashes. The
08:21 local-time diagnostic upload confirms installFile END for generation 4's
Ver240461_spdungeon1.cpk in the preceding session. That session ends at
GateEntryScene, with no new event_1115.png texture failure or other explicit
asset-load error. Background master installation was still at 24/124; the log
does not establish that this caused the crash. The null-offset repair reached
the phone but has not established physical recovery. Requested clarification
whether the app now closes to the iPhone Home screen or stays on the blue screen
with music. No further pack/gate/save change was applied without that evidence.

The user clarifies that the failure closes FFBE to the iPhone Home screen;
this is now an app exit rather than the earlier blue-screen freeze. The 08:29
relaunch upload contains the 08:29:03 attempt: GateEntryScene is the last scene,
with no new missing-texture error, assertion or crash stack in the uploaded log.
Master installation was still at 30/100 before that attempt. Requested reopening
and remaining on Home to permit background completion and capture the latest
session. Download concurrency is an observation, not an established cause.
No additional runtime preparation or source change was applied.

The user is back on Home. The local host remains ready in gameplay mode; the
retained client upload still predates this Home wait, so download completion is
not yet proven. Requested one Vortex retry, followed by reopening to Home if it
exits, so the next upload includes both the wait and the failed attempt. No
further code or data-generation change was made.

The user now confirms Vortex opens after the Home wait. No code, pack or
generation change intervened between the last failed attempt and this success.
This strongly supports incomplete background data as the immediate trigger:
the last captured failed attempt had installed only 30/100 remaining masters.
The retained upload predates the wait, so exact download completion and the
specific missing dependency are not directly observed. The earlier encoding
repair was installed but its causal contribution is not isolated. Mark Vortex
entry recovered from the physical observation; footer navigation, individual
tabs/artwork and entering an event remain separate pending checks.

Next requested check: switch Vortex to Enhance, inspect its banner display, then
return through the footer Home button. No battle or transaction is part of this
navigation check. Companion battle use and clean server-restart persistence
remain later acceptance checks.

The user confirms the Enhance banner appears, but reports that the footer is
missing. Mark this banner-display check passed; returning Home remains unresolved.
The retained upload predates this view and cannot identify its current native
navigation controls. Requested a full-screen screenshot to distinguish a layout
failure from a screen with another return control. No additional pack or code
change was made from the missing-footer observation alone.

The user finds a Back button and confirms it returns to Home with the footer
visible. Vortex/Enhance banner display and the observed return-navigation flow
therefore pass. No layout repair or additional prepared generation was needed.
Next is a companion-selection check from the easiest Chamber of Experience
mission (canonical area 226, first mission 2110401), followed by a battle only
after the native companion list is confirmed.

The user confirms offline friends and their units appear at companion selection.
Read-only pre-battle saved-state baseline: rank 1/EXP 10, stored NRG 41, free
Lapis 150, paid Lapis 0, Gil 1,000,013, friend points 0, and two cleared missions.
Mission 2110401 is not previously cleared. The two original roster units are
level 2/EXP 3; Strago is level 1/EXP 0. DailyDungeonSelectRequest is observed;
no MissionStart was submitted by the agent. Requested selecting one offline
friend, completing the easiest mission and its rewards, and returning Home to
check physical companion use and subsequent saved settlement.

The user confirms the borrowed unit fights normally and the reward screen
appears after the battle. TfaMissionStartRequest and MissionEndRequest complete
without decryption errors. Read-only saved-state verification finds mission
2110401 cleared, attempt sequence 3 completed, normal rewards and quest progress
recorded, three paid challenge receipts and no blocked claims. Settlement echo
records 3,250 EXP, zero Gil and material drops. Rank advanced 1 → 3; the two
original units advanced level 2 → 11, while Strago remains level 1. Free Lapis
advanced 150 → 1,350, paid Lapis remains zero, and Gil remains 1,000,013. These
are the observed saved deltas; no claim is made that all Lapis came from the
challenge receipts alone. Physical companion battle/reward flow and durable
mission settlement pass. No request was replayed or submitted by the agent.

Next is clean server-restart persistence. Requested fully closing FFBE before
stopping and restarting the local host, then checking the same saved progress
through a fresh native login. The server has not yet been stopped for this check.

The user confirms FFBE is fully closed. Completed a clean server stop/start
without preparation or synthetic gameplay commands. SHA-256 comparisons across
seven files verify the full campaign, every existing certificate file and the
prepared-generation pointer are identical before stop, after start and after
read-only probes. Generation 4 remains active. Ten DNS/HTTP/HTTPS checks pass;
the host is ready in gameplay mode with the same trusted CA identity. Temporary
client diagnostics remain enabled for the fresh-login observation.

Expected persisted display remains rank 3, free Lapis 1,350 (paid zero), Gil
1,000,013, the two original units at level 11 and Strago at level 1, with mission
2110401 cleared and its completed settlement retained. Requested reopening FFBE
and checking rank, Lapis and Strago in the native Units list. Physical
server-restart persistence is pending that fresh-device observation.

The user confirms all three persisted values after reopening: rank 3, 1,350
Lapis and Strago in the native Units list. Fresh Initialize/GetUserInfo and
Home requests are observed. Read-only state still has the same balances, unit
levels and completed 2110401 settlement; no duplicate reward is observed on this
login. Physical clean-server-restart persistence passes. The newly uploaded log
also records the prior successful battle's result/EXP/challenge screens; it does
not directly establish completion of the earlier background master batch.

Next requested check is the first Summon banner's Drop Rates page, verifying
that native navigation opens readable unit names and probabilities. This does
not require another draw. Exchange transactions and the legitimate Arena story
lock remain separate pending/deferred checks.

Drop Rates failed physically: the user sees a blank page. Device transport logs
show two form POSTs to the exact published native URL ending in
/statics/probability/sg_summons_list.php, both returning empty 404 responses.
Read-only TLS reproduction agrees: native POST gacha_id=9 and query GET return
404, while /exvius/gacha-rates/9.html returns valid 8,927-byte HTML. The URL
projection is correct, but the canonical content handler lacked the stock
WebView route adapter. The earlier encrypted-API-routing hypothesis was refuted;
the request correctly reached resource routing and then missed its HTML handler.

Added a small iOS-only rates-delivery adapter under the canonical state lock,
reusing the existing replay-aware renderer. It reads bounded fresh form/query
fields, supports GET/HEAD/POST, and renders current summon links when no ID is
supplied. Invalid/ambiguous requests fail without gameplay dispatch. It retains
the reference form reader's MIME-label tolerance, while avoiding retained form
state and body logging. Legacy routing, banner pools and purchases are unchanged.

The native-form BDD regression reproduced the empty 404 before the fix. All four
new route tests, all 490 iOS tests and 22 legacy summon tests pass. Tests cover
matching HTML, distinct successive banners, exact HEAD lengths, escaped replay
index content, malformed/oversized requests and legacy isolation; campaign/save,
RNG and ordinary request-record preservation are asserted. Updated both specs,
ADR-0001, runtime documentation and AP-008. Strict validation adds no findings
to the 417-error/three-warning baseline; static diff drift reports zero issues.

Restarted the host with the adapter, retaining generation 4 and all seven
save/certificate/generation-pointer fingerprints. An early TLS probe ran before
startup completed and timed out; after readiness, all ten transport probes and
all three rates checks pass. Native POST, native query GET and the existing HTML
route each return UTF-8 HTML with the chance table and matching 8,927-byte
lengths. No preparation or gameplay command was issued. Requested closing the
blank page and reopening Drop Rates; physical rendering recovery remains pending.

The user now confirms Drop Rates displays unit names and probabilities. A new
native form POST for banner 9 returns 200 with 8,927-byte HTML. Physical page
rendering passes, and saved rank, Lapis and Gil remain unchanged at 3, 1,350 and
1,000,013. This closes the missing-native-route failure for the observed banner.
Next is Exchange Shop catalogue display. The current save has summon tickets
and ordinary materials; no event-exchange currency was established, so an
exchange purchase is not requested before eligibility and cost are verified.

The user confirms exchange item names and prices display. Current-source
inspection finds a purchase eligible without event tokens: the Daily Coin Shop's
NRG Restore 10, product 940002004/detail 850001002. The permanent category-6
catalogue uses Lapis (kind 50/id 1), with price 3, one item per purchase and a
monthly limit of 80. This non-unit reward is replay-eligible. Saved baseline is
1,350 free Lapis, zero NRG Restore 10 items (23:100), and no receipt for this
product. Requested purchasing exactly one offer showing 3 Lapis; expected balance
is 1,347 free Lapis with one restore item and one saved stock count. No purchase
or currency grant was submitted by the agent.

The user confirms the purchase completed. GachaSelectExchangeExeRequest at
11:15:45 local time has product 940002004, quantity 1 and no decryption error.
Read-only saved-state verification confirms free Lapis 1,350 → 1,347, paid Lapis
unchanged at zero, NRG Restore 10 count 0 → 1, and stock receipt
exvius_shop_catalogue/counts/940002004/24322 = 1. Gil remains 1,000,013. This
physical exchange transaction and its saved charge/grant/stock pass. No request
was submitted or replayed by the agent.

The exercised core native flows now form a reviewable check-in checkpoint.
Arena gameplay remains deferred until natural story progression clears
Grandshelt Castle - Throne Room; no unlock or currency was fabricated to finish
acceptance. Other explicitly pending rows above are not marked passed.
