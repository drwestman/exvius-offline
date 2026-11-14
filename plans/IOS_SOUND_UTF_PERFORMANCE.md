# ⚡ Bolt: avoid copying embedded audio during sound validation

Measured November 14, 2026 against baseline
`75cb116cfc2d4786f102c686241e0afc54c88c8c`. Changes are uncommitted.

## Change and rationale

`sound_codec.Utf` calls the validated `cpk.table` parser to inspect sound-bank
metadata. That parser also decoded binary blob cells into independent bytes,
copying the embedded AWB audio even though the caller only needed the schema,
row count and blob offsets. The largest bank in the read-only corpus incurred
32,611,332 incremental traced bytes during inspection.

The parser is now split by intent (CQRS-style read models): `cpk.table` keeps
decoding full rows for pack callers, unchanged, while the new `cpk.check` runs the
identical validation walk (`cpk._walk`) without building rows or blob payloads.
It returns the table name, schema and row count; constant blob columns carry
absolute `(offset, length)` spans instead of copies. `sound_codec.Utf` uses
`check`, and passes a UTF that spans the whole buffer without slicing, so `bytes`
and `bytearray` banks are both inspected without a whole-bank copy (previously a
`bytearray` input still copied the bank once). Every header, schema, string and
blob bound still fails exactly as before, and every HCA header and frame still
passes its CRC check. No views, caches or retained buffers are introduced.

> Review follow-up (2026-11-14): this replaces an earlier opt-in
> `table(..., blob_views=True)` variant, which changed the return type to
> `memoryview`, could expose writable views over `bytearray` input and relied on
> CPython returning the same object for a full-length `bytes` slice. The
> measurements below were re-run with the final `cpk.check` design.

The entrypoint dispatches explicit preparation/verification commands through
`ios_server.commands` to `sound_snapshots`. Sound publication and verification
use `sound_codec.prepare`/`validate`; prepared startup reaches validation through
`Gameplay.preflight` and `Engine.initialize(prepared=True)` → `open_prepared` →
`native_sounds.load` → `sound_snapshots.load`. The shared canonical
`capture_server.Handler._cdn_fetch` continues to serve bound sound through
`table_delivery` and `native_sounds.Delivery`. No engine, transport, persistence,
delivery, preparation fingerprint or pipeline-version change is required.

## Measurements and reproduction

Existing prepared-host source corpus, read-only: 735 banks, 2,202,569,152 bytes;
largest bank 32,600,768 bytes. Python 3.12.13, existing `.venv-ios`, macOS ARM64.
No profiling package was installed.

From the repository root:

```sh
.venv-ios/bin/python -B source/exvius/benchmark_ios_sound_utf.py source/out/browser-data --baseline 75cb116cfc2d4786f102c686241e0afc54c88c8c --trials 7
```

The standard-library benchmark reads baseline modules from Git without modifying
the checkout. Seven fresh processes per implementation alternate before/after
order. Each child performs an initial application scan, a warm repeated scan,
a separately traced largest-bank read/hash/inspection, and a separately traced
inspection with its input allocated before tracing. Every full scan reads and SHA-256-checks
every input and validates its UTF/AFS2/HCA structure and CRCs. Layout signatures
must agree across every scan and implementation. Initial/final inventories must
also match. A child audit hook refuses file writes and network access; the
disposable private runtime remains absent.

Filesystem caches are warm and are not flushed. Initial application scans exclude
imports/inventory construction and are not cold-disk or whole-startup measurements.
Timed scans run without allocation tracing. The corpus is not retained in memory
between scans; one bank is released before reading the next.

An initial experiment tracing every bank in every trial was interrupted because
of instrumentation overhead. No measurements from that incomplete run are used.

| Metric | Before median (range) | After median (range) |
| --- | ---: | ---: |
| Largest-bank read/hash/inspection peak | 62.191 MiB (65,211,957 bytes in all seven trials) | 31.430 MiB (32,956,575 bytes in all seven trials) |
| Largest-bank inspection alone, input already allocated | 31.100 MiB (32,611,156 bytes in all seven trials) | 0.339 MiB (355,774 bytes in all seven trials) |
| Retained allocations after largest-bank inspection | 114,304 bytes in all seven trials | 109,184 bytes in all seven trials |
| Initial application scan of all banks | 1,484.45 ms (1,479.41–1,506.64) | 1,445.95 ms (1,434.37–1,460.19) |
| Warm repeated scan of all banks | 1,475.65 ms (1,471.30–1,485.27) | 1,438.32 ms (1,432.51–1,453.88) |

The primary result is a **49.5% / 30.76 MiB reduction** in the largest-bank
read/hash/inspection allocation peak. Excluding the necessary input buffer,
inspection allocations fall 98.9%. Retained allocations fall by 5,120 bytes
(no row dicts are kept). Warm timing medians differ by 37.33 ms (2.5%) and the
ranges do not overlap in this run, but a scan-level gain is not an end-to-end
latency claim; treat this as a memory optimization. No test suites ran during
the completed comparison.

The table is from the final `cpk.check` design (re-run 2026-11-14 after review).
The earlier `blob_views` variant measured 33,133,599 / 532,798 / 114,304 bytes on
the same three memory rows.

These are Python allocation peaks, not process RSS. Full startup and preparation
include other buffers and validation stages. This does not measure end-to-end
iPhone latency. Source and prepared output buffers remain necessary; there is no
new retained audio cache or integrity/freshness shortcut.

