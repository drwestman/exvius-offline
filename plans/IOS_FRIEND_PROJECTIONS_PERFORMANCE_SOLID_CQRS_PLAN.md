# iOS Friend and Reinforcement Projection Performance — SOLID / CQRS Plan

Status: proposed, plan only. Baseline measured November 25, 2026 against the
current worktree. Reviewed the same day: the call path, call counts, output
shape, and allocation baseline were independently reproduced, and a throwaway
prototype confirmed the targets (see Section 7). This plan targets the iOS
native friend/support read path and keeps its saved relationship and wire
contracts unchanged.

## 1. Goals & Measured Bottleneck

The iOS GetReinforcementInfoRequest projects the friend list, suggestions, and
support rows. Its pipeline currently calls
[exvius_actions_arena.friend_list](../source/server/exvius_actions_arena.py)
and then friend_reinforcements. Both call _friends(), which calls
[revival_friends.catalogue](../source/server/revival_friends.py). With the
default 200 simulated peers, each catalogue build constructs every generated
friend through CompanionDirectory.by_id() and ffbe_friends._entry(). The
support response therefore builds 400 generated rows for a synthetic campaign
that returns 15 accepted friends and 10 suggestions. The friend-list response
alone builds the same 200-entry catalogue once.

The affected native path is:

macos_ios_server.py start → ios_server.cli.serve →
Service.start → Gameplay.start → ios_server.engine.Engine(config,
prepared=True).initialize(lease=lease) → capture_server.main(in_process=True) →
ios_server.game_http.handler → capture_server.Handler.do_POST / _handle
(under STATE_LOCK) → ffbe_pipeline.reply_pipeline →
ffbe_friends.serve_friends → exvius_actions_arena.friend_list and
friend_reinforcements → _friends → revival_friends.catalogue →
CompanionDirectory.by_id → ffbe_friends._entry →
player_state.unit_stats.

File locations: macos_ios_server.py is
[source/exvius/macos_ios_server.py](../source/exvius/macos_ios_server.py), the
ios_server package is [source/ios_server](../source/ios_server), and Gameplay
lives in [hosting.py](../source/ios_server/hosting.py). The action dispatcher
does not also run friend_list / friend_reinforcements for these replies:
[exvius_actions.KEEP_EXISTING](../source/server/exvius_actions.py) excludes
u7Id4bMg and AJhnI37s, so serve_friends is the only builder and the support
reply performs exactly two catalogue builds.

The bounded change is to build the companion rows needed by the current social
read and share that request-local projection between the two support-reply
steps. Keep revival_friends.catalogue() as the full-catalogue API for its
other callers.

**Implementation targets (not measured gains):**

- Reduce the warm support-query median from 9.29 ms to **6.0 ms or less** on
  the same host and fixture, and to **at least 30% below a baseline re-measured
  immediately before the after-run**. Warm timings varied about 10% between
  runs on this host (9.29 ms in the original run, 8.33 ms on review), so the
  relative target is authoritative.
- Reduce that query's peak traced Python allocations from 261,654 bytes to
  **200,000 bytes or less**.
- Keep the seven-worker median of application-cache-cold first queries at or
  below **75 ms**.
- Return byte-identical JSON for the baseline fixture, including list order,
  fields, and accepted/suggested/support rows.
- Project no more generated peers than the current relation IDs and suggestion
  IDs require; in the measured fixture that is 25 instead of 400 projections.

**Non-goals:** changing friend eligibility, suggestion rotation, names, rank,
unit selection, roster caps, saved relationships, friend commands, Arena policy,
legacy friend behavior, HTTP/encryption, service lifecycle, preparation, CLI
output, or physical device configuration. Do not add cross-request caching.

## 2. Baseline Measurements & Reproduction

Environment: Python 3.12.13, macOS 27.2.1, ARM64, existing .venv-ios, and
standard-library profiling only. The shared
[source/out/browser-data](../source/out/browser-data) corpus was read-only.
Each worker made a synthetic private root, campaign save, and empty
friends.yaml under a temporary directory, selected the ios-revival profile,
and used one owned starter-family unit with the default 200 simulated peers,
15 initialized friends, and 10 suggestions.

