#!/usr/bin/env python3
"""Manage one persistent Exvius AVD on Apple silicon, without rebuilding the APK."""
import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
AVD = 'Exvius_Offline_API_33'
IMAGE = 'system-images;android-33;google_apis;arm64-v8a'
PACKAGE = 'com.exvius.offline.test'
ACTIVITY = PACKAGE + '/com.exvius.local.DataDownloadActivity'
GIB = 1024 ** 3


class SetupError(RuntimeError):
    pass


def run(args, *, env=None, input=None, capture=True, timeout=60):
    """All subprocess arguments remain separate; never invoke a shell."""
    result = subprocess.run([str(arg) for arg in args], env=env, input=input,
                            text=True, capture_output=capture, timeout=timeout)
    if result.returncode:
        detail = ((result.stdout or '') + (result.stderr or '')).strip()
        raise SetupError(f'{Path(args[0]).name} failed ({result.returncode}). {detail}')
    return (result.stdout or '').strip()


def properties(path):
    if not path.is_file():
        return {}
    return dict(line.split('=', 1) for line in path.read_text().splitlines()
                if '=' in line and not line.lstrip().startswith('#'))


@dataclass
class Locations:
    home: Path
    sdk: Path

    @property
    def avds(self):
        return Path(os.environ.get('ANDROID_AVD_HOME', self.home / '.android/avd')).expanduser()

    @property
    def avd(self):
        return self.avds / (AVD + '.avd')

    @property
    def cache(self):
        return self.home / 'Library/Caches/exvius-offline/emulator'

    @property
    def logs(self):
        return self.home / 'Library/Logs/Exvius Offline'

    @property
    def tools(self):
        local = self.sdk / 'cmdline-tools/latest/bin'
        if (local / 'sdkmanager').is_file():
            return local
        return Path('/opt/homebrew/share/android-commandlinetools/cmdline-tools/latest/bin')

    @property
    def java(self):
        return Path('/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home')

    @property
    def env(self):
        return dict(os.environ, ANDROID_HOME=str(self.sdk), ANDROID_SDK_ROOT=str(self.sdk),
                    ANDROID_AVD_HOME=str(self.avds), JAVA_HOME=str(self.java))

    @property
    def adb(self):
        return self.sdk / 'platform-tools/adb'

    @property
    def emulator(self):
        return self.sdk / 'emulator/emulator'


