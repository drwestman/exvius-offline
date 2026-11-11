"""BDD for prepared native gameplay transport and its shared runtime lease."""
import http.client
import io
import json
import os
from pathlib import Path
import socket
import ssl
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SOURCE), str(SOURCE / 'server')]

from ios_server.certificates import CertificateStore
from ios_server.config import Configuration
from ios_server.game_http import handler, MAX_BODY
from ios_server.hosting import Gameplay
from ios_server.http import PublicHandler
from ios_server.network import Network
from ios_server.request_retention import prune
from ios_server.runtime import InstanceLock, instance_busy, read_service
from ios_server.service import Service


class Application:
    def __init__(self, config):
        self.config = config
        self.started = self.closed = False
        self.closed_event = threading.Event()
        self.calls = []
        self.entered = threading.Event()
        self.release = threading.Event(); self.release.set()
        owner = self
        class Base(PublicHandler):
            def do_GET(self):
                owner.calls.append(self.path)
                owner.entered.set(); owner.release.wait(5)
                self.send_body(200, b'canonical content', 'application/octet-stream')
            do_HEAD = do_GET
            def do_POST(self):
                owner.calls.append(self.rfile.read(int(self.headers['Content-Length'])))
                self.send_body(200, b'canonical reply', 'application/json')
        self.handler = handler(Base)

    def configuration(self):
        return {'data': str(self.config.data), 'content': str(self.config.content_root), 'slot': self.config.slot}

    def start(self, lease):
        assert lease.root == self.config.root and instance_busy(self.config.root)
        self.started = True
        return self.handler

    def describe(self): return {'slot': self.config.slot}
    def maintain(self): pass
    def close(self):
        self.closed = True
        self.closed_event.set()


class GameplayLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.certificates = tempfile.TemporaryDirectory(prefix='ios-game-certs-')
        cls.addClassCleanup(cls.certificates.cleanup)
        CertificateStore(Path(cls.certificates.name)).prepare()

    def setUp(self):
        import shutil
        temp = tempfile.TemporaryDirectory(prefix='ios-game-wire-'); self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.config = Configuration(self.base / 'private', self.base / 'content')
        shutil.copytree(Path(self.certificates.name) / 'certs', self.config.root / 'certs')
        self.network = Network('192.168.86.40', '192.168.86.0/24', '192.168.86.1',
                               bind='127.0.0.1', dns_port=0, http_port=0, https_port=0)
        self.application = Application(self.config)
        self.service = Service(self.config.root, self.network, application=self.application)
        self.addCleanup(self.service.close)

    def request(self, path, method='GET', body=None):
        peer = http.client.HTTPConnection('127.0.0.1', self.service.ports['http'], timeout=3)
        try:
            peer.request(method, path, body)
            reply = peer.getresponse()
            return reply.status, reply.read(), dict(reply.getheaders())
        finally:
            peer.close()

    def test_given_prepared_application_when_started_then_serve_public_and_canonical_routes_with_one_lease(self):
        self.service.start()
        report = read_service(self.config.root)
        self.assertTrue(report['ready']); self.assertEqual(report['mode'], 'gameplay')
        self.assertEqual(report['configuration']['gameplay']['slot'], self.config.slot)
        self.assertTrue(self.application.started)
        with self.assertRaises(RuntimeError), InstanceLock(self.config.root): pass
        self.assertEqual(self.request('/native/resource')[1], b'canonical content')
        self.assertEqual(self.request('/native/resource', 'HEAD')[1], b'')
        self.assertEqual(self.request('/actionSymbol/test.php', 'POST', b'fixture')[1], b'canonical reply')
        self.assertEqual(self.application.calls[-1], b'fixture')
        for path in ('/', '/ca.mobileconfig', '/__exvius/hello'):
            self.assertEqual(self.request(path)[0], 200)
        before = list(self.application.calls)
        for path in ('/__exvius/status', '/__exvius/new-game', '/%5f_exvius/status'):
            self.assertEqual(self.request(path)[0], 404)
            self.assertEqual(self.request(path, 'POST', b'{}')[0], 404)
        self.assertEqual(self.application.calls, before)

    def test_given_uninitialized_campaign_when_started_then_refuse_without_engine_imports_and_unlock(self):
        self.service.application = Gameplay(self.config)
        before = set(sys.modules)
        with self.assertRaisesRegex(ValueError, 'init-campaign'):
            self.service.start()
        self.assertFalse(self.service.snapshot()['ready'])
        self.assertFalse(self.config.state_file.exists())
        self.assertIsNone(read_service(self.config.root))
        self.assertFalse({'capture_server', 'data_paths', 'player_state'} & (set(sys.modules) - before))
        with InstanceLock(self.config.root): pass

    def test_given_occupied_port_when_started_then_never_initialize_application(self):
        from dataclasses import replace
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0)); occupied.listen()
            self.service.network = replace(self.network, https_port=occupied.getsockname()[1])
            with self.assertRaisesRegex(OSError, 'HTTPS'): self.service.start()
        self.assertFalse(self.application.started)
        self.assertFalse(instance_busy(self.config.root))

    def test_given_application_failure_when_started_then_close_all_listeners_and_application(self):
        with patch.object(self.application, 'start', side_effect=ValueError('fixture failed')):
            with self.assertRaisesRegex(ValueError, 'fixture failed'): self.service.start()
        self.assertTrue(self.application.closed)
        self.assertFalse(self.service.listeners); self.assertFalse(instance_busy(self.config.root))
        self.assertIsNone(read_service(self.config.root))

    def test_given_bound_control_while_engine_starts_when_status_runs_then_report_not_ready_without_timeout_error(self):
        entered, release = threading.Event(), threading.Event()
        original = self.application.start
        def delayed(lease):
            entered.set(); release.wait(8)
            return original(lease)
        results = []
        with patch.object(self.application, 'start', side_effect=delayed):
            starting = threading.Thread(target=lambda: results.append(self.service.start()))
            starting.start()
            try:
                self.assertTrue(entered.wait(2))
                self.assertIsNone(read_service(self.config.root))
                self.assertTrue(instance_busy(self.config.root)); self.assertFalse(self.service.ready)
                self.assertIsNone(read_service(self.config.root, stop=True))
            finally:
                release.set(); starting.join(5)
        self.assertFalse(starting.is_alive()); self.assertTrue(results[0]['ready'])
        self.assertTrue(self.service.stop_event.wait(2))

    def test_given_active_request_when_stopping_then_drain_before_application_close_and_lease_release(self):
        self.service.start(); self.application.release.clear()
        results = []
        request = threading.Thread(target=lambda: results.append(self.request('/slow')))
        request.start(); self.assertTrue(self.application.entered.wait(2))
        closing = threading.Thread(target=self.service.close); closing.start()
        try:
            self.assertTrue(instance_busy(self.config.root))
            self.assertFalse(self.application.closed_event.wait(.2))
            self.application.release.set()
            request.join(3); closing.join(3)
            self.assertFalse(request.is_alive()); self.assertFalse(closing.is_alive())
            self.assertEqual(results[0][1], b'canonical content')
            self.assertTrue(self.application.closed); self.assertFalse(instance_busy(self.config.root))
        finally:
            self.application.release.set(); request.join(5); closing.join(5)

    def test_given_first_listener_drain_blocks_when_stopping_then_stop_all_accepts_first(self):
        self.service.start()
        listeners = list(self.service.listeners)
        https = next(row.server for row in listeners if row.name == 'HTTPS')
        entered, release = threading.Event(), threading.Event()
        original = https.server_close
        def draining():
            entered.set(); release.wait(5); original()
        with patch.object(https, 'server_close', side_effect=draining):
            closing = threading.Thread(target=self.service.close); closing.start()
            try:
                self.assertTrue(entered.wait(2))
                self.assertTrue(all(not row.thread.is_alive() for row in listeners))
                self.assertTrue(instance_busy(self.config.root)); self.assertFalse(self.application.closed)
            finally:
                release.set(); closing.join(5)
        self.assertFalse(closing.is_alive())

    def test_given_same_or_different_mode_data_or_slot_when_repeated_then_reuse_only_matching_gameplay(self):
        from contextlib import redirect_stdout
        from ios_server.cli import main
        self.service.start()
        options = ['--root', str(self.config.root), '--data', str(self.config.data)]
        for args, code in ((['start', *options], 0), (['serve', *options], 1),
                           (['start', *options, '--slot', 'other'], 1),
                           (['start', *options, '--data', str(self.base / 'other')], 1)):
            with self.subTest(args=args), patch('ios_server.network.discover', return_value=self.network), redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(args), code)
                self.assertEqual('error' in json.loads(output.getvalue()), bool(code))

    def test_given_invalid_body_framing_when_posted_then_reject_before_canonical_dispatch(self):
        self.service.start()
        cases = [('Content-Length: -1', 400), ('Content-Length: 1\r\nContent-Length: 1', 400),
                 ('Transfer-Encoding: chunked', 400), ('', 400),
                 (f'Content-Length: {MAX_BODY + 1}', 413),
                 (f'Content-Length: {MAX_BODY + 1}\r\nExpect: 100-continue', 413)]
        for headers, expected in cases:
            with self.subTest(headers=headers), socket.create_connection(('127.0.0.1', self.service.ports['http']), timeout=3) as peer:
                peer.sendall(('POST /actionSymbol/test.php HTTP/1.1\r\nHost: fixture\r\n' + headers + '\r\n\r\n').encode())
                response = http.client.HTTPResponse(peer); response.begin()
                self.assertEqual(response.status, expected); response.read()
        self.assertFalse(self.application.calls)

    def test_given_start_from_system_python_when_dispatched_then_use_isolated_runtime_and_emit_json(self):
        import subprocess
        before = {p: p.read_bytes() for p in self.config.root.rglob('*') if p.is_file()}
        result = subprocess.run(['/usr/bin/python3', '-B', str(SOURCE / 'exvius/macos_ios_server.py'),
                                 'start', '--root', str(self.config.root), '--data', str(self.config.data),
                                 '--dns-port', '0'], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Choose listener ports', json.loads(result.stdout)['error'])
        self.assertEqual(before, {p: p.read_bytes() for p in before})


class RequestRetention(unittest.TestCase):
    def test_given_old_and_oversize_records_when_maintained_then_bound_only_owned_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); folder = root / 'requests'; folder.mkdir()
            for i, modified in enumerate((10, 20, 30), 1):
                file = folder / f'20261111T120000_{i:04d}.json'; file.write_bytes(b'x' * 10)
                os.utime(file, (modified, modified))
            (folder / 'keep.json').write_bytes(b'keep')
            outside = root / 'outside'; outside.write_bytes(b'private')
            (folder / '20261111T120000_0004.json').symlink_to(outside)
            result = prune(root, now=40, max_age=25, max_bytes=10)
            self.assertEqual(result, {'removed': 2, 'bytes': 10})
            self.assertTrue((folder / '20261111T120000_0003.json').exists())
            self.assertEqual(outside.read_bytes(), b'private'); self.assertEqual((folder / 'keep.json').read_bytes(), b'keep')

    def test_given_missing_directory_when_maintained_then_create_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.assertEqual(prune(root), {'removed': 0, 'bytes': 0})
            self.assertFalse(list(root.iterdir()))