Seven fresh worker processes ran sequentially. Each process imported the handler
modules before timing, then measured one application-cache-cold
ffbe_friends.serve_friends({}, 'AJhnI37s') call and nine warm repeats while
holding the canonical capture_server.STATE_LOCK. It separately traced one
warm query and profiled another warm query. Filesystem caches were not flushed.
The audit hook rejected file-write opens and socket bind/connect calls during
the query. Each worker checked that the synthetic campaign, save bytes, and
global RNG state were unchanged. Temporary roots were removed on exit.

| Measurement | Baseline |
| --- | ---: |
| First application-cache-cold support query, median (min–max) | 68.16 ms (66.21–89.45 ms) |
| Warm query median per worker, median (min–max across seven workers) | 9.29 ms (9.23–10.14 ms) |
| Warm peak traced Python allocations, median (min–max) | 261,654 bytes (261,554–261,754 bytes) |
| Output rows: friends / suggestions / supports | 15 / 10 / 15 |
| Compact JSON response size | 21,448 bytes |

The separate cProfile call recorded two revival_friends.catalogue() calls,
400 CompanionDirectory.by_id() calls, 400 ffbe_friends._entry() calls, and
452 player_state.unit_stats() calls. Its instrumented duration is excluded
from latency results.

Review re-run (same host, same command, November 25, 2026): cold median
66.94 ms (66.36–74.11 ms), warm median 8.33 ms (8.28–8.44 ms), peak traced
261,704 bytes (261,652–261,754 bytes), rows 15 / 10 / 15, 21,448 reply bytes,
and identical profile counts (2 / 400 / 400 / 452). All queries were pure.

Reproduce the seven-worker baseline from the repository root:

~~~sh
.venv-ios/bin/python -B - <<'PY'
import json, statistics, subprocess, sys

worker = r'''import cProfile, hashlib, json, os, pstats, random, sys, tempfile, time, tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

repo = Path.cwd()
sys.path[:0] = [str(repo / 'source'), str(repo / 'source/server')]
from engine_profile import IOS_REVIVAL, select_profile
select_profile('ios-revival')
from ios_server.config import Configuration
now = datetime(2026, 11, 25, 17, tzinfo=timezone.utc)

with tempfile.TemporaryDirectory(prefix='bolt-friend-support-') as tmp:
    root = Path(tmp) / 'private'
    config = Configuration(root, repo / 'source/out/browser-data')
    root.mkdir(parents=True)
    config.state_file.parent.mkdir(parents=True)
    friends_file = Path(tmp) / 'friends.yaml'
    friends_file.write_text('friends: []\n', encoding='utf-8')
    data = {
        'ios_revival': {'version': 1, 'replay': __import__('replay_calendar').new_anchor(now, IOS_REVIVAL.replay)},
        'identity': {'user_id': 'synthetic-local'},
        'roster': [{'master_id': '100000102', 'level': 30, 'instance_id': 'synthetic-starter'}],
    }
    os.environ.update(config.engine_environment())
    os.environ.update({
        'FRIENDS_FILE': str(friends_file), 'EXVIUS_PLAYERS': '200',
        'EXVIUS_START_FRIENDS': '15', 'EXVIUS_PLAYER_SUGGESTIONS': '10',
    })
    import revival_friends
    revival_friends.initialize(data, yaml_friends=[])
    config.state_file.write_text(json.dumps(data, sort_keys=True), encoding='utf-8')
    saved_digest = hashlib.sha256(config.state_file.read_bytes()).hexdigest()
    import ffbe_state
    ffbe_state.State.player = SimpleNamespace(data=data, mode='live', dirty=False)
    import capture_server
    import ffbe_friends
    import exvius_actions_arena as arena

    def query():
        with capture_server.STATE_LOCK:
            response = ffbe_friends.serve_friends({}, 'AJhnI37s')
            return json.dumps(response, sort_keys=True, separators=(',', ':')).encode()

    def readonly(event, args):
        if event == 'open' and len(args) > 2 and args[2] & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            raise AssertionError('query attempted a file write')
        if event in ('socket.bind', 'socket.connect'):
            raise AssertionError('query attempted network access')

    sys.addaudithook(readonly)
    before, rng = json.dumps(data, sort_keys=True), random.getstate()
    with patch.object(revival_friends, 'clock', return_value=now), patch.object(
            arena.time, 'gmtime', return_value=now.timetuple()):
        start = time.perf_counter()
        first = query()
        cold_ms = (time.perf_counter() - start) * 1000
        warm_ms = []
        for _ in range(9):
            start = time.perf_counter()
            reply = query()
            warm_ms.append((time.perf_counter() - start) * 1000)
            assert reply == first
        tracemalloc.start()
        assert query() == first
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        profiler = cProfile.Profile()
        profiler.enable()
        assert query() == first
        profiler.disable()

    assert json.dumps(data, sort_keys=True) == before
    assert random.getstate() == rng
    assert hashlib.sha256(config.state_file.read_bytes()).hexdigest() == saved_digest
    profile = pstats.Stats(profiler)
    counts = {
        name: sum(value[1] for key, value in profile.stats.items() if key[2] == name)
        for name in ('catalogue', 'by_id', '_entry', 'unit_stats')
    }
    result = json.loads(first)
    print(json.dumps({
        'cold_ms': cold_ms, 'warm_ms': warm_ms, 'traced_peak_bytes': peak,
        'rows': [len(result.get(key, [])) for key in ('56gJBnVh', 'f6yGgCj2', 'pzf5se6V')],
        'reply_bytes': len(first), 'profile_calls': counts, 'query_pure': True,
    }, sort_keys=True))'''

