# ⚡ Bolt: stream iOS sound inventory hashing

Measured November 13, 2026 against baseline `a5b2a9565f8467482ac1aa851e413af3cab05cef`.
Changes are intentionally uncommitted.

## Change and scope

`ios_server.sound_inputs.collect` previously read each complete bank into a
`bytes` object to compute its length and SHA-256. During the next read, the
previous bank remained live. Inventory now hashes 1 MiB chunks and counts the
bytes actually read, including the final partial chunk. It retains only facts.
There is no hash cache, stat-based shortcut, new dependency or pipeline revision.
Identical source bytes produce identical provenance and snapshot fingerprints.

The entrypoint dispatches preparation/verification through `ios_server.commands`
to `sound_snapshots`. Its preparation and freshness passes call this collector.
`Gameplay.preflight` and `Engine.initialize(prepared=True)` also reach it through
`open_prepared` → `native_sounds.collect` → `sound_snapshots.current`.
The canonical `capture_server.Handler._cdn_fetch` still uses the existing
`table_delivery`/`native_sounds.Delivery` path. Conversion, structural/CRC checks,
publication, per-response integrity checks, encrypted gameplay and saves are
unchanged. The shared engine and legacy adapters were not edited.

## Measurements

Existing prepared-host source corpus, read-only: 735 unique banks / 782 resource
references / 2,202,569,152 bytes; largest bank 32,600,768 bytes. Python 3.12.13,
macOS ARM64, the existing `.venv-ios`, no profiling packages installed.

Seven fresh child processes per implementation, alternating before/after order.
Each child performs one first application scan, one warm repeated scan, then one
separate scan under `tracemalloc`. Timing excludes imports and configuration;
timed scans run without tracing. Filesystem caches were not flushed: these are
warm filesystem measurements, including the first application scans. Other test
suites were not running during the comparison. The one initial before-process
outlier is included below. Every source record and fingerprint matched across
all processes and all three scans per process. An audit hook refused file-write
opens and socket binds/connects; the disposable runtime directory stayed absent.

| Metric | Before median (range) | After median (range) | Median reduction |
| --- | --- | --- | --- |
| Peak traced Python allocations | 59.77 MiB (62,674,952–62,674,956 bytes) | 31.37 MiB (32,897,728–32,897,732 bytes) | 47.5% / 28.40 MiB |
| First application scan | 1,005.21 ms (1,003.24–1,355.80) | 969.14 ms (968.39–977.66) | 3.6% |
| Warm repeated scan | 992.55 ms (991.59–997.48) | 961.80 ms (961.18–963.72) | 3.1% |

The memory reduction is the primary result. Retained traced allocations were
885,540 versus 888,480 bytes (about 2.9 KiB higher after); there is no retained
bank cache. The inventory still parses six resource masters and reads/hashes
every bank byte on each call. The timing ranges do not overlap in this run,
but this is a roughly 31 ms inventory saving, not a measured gameplay speedup.

These are incremental Python allocation peaks for the inventory operation, not
process RSS, whole-server startup peaks, full preparation duration, or physical
iPhone latency. Bank conversion and delivery still need their existing buffers.
The active installation, private campaign, prepared generations and certificate
identity were not opened for mutation or restarted.

## Reproduce

From the repository root, while this patch is uncommitted and HEAD is the
baseline above, run the following with the prepared interpreter. After check-in,
replace `HEAD` in `git show` with the recorded baseline revision. Select an
existing content root as the argument; all runtime roots are disposable. This
benchmarks only the collector and never initializes the engine or a campaign.

