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