## Verification

The synthetic 4 MiB, CRC-valid native waveform regression failed before the change at
4,195,850 incremental traced bytes against a 1 MiB allocation budget. After review
it runs for both `bytes` and `bytearray` input; the `bytearray` subtest failed at
4,196,793 bytes (whole-bank slice copy) before `Utf` stopped slicing a full-buffer
UTF, and both now pass, return the input object and reject a corrupted final frame.
BDD scenarios in `BannerCpk` check that `cpk.check` reports the same name, schema
and row count as `cpk.table` (constant blobs as spans resolving to identical bytes)
for plain, masked and `bytearray` UTF, and that both functions reject the same
corrupt header, bounds/layout, column kind, string offset, UTF-8 and blob cells.

| Exact command from the repository root | Outcome |
| --- | --- |
| `.venv-ios/bin/python -B source/exvius/test_ios_server.py` | 24 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_sounds.py` | 38 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_vortex_art.py` | 23 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_preparation.py` | 19 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_full_tables.py` | 21 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_sound_delivery.py` | 19 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_launcher.py` | 6 passed |
| `.venv-ios/bin/python -B source/exvius/test_ios_hosting.py RequestRetention GameplayLifecycle.test_given_start_from_system_python_when_dispatched_then_use_isolated_runtime_and_emit_json NativeGameplayWire.test_given_public_cli_data_argument_when_engine_imports_then_keep_private_policy_root NativeGameplayWire.test_given_missing_coordinated_features_when_preflight_runs_then_refuse_without_state_import_or_writes NativeGameplayWire.test_given_managed_layout_when_hosted_then_serve_native_tables_and_sound_through_tls` | 6 passed (run with socket access) |
| `git diff --check` | Passed |
| `git -c core.whitespace=cr-at-eol diff --check` | Passed |

The seven complete suites contain 150 passing checks; the hosting subset adds six,
including the TLS wire test serving native tables and sound. Existing scenarios
cover both content layouts, read-only verification, stale/corrupt sources, symlink
containment, publication failures and retries, pinned generations, exact GET/HEAD
responses and CLI JSON. `cpk.table` output is unchanged and remains covered by
Vortex pack reconstruction checks. The canonical shared engine and legacy
entrypoints were not edited. The remaining socket suites were not run.

A read-only real-corpus comparison separately confirmed **identical converted
bytes and facts for all 735 banks / 2,202,569,152 bytes**, with 1,727 waveforms,
388 decrypted streams and 816 reflagged waveform rows. Both implementations
validated their results (re-run against the final `cpk.check` design with the
same totals). It created no prepared outputs or campaign, and source
inventories matched before/after. Reproduce that check with:

```sh
.venv-ios/bin/python -B - <<'PY'
import json, os, subprocess, sys, tempfile, types
from pathlib import Path
sys.path[:0] = ['source', 'source/server']
from ios_server import sound_codec, sound_inputs
from ios_server.config import Configuration
revision = '75cb116cfc2d4786f102c686241e0afc54c88c8c'
def original(name):
    source = subprocess.check_output(['git', 'show', revision + ':source/ios_server/' + name + '.py'], text=True)
    result = types.ModuleType('baseline_' + name)
    exec(compile(source, result.__name__, 'exec'), result.__dict__)
    return result
baseline = original('sound_codec'); baseline.cpk = original('cpk')
with tempfile.TemporaryDirectory(prefix='bolt-utf-parity-') as temp:
    config = Configuration(Path(temp) / 'runtime', Path('source/out/browser-data'))
    def readonly(event, args):
        if event == 'open' and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            raise AssertionError('Parity check attempted a file write')
        if event in ('socket.bind', 'socket.connect'):
            raise AssertionError('Parity check attempted network access')
    sys.addaudithook(readonly)
    inputs = sound_inputs.collect(config)
    totals = {'banks': 0, 'bytes': 0, 'waveforms': 0, 'decrypted': 0, 'reflagged': 0}
    for entry in inputs.sources['banks'].values():
        raw = sound_inputs.read(config, entry)
        before, old_facts = baseline.prepare(raw, native=entry['native'])
        after, facts = sound_codec.prepare(raw, native=entry['native'])
        assert before == after and old_facts == facts
        assert baseline.validate(before, native=entry['native']) == sound_codec.validate(after, native=entry['native'])
        totals['banks'] += 1; totals['bytes'] += len(after)
        for key in facts: totals[key] += facts[key]
    assert sound_inputs.collect(config) == inputs
    assert not config.root.exists()
    assert not {'capture_server', 'data_paths', 'ffbe_state'} & set(sys.modules)
    print(json.dumps({'equal_prepared_bytes_and_facts': True, **totals}))
PY
```

The initial worktree was clean. Tracked changes and new files are reviewed
separately. OpenLore's partial BM25 navigation/impact results were checked against
current source; its impact graph did not include the sound reader's cross-module
call. The inherited task-observer hook is unavailable: its skill and observation
directory are absent from the inspected local skill locations.

## Limits and manual iPhone validation

The playing service, private campaign, certificates, prepared generations and
network settings were not changed or restarted. Shared game data was read-only
input. No new physical-iPhone success is recorded. After a later normal start
with the reviewed code, confirm native login, music and button sounds. Existing
device acceptance gaps retain their status; this optimization does not resolve
artwork/download issues or establish full-catalogue acceptance.
