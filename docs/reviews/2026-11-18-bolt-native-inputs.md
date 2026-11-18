# ⚡ Bolt: Scan native master directories once per collection

Native input collection validated table directories once, then enumerated the
same master directory separately for each registered JSON table. It now records
the latest numeric master version during that existing validation walk and uses
the resulting invocation-local inventory for selection. The production change is
confined to `source/ios_server/native_inputs.py`.

This addresses repeated directory work in explicit preparation, verification and
prepared startup. The path is `macos_ios_server.py` → preparation commands or
gameplay preflight/`Engine.initialize` → `prepare_data`/`verify_data`/`open_prepared`
→ `_complete_inputs` → `native_inputs.collect`. The collector still calls the
same pure shared-engine catalogue, exchange and economy helpers. No shared engine,
transport, save, launcher or preparation-version implementation changes.

Overlay precedence still wins over a newer base version. Localized tables still
use the exact version from their index. Every collection re-enumerates sources,
reads their bytes and hashes them. Resolved folder/file containment checks,
unknown-token refusal and positive selected-version validation remain in place.
There is no process-wide cache or new disk artifact: retained index entries are
bounded by registered master tokens per content root (at most overlay and base),
and are released after collection. This trades a small temporary filename/version
dictionary for repeated glob traversal; no memory/RSS improvement is claimed.

## Measurements

From the repository root:

```sh
.venv-ios/bin/python -B source/exvius/benchmark_ios_native_inputs.py source/out/browser-data --baseline 963c33f2132860a8a407e0e51ab0bc9357d5c994 --trials 7
```

Python 3.12.13 on this Mac. The real shared corpus was read-only input: 364 tables,
219 masters and 145 localized tables, totaling 366,083,821 encrypted bytes.
Each implementation/trial runs in a fresh subprocess with one first collection
and one warm repeated collection. Trial order alternates before/after. Timing
includes directory selection, file reads, content hashing, parsing and label
planning; imports and post-collection equality checks are outside timing.
First-call results include initially cold process-local catalogue metadata;
warm results reuse existing catalogue metadata, but neither implementation caches
the table inventory or input bytes. The OS file cache is not evicted, so neither
condition represents cold disk or whole-server startup. Tests did not overlap
the measurement run.

The worker rejects filesystem writes/mutations, network access and process
launches, and asserts that engine state modules remain unloaded and the private
runtime is never created. Across all workers and both passes, returned source
versions/bytes, provenance, fingerprint, policy context and labels agree.
Comparison hashing happens outside timing. Raw measurement dumps are confined
to `/private/tmp`, outside the patch.

Results are median [minimum–maximum] over seven samples per condition:

| Metric | Before | After |
| --- | --- | --- |
| Directory enumerations per collection | 221 [221–221] | 2 [2–2] |
| First collection, seconds | 1.0203 [0.9813–1.0780] | 0.9884 [0.9432–1.0597] |
| Warm collection, seconds | 0.8906 [0.8597–0.9473] | 0.8455 [0.8275–0.8712] |

Directory enumerations fall by 99.1%. Warm median collection time falls by 5.1%
(45.1 ms). All seven paired warm trials improve, with savings from 25.3 to
101.8 ms and median paired saving 35.2 ms. Individual timing ranges overlap;
the consistent paired direction and deterministic reduction in directory work
support a modest collection improvement. First-call ranges overlap substantially,
and one paired first call regresses by 14.4 ms; no reliable cold/startup latency
improvement is claimed. These measurements do not establish faster iPhone
gameplay, downloads, or an equivalent whole-command improvement.

Initial cProfile investigation measured 1.69 seconds for the original collector,
including 0.42 seconds in its per-table reader. The prototype profile measured
1.59 seconds overall and 0.26 seconds in that reader. Instrumented timings only
identified the candidate; the uninstrumented comparison above is the result.

## Verification

Each suite ran as a separate script using the prepared interpreter:

| Exact command | Outcome |
| --- | --- |
| `.venv-ios/bin/python -B source/exvius/test_ios_server.py` | 24 passed before and after implementation |
| `.venv-ios/bin/python -B source/exvius/test_ios_preparation.py` | 22 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_full_tables.py` | 25 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_native_labels.py` | 16 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_sounds.py` | 38 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_sound_delivery.py` | 24 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_vortex_art.py` | 30 passed, including the pre-existing artwork worktree changes |
| `.venv-ios/bin/python -B source/exvius/test_ios_update_native.py` | 7 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_cdn.py` | 6 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_launcher.py` | 6 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_hosting.py` | Failed: 17 attempted, seven failures/eight errors; socket binding denied with `PermissionError: [Errno 1] Operation not permitted`, followed by readiness/cleanup assertion failures |
| `.venv-ios/bin/python -B source/exvius/test_ios_connectivity.py` | Failed: 27 attempted, two failures/14 errors from socket restrictions and resulting readiness failures |
| `git diff --check` | Passed |
| `git -c core.whitespace=cr-at-eol diff --check` | Passed |

The ten passing scripts contain 198 tests, with no skips. The new scan-budget
scenario fails against the original collector: 220 master-directory enumerations
instead of one. It passes after the change. New BDD coverage also checks numeric
version ordering, overlay precedence, additions/removals, same-size byte changes,
previous-result ownership, read-only collection and concurrent independent
prepared-host/managed-layout inventories. Existing scenarios cover malformed and
missing sources, unknown tokens, source/private symlinks, source freshness,
failed publication/retry, exact prepared bytes, and one-document CLI output.
Initial new-test failures came from expecting a scan of nonexistent directories
and using an LF-normalizing helper for a same-size CRLF fixture; both assertions
were corrected before the final passing run.

OpenLore orientation was consulted but keyword fallback returned weak/incomplete
call edges; the call paths and contracts above were verified against source.
The inherited `task-observer` skill and observation directory are absent, so
its session/post-task protocols could not run. No shared engine or launcher
implementation changed, so additional legacy gameplay suites were not run.
No critical repository-specific trap emerged; Bolt's journal is unchanged.

## Review limits

The patch remains uncommitted. Existing Vortex artwork, README, spec and
antipattern worktree changes are preserved. No packages, campaign saves,
prepared assets, certificate identities, services or Mac/iPhone settings changed.

The inventory reflects each collection's directory walk; concurrent content
replacement during a collection remains unsupported as before. Managed content
continues to use its pinned generation. Each later call rebuilds the inventory,
and selected paths still resolve against the containment boundary before reads.

Host wire validation remains blocked by sandbox socket permissions. After a
user-controlled deployment/restart, normal iPhone login, Home/Summon/Vortex
navigation and prepared downloads remain relevant manual checks. Physical-device
performance and acceptance of this patch are unverified; the dated November 12
core-flow evidence describes the earlier installation.
