# iPhone Vortex crash investigation

The November 18 artwork rollback reached the phone, but Vortex still crashed.
The OS report and client logs now point to missing resident town data while
background masters are still downloading. The user subsequently confirmed that
Home icons returned and Vortex stopped crashing after the Home wait and relaunch.

## Evidence

- `logs/FF EXVIUS-2026-11-18-084219.ips` records an `EXC_BAD_ACCESS` /
  `SIGSEGV` at address `0x90` on thread 0 at 08:42:18 local time. Register
  `x0` is zero and `x20` is 9001. This is not an OS memory-pressure termination.
- The locally available Android ARM64 `libgame.so` has matching game concepts:
  `GateEntryScene::initialize` resolves `OTHER_WORLD_TOWN_ID` (9001), looks up
  `TownMstList`, and reads the field BGM at offset `0x90`. A missing town yields
  precisely this null-plus-offset access. Its SHA-256 is
  `a127654037f2f28a70cce7c64ff0a9d291770ea904cdf5bcba59a7af9a6937e4`.
  This corroborates the hypothesis; it does not symbolicate the iOS executable.
- Prepared generation 7 contains town 9001 in `F_TOWN_MST`. Exact TLS GETs for
  that table, `F_ICON_MST`, and `F_HOME_SCREEN_ICON_MST` return 200 with the
  published sizes and SHA-256 hashes. Their files are available on the host.
- The latest retained game report contains no generation-7 town-table install.
  Its last background master installation before GateEntryScene is file
  `127/223`, `Ver270006_tUQ2Lkc1.dat`. An earlier generation-5 report installs
  that same table followed by two other masters and then `F_TOWN_MST`.
  The latest log therefore does not establish completion of the required table.
- The acceptance record already contains a physical November 12 Vortex recovery
  after waiting on Home, with no intervening code or asset-generation change.
- Generation 7's Vortex CPK is byte-identical to generation 5. Completing its
  download does not establish completion of the separate background master queue.

## Current action and validation

No additional pack or master generation was published during this investigation.
The host was stopped when checked; it was restarted with the existing generation
7, campaign, configuration, and opt-in client diagnostics. Status reports gameplay
mode and readiness. No synthetic gameplay request or manual save edit was made.

The requested device check was to remain on Home with the screen awake for five
minutes, then fully close/reopen FFBE and retry Vortex. The user reports that Home
icons are back and Vortex no longer crashes. No new asset generation or code fix
intervened. This supports incomplete background masters as the immediate trigger;
the exact town-table installation time has not been independently verified.

`revival_boot.step` also narrows a returning device's early version carrier to
`F_FUNCTION_MST`. Its involvement in this crash is unconfirmed; it was not changed.
Running Through Daybreak's original blank inner tiles remain unresolved, and
experimental inner-icon embedding remains disabled.

## Visible download progress follow-up

The user requests remaining on the download progress screen so players can tell
that the game is still downloading. This behavior is not implemented by this
investigation. No supported server-only setting has been established.

The inspected local Android native binary separates the queues:
`DownloadSequencePopup::requestMstDownload` obtains the startup subset through
the native master manager (`0x1d56100`, called with false), while
`LoginScene::procStateBackgroundDownload` starts the background downloader and
immediately advances login. The stock iOS executable has not been inspected, so
these symbols establish a related native design rather than an iOS patch point.
The server's `ResourceAllDownloadRequest` endpoint has no authored response;
the native bulk-download scene is therefore not a verified workaround here.
Do not advertise an untested protocol flag as a working progress-screen control.