class Emulator:
    def __init__(self, locations, runner=run):
        self.paths = locations
        self.run = runner

    def require_host(self):
        if platform.system() != 'Darwin' or platform.machine() != 'arm64':
            raise SetupError('This setup supports Apple silicon macOS (arm64).')

    def doctor(self):
        """Inspect files only: do not start adb, fetch packages, or create directories."""
        self.require_host()
        p = self.paths
        checks = {
            'OpenJDK 25': (p.java / 'bin/java').is_file(),
            'SDK command-line tools': (p.tools / 'sdkmanager').is_file(),
            'AVD manager': (p.tools / 'avdmanager').is_file(),
            'Android emulator': p.emulator.is_file(),
            'Android Debug Bridge': p.adb.is_file(),
            'Android 13 ARM64 image': (p.sdk / 'system-images/android-33/google_apis/arm64-v8a/package.xml').is_file(),
            AVD: (p.avd / 'config.ini').is_file(),
        }
        print(f'SDK: {p.sdk}\nAVD data: {p.avd}\nLogs: {p.logs}')
        print(f'Free host storage: {shutil.disk_usage(p.home).free / GIB:.1f} GiB')
        for name, present in checks.items():
            print(f'{"OK     " if present else "MISSING"} {name}')
        if checks[AVD]:
            self.validate_avd()
        if not all(checks.values()):
            print('Run: python3 source/exvius/macos_emulator.py setup')
        return all(checks.values())

    @contextmanager
    def lock(self):
        self.paths.cache.mkdir(parents=True, exist_ok=True)
        with (self.paths.cache / 'controller.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SetupError('Another Exvius setup, launch, or stop command is running.')
            yield

    def bootstrap(self):
        p = self.paths
        brew = Path('/opt/homebrew/bin/brew')
        if not brew.is_file():
            raise SetupError('Install Apple silicon Homebrew from https://brew.sh first.')
        if not (p.java / 'bin/java').is_file():
            self.run([brew, 'install', 'openjdk@25'], capture=False, timeout=1800)
        if not all((p.tools / name).is_file() for name in ('sdkmanager', 'avdmanager')):
            self.run([brew, 'install', '--cask', 'android-commandlinetools'],
                     capture=False, timeout=1800)
        p.sdk.mkdir(parents=True, exist_ok=True)
        sdkmanager = [p.tools / 'sdkmanager', '--sdk_root=' + str(p.sdk)]
        print('Installing emulator packages and accepting their required SDK licenses.', flush=True)
        # avdmanager derives its SDK from its own install location, regardless
        # of ANDROID_HOME. Install a managed copy in the selected SDK root.
        self.run(sdkmanager + ['cmdline-tools;latest', 'platform-tools', 'emulator', IMAGE], env=p.env,
                 input='y\n' * 100, capture=False, timeout=1800)

    def validate_avd(self):
        config = properties(self.paths.avd / 'config.ini')
        expected = 'system-images/android-33/google_apis/arm64-v8a/'
        image = config.get('image.sysdir.1', '').replace('\\', '/')
        if config.get('abi.type') != 'arm64-v8a' or not image.endswith(expected):
            raise SetupError(f'{AVD} has an incompatible image. Its data was preserved; '
                             'choose a different AVD name manually before retrying.')
        size = re.fullmatch(r'(\d+)([KMG]?)', config.get('disk.dataPartition.size', '0'))
        capacity = int(size[1]) * (1024 ** ('KMG'.index(size[2]) + 1) if size[2] else 1) if size else 0
        if capacity < 32 * GIB:
            raise SetupError(f'{AVD} does not have the expected 32 GiB internal storage. '
                             'Its data was preserved; do not wipe it to resize.')

    def create_avd(self):
        p = self.paths
        if p.avd.exists() or (p.avds / (AVD + '.ini')).exists():
            self.validate_avd()
            print('Reusing existing AVD and its saved data.', flush=True)
            return
        p.avds.mkdir(parents=True, exist_ok=True)
        self.run([p.tools / 'avdmanager', 'create', 'avd', '--name', AVD,
                  '--package', IMAGE, '--device', 'pixel_6', '--path', p.avd],
                 env=p.env, input='no\n', timeout=120)
        config = properties(p.avd / 'config.ini')
        config.update({'hw.cpu.ncore': '4', 'hw.ramSize': '4096',
                       'disk.dataPartition.size': '32G', 'hw.gpu.enabled': 'yes',
                       'hw.gpu.mode': 'auto', 'hw.keyboard': 'yes',
                       'hw.sdCard': 'no', 'showDeviceFrame': 'no'})
        (p.avd / 'config.ini').write_text(''.join(f'{k}={v}\n' for k, v in sorted(config.items())))
        self.validate_avd()

    def target(self):
        """Read each emulator's AVD identity; never select a physical device."""
        output = self.run([self.paths.adb, 'devices'], env=self.paths.env)
        matches = []
        for line in output.splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[0].startswith('emulator-') and fields[1] == 'device':
                serial = fields[0]
                try:
                    name = self.run([self.paths.adb, '-s', serial, 'emu', 'avd', 'name'],
                                    env=self.paths.env, timeout=10).splitlines()[0]
                except (SetupError, subprocess.TimeoutExpired, IndexError):
                    continue
                if name == AVD:
                    matches.append(serial)
        if len(matches) > 1:
            raise SetupError(f'Multiple instances of {AVD} are running; close duplicates first.')
        return matches[0] if matches else None

    def adb(self, serial, *args, timeout=60):
        return self.run([self.paths.adb, '-s', serial, *args], env=self.paths.env, timeout=timeout)

    def boot(self, *, headless=False):
        p = self.paths
        if not p.emulator.is_file() or not p.adb.is_file():
            raise SetupError('Android tools are missing. Run the setup command first.')
        self.validate_avd()
        serial = self.target()
        process = None
        if not serial:
            self.run([p.emulator, '-accel-check'], env=p.env)
            # Reserve an unused console/adb port pair; the controller lock prevents
            # two simultaneous launches of our AVD, while adb verifies ownership.
            port = None
            for candidate in range(5554, 5682, 2):
                try:
                    with socket.socket() as console, socket.socket() as bridge:
                        console.bind(('127.0.0.1', candidate))
                        bridge.bind(('127.0.0.1', candidate + 1))
                    port = candidate
                    break
                except OSError:
                    continue
            if port is None:
                raise SetupError('No free Android emulator port pair is available.')
            p.logs.mkdir(parents=True, exist_ok=True)
            with (p.logs / 'emulator.log').open('a') as log:
                process = subprocess.Popen([str(p.emulator), '-avd', AVD, '-port', str(port),
                                            '-gpu', 'auto', '-no-snapshot',
                                            *(['-no-window'] if headless else [])], env=p.env,
                                           stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                           start_new_session=True)
            print(f'Starting {AVD}; log: {p.logs / "emulator.log"}', flush=True)
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            if process is not None and process.poll() is not None:
                raise SetupError(f'Emulator exited. See {p.logs / "emulator.log"}')
            serial = self.target()
            if serial and self.adb(serial, 'shell', 'getprop', 'sys.boot_completed', timeout=10) == '1':
                if self.adb(serial, 'shell', 'getprop', 'ro.product.cpu.abi') != 'arm64-v8a':
                    raise SetupError('Unexpected emulator CPU architecture.')
                if self.adb(serial, 'shell', 'getprop', 'ro.build.version.sdk') != '33':
                    raise SetupError('Unexpected Android API level.')
                return serial
            time.sleep(2)
        raise SetupError(f'Android did not become ready within five minutes. See {p.logs / "emulator.log"}')

    def fetch_apk(self, manifest):
        self.paths.cache.mkdir(parents=True, exist_ok=True)
        target = self.paths.cache / ('exvius-offline-v' + manifest['version'] + '.apk')

        def valid(path):
            if not path.is_file() or path.stat().st_size != manifest['size']:
                return False
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
            return digest.hexdigest() == manifest['sha256']

        if valid(target):
            return target
        partial = target.with_suffix('.apk.part')
        print(f'Downloading verified Exvius APK v{manifest["version"]}...', flush=True)
        try:
            with urllib.request.urlopen(manifest['url'], timeout=60) as response, partial.open('wb') as out:
                shutil.copyfileobj(response, out, length=1024 * 1024)
            if not valid(partial):
                raise SetupError('APK size or SHA-256 mismatch. Nothing was installed.')
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)
        return target

    def install(self, serial, apk, manifest):
        installed = self.adb(serial, 'shell', 'dumpsys', 'package', PACKAGE)
        match = re.search(r'\bversionCode=(\d+)', installed)
        if match and int(match.group(1)) >= manifest['versionCode']:
            print('The requested APK or a newer version is already installed; keeping it.', flush=True)
            return
        try:
            output = self.adb(serial, 'install', '-r', str(apk), timeout=300)
            if 'Success' not in output:
                raise SetupError(output)
        except SetupError as error:
            raise SetupError(f'APK installation failed; existing app data was preserved. '
                             f'Do not uninstall to fix a signing mismatch. {error}') from error

    def setup(self):
        self.require_host()
        with self.lock():
            if shutil.disk_usage(self.paths.home).free < 40 * GIB:
                raise SetupError('Allow 40 GiB free host storage for Android, game data, and working space.')
            self.bootstrap()
            self.create_avd()
            manifest = json.loads((ROOT / 'release/app.json').read_text())
            apk = self.fetch_apk(manifest)
            serial = self.boot()
            space = self.adb(serial, 'shell', 'df', '-k', '/data').splitlines()[-1].split()
            if int(space[3]) * 1024 < 18_000_000_000:
                # Completed installations already occupy this space; reruns remain safe.
                if 'versionCode=' not in self.adb(serial, 'shell', 'dumpsys', 'package', PACKAGE):
                    raise SetupError('Android needs at least 18 GB free internal storage for first setup.')
            self.install(serial, apk, manifest)
            print('Setup complete. Double-click Play Exvius.command to open the game.', flush=True)

    def launch(self):
        self.require_host()
        with self.lock():
            serial = self.boot()
            if 'headless' in self.adb(serial, 'emu', 'avd', 'windowtype'):
                raise SetupError('Android is running headless. Use browser mode, or stop then launch for a visible window.')
            if 'versionCode=' not in self.adb(serial, 'shell', 'dumpsys', 'package', PACKAGE):
                raise SetupError('Exvius is not installed. Run the setup command first.')
            output = self.adb(serial, 'shell', 'am', 'start', '-W', '-n', ACTIVITY)
            if 'Error:' in output or 'Status: timeout' in output:
                raise SetupError(output)
            print('Exvius is open. First launch downloads about 14.65 GB; keep the Mac awake.\n'
                  'Close the emulator window to stop it. Saved data persists between launches.')

    def stop(self):
        self.require_host()
        if not self.paths.adb.is_file():
            print('The emulator is not installed.')
            return
        with self.lock():
            from browser_launcher import BrowserLauncher
            BrowserLauncher(self).stop()
            serial = self.target()
            if serial:
                self.adb(serial, 'emu', 'kill')
                print('Emulator shutdown requested; saved data is retained.')
            else:
                print('The Exvius emulator is already stopped.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('doctor', 'setup', 'launch', 'stop', 'setup-browser', 'browser', 'browser-status', 'browser-stop'))
    parser.add_argument('--sdk-root', type=Path, default=Path.home() / 'Library/Android/sdk')
    parser.add_argument('--lan', action='store_true', help='Enable browser access on the home network')
    parser.add_argument('--lan-address', help='Private LAN IPv4 address (implies --lan)')
    parser.add_argument('--port', type=int, default=8443)
    parser.add_argument('--browser', action='store_true', help='Include browser prerequisite checks in doctor')
    parser.add_argument('--no-open', action='store_true', help='Print browser addresses without opening a tab')
    args = parser.parse_args(argv)
    controller = Emulator(Locations(Path.home(), args.sdk_root.expanduser().resolve()))
    try:
        from browser_launcher import BrowserLauncher
        browser = BrowserLauncher(controller)
        lan = args.lan or bool(args.lan_address)
        if args.command == 'setup-browser':
            with controller.lock():
                browser.setup(lan, args.lan_address)
            outcome = True
        elif args.command == 'browser':
            outcome = browser.launch(lan, args.lan_address, args.port, not args.no_open)
        elif args.command == 'browser-status':
            status = browser.query()
            print(json.dumps({k: v for k, v in (status or {'phase': 'stopped'}).items() if k != 'code'}, indent=2))
            outcome = True
        elif args.command == 'browser-stop':
            with controller.lock():
                browser.stop()
            print('Browser streaming stopped. Android and its save are retained.')
            outcome = True
        else:
            outcome = getattr(controller, args.command)()
            if args.command == 'doctor' and args.browser:
                outcome = browser.doctor() and outcome
        return 1 if outcome is False else 0
    except (SetupError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'Exvius: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