samples = []
for _ in range(7):
    run = subprocess.run([sys.executable, '-B', '-c', worker], capture_output=True, text=True)
    if run.returncode:
        raise SystemExit(run.stdout + run.stderr)
    samples.append(json.loads(run.stdout.strip().splitlines()[-1]))
med = statistics.median
warm = [med(sample['warm_ms']) for sample in samples]
print(json.dumps({
    'workers': len(samples), 'warm_repeats_per_worker': 9,
    'cold_ms': {'median': med([sample['cold_ms'] for sample in samples]),
                'min': min(sample['cold_ms'] for sample in samples),
                'max': max(sample['cold_ms'] for sample in samples)},
    'warm_worker_medians_ms': {'median': med(warm), 'min': min(warm), 'max': max(warm)},
    'warm_traced_peak_bytes': {
        'median': med([sample['traced_peak_bytes'] for sample in samples]),
        'min': min(sample['traced_peak_bytes'] for sample in samples),
        'max': max(sample['traced_peak_bytes'] for sample in samples)},
    'rows': samples[0]['rows'], 'reply_bytes': samples[0]['reply_bytes'],
    'profile_calls': samples[0]['profile_calls'],
    'all_queries_pure': all(sample['query_pure'] for sample in samples),
}, indent=2))
PY
~~~

The cold value is application-cache-cold after imports, not process startup or
cold storage. The workload measures the friend pipeline transform and compact
JSON serialization under its existing lock; it excludes envelope encryption,
TLS, network transfer, other reply-pipeline steps, iPhone rendering, and device
latency. tracemalloc is Python allocation data, not process RSS. These results
show repeated host-side construction in this synthetic social workload; they
do not claim an end-to-end iPhone speedup.

## 3. Architecture Overview (CQRS + SOLID)

~~~mermaid
flowchart LR
    A[macos_ios_server.py start] --> B[ios_server.cli and Service]
    B --> C[Gameplay and prepared Engine]
    C --> D[game_http handler]
    D --> E[capture_server Handler under STATE_LOCK]
    E --> F[ffbe_pipeline.reply_pipeline]
    F --> G[ffbe_friends.serve_friends]
    G --> H[FriendListReadQuery]
    H --> I[CompanionDirectory]
    I --> J[Selected friend rows]
    J --> K[friend_list and friend_reinforcements]
    K --> L[Existing native reply fields]
~~~

### CQRS Boundary

FriendListReadQuery derives a request-local projection from the current saved
campaign, friend relations, replay time, and configured friend catalogue. It
does not modify State.player.data, call save_state, advance replay state,
initialize a campaign, write a cache, download content, open a network
connection, or start a service. It acquires no new lock; the gameplay handler
continues to hold its existing STATE_LOCK around the whole reply transform.
This read model runs only inside the initialized gameplay pipeline after profile
selection; it adds no engine imports to diagnostic or preparation query paths.
Friend add/remove/favorite commands continue through
revival_friend_commands.execute and retain their current save-before-publish
behavior.

