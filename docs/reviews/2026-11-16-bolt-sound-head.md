# ⚡ Bolt: Bound memory during prepared-sound HEAD verification

Prepared-sound HEAD requests previously read the whole bank into a Python bytes
object before discarding the body. They now hash in 256 KiB chunks and publish
the verified size. This is a small iOS adapter change: the existing contained,
no-follow file opener is shared with GET, and the reply helper accepts a verified
length. Full per-request SHA-256 and length checks remain in place.

There is no cross-request cache. Each request owns its descriptor, hash and
temporary chunks. Reads stop at the expected size plus one byte, preserving the
existing oversized-file bound. Missing/corrupt bound banks still return empty
500 responses; unknown or old versions still return 404. Preparation, campaign
transactions, profile binding, encrypted gameplay, advertised asset facts and
GET payloads retain their contracts.

## Measurements

Run from the repository root:

```sh
.venv-ios/bin/python -B tools/benchmark_ios_sound_head.py --baseline ce9a237 --trials 7 --repetitions 10
.venv-ios/bin/python -B tools/benchmark_ios_sound_head.py --baseline ce9a237 --trials 7 --repetitions 10 --size-mib 3
```

Python 3.12.13 on this Mac. Each command compares the original two adapter modules
from `ce9a237` with the working tree, using the same unchanged dependencies.
Before changing production code, a three-trial control compared the original
implementation with itself: both variants allocated 33,561,267 peak traced bytes
for a 32 MiB HEAD, with warm medians 11.944 and 11.960 ms.

The final comparison alternates implementation order across seven trials. Each
method/implementation gets a fresh subprocess, one first request, ten warm
requests, and one separately traced request: seven first-request samples, 70 warm
samples and seven allocation samples per variant. Timing excludes tracing.
The OS file cache is not evicted; “first” means first application request after
imports, not a cold disk or whole-server startup.

Files contain deterministic synthetic bytes in disposable private temporary
roots. Delivery treats a prepared bank as opaque bytes, so these exercise the
actual size/hash and handler path without audio conversion or preparation.
Read-only inspection found 735 shared-source banks with a 2,560,256-byte median
and 32,600,768-byte maximum; the 3 and 32 MiB fixtures approximate those sizes.
GET writes into a SHA-256 sink that retains no response body. Every response's
status, length, body hash and close behavior are checked. Workers reject file
writes and network access, and assert that engine state modules stay unloaded.

Final results: median [minimum–maximum]. Times are milliseconds.

| Workload / metric | Before | After |
| --- | --- | --- |
| 32 MiB HEAD peak traced bytes | 33,561,347 [same in all trials] | 530,718 [same in all trials] |
| 32 MiB HEAD first request | 12.704 [12.653–12.780] | 11.462 [11.455–11.504] |
| 32 MiB HEAD warm request | 11.506 [11.460–11.679] | 11.042 [10.980–11.170] |
| 32 MiB GET warm request | 21.288 [21.215–22.173] | 21.293 [21.244–21.467] |
| 3 MiB HEAD peak traced bytes | 3,152,643 [same in all trials] | 530,718 [same in all trials] |
| 3 MiB HEAD first request | 1.393 [1.359–1.410] | 1.282 [1.275–1.295] |
| 3 MiB HEAD warm request | 1.104 [1.091–1.186] | 1.123 [1.102–1.258] |
| 3 MiB GET warm request | 2.031 [2.005–2.101] | 2.034 [2.008–2.093] |

The primary gain is 98.4% less peak traced allocation for the large HEAD and
83.2% less for the smaller HEAD. Large-bank warm HEAD latency improves about 4.0%
with non-overlapping observed ranges. Smaller warm HEAD is about 1.7% slower at
the median with overlapping ranges; no smaller-bank latency improvement is claimed.
GET timing stays within observed variability. HEAD retains the same 1,489/1,488
traced bytes after completion, respectively, and still reads/hashes the full file.
The tradeoff is more small reads and hash updates in place of one large allocation.
These are Python allocation and handler measurements, not RSS or iPhone timings.
Raw benchmark dumps remain outside the patch under `/private/tmp/`.

## Verification

Each command ran as a separate script with disposable fixtures:

| Exact command | Outcome |
| --- | --- |
| `.venv-ios/bin/python -B source/exvius/test_ios_server.py` | 24 passed; foundation ran first and again after implementation |
| `.venv-ios/bin/python -B source/exvius/test_ios_preparation.py` | 19 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_full_tables.py` | 21 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_sounds.py` | 38 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_sound_delivery.py` | 20 passed, including a rerun after the final reply-flow edit |
| `.venv-ios/bin/python -B source/exvius/test_ios_vortex_art.py` | 23 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_cdn.py` | 6 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_hosting.py` | Failed: 17 tests attempted, seven failures and eight errors; sandbox denies socket binds (`PermissionError: [Errno 1] Operation not permitted`), preventing listener startup and wire acceptance |
| `git diff --check` | Passed |
| `git -c core.whitespace=cr-at-eol diff --check` | Passed |

The new Given/When/Then memory regression failed against the original code
(8,395,000 peak traced bytes exceeded its 1 MiB limit) and passes after the change.
It covers a partial final chunk, concurrent requests, and a same-size edit with
the original mtime restored after a successful HEAD. Existing integration cases
cover both layouts, pinned generations, GET/HEAD byte lengths, query immutability,
encrypted initialization, stale/unknown versions, corruption, truncation and
oversized files. Expanded rejection checks exercise HEAD and GET for missing files
and symlinks escaping either the generation or runtime root. No shared engine or
launcher code changed; additional legacy gameplay suites were not run.

OpenLore orientation/impact was consulted, but its graph was stale and method-name
matching produced unrelated callers. Current source established the path:
`macos_ios_server.py` → CLI/start hosting → prepared `Engine` → canonical
`Handler._cdn_fetch` → `table_delivery.serve` → pinned sound delivery.

## Review limits

The worktree started clean. Changes remain uncommitted. The active service,
campaign, prepared installation, certificates and network settings were untouched.
No packages were installed. No journal entry was added because this result did not
reveal a new repository-specific correctness trap beyond the existing integrity
contract.

Socket-based hosting checks need rerunning where local binds are permitted. No
physical iPhone check was performed, and no end-to-end loading gain is claimed.
At the next user-controlled server restart, ordinary native login and sound
playback remain the relevant smoke checks; this change requires no preparation.
