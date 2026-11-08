"""Browser-mode lifecycle. Android and gameplay state remain owned by the existing AVD."""
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import ssl
import subprocess
import time
import urllib.request
import webbrowser

BRIDGE = Path(__file__).resolve().parents[1] / 'browser_bridge'
MANIFEST = json.loads((BRIDGE / 'server-manifest.json').read_text())


def private_address(value):
    ip = ipaddress.IPv4Address(value)
    if not ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast:
        raise ValueError('Choose a private IPv4 address on your home network.')
    return str(ip)


def addresses(lan=False, explicit=None):
    hosts, names = ['127.0.0.1'], ['localhost', '127.0.0.1']
    if lan:
        if explicit:
            ip = private_address(explicit)
        else:
            route = subprocess.run(['/sbin/route', '-n', 'get', 'default'], text=True, capture_output=True, check=True)
            interface = re.search(r'interface:\s*(\S+)', route.stdout)
            if not interface:
                raise ValueError('Cannot find the LAN interface. Specify --lan-address.')
            ip = private_address(subprocess.run(['/usr/sbin/ipconfig', 'getifaddr', interface[1]],
                                              text=True, capture_output=True, check=True).stdout.strip())
        hosts.append(ip)
        names.append(ip)
        hostname = socket.gethostname().lower()
        if re.fullmatch(r'[A-Za-z0-9-]+(?:\.local)?', hostname):
            names.append(hostname if hostname.endswith('.local') else hostname + '.local')
    return hosts, names


