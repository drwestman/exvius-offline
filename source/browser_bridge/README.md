# Exvius browser streaming

The original Android APK runs on the existing Apple silicon AVD. A local bridge
streams its main display and audio to a browser and relays a restricted set of
touch/key commands. All clients share that Android installation and save.

## Setup and play

Complete the normal Android setup first:

```sh
python3 source/exvius/macos_emulator.py setup
python3 source/exvius/macos_emulator.py setup-browser --lan
python3 source/exvius/macos_emulator.py browser --lan
```

The browser setup installs Node if necessary, mkcert, locked npm dependencies,
the compiled browser/bridge bundle, and the SHA-256-pinned official scrcpy 3.3.3
server. It creates a **project-specific local certificate authority**, generates
the browser certificate, and then attempts to install the public CA certificate
into the Mac's system trust store. macOS may request administrator authentication
for that trust change. Regular launch performs no dependency downloads or trust
changes.

### If macOS cannot authorize certificate trust

Some terminal, remote, or automated sessions cannot display macOS's trust
authorization dialog. If setup reports **Mac CA trust is pending**, its files
are ready but local browser play still needs this one-time approval:

1. On the Mac's desktop, open **Keychain Access** and import the printed
   **ca/rootCA.pem** public certificate into the **System** keychain.
2. Double-click that certificate and expand **Trust**.
3. Set **When using this certificate** to **Always Trust**, close the window,
   and approve the change with your Mac credentials when prompted.
4. Run `python3 source/exvius/macos_emulator.py browser --lan`.

The launcher retains the existing project CA and private key. It handles only
this specific authorization denial as pending trust; other certificate errors
still fail setup. Do not run the whole setup command with `sudo`.

### Start playing

Double-click **Play Exvius in Browser.command** for subsequent launches. Keep its
terminal open. It opens a tab on the Mac and prints the LAN URL and an eight-digit
access code. Open that URL from a device on the same home network, enter the code,
then tap **Play** to enable sound and video. One player can connect at a time.

For localhost access only, omit `--lan`. Use `--lan-address 192.168.x.x` to select
a specific private IPv4 address when VPNs or multiple adapters confuse detection.
`--port 8444` changes the HTTPS port; `--no-open` prints addresses without
opening a browser. Allow incoming connections for Node in the macOS firewall if
requested; Wi-Fi client isolation or guest networks may prevent LAN access.

### Trust the certificate on other devices

Setup prints the location of **ca/rootCA.pem** under
`~/Library/Caches/exvius-offline/emulator/browser/`. Transfer only that public
certificate, for example with AirDrop or USB.

- **iPhone/iPad:** open the certificate, install its profile under Settings >
  General > VPN & Device Management (or Profile Downloaded), then enable full
  trust under Settings > General > About > Certificate Trust Settings.
- **Other Macs/computers:** import the public CA certificate into the browser's
  trusted root store.
- **Android Chrome:** install the public certificate as a CA certificate through
  the device's security settings.

Never transfer **rootCA-key.pem** or **key.pem**. Server keys and CA files stay
outside the repository. Reuse the same CA when rerunning setup after the Mac's
LAN IP changes or its leaf certificate expires; clients do not need a new CA.
Setup includes localhost, the selected IP, and the Mac's local hostname in the
certificate. Current Chrome/Edge and Safari with WebCodecs are the supported
targets. Real iPhone/iPad certificate trust and playback require device validation.

### Lifecycle

```sh
python3 source/exvius/macos_emulator.py browser-status
python3 source/exvius/macos_emulator.py doctor --browser
python3 source/exvius/macos_emulator.py browser-stop
python3 source/exvius/macos_emulator.py stop
```

Status does not start Android or ADB. Doctor inspects prerequisites only.
Disconnecting, closing a tab, or leaving a mobile browser releases held input and
stops capture; press Play to reconnect. Android continues running. Ctrl+C or
closing the launcher terminal stops the bridge, and `browser-stop` provides the
same action from another terminal. `stop` stops both the bridge and the named AVD.

A stopped AVD starts headlessly in browser mode. An existing visible AVD is reused
without restarting its game. To switch between headless and visible Android,
explicitly stop it and start the desired launcher. Browser mode does not reinstall
the game or clear data. It leaves a visible game activity untouched, brings an
existing background game task forward, and opens the game launcher if no game
activity exists. This also applies when reusing an already-running browser bridge.

Logs: `~/Library/Logs/Exvius Offline/browser.log`. The host-only control socket
lives in a private, user-owned directory under `/private/tmp/exvius-browser-*`.
The access code changes whenever the bridge starts. Browser cookies expire with
that bridge run. Keep the Mac awake. After the game data and browser setup are
complete, no Internet connection is required for LAN play.

## Boundaries

- Python owns emulator lifecycle and selects/verifies the named AVD.
- SessionCommands is the only writer of capture/controller state. SessionQueries
  returns immutable status snapshots; reads never start capture or Android.
- ScrcpyAdapter verifies the selected AVD again before capture. Its ADB connection
  stays on 127.0.0.1. The browser cannot select devices or invoke arbitrary ADB.
- The HTTPS service enforces authentication, origins/hosts, rate and payload
  limits, and one controller. Input is validated and never retried after reconnect.
- Video is H.264, maximum dimension 1280, 30 FPS and 4 Mb/s. Audio uses 48 kHz,
  stereo signed 16-bit PCM (~1.54 Mb/s) and a bounded Web Audio worklet buffer.
  Media queues are bounded; slow clients reconnect instead of accumulating delay.
- Playback, normalized input mapping, and connection UI are separate browser
  components. There is no new gameplay API, save format, database, or event store.

## Validation

```sh
npm ci --prefix source/browser_bridge
npm test --prefix source/browser_bridge
npm run test:browser --prefix source/browser_bridge
python3 -m unittest discover -s source/exvius -p test_macos_emulator.py
python3 -m unittest discover -s source/exvius -p test_browser_launcher.py
```

Playwright needs Chromium and WebKit installed (`npx playwright install chromium
webkit` from this directory). Its fixture serves real H.264 and generated PCM over
the production HTTPS service, verifies rendered pixels and input delivery, and
uses temporary certificates without installing trust.

For explicit live probes, boot the named AVD first and provide its serial, verified
server binary, and SDK adb path:

```sh
cd source/browser_bridge
node test/live-capture.mjs emulator-5554 /path/to/scrcpy-server.jar /path/to/sdk/platform-tools/adb
node test/live-browser.mjs emulator-5554 /path/to/scrcpy-server.jar /path/to/sdk/platform-tools/adb
```

Live probes capture the existing display and audio without launching an activity
or injecting controls. The browser probe checks actual Android frames in Chromium
and WebKit. These checks do not replace testing battle play, sound quality,
certificate installation, and reconnect on physical iPhone/iPad devices.