```sh
.venv-ios/bin/python -B - source/out/browser-data <<'PY'
import json, statistics, subprocess, sys

baseline = subprocess.check_output(['git', 'show', 'HEAD:source/ios_server/sound_inputs.py'], text=True)
worker = r'''
import json, os, sys, tempfile, time, tracemalloc, types
from pathlib import Path
sys.path[:0] = ['source', 'source/server']
from ios_server.config import Configuration
if sys.argv[1] == 'before':
    module = types.ModuleType('bolt_baseline')
    sys.modules[module.__name__] = module
    exec(compile(sys.stdin.read(), 'baseline_sound_inputs.py', 'exec'), module.__dict__)
    collect = module.collect
else:
    from ios_server.sound_inputs import collect
with tempfile.TemporaryDirectory(prefix='bolt-inventory-') as temp:
    config = Configuration(Path(temp) / 'runtime', Path(sys.argv[2]))
    def readonly(event, args):
        if event == 'open' and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            raise AssertionError('Benchmark attempted a file write')
        if event in ('socket.bind', 'socket.connect'):
            raise AssertionError('Benchmark attempted network access')
    sys.addaudithook(readonly)
    start = time.perf_counter(); first = collect(config); first_s = time.perf_counter() - start
    start = time.perf_counter(); warm = collect(config); warm_s = time.perf_counter() - start
    tracemalloc.start(); traced = collect(config); retained, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
    assert first == warm == traced
    assert not config.root.exists()
    assert not {'capture_server', 'data_paths', 'ffbe_state'} & set(sys.modules)
    print(json.dumps({'first_seconds': first_s, 'warm_seconds': warm_s,
        'peak_traced_bytes': peak, 'retained_traced_bytes': retained,
        'sources': first.sources, 'fingerprint': first.fingerprint}))
'''
results = {'before': [], 'after': []}
reference = None
for trial in range(7):
    for label in (('before', 'after') if trial % 2 == 0 else ('after', 'before')):
        run = subprocess.run([sys.executable, '-B', '-c', worker, label, sys.argv[1]],
                             input=baseline, text=True, capture_output=True, check=True)
        sample = json.loads(run.stdout)
        sources = sample.pop('sources')
        if reference is None:
            reference = sources
        assert sources == reference
        results[label].append(sample)
        print(json.dumps({'trial': trial + 1, 'implementation': label, **sample}), flush=True)
for label, samples in results.items():
    summary = {key: {'median': statistics.median([row[key] for row in samples]),
                     'min': min(row[key] for row in samples), 'max': max(row[key] for row in samples)}
               for key in ('first_seconds', 'warm_seconds', 'peak_traced_bytes', 'retained_traced_bytes')}
    print(json.dumps({'implementation': label, 'summary': summary}), flush=True)
print(json.dumps({'python': sys.version, 'banks': len(reference['banks']),
                  'bytes': sum(row['size'] for row in reference['banks'].values()),
                  'largest_bank_bytes': max(row['size'] for row in reference['banks'].values()),
                  'resources': len(reference['resources']), 'equal_inventories': True}), flush=True)
PY
```

## Verification

The new Given/When/Then allocation scenario failed before the implementation:
a synthetic 12 MiB bank required 12,612,074 traced bytes, exceeding its 6 MiB
budget. It passes after streaming and verifies exact size/SHA-256 across multiple
chunks and a short tail. A second scenario edits a byte beyond the first chunk,
preserves size/mtime, and requires a changed fingerprint. Existing scenarios
retain exact native precedence, both layouts, read-only verification, source
changes during preparation, corrupt/escaping paths, failed publication/retry,
pinned generations, exact GET/HEAD bytes and CLI JSON behavior.

| Command | Outcome |
| --- | --- |
| `.venv-ios/bin/python -B source/exvius/test_ios_server.py` | 24 passed; run before and after the change |
| `.venv-ios/bin/python -B source/exvius/test_ios_sounds.py` | 37 passed, including the two new scenarios |
| `.venv-ios/bin/python -B source/exvius/test_ios_preparation.py` | 19 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_full_tables.py` | 21 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_sound_delivery.py` | 19 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_launcher.py` | 6 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_hosting.py` | Failed: 17 tests run, 7 failures / 8 errors, including cleanup failures; listener binds denied by the sandbox and dependent readiness assertions fail |
| `.venv-ios/bin/python -B source/exvius/test_ios_connectivity.py` | Failed: 27 tests run, 2 failures / 14 errors, including subtest errors; loopback socket binding returns `PermissionError: [Errno 1] Operation not permitted` |
| `.venv-ios/bin/python -B source/exvius/test_ios_connectivity.py NetworkBehavior DnsBehavior CertificateBehavior` | 12 non-socket checks passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_hosting.py RequestRetention GameplayLifecycle.test_given_start_from_system_python_when_dispatched_then_use_isolated_runtime_and_emit_json NativeGameplayWire.test_given_public_cli_data_argument_when_engine_imports_then_keep_private_policy_root NativeGameplayWire.test_given_missing_coordinated_features_when_preflight_runs_then_refuse_without_state_import_or_writes` | 5 non-socket checks passed |
| `git diff --check` | Passed |
| `git -c core.whitespace=cr-at-eol diff --check` | Passed |
| `git diff --no-index --check /dev/null plans/IOS_SOUND_INVENTORY_PERFORMANCE.md` | No whitespace diagnostics; exit 1 is expected because the new file differs from `/dev/null` |

The socket suites are not marked skipped or passed. No socket permissions or
playing-installation settings were changed. The six complete passing suites
contain 126 checks, with another 17 passing checks in the non-socket subsets.
Tracked changes and the new report were reviewed; the pre-existing untracked
`docs/bolt-prompt.md` and `docs/palette-prompt.md` were preserved. No Bolt journal
was created because this change uncovered no new repository-specific trap.

OpenLore returned a partial BM25 graph with stale impact metadata; the call paths
above were verified directly against current source. The inherited AGENTS.md
task-observer check was unavailable: neither its skill nor its observation
directory exists in the inspected local skill locations.

## Limits and manual validation

The implementation changes only source inventory allocation. It does not claim
to fix outstanding device artwork/download acceptance issues. Wire-level hosting
checks need rerunning in an environment allowed to bind disposable loopback
listeners. On a later user-authorized normal server start, confirm native login
and ordinary music/button sounds on the iPhone. No device success was recorded
for this patch; no immediate playing-server restart is required for review.