### SOLID Mapping

| Principle | Concrete design |
| --- | --- |
| **S — Single Responsibility** | revival_friends.FriendListReadQuery determines and materializes only the IDs needed for a friend/support read. exvius_actions_arena.friend_list and friend_reinforcements continue to build their existing wire rows. ffbe_friends.serve_friends remains the reply-pipeline adapter and shares one read model for a support reply. |
| **O — Open/Closed** | Add a targeted projection API while keeping revival_friends.catalogue(data, now) as the full-catalogue contract for Arena, gifts, commands, and other callers. New read views can request their IDs without changing CompanionDirectory selection rules. |
| **L — Liskov Substitution** | A narrow FriendDirectory Protocol exposes the existing ids(), curated(friend), and by_id(friend_id) results, including None for an unavailable friend. ids() is required so the query keeps the full catalogue's generated-ID range and ascending order. CompanionDirectory remains the production implementation; a deterministic test directory can substitute it without changing query behavior. |
| **I — Interface Segregation** | The query consumes only FriendDirectory.ids, FriendDirectory.curated, and FriendDirectory.by_id; it does not depend on friend mutation, persistence, Arena, transport, or engine lifecycle methods. A frozen FriendProjectionRequest carries a tuple of requested IDs and one injected timestamp. A frozen FriendReadModel carries the request-local projected rows, relation view, and suggestion IDs to the two reply builders. The frozen dataclass does not freeze its nested dicts; consumers must treat rows and relations as read-only. |
| **D — Dependency Inversion** | FriendListReadQuery accepts a FriendDirectoryFactory Protocol; production injects CompanionDirectory, and tests inject a call-counting implementation. The shared action adapter depends on the read-model contract rather than constructing or caching all simulated peers itself. |

**Simpler alternative (prefer unless the extra types earn their keep):** the
review prototype achieved the full result in about 15 lines with an optional
ids filter on catalogue(data, now, ids=None) and one request-local
(catalog, state, suggestion_ids) tuple passed to both reply builders. The
protocols and dataclasses above are acceptable, but they must not grow beyond
what the BDD scenarios need; a call-counting test can patch
CompanionDirectory directly.

### Cache, Concurrency & Compatibility Invariants

- Add no cross-request cache. The selected peer and eligibility still derive
  from the current profile, campaign roster and relationships, configured
  friend file, replay week, and current saved timezone.
- Add no master-generation cache; content root and profile remain bound to the
  running engine process, and changing either continues to require a fresh
  process.
- Reuse one CompanionDirectory only within the current support request.
  Its current request-local companion pool remains request-local.
- Keep generated IDs and curated friend rows in the same relative order as the
  full catalogue. Preserve saved tombstones, favorites, default curated
  relationships, helper eligibility, and current suggestion ordering.
- Preserve the two ID-range rules: catalogue() excludes configured (YAML)
  friend IDs from the generated set, and state_view() does not add a default
  accepted relation for IDs inside the generated range (ID_BASE+1 to
  ID_BASE+999).
- Use one timestamp per request. Today catalogue() and suggestion_ids() each
  call clock() separately, and the two support-reply steps each build their own
  directory, so one reply can straddle a local-day or replay-week boundary. A
  single injected timestamp makes the reply internally consistent. This is an
  intentional, documented behavior change at boundaries only; output for any
  fixed time is unchanged.
- The suggestion IDs used to select generated rows must be the same IDs that
  _suggestions renders. Otherwise a suggestion picked under a different clock
  reading is silently dropped by its `if fid in catalog` filter.
- Shared rows are read-only. The current reply builders (_friend_row,
  _reinforce_row, _friend_reply) create new row dicts and do not mutate friend
  dicts; keep it that way, and keep state_view's copy semantics for callers
  that might mutate relations.
- The full catalogue remains available to other consumers. The legacy branch
  in exvius_actions_arena remains unchanged; profile selection still happens
  before engine imports.
- Preserve all reply tags, row fields, JSON values, encryption, GET/HEAD
  behavior, save receipts, and CLI stdout JSON / stderr diagnostics. This
  change does not touch transport, diagnostics, or the CLI.

## 4. Planned Modules & File Changes

