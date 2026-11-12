# Native iPhone gameplay acceptance

This record follows the [server plan](IOS_SERVER_SOLID_CQRS_PLAN.md) and
[setup/launch guide](../source/ios_server/README.md). Mac preparation and local
probes do not establish physical-iPhone gameplay acceptance.

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
| Home navigation | Summon transition confirmed; loading defect pending | Summon opens, but its loading indicator is a blank square; other icons remain unverified |
| Audio | Pending | Sound effects and music work after needed background downloads complete |
| Summons | Banner-open crash on iPhone | Summon list opens; first banner crashes the app before a draw; blank loading square not observed in this attempt |
| Shops/exchanges | Pending | Listings, prices, purchase and resulting balances agree |
| Friends | Pending | Simulated list, companion selection and return flow work |
| Arena | Pending | Entry, battle/result and saved progression work |
| Artwork and taps | Pending | Home/Vortex/summon images display correctly and eligible home taps open the intended destination |
| Restart persistence | Pending | Completed progress survives closing the app, clean server stop/start and reconnecting |

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
