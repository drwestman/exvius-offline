# ⚡ Bolt: stream ordinary CDN files with bounded memory

Measured November 15, 2026 against baseline
`922183ae20ed90e4762a783fca8a0e71829111c5`. Changes are uncommitted.

## Change and rationale

The ordinary CDN handler read a complete selected file before replying, including
for HEAD. The dated device record includes a 166 MB movie download, so these
buffers can be substantial during native background downloads. A disposable
160 MiB fixture confirmed a 167,778,564-byte allocation peak before implementation.

`Handler._cdn_fetch` now selects a filename using the same decoded-path checks,
overlay precedence, token fallback and contained artwork index. The small
`_cdn_reply` transport helper opens that selected file once, gets its length from
the descriptor and writes GET bodies in at most 256 KiB chunks. HEAD opens and
measures the file without reading payload bytes. The descriptor closes after a
response or client disconnect. File growth cannot send bytes beyond the declared
length, and pathname replacement keeps the original open file for that response.

The native path is `macos_ios_server.py` → `ios_server.cli.serve` → `Service` →
`Gameplay.start` → `Engine.initialize` → canonical `capture_server.Handler`,
wrapped by `game_http.handler`. The shared change also benefits legacy CDN reads.
Prepared tables/Vortex, bound sound and fitted/home artwork still return through
their existing adapters before this helper; their validation, exact versions,
hashes and corrupt/missing handling remain in place. Encryption, state locks,
commands, save transactions, preparation and bootstrap metadata are unchanged.

No cache is added. Buffers and the file descriptor belong to one request and are
released when it finishes. Two adjacent chunk allocations can coexist during a
read; retained memory does not scale with asset size or survive across requests.
The scope is one shared handler and its file-response helper, with regression
coverage, a standard-library benchmark and documentation.

## Measurements and reproduction

From the repository root:

```sh
.venv-ios/bin/python -B tools/benchmark_ios_cdn.py --baseline 922183ae20ed90e4762a783fca8a0e71829111c5
```

Python 3.12.13, macOS ARM64, existing `.venv-ios`; no packages installed. The
benchmark creates one deterministic 160 MiB (167,772,160-byte) opaque CPK under a
temporary content root. This route treats movie packs as opaque bytes, so a real
CPK header is unnecessary. A SHA-256 sink consumes GET bodies without retaining
them and verifies every byte, length and status; HEAD must have no body.

There are seven fresh processes for each implementation and method, alternating
before/after order: 28 child processes total. Each makes one first application
request, five warm repetitions and one separately traced request. Warm timing
statistics cover 35 requests per implementation/method. The baseline Handler is
compiled from Git with the same engine dependencies as the current Handler.
Child audit hooks reject writes and socket binds/connects; the private runtime
stays absent. Synthetic content is removed at completion. Stdout is one JSON
document containing samples and summaries; progress is on stderr.

The final comparison ran without test suites alongside it. File-system caches
were not evicted; fixture creation itself warms them. First-request timings
include lazy route imports but exclude process startup and initial engine-module
imports. These are fresh application-path measurements, not cold-disk or complete
gameplay-startup measurements. Timings do not include allocation tracing.

| Metric | Before median (min–max) | After median (min–max) |
| --- | ---: | ---: |
| GET peak traced allocations | 167,778,532 bytes (identical in all seven trials) | 532,281 bytes (identical in all seven trials) |
| HEAD peak traced allocations | 167,778,532 bytes (identical in all seven trials) | 7,449 bytes (identical in all seven trials) |
| First GET | 73.712 ms (73.303–74.585) | 67.174 ms (67.104–67.521) |
| Warm GET | 58.058 ms (57.987–58.419) | 55.643 ms (55.365–57.117) |
| First HEAD | 24.728 ms (24.493–24.831) | 11.137 ms (10.986–11.185) |
| Warm HEAD | 9.204 ms (9.142–9.697) | 0.097 ms (0.092–0.136) |

The primary result is a **99.68% reduction in GET peak traced Python allocations**,
from 160.006 MiB to 0.508 MiB. HEAD drops to about 7.27 KiB. Retained traced
allocations after the request are unchanged: 1,127 bytes for GET and 1,135 for
HEAD, including benchmark logging. The timing ranges do not overlap in this run;
the GET median improves by 2.415 ms (4.2%), and HEAD avoids a full-file read.