1. **source/server/revival_friends.py**
   - Add frozen FriendProjectionRequest and FriendReadModel dataclasses.
   - Add narrow FriendDirectory and FriendDirectoryFactory protocols.
   - Add FriendListReadQuery to:
     1. Read the configured curated friends and current relation state.
     2. Keep eligible configured rows in their existing order.
     3. Select generated IDs from persisted visible relations (types 1, 2,
        and 3) plus the current suggestion_ids(data, now), computed with the
        directory's single timestamp.
     4. Build those generated rows once, in the same order as the full
        catalogue (ascending over directory.ids(), skipping YAML IDs), using
        one request-local CompanionDirectory.
     5. Return the suggestion IDs in the read model so the reply builders do
        not recompute them.
   - Keep catalogue() behavior and return type unchanged for full-catalogue
     consumers.

2. **source/server/exvius_actions_arena.py**
   - Allow friend_list and friend_reinforcements to consume the optional
     FriendReadModel.
   - Keep their current projection and row construction, using the supplied
     rows when present. The iOS read path creates one model; the legacy path
     keeps _friends() and its current behavior.
   - When a read model is supplied, _suggestions must use its suggestion IDs
     instead of calling suggestion_ids(State.player.data) with a fresh clock.
   - Friend commands (search, detail, agree, request, favorite, delete,
     refuse) and gifts (ffbe_friends.all_friends) keep the full catalogue,
     because they look up arbitrary target IDs.

3. **source/server/ffbe_friends.py**
   - For the iOS GetReinforcementInfoRequest, create one request-local
     FriendReadModel and pass it to both friend_list and
     friend_reinforcements, instead of constructing two full catalogues.
   - For FriendListRequest and boot friend-list projection, construct one
     targeted model and pass it through the same existing reply adapter.
   - Leave the legacy YAML path and all write commands unchanged.

4. **source/exvius/test_ios_friends.py**
   - Add BDD coverage for exact output parity, requested-ID call counts, current
     campaign/time inputs, purity, and shared support-query projection.

This is a medium-sized change across one read model, its existing reply
adapter, and its focused iOS scenarios. It adds no framework, durable cache,
save migration, launcher change, or dependency.

## 5. Verification, Benchmark & BDD Test Plan

### Given / When / Then Scenarios

- **Given** a synthetic initialized campaign with the default simulated-peer
  count, 15 accepted friends, 10 suggestions, and one owned starter family,
  **when** FriendListRequest is projected, **then** all existing friend and
  suggestion rows, ordering, and serialized JSON match the full-catalogue
  reference while by_id() is called only for requested generated IDs.
- **Given** the same campaign, **when** GetReinforcementInfoRequest builds
  both the friend list and support response, **then** one FriendReadModel
  supplies both views, every existing reply field is byte-identical, and the
  query does not build unused generated peers twice.
- **Given** a roster-level or family change, **when** the next query runs,
  **then** helper eligibility and level caps reflect the new campaign state.
- **Given** a replay-week/timezone boundary, **when** the query runs at the
  corresponding injected time, **then** the selected suggestions and helper
  forms follow the same saved-calendar rules as before.
- **Given** a fixed time just before and just after a local-day boundary,
  **when** the support query runs, **then** the friend list, suggestions, and
  support rows all use the same day, and every suggestion ID returned by the
  model is rendered (none dropped by the catalogue filter).
- **Given** a configured YAML friend whose friend_id falls inside the generated
  range, **when** the query runs, **then** inclusion, default relationship, and
  ordering match the full-catalogue reference.
- **Given** pending outgoing (type 2) and incoming (type 3) generated
  relations, **when** FriendListRequest is projected, **then** those peers are
  projected and listed exactly as before, and tombstoned (type 0) peers are
  projected only if they are current suggestions.
- **Given** a missing owned family or invalid saved relationship, **when** the
  query runs, **then** it preserves the current empty/error behavior without
  repairing campaign data.
- **Given** concurrent read requests, **when** they run through the existing
  state lock, **then** each response is stable, no shared mutable projection is
  retained, and the campaign, save bytes, and global RNG remain unchanged.
- **Given** a saved campaign reloaded in a fresh process, **when** friend and
  support queries run, **then** they return the same rows without adding
  projection state to the save.