class UnixHTTP(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__('localhost', timeout=3)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(str(self.path))


class BrowserLauncher:
    def __init__(self, emulator):
        self.emulator = emulator
        self.paths = emulator.paths
        self.root = self.paths.cache / 'browser'
        identity = hashlib.sha256(str(self.root).encode()).hexdigest()[:12]
        self.ipc = Path('/private/tmp') / f'exvius-browser-{os.getuid()}-{identity}' / 'bridge.sock'

    def query(self, stop=False):
        """Read bridge status without starting adb, Android, or a bridge."""
        if not self.ipc.exists():
            return None
        if self.ipc.parent.is_symlink() or self.ipc.parent.stat().st_uid != os.getuid() or self.ipc.parent.stat().st_mode & 0o077:
            raise ValueError('Browser control directory must be private and owned by this user.')
        connection = UnixHTTP(self.ipc)
        try:
            connection.request('POST' if stop else 'GET', '/stop' if stop else '/status')
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError('Unexpected browser bridge response.')
            result = json.loads(response.read())
            if not stop and result.get('sdk') != str(self.paths.sdk):
                raise ValueError('Browser bridge uses a different SDK root.')
            return result
        except (FileNotFoundError, ConnectionRefusedError):
            return None
        finally:
            connection.close()

    def stop(self):
        # Verify ownership before issuing a command through the private socket.
        if self.query() is None:
            return
        self.query(stop=True)
        for _ in range(50):
            if self.query() is None:
                return
            time.sleep(.1)
        raise ValueError('Browser bridge has not stopped yet; retry before stopping Android.')

    def doctor(self):
        checks = {
            'Node.js': shutil.which('node') is not None,
            'Browser bridge build': (BRIDGE / 'dist/main.js').is_file(),
            'Locked dependencies': (BRIDGE / 'node_modules/@yume-chan/adb-scrcpy/package.json').is_file(),
            'Local certificate': (self.root / 'cert.pem').is_file(),
            'Local certificate key': (self.root / 'key.pem').is_file(),
            'Verified scrcpy server': self.valid_server(),
        }
        for label, present in checks.items():
            print(f'{"OK     " if present else "MISSING"} {label}')
        return all(checks.values())

    def valid_server(self):
        path = self.root / 'scrcpy-server.jar'
        return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == MANIFEST['sha256']

    def setup(self, lan=False, address=None):
        self.emulator.require_host()
        _, names = addresses(lan, address)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        run = self.emulator.run
        brew = '/opt/homebrew/bin/brew'
        if not shutil.which('node') or not shutil.which('npm'):
            run([brew, 'install', 'node'], capture=False, timeout=1800)
        if not shutil.which('mkcert'):
            run([brew, 'install', 'mkcert'], capture=False, timeout=1800)
        run(['npm', 'ci', '--prefix', BRIDGE], capture=False, timeout=600)
        run(['npm', 'run', 'build', '--prefix', BRIDGE], capture=False, timeout=120)
        # A project-specific CA: never alter the Android trust store or global mkcert CA.
        cert_env = dict(os.environ, CAROOT=str(self.root / 'ca'), TRUST_STORES='system')
        run(['mkcert', '-cert-file', self.root / 'cert.pem', '-key-file', self.root / 'key.pem', *names],
            env=cert_env, capture=False, timeout=60)
        (self.root / 'key.pem').chmod(0o600)
        (self.root / 'certificate.json').write_text(json.dumps({'names': names}))
        if not self.valid_server():
            partial = self.root / 'scrcpy-server.part'
            try:
                with urllib.request.urlopen(MANIFEST['url'], timeout=60) as response:
                    data = response.read(2_000_000)
                if hashlib.sha256(data).hexdigest() != MANIFEST['sha256']:
                    raise ValueError('Scrcpy server checksum mismatch; nothing was installed.')
                partial.write_bytes(data)
                partial.replace(self.root / 'scrcpy-server.jar')
            finally:
                partial.unlink(missing_ok=True)
        try:
            # Capture diagnostics so a macOS authorization denial can be identified.
            run(['mkcert', '-install'], env=cert_env, capture=True, timeout=120)
        except RuntimeError as error:
            detail = str(error)
            no_dialog = ('SecTrustSettingsSetTrustSettings' in detail
                         and 'no user interaction was possible' in detail)
            no_terminal = 'sudo: a terminal is required to read the password' in detail
            if not (no_dialog or no_terminal):
                raise
            print('Browser files prepared. Mac CA trust is pending.\n'
                  'macOS could not request trust authorization in this session.\n'
                  'On the Mac, open Keychain Access and import this PUBLIC CA certificate\n'
                  f'into the System keychain: {self.root / "ca/rootCA.pem"}\n'
                  'Double-click that certificate, expand Trust, set "When using this\n'
                  'certificate" to "Always Trust", then close it and approve the change.\n'
                  'After approving trust, run browser --lan. No setup rerun is needed.')
        else:
            print('Browser setup complete. Run browser --lan to play.')
        print(f'Trust this PUBLIC CA certificate on each client: {self.root / "ca/rootCA.pem"}\n'
              'On iPhone/iPad: install its profile, then enable full trust in Settings > General > About > Certificate Trust Settings.\n'
              'Keep rootCA-key.pem and key.pem private.')

    def preflight(self, names):
        if not self.doctor():
            raise ValueError('Run setup-browser --lan first.')
        saved = json.loads((self.root / 'certificate.json').read_text())
        if not set(names).issubset(saved['names']):
            raise ValueError('LAN address changed. Rerun setup-browser --lan (the existing CA is reused).')
        cert = ssl._ssl._test_decode_cert(str(self.root / 'cert.pem'))
        if ssl.cert_time_to_seconds(cert['notAfter']) <= time.time():
            raise ValueError('Certificate expired. Rerun setup-browser --lan.')
        version = self.emulator.run(['node', '--version'])
        if int(version.lstrip('v').split('.')[0]) < 22:
            raise ValueError('Browser mode requires Node.js 22 or newer.')

    def ensure_game_visible(self, serial):
        """Restore the verified device's game task, preserving an active screen."""
        from macos_emulator import PACKAGE, ACTIVITY
        if 'versionCode=' not in self.emulator.adb(serial, 'shell', 'dumpsys', 'package', PACKAGE):
            raise ValueError('Exvius is not installed. Run setup first.')
        activities = self.emulator.adb(serial, 'shell', 'dumpsys', 'activity', 'activities')
        package = re.escape(PACKAGE)
        if re.search(r'(?m)^\s*(?:topResumedActivity|mResumedActivity|ResumedActivity)\s*[:=]'
                     r'[^\n]*\s' + package + r'/', activities):
            return
        tasks = re.findall(r'(?m)^\s*\*\s*Hist\s+#\d+:\s*ActivityRecord\{[^}\n]*\s'
                           + package + r'/[^}\n]*[ \t]+t(\d+)\b[^}\n]*\}', activities)
        if tasks:
            # Resume the existing activity/task instead of launching the downloader again.
            output = self.emulator.adb(serial, 'shell', 'am', 'task', 'focus', tasks[0])
        else:
            # A background process can outlive its activities; it is not proof of visibility.
            output = self.emulator.adb(serial, 'shell', 'am', 'start', '-W',
                                       '-a', 'android.intent.action.MAIN',
                                       '-c', 'android.intent.category.LAUNCHER',
                                       '-f', '0x10000000', '-n', ACTIVITY)
        if 'Error:' in output or 'Status: timeout' in output:
            raise ValueError(output)

    def launch(self, lan=False, address=None, port=8443, open_browser=True):
        self.emulator.require_host()
        if not 1024 <= port <= 65535:
            raise ValueError('Choose a port between 1024 and 65535.')
        hosts, names = addresses(lan, address)
        child = None
        with self.emulator.lock():
            existing = self.query()
            if existing:
                if set(existing['urls']) != {'https://' + n + ':' + str(port) for n in names}:
                    raise ValueError('Browser mode is already running with different addresses/port. Use browser-stop first.')
                serial = self.emulator.target()
                if not serial or serial != existing.get('serial'):
                    raise ValueError('Browser bridge device changed. Use browser-stop, then browser to reconnect.')
                self.ensure_game_visible(serial)
                self.show(existing, open_browser)
                return
            self.preflight(names)
            # Check listener availability before booting Android; never evict another service.
            for host in hosts:
                with socket.socket() as probe:
                    probe.bind((host, port))
            serial = self.emulator.boot(headless=True)
            self.ensure_game_visible(serial)
            self.ipc.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.ipc.unlink(missing_ok=True)  # only a stale socket, under the startup lock
            config = dict(hosts=hosts, names=names, port=port, cert=str(self.root / 'cert.pem'),
                          key=str(self.root / 'key.pem'), ipc=str(self.ipc), serial=serial,
                          serverFile=str(self.root / 'scrcpy-server.jar'), adb=str(self.paths.adb), sdk=str(self.paths.sdk))
            self.paths.logs.mkdir(parents=True, exist_ok=True)
            with (self.paths.logs / 'browser.log').open('a') as log:
                child = subprocess.Popen(['node', str(BRIDGE / 'dist/main.js')], stdin=subprocess.PIPE,
                                         stdout=log, stderr=log, text=True)
            child.stdin.write(json.dumps(config) + '\n')
            child.stdin.flush()
            try:
                for _ in range(100):
                    if child.poll() is not None:
                        raise ValueError(f'Browser bridge failed. See {self.paths.logs / "browser.log"}')
                    ready = self.query()
                    if ready:
                        break
                    time.sleep(.1)
                else:
                    raise ValueError('Browser bridge did not become ready.')
            except BaseException:
                child.stdin.close()
                child.wait(timeout=10)
                raise
        # Do not hold the startup lock for the duration of the session.
        self.show(ready, open_browser)
        print('Keep this terminal open. Ctrl+C stops streaming and leaves Android running.')
        previous = {}
        def interrupted(_signum, _frame):
            raise KeyboardInterrupt
        for sig in (signal.SIGTERM, signal.SIGHUP):
            previous[sig] = signal.signal(sig, interrupted)
        try:
            child.wait()
        except KeyboardInterrupt:
            pass
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            child.stdin.close()  # EOF also cleans up if the launcher itself disappears
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.terminate()
                child.wait(timeout=10)
        if child.returncode:
            raise ValueError(f'Browser bridge exited ({child.returncode}). See browser.log.')

    @staticmethod
    def show(status, open_browser=True):
        print('Browser addresses: ' + ', '.join(status['urls']))
        print('Access code: ' + status['code'])
        if open_browser:
            webbrowser.open(next(url for url in status['urls'] if '127.0.0.1' in url))