These are Python allocations, not process RSS. The hashing sink excludes network,
TLS and client installation costs. More small writes replace the single large
write; network throughput and end-to-end iPhone latency were not measured.
Prepared table/art buffers and per-response sound verification are outside this
optimization. Existing source bytes and advertised asset metadata are preserved.

## Verification

Before implementation, the new allocation scenario failed for both profiles at
about 8.395 MB for an 8 MiB-plus-tail fixture, exceeding its 2 MiB budget. The HEAD
scenario also failed because the handler called `read`. Both pass after the
change. Six new BDD scenarios run in fresh iOS and legacy processes and cover:

- Exact large GET hashes, partial last chunks, empty files and body-free HEAD.
- Actual HTTP response framing through the native wrapper and legacy adapter.
- Overlay, token, artwork and authored-policy-page selection; missing paths,
  encoded traversal, null/backslash paths and escaping symlinks.
- Four simultaneous readers, disconnected clients, descriptor closure, and
  source growth/replacement at the response-header boundary.
- Read-only campaign/save/RNG behavior and query-time write/network rejection.

| Exact command from the repository root | Outcome |
| --- | --- |
| `.venv-ios/bin/python -B source/exvius/test_ios_server.py` | 24 passed, including initial foundation run and rerun |
| `.venv-ios/bin/python -B source/exvius/test_ios_cdn.py` | 6 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_preparation.py` | 19 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_full_tables.py` | 21 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_sound_delivery.py` | 19 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_vortex_art.py` | 23 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_banner_fitting.py` | 19 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_home_banners.py` | 26 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_launcher.py` | 6 passed |
| `PYTHONPATH=source/exvius .venv-ios/bin/python -B -m unittest test_browser_launcher` | 18 passed |
| `.venv-ios/bin/python -B source/exvius/test_macos_emulator.py` | 12 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_hosting.py` | Cannot complete in sandbox: 17 tests, 7 failures/8 errors, socket binds denied and dependent readiness assertions fail |
| `.venv-ios/bin/python -B source/exvius/test_ios_connectivity.py` | Cannot complete in sandbox: 27 tests, 2 failures/14 errors, socket binds denied |
| `.venv-ios/bin/python -B source/exvius/test_local_game.py` | 0 tests: class setup fails because `data/client/files/en/sd/static_banner/gacha` is absent |
| `git diff --check` | Reports existing CRLF convention as trailing whitespace on changed CRLF source lines |
| `git -c core.whitespace=cr-at-eol diff --check` | Passed |

The passing complete suites contain 163 iOS checks and 30 legacy launcher checks.
The new suite additionally exercises the shared handler with a synthetic legacy
engine/save. The broader local-game fixture was not repaired or redirected into
the playing installation. Running `test_browser_launcher.py` directly exits
without executing tests; the module invocation above is the actual verification.
No tests were marked skipped to hide socket or fixture restrictions.

Tracked changes and new files were reviewed separately, including syntax and
whitespace checks on the new files. CRLF source line endings were retained.
OpenLore returned partial keyword-based navigation, checked against current
source. The inherited task-observer skill and observation directory are absent.
The unrelated untracked `play-exvius-on-iphone.command` was left untouched.
No critical cache/lifetime discovery warranted changing Bolt's existing journal.

## Limits and manual iPhone validation

The playing server was not stopped/restarted, and its campaign, certificates,
prepared content and network settings were not changed. Benchmarks use only
synthetic disposable content; the active campaign is never loaded by them.
No physical-iPhone acceptance is recorded for this patch.

Run the socket suites in an environment permitting loopback listeners before
claiming wire validation. After a later normal start with reviewed code, observe
a naturally requested native pack download and subsequent navigation/audio on
the iPhone. No redownload, campaign reset or network-setting change is required
for this review. Ordinary files should remain stable while served: an in-place
overwrite/truncation can interrupt a streaming response; atomic pathname
replacement is pinned to the already-open file. Prepared-asset integrity failures
retain their existing verified behavior. Existing device-acceptance gaps keep
their dated status.