import test_ios_preparation as native_fixture
import test_ios_server as engine_fixture
import test_ios_sound_delivery as sound_fixture
import test_ios_vortex_art as art_fixture
from ios_server import preparation, native_tables, sound_snapshots, banner_snapshots, home_banners, banner_inputs


class NativeGameplayWire(unittest.TestCase):
    setUp = native_fixture.NativePreparation.setUp
    fixture = native_fixture.NativePreparation.fixture
    source = native_fixture.NativePreparation.source
    artwork = art_fixture.VortexPreparation.artwork
    install = sound_fixture.SoundTableDelivery.install
    child = engine_fixture.IosServerBehavior.child

    def test_given_public_cli_data_argument_when_engine_imports_then_keep_private_policy_root(self):
        self.fixture()
        for relative in ('mst_decoded', 'text_decoded', 'cpk_extract', 'client/files/common_lang'):
            (self.config.data / relative).mkdir(parents=True, exist_ok=True)
        engine_fixture.IosServerBehavior.write_masters(self, self.config.data / 'mst_decoded')
        done = self.child('''
import sys
from pathlib import Path
sys.path[:0]=sys.argv[1:3]
from ios_server.config import Configuration
from ios_server.engine import Engine
config=Configuration(Path(sys.argv[3]),Path(sys.argv[4]))
sys.argv=['macos_ios_server.py','init-campaign','--root',str(config.root),'--data',str(config.data)]
engine=Engine(config)
try:
    engine.initialize()
    import data_paths
    assert data_paths.DATA_ROOT==str(config.root),(data_paths.DATA_ROOT,config.root)
finally:engine.close()
''', str(self.config.root), str(self.config.data))
        self.assertEqual(done.returncode, 0, done.stdout[-1000:] + done.stderr)

    def prepare(self, managed=False):
        self.artwork(managed); self.install()
        static = self.config.data / 'static' if managed else self.config.data
        for relative in ('mst_decoded', 'text_decoded', 'cpk_extract'):
            (static / relative).mkdir(parents=True, exist_ok=True)
        engine_fixture.IosServerBehavior.write_masters(self, static / 'mst_decoded')
        done = self.child('''
import sys
from pathlib import Path
sys.path[:0]=sys.argv[1:3]
from ios_server.config import Configuration
from ios_server.engine import Engine
engine=Engine(Configuration(Path(sys.argv[3]),Path(sys.argv[4])))
try:engine.initialize_campaign()
finally:engine.close()
''', str(self.config.root), str(self.config.data))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        documents = json.loads((home_banners.HERE / 'event_art.json').read_bytes())
        self.area_id, row = next(iter(documents['events'].items()))
        (self.area / row['filename']).write_bytes(art_fixture.png())
        art = static / 'cpk_extract/en/banner'; art.mkdir(parents=True)
        (art / banner_inputs.DEFAULT).write_bytes(art_fixture.png())
        sound_snapshots.prepare(self.config)
        banner_snapshots.prepare(self.config); home_banners.prepare(self.config)
        preparation.prepare_data(self.config, vortex_art=True, sounds=True)
        self.pack = preparation.load_prepared(self.config)
        CertificateStore(self.config.root).prepare()
        self.process = None
        self.addCleanup(self.stop)

    def start(self):
        import subprocess
        script = '''
import sys
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=sys.argv[1:3]
from ios_server import vortex_art
vortex_art.HERE=Path(sys.argv[5])
from ios_server.cli import main
from ios_server.network import Network
network=Network('192.168.86.40','192.168.86.0/24','192.168.86.1',bind='127.0.0.1',dns_port=0,http_port=0,https_port=0)
with patch('ios_server.network.discover',return_value=network):
    raise SystemExit(main(['start','--root',sys.argv[3],'--data',sys.argv[4]]))
'''
        self.errors = self.root / 'gameplay-stderr.log'
        with self.errors.open('wb') as error:
            self.process = subprocess.Popen([sys.executable, '-B', '-c', script, str(SOURCE), str(SOURCE / 'server'),
                                             str(self.config.root), str(self.config.data), str(self.docs)],
                                            stdout=subprocess.PIPE, stderr=error, text=True)
        deadline = time.monotonic() + 15
        while True:
            report = read_service(self.config.root)
            if report is not None:
                self.assertTrue(report['ready']); self.assertEqual(report['mode'], 'gameplay')
                self.report = report
                return
            if self.process.poll() is not None or time.monotonic() >= deadline:
                self.fail('Gameplay did not become ready: ' + self.errors.read_text()[-5000:])
            time.sleep(.025)

    def stop(self):
        if self.process is None: return
        try:
            if self.process.poll() is None:
                read_service(self.config.root, stop=True)
            output, _ = self.process.communicate(timeout=8)
            self.assertEqual(self.process.returncode, 0, self.errors.read_text()[-5000:])
            self.assertTrue(json.loads(output)['ready'])  # exactly one document despite request diagnostics
            self.assertFalse(instance_busy(self.config.root)); self.assertIsNone(read_service(self.config.root))
        finally:
            if self.process.poll() is None:
                self.process.kill(); self.process.communicate(timeout=3)
            self.process = None

    def request(self, path, method='GET', body=b'', *, secure=False):
        from ios_server.certificates import HELLO_HOST
        raw = socket.create_connection(('127.0.0.1', self.report['ports']['https' if secure else 'http']), timeout=5)
        context = ssl.create_default_context(cafile=str(self.config.root / 'certs/ca.pem'))
        peer = context.wrap_socket(raw, server_hostname=HELLO_HOST) if secure else raw
        try:
            request = f'{method} {path} HTTP/1.1\r\nHost: {HELLO_HOST}\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'
            peer.sendall(request.encode() + body)
            response = http.client.HTTPResponse(peer, method=method); response.begin()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            peer.close()

    def initialize(self):
        import ffbe_crypto as crypto
        endpoint = json.loads((SOURCE / 'server/endpoints.json').read_bytes())['by_class']['InitializeRequest']
        key = crypto.key16(endpoint['encode_key'])
        envelope = {'TEAYk6R1': {'z5hB3P01': endpoint['request_id'], 'ytHoz4E2': '1', '9K0Pzcpd': '1167'},
                    't7n6cVWf': {'qrVcDe48': crypto.cbc_encrypt(key, b'{}', double_pad=True)}}
        code, raw, _ = self.request(endpoint['url'], 'POST', json.dumps(envelope).encode(), secure=True)
        self.assertEqual(code, 200, raw[:200])
        return json.JSONDecoder().raw_decode(crypto.cbc_decrypt(key, json.loads(raw)['t7n6cVWf']['qrVcDe48']).decode())[0]

    def test_given_real_prepared_engine_when_tls_initializes_then_deliver_every_advertised_table_and_bound_asset(self):
        self.prepare(); self.start()
        initialized = self.initialize()
        versions = {row['a4hXTIm0']: int(row['wM9AfX6I']) for row in initialized['c1qYg84Q']}
        self.assertEqual(len(versions), 364)
        saved = self.config.state_file.read_bytes()
        shared = {p: p.read_bytes() for p in self.config.data.rglob('*') if p.is_file()}
        expected = {entry['path']: self.pack.lookup(entry['path']) for entry in self.pack.manifest['tables'].values()}
        expected.update({entry['path']: self.pack.lookup(entry['path']) for entry in self.pack.manifest['packs'].values()})
        expected.update({entry['path']: self.pack.sounds.read(entry['path']) for entry in self.pack.manifest['sounds']['banks'].values()})
        for name, version in versions.items():
            self.assertIn(native_tables.BY_NAME[name].path(version), expected)
        home = home_banners.current(self.config)
        home_path = home.image(self.area_id)['url']
        expected[home_path] = home.lookup(home_path)
        banners = banner_snapshots.current(self.config)
        for row in banners.manifest['images'].values():
            path = banner_inputs.DETAIL_URL + '/' + Path(row['path']).name
            expected[path] = banners.lookup(path)
        for path, raw in expected.items():
            self.assertIsNotNone(raw, path)
            for method in ('GET', 'HEAD'):
                code, body, headers = self.request('/' + path, method)
                self.assertEqual(code, 200, path)
                self.assertEqual(body, raw if method == 'GET' else b'', path)
                self.assertEqual(int(headers['Content-Length']), len(raw), path)
        self.assertIn(b'You can open the game', self.request('/__exvius/hello', secure=True)[1])
        for path in ('/certs/identity.json', '/%2e%2e/state/campaign.json', '/__exvius/status',
                     '/mst/Ver1_unknown0.dat', '/common_lang/sound/se/ios/Ver1_System.acb'):
            self.assertIn(self.request(path)[0], (400, 404), path)
        sound_path, source = next(iter(self.pack.sounds.files.items()))
        bank = self.pack.sounds.snapshot.directory / self.pack.sounds.snapshot.manifest['banks'][source]['path']
        original = bank.read_bytes()
        try:
            bank.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
            for method in ('GET', 'HEAD'):
                code, body, headers = self.request('/' + sound_path, method, secure=True)
                self.assertEqual((code, body, headers['Content-Length']), (500, b'', '0'))
        finally:
            bank.write_bytes(original)
        self.assertEqual(self.config.state_file.read_bytes(), saved)
        self.assertEqual(shared, {p: p.read_bytes() for p in shared})
        self.stop()

    def test_given_initialized_campaign_when_host_restarts_then_preserve_replay_and_private_save(self):
        self.prepare()
        before = json.loads(self.config.state_file.read_bytes())['ios_revival']
        for _ in range(2):
            self.start(); self.initialize(); self.stop()
            self.assertEqual(json.loads(self.config.state_file.read_bytes())['ios_revival'], before)

    def test_given_managed_layout_when_hosted_then_serve_native_tables_and_sound_through_tls(self):
        self.prepare(managed=True); self.start()
        self.assertEqual(len(self.initialize()['c1qYg84Q']), 364)
        row = next(iter(self.pack.manifest['tables'].values()))
        self.assertEqual(self.request('/' + row['path'], secure=True)[1], self.pack.lookup(row['path']))
        row = next(iter(self.pack.manifest['sounds']['banks'].values()))
        self.assertEqual(self.request('/' + row['path'], secure=True)[1], self.pack.sounds.read(row['path']))
        self.stop()

    def test_given_missing_coordinated_features_when_preflight_runs_then_refuse_without_state_import_or_writes(self):
        self.prepare()
        pointer = self.config.root / home_banners.POINTER
        pointer.unlink()
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        modules = set(sys.modules)
        with self.assertRaisesRegex(ValueError, 'prepare-home-banners'):
            Gameplay(self.config).preflight()
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.assertFalse({'capture_server', 'data_paths', 'player_state'} & (set(sys.modules) - modules))


if __name__ == '__main__': unittest.main()
