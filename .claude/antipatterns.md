# Antipatterns

## AP-001 — Treating interactive authorization as file preparation

- **Class**: boundary
- **Symptom**: Setup aborts before preparing usable files when macOS cannot display a certificate trust authorization prompt.
- **Rule**: Separate file preparation from OS trust authorization. Preserve prepared artifacts and report known noninteractive authorization failures as pending approval; propagate unrelated failures and explicit refusals.
- **Discovered**: 2026-11-07 via setup-browser mkcert trust-registration failure.

## AP-002 — Treating process liveness as UI visibility

- **Class**: assumption
- **Symptom**: A launcher shows Android home even though the app process is running.
- **Rule**: Query foreground activity/task state before assuming an application is visible. Preserve an existing task and apply the same visibility check when reusing an existing session.
- **Discovered**: 2026-11-07 via Exvius browser mode displaying Android home.

## AP-003 — Filtering mixed metadata carriers as file inventories

- **Class**: boundary
- **Symptom**: Complete prepared-table filtering removed global bootstrap counters from a native initialization reply during MST_LOAD_FAILED diagnosis.
- **Rule**: Classify metadata rows separately from downloadable resource identities before applying publication allowlists; preserve canonical metadata values and test the mixed carrier.
- **Discovered**: 2026-11-11 via physical iPhone initialization.

## AP-004 — Trusting size metadata after selecting asset overlays

- **Class**: boundary
- **Symptom**: Three upfront iOS download packs had different byte lengths from their size-table rows, followed by a physical download error at 98%.
- **Rule**: Measure the exact served asset after overlay selection and bind its size/hash to published metadata; do not assume platform tables still describe repacked bytes.
- **Discovered**: 2026-11-11 via physical iPhone download acceptance.

## AP-005 — Repeating bulk diagnostics from periodic polling

- **Class**: resource
- **Symptom**: Upstream's home-poll report-back instruction caused whole device logs to upload every few seconds and slowed loading.
- **Rule**: Request bulk diagnostics at an explicit session boundary with bounded private storage; acknowledge queued work when disabled and keep bodies out of ordinary records.
- **Discovered**: 2026-11-11 while reviewing upstream 590d4fb during native UI diagnosis.

## AP-006 — Opening synchronous UI before background dependencies are ready

- **Class**: ordering
- **Symptom**: Native summon detail reported missing button textures and monster animation data immediately before the app crashed; their intact packs were still queued behind background movies.
- **Rule**: Preload a synchronous scene's mandatory packs or wait for their availability before opening it; file presence on the server does not establish readiness on the client.
- **Discovered**: 2026-11-11 via the iPhone's uploaded summon-crash session.
