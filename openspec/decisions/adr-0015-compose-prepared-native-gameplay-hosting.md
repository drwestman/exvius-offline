# ADR-0015: Compose prepared gameplay with the native listener lifecycle

## Status

Accepted for native Mac gameplay hosting; physical-iPhone gameplay acceptance pending.

## Context

The accepted native service owns DNS, HTTP, HTTPS, TLS renewal and private control,
but serves only setup and hello pages. The engine adapter consumes verified native
tables, Vortex, sound and artwork while independently owning the runtime lock.
Combining them needs one lease and one shutdown order. Reusing only network
identity would also allow a connection-check command or a different slot to be
mistaken for the running game instance.

## Decision

First extract explicit lifecycle and preparation command groups from the CLI and
certificate/log/resolver preparation from startup. This preserves behavior while
reducing coordinator coupling before hosting integration.

Keep serve as the independent connection check. Add foreground start for prepared
gameplay and a separate double-click launcher. Require an explicitly initialized
campaign and current complete schema-5 tables with Vortex and sound bindings,
plus prepared summon/home snapshots. Missing source art remains a reported gap.
No startup downloads, conversion, native preparation or campaign backfill occurs.

Let the transport acquire the private InstanceLock and bind every listener before
activating the game application. Supply that held, root-matching lease to Engine;
standalone engine consumers continue to own their lock. Validate prepared inputs
before importing state, compose a narrow handler over the canonical implementation,
then start listeners and report readiness. Failure closes all acquired resources.

The wrapper keeps public setup/profile/hello GET/HEAD routes and delegates game
API, native assets and WebViews to the canonical handler. Block its local debug
and new-game routes. Require one bounded Content-Length for POST, reject transfer
encoding and close connections after replies. Preserve subnet restrictions, exact
prepared versions, canonical state locking and wire fields.

Stop all listener accept loops first, then use non-daemon gameplay request
threads so listener close drains active responses
before Engine.close or lock release. Game socket I/O is bounded at 30 seconds;
stop waits up to 40 seconds for lock and socket release. Preserve the default
connection-check lifecycle and in-process certificate renewal.

Include mode, logical/physical data roots and slot in the configuration identity.
Matching starts reuse the service; changing mode, data generation, slot or network
requires stop. Status remains a control query. A timed-out probe during bound
startup reports no ready instance; the lease still prevents a competing start.
Record queued stop intent before writing its reply, including for disconnected
clients after slow activation. Redirect canonical diagnostics to
stderr for the whole foreground lifetime, keeping readiness as one JSON document.

Prune only recognized private request records during explicit startup/maintenance,
under the state lock: three-day age and 300 MiB oldest-first size limits. Exclude
other files and links. Asset GET/HEAD and diagnostic queries never run retention.

## Consequences

Users initialize and prepare their chosen data/root/slot before starting gameplay.
Stopped time still advances the recorded replay calendar. The accepted connection
check remains usable without any game data. Existing Android/browser entrypoints,
saves, profile defaults and canonical transactions remain unchanged.

BDD exercises full listener startup/failure, shared lease and drainage, framing,
configuration reuse, system-Python dispatch, both data layouts, encrypted TLS
initialization, exact table/pack/sound/image GET/HEAD, damaged audio, query write
guards, retention and restart persistence. Native physical-device download,
first-login relaunch, tutorial, audio, UI/taps and gameplay acceptance remain open.
