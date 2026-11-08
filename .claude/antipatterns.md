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
