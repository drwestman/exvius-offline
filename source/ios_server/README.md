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
the campaign. Events and shops do not yet follow this calendar.

The engine uses the same policy for encrypted summon lists, purchases, and drop
rates. Historical pools include units released before the window's end, with the
pinned fork's featured-holiday and one-off-ticket exceptions. NV permanent
summons appear at the NV era. After history ends, a deterministic weekly shuffle
selects one special and two featured release sets. Purchases recheck eligibility
before spending, so a banner opened before rollover cannot be pulled afterward.
Unavailable guaranteed rewards also decline without spending. The two SP ticket
bundles are one-off purchases on iOS; the plain SP ticket bundle is removed, while
already held plain SP tickets retain the historical pool limit.

This is engine integration; the running native service still serves the connection
check. Full iPhone gameplay hosting and the remaining revival ports are pending.

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
