# ⚡ Bolt: Reduce decoded-master memory during native validation

Native table preparation and startup validation built a list containing every
decrypted JSON row, even when the caller immediately discarded it. The largest
installed master alone added about 200 MB of peak traced Python allocations.
Validation and passthrough normalization now consume decoded rows incrementally
through one shared decoder. This is a small change in two iOS adapter modules.

`master_rows()` still returns a fully validated list. Transformation callbacks
still run only after the complete input has passed validation. Cipher selection,
strict base64, AES/padding checks, JSON-object checks, empty-table refusal and
outer-line handling share the original implementation. There is no memoization,
cross-call state or new cache invalidation rule. Encoded input/line buffers remain
table-sized; this change removes retention of the whole decoded catalogue.

The source path is `macos_ios_server.py` → preparation CLI or gameplay hosting →
`open_prepared`/`load_prepared` → `native_tables.validate` → `validate_master`.
Preparation's passthrough builder uses `normalize_master`. The prepared engine
still validates before importing campaign state. Shared `ffbe_crypto` supplies the
same decryption operations. OpenLore orientation/impact was consulted; its stale
graph was checked against these current source paths.

## Measurements

From the repository root:

```sh
.venv-ios/bin/python -B source/exvius/benchmark_ios_master_validation.py source/out/browser-data --baseline 15f2f143e29a9207d549127cce546382cf349903 --trials 5
```

Python 3.12.13 on this Mac. The unchanged installed inputs contain 219 JSON
masters, 592,817 encrypted outer lines and 248,738,475 bytes. The largest is the
ECB `F_ABILITY_MST`: 44,322 lines and 44,144,800 bytes. The initial investigation
also measured the CBC `F_AI_MST`: 49,944 lines and 30,748,440 bytes; original
validation allocated 124,653,492 peak traced bytes. cProfile confirmed row
decryption and JSON decoding on these paths.

The benchmark alternates original/current implementation order over five trials,
using a fresh subprocess for each implementation/trial. Each operation gets one
first pass and one warm pass over the same preloaded inputs. Imports, file reads
and input hashing are outside timing; normalization includes output comparison
and hashing. The OS file cache is not evicted. “First” is the first pass of that
operation in the worker, not cold disk or whole-server startup. There is no
application result cache in either implementation. Tests and preparation jobs
finished before the final timing run.

Separate tracemalloc runs measure each operation on the largest preloaded master.
They exclude input allocation and do not measure process RSS. Normalization
includes its output allocation. Every worker rejects file writes/network access
and asserts that engine-state modules remain unloaded. All normalized bytes match
the original implementation; input hashes are checked before and after the
comparison. Raw dumps are under
`/private/tmp/`, outside the patch.

Final results are median [minimum–maximum], with seconds for timing. Each peak
allocation value was identical in all five trials.

| Workload / metric | Before | After |
| --- | --- | --- |
| Largest master validation peak traced bytes | 200,140,325 | 90,413,463 |
| Largest master normalization peak traced bytes | 200,140,485 | 90,413,959 |
| All masters: validation first pass, s | 2.8107 [2.7925–2.8364] | 2.7288 [2.7077–2.7422] |
| All masters: validation warm pass, s | 2.7822 [2.7653–2.8038] | 2.6958 [2.6783–2.7264] |
| All masters: normalization first pass, s | 3.1719 [3.1643–3.2102] | 3.0551 [3.0369–3.0914] |
| All masters: normalization warm pass, s | 3.1450 [3.1434–3.1676] | 3.0362 [3.0284–3.0670] |
| All masters: eager reader first pass, s | 2.7562 [2.7429–2.7982] | 2.7619 [2.7598–2.8067] |
| All masters: eager reader warm pass, s | 2.7530 [2.7519–2.7616] | 2.8051 [2.7831–2.9003] |

The primary gain is **54.8% less peak traced allocation** for both operations,
about 109.7 MB on this master. Final warm validation and normalization are 3.1%
and 3.5% faster, respectively, with non-overlapping observed ranges. These are
corpus-pass timings, not whole-command startup or iPhone response measurements.
An earlier comparison overlapped concurrent tests and had wider timing ranges;
only the final run above is used for the timing conclusion.

The eager compatibility wrapper is a tradeoff: its full-corpus warm probe is
1.9% slower (about 52 ms), while first-pass ranges overlap. It still retains its
decoded list by contract. Callers needing rows keep this behavior; only consumers
discarding rows use the lower-memory path. No eager-reader speedup is claimed.

## Verification

Each suite ran as a separate script through the prepared interpreter:

| Exact command | Outcome |
| --- | --- |
| `.venv-ios/bin/python -B source/exvius/test_ios_server.py` | 24 passed, before and after implementation |
| `.venv-ios/bin/python -B source/exvius/test_ios_preparation.py` | 19 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_full_tables.py` | 25 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_native_labels.py` | 16 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_sounds.py` | 38 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_sound_delivery.py` | 24 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_vortex_art.py` | 23 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_update_native.py` | 7 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_cdn.py` | 6 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_launcher.py` | 6 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_hosting.py` | Failed: 17 attempted, seven failures/eight errors; socket binds denied with `PermissionError: [Errno 1] Operation not permitted` |
| `.venv-ios/bin/python -B source/exvius/test_ios_connectivity.py` | Failed: 27 attempted, two failures/14 errors from the same socket restriction and resulting readiness failures |
| `git diff --check` | Passed |
| `git -c core.whitespace=cr-at-eol diff --check` | Passed |

The memory regression failed on the original implementation: 9,940,152 peak
traced bytes exceeded a 6,498,964-byte budget for the synthetic wide-row fixture.
It now passes for normalization and validation in both CBC and ECB modes. Other
new BDD coverage preserves mixed padding, uncommon ASCII line separators, exact
normalized bytes and eager list/callback behavior. Invalid final rows still fail
before publication and leave the previous generation loadable. Existing suites
cover checksum/freshness failures, both content layouts, query immutability,
source/private symlinks, failed saves/publication, retries and encrypted delivery.

A guarded real-data smoke comparison ran original/current codec bindings through
`prepare_data`, `load_prepared`, `verify_data` and `table_delivery.serve` in separate
disposable private runtimes. Both prepared 364 tables totaling 367,946,612 bytes,
with identical full manifests/output hashes. Each passed 728 exact GET/HEAD checks.
Verification/delivery allowed no writes; commands allowed writes only beneath the
temporary root. Network access was rejected, engine-state modules remained
unloaded, and no campaign was created. The temporary prepared trees were removed.
The local reproduction
script is `/private/tmp/bolt_master_preparation_smoke.py`; it is outside the patch.

No shared engine or launcher implementation changed, so additional legacy
gameplay suites were not run. There were no skips in the passing suites. The
inherited `task-observer` skill and observation directory were unavailable.

## Limits and review state

This measures decoded-master allocation, not total preparation/startup RSS or
physical-iPhone latency. Complete encrypted snapshots and localized-table parsing
retain their existing memory behavior. The playing installation, campaign,
prepared assets, certificates, services and network settings were not changed.
The patch is uncommitted; no dependencies or preparation revisions changed.

Wire acceptance remains unavailable in this sandbox. After a user-controlled
deployment/restart, a normal iPhone login and Home/Summon/Vortex navigation remain
the relevant manual checks. No new physical-device success is claimed. The dated
November 12 core-flow acceptance remains historical evidence, not validation of
this patch. No routine-success entry was added to Bolt's critical-learning journal.