- **Given** friend add/remove/favorite commands, **when** their existing
  scenarios run, **then** their transaction, retry, and save behavior remains
  unchanged.

### Verification Commands

Run these during implementation, in order:

~~~sh
.venv-ios/bin/python -B source/exvius/test_ios_server.py
.venv-ios/bin/python -B source/exvius/test_ios_friends.py
.venv-ios/bin/python -B source/exvius/test_ios_arena.py
.venv-ios/bin/python -B source/exvius/test_local_game.py
.venv-ios/bin/python -B source/exvius/test_macos_emulator.py
git diff --check
~~~

The friend and Arena suites cover the affected social projection and related
native list behavior. The two legacy suites check that the shared action module
keeps its existing profile-specific behavior. During review,
test_ios_friends.py passed (exit 0) against the unmodified worktree; the other
suites were not run.

### Before / After Benchmark Protocol

Run the reproduction command from Section 2 immediately before and after
implementation (back to back, not against the recorded numbers), with the same
source corpus, Python interpreter, fixed time, temporary fixture,
workers, repetitions, audit hooks, and no other test suite running. Compare
application-cache-cold first requests separately from warm worker medians.
Collect tracemalloc and cProfile outside the timed samples. Confirm output
bytes, row order, and purity match. Do not interpret traced allocations as RSS
or the host-side query as an iPhone end-to-end latency result.

## 6. Risks, Tradeoffs & Manual iPhone Validation

The main correctness risk is changing the order or inclusion of generated and
configured friends while narrowing the projection. Preserve the existing
curated-first / generated-ID order and cover saved removals, favorites, empty
eligible pools, and current-time selection in BDD scenarios. If a campaign has
all generated peers accepted, the read model still needs all visible peers and
the speedup will be smaller; it must return them all.

The plan trades construction of unused request-local dictionaries for one
request-scoped projection object. It retains no new state between requests and
does not weaken master validation, eligibility, save checks, or locks.

The dated [native device acceptance record](IOS_DEVICE_ACCEPTANCE.md) reports
friend-list, companion-selection, and companion-battle use accepted on the
iPhone. After implementation, repeat those screens on the device: load the
friend list, open the support list, select an eligible helper, and enter a
battle. Confirm the same friend rows render and the helper remains usable.
Host tests and benchmarks cannot establish physical-iPhone latency or
acceptance.


## 7. Review Findings (November 25, 2026)

An independent review reproduced the Section 2 baseline (see the review re-run
note there) and traced the call path in source. It found every measured claim
correct; the warm median differed by about 10% from the original run because
of host noise, with identical call counts.

A throwaway prototype (not committed) narrowed generated IDs to saved type
1–3 relations plus suggestion_ids and shared one result across friend_list and
friend_reinforcements in the support reply. It was measured with the Section 2
worker:

| Measurement | Baseline (review run) | Prototype | Target |
| --- | ---: | ---: | ---: |
| Warm median | 8.35 ms | 1.74 ms | ≤ 6.0 ms and ≥ 30% lower |
| Peak traced allocations | 261,604 bytes | 139,417 bytes | ≤ 200,000 bytes |
| Application-cache-cold first query | 67.03 ms | 59.93 ms | ≤ 75 ms |
| by_id / _entry / unit_stats calls | 400 / 400 / 452 | 25 / 25 / 71 | 25 projections |
| Reply SHA-256 | 88e7f788…fed0a8 | 88e7f788…fed0a8 | byte-identical |

The targets are achievable with margin. The review added these requirements,
now folded into Sections 1, 3, 4, and 5:

1. _suggestions must use the read model's suggestion IDs; otherwise a separate
   clock reading can silently drop a suggestion.
2. A single per-request timestamp is an intentional boundary-only behavior
   change and is documented as such.
3. FriendDirectory must expose ids() to preserve generated-ID range and order.
4. Prefer the simpler catalogue(..., ids=) plus shared tuple design unless the
   extra protocol and dataclass types are needed by tests.
5. Read-model rows and relations are read-only; frozen dataclasses do not
   freeze nested dicts.
6. Preserve the YAML-ID-in-generated-range rules of catalogue() and
   state_view(), with a BDD scenario.
7. Judge the warm target relative to a back-to-back re-measured baseline.
