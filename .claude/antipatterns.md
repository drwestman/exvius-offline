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
- **Additional evidence**: On 2026-11-17, Running Through Daybreak's inner tiles referenced 15 icons in separate story-area packs. The first embedding trial passed host checks but was followed by physical Home/Vortex failures on 2026-11-18; it is disabled. Validate native mounting and scene compatibility before treating an upfront dependency copy as accepted.
- **Discovered**: 2026-11-11 via the iPhone's uploaded summon-crash session.

## AP-007 — Losing reserved binary values in text round trips

- **Class**: boundary
- **Symptom**: A rebuilt CPK decoded like its source but changed the TOC's reserved null-string offset from zero to an ordinary string offset.
- **Rule**: Preserve reserved wire values explicitly and test binary cells against the native contract; decoded text equality cannot establish binary compatibility.
- **Discovered**: 2026-11-11 during Vortex banner-load diagnosis; physical recovery remains a separate device check.

## AP-008 — Publishing native URLs without their request adapters

- **Class**: boundary
- **Symptom**: The iPhone's Drop Rates page was blank because its advertised form-POST URL returned an empty 404, while an alternate HTML URL worked.
- **Rule**: Exercise the exact advertised native URL, method and parameter encoding through the real HTTP handler; rendering the same content through another route does not verify native navigation.
- **Discovered**: 2026-11-12 via physical Drop Rates acceptance and matching live 404 probes.

## AP-009 — Treating release metadata as an installed content tree

- **Class**: assumption
- **Symptom**: The iPhone launcher selected the metadata-only checkout data directory and failed on a missing native registry despite prepared host assets being available.
- **Rule**: Distinguish installation markers from release metadata when choosing default content paths. Preserve explicit selections and existing installations; never silently switch away from an incomplete installation.
- **Discovered**: 2026-11-12 via Play Exvius on iPhone.command startup failure.

## AP-010 — Joining battle IDs directly to quest target IDs

- **Class**: boundary
- **Symptom**: Reported wolf defeats never advanced the accepted town quest after returning from a mission.
- **Rule**: Resolve battle monster IDs through the served bundle's dictionary-family mapping and retain that mapping with the attempt before joining defeat reports to quest targets.
- **Discovered**: 2026-11-14 via Bleeder of the Pack quest progress.

## AP-011 — Gating catalogue corrections behind optional save upgrades

- **Class**: assumption
- **Symptom**: Existing iOS campaigns advertise duplicate event missions because clone filtering requires an unrelated update-policy marker, and exploration collection points (`vM21k0do` / `COLLECTION` in `revival_battle_updates.py`) never spawn or pay out harvest drops such as Lumber in Latius Woods without `ios_revival_update`.
- **Rule**: Separate catalogue identity corrections and base exploration mechanics from optional saved feature policies; test both existing campaigns without the marker and upgraded campaigns without mutating either.
- **Discovered**: 2026-11-16 via duplicate Mana Mystery difficulties; recurred 2026-11-17 via missing Lumber collection drops in Latius Woods - Exploration.

## AP-012 — Substituting replay weeks for annual event dates

- **Class**: boundary
- **Symptom**: January Vortex events run during November, and News presents their original dates without current availability bounds.
- **Rule**: Resolve one annual occurrence from pinned run metadata and use it for listings, date fields and entry checks. Keep summon replay history separately labelled; never cache clock-dependent eligibility across midnight.
- **Discovered**: 2026-11-16 via Notices -> News date mismatch and shared legacy/iOS event reproduction.

## AP-013 — Treating a base receipt as optional-feature initialization

- **Class**: assumption
- **Symptom**: Upgrading during a pending exploration preserves an existing collection receipt whose empty reward placeholders suppress first-clear Lapis and Gil.
- **Rule**: Initialize optional-feature snapshots independently of base receipts; exercise enabling the feature during a pending operation, preserving existing rolls and authoritative snapshots.
- **Discovered**: 2026-11-17 via pending-exploration upgrade reward regression.
