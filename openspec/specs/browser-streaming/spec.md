# Browser Streaming Specification

## Purpose

Stream the original Android game from the existing Apple silicon virtual phone
to authenticated browsers on the same computer or private home network.

## Requirements

### Requirement: PreserveAndroidOwnership

The launcher SHALL reuse Exvius_Offline_API_33 and its installed APK, downloaded
data, and save. Browser capture SHALL verify the emulator name and SHALL NOT
expose general ADB, device selection, shell, install, or file operations.

#### Scenario: AttachToActiveGame
- **GIVEN** the named AVD and a visible game activity are running
- **WHEN** browser mode starts
- **THEN** capture attaches without a second emulator or activity restart.

#### Scenario: BootHeadlessly
- **GIVEN** the named AVD is stopped
- **WHEN** browser mode starts
- **THEN** Android starts with -no-window and persistent userdata.

#### Scenario: RestoreBackgroundGame
- **GIVEN** the Android home screen is visible and an Exvius task exists
- **WHEN** browser mode starts or reopens an existing bridge
- **THEN** the existing game task is brought forward without an activity restart.

#### Scenario: ProcessWithoutActivity
- **GIVEN** Exvius has a background process but no game activity
- **WHEN** browser mode starts or reopens an existing bridge
- **THEN** the launcher activity is opened with the normal Android launcher intent.

### Requirement: SeparateCommandsAndQueries

Session commands SHALL exclusively own capture lifecycle, controller acquisition,
and validated pointer/key/text input. Status queries SHALL return immutable
snapshots and SHALL NOT start Android, ADB, capture, activities, or installation.

#### Scenario: ReadIdleStatus
- **GIVEN** capture is idle
- **WHEN** an authenticated client queries status
- **THEN** status is returned without invoking the capture adapter.

### Requirement: AuthenticateAndLimitLANAccess

LAN mode SHALL use HTTPS/WSS, a per-run access code, secure session cookies,
validated hosts/origins, bounded authentication attempts and command payloads.
ADB SHALL remain local. Setup SHALL keep certificate keys outside the repository.

#### Scenario: RejectUnpairedClients
- **GIVEN** a client has no valid session cookie
- **WHEN** it requests status or a WebSocket session
- **THEN** access is denied before capture starts.

#### Scenario: ExclusiveController
- **GIVEN** a player owns the capture session
- **WHEN** a second player requests control
- **THEN** the request is rejected as Game in use.

### Requirement: PlayAndRecover

The browser SHALL decode H.264 video and play 48 kHz stereo PCM through bounded
buffers. Input coordinates SHALL account for screen scaling and letterboxing.
Disconnect SHALL release held input, close capture, and retain Android.

#### Scenario: DecodeAndControl
- **GIVEN** an authenticated Chrome or Safari browser
- **WHEN** Play is pressed
- **THEN** video frames and audio samples are played
- **AND** pointer/key commands reach the selected emulator.

#### Scenario: RejectStaleInput
- **GIVEN** a previous capture session has ended
- **WHEN** an input command carries its old session ID
- **THEN** no input is delivered.

#### Scenario: StopStreaming
- **GIVEN** a running browser bridge
- **WHEN** browser-stop or launcher termination occurs
- **THEN** bridge resources close and Android remains running
- **AND** the existing stop command can separately stop the named AVD.

## Verification

Host/device boundaries: test_browser_launcher.py and test_macos_emulator.py.
Command/authentication behavior: source/browser_bridge/test/*.test.mjs.
Browser media, volume, mobile-sized touch mapping, and reconnect:
source/browser_bridge/test/playback.browser.mjs.
Live capture and browser probes: live-capture.mjs and live-browser.mjs.
Physical iPhone/iPad trust, sound quality, and battle play require manual acceptance.

<!-- manual -->
### Known Invariants

- `BrowserLauncher.setup` must prepare the browser certificate, private key,
  metadata, and verified server before requesting macOS CA trust approval.
  If SecTrustSettingsSetTrustSettings cannot display authorization, or sudo has
  no terminal to request a password, setup must retain those files and explicitly
  report **Mac CA trust is pending** with Keychain Access approval steps.
  It must not report full completion or suppress explicit refusals, unrelated
  certificate errors, or certificate-generation failures.
  Discovered via setup-browser failure on 2026-11-07: trust registration was an
  unconditional prerequisite and a noninteractive authorization denial aborted
  the rest of setup.
- `BrowserLauncher.launch` must ensure an Exvius activity is visible on both
  new-bridge and existing-bridge paths. Process existence alone is not a visibility
  query. Resume an existing task without restarting it, and issue a launcher
  intent only when no game activity exists.
  Discovered via the Android home screen appearing instead of the game on
  2026-11-07; root cause: process-only checks and an early bridge-reuse return.
<!-- /manual -->
