"""BDD for the hello-only iPhone/Mac transport; all saves/certificates are disposable."""
from datetime import datetime, timedelta, timezone
import http.client
import json
from pathlib import Path
import plistlib
import socket
import ssl
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SOURCE), str(SOURCE / 'server')]

from dnslib import A, DNSRecord, QTYPE, RCODE, RR
from ios_server.certificates import CertificateStore, HELLO_HOST
from ios_server.dns import Resolver
from ios_server.network import Network, discover
from ios_server.runtime import InstanceLock, read_service
from ios_server.service import Service

NOW = datetime(2026, 11, 9, tzinfo=timezone.utc)


class NetworkBehavior(unittest.TestCase):
    def test_given_mac_network_when_discovered_then_select_actual_lan_and_upstream(self):
        calls = []
        def read(args):
            calls.append(args)
            if args[0] == '/sbin/ifconfig':
                return ('lo0: flags=UP\n inet 127.0.0.1 netmask 0xff000000\n'
                        'en0: flags=UP\n inet 192.168.86.40 netmask 0xffffff00\n')
            if args[0] == '/sbin/route':
                return 'interface: en0\n'
            return 'resolver #1\n nameserver[0] : 192.168.86.1\n'
        network = discover(read=read)
        self.assertEqual(network.address, '192.168.86.40')
        self.assertEqual(network.subnet, '192.168.86.0/24')
        self.assertEqual(network.upstream, '192.168.86.1')
        self.assertTrue(network.allows('192.168.86.50'))
        self.assertTrue(network.allows('127.0.0.1'))
        self.assertFalse(network.allows('192.168.87.50'))
        self.assertFalse(network.allows('::1'))

    def test_given_local_or_invalid_upstream_when_configured_then_reject_forwarding_loop(self):
        for upstream in ('127.0.0.1', '0.0.0.0', '192.168.86.40', '224.0.0.1', '::1'):
            with self.subTest(upstream=upstream), self.assertRaises(ValueError):
                Network('192.168.86.40', '192.168.86.0/24', upstream)

    def test_given_unconfigured_override_when_discovered_then_reject_wrong_advertised_address(self):
        def read(args):
            return 'en0: flags=UP\n inet 192.168.86.40 netmask 0xffffff00\n'
        with self.assertRaisesRegex(ValueError, 'not configured'):
            discover(address='192.168.86.99', upstream='192.168.86.1', read=read)


class DnsBehavior(unittest.TestCase):
    def setUp(self):
        self.network = Network('192.168.86.40', '192.168.86.0/24', '192.168.86.1')
        self.forwarded = []
        def forward(request, tcp):
            self.forwarded.append((str(request.q.qname), tcp))
            reply = request.reply()
            reply.add_answer(RR(request.q.qname, QTYPE.A, rdata=A('203.0.113.9')))
            return reply
        self.resolver = Resolver(self.network, forward=forward)

    def answer(self, name, kind='A', peer='192.168.86.50', tcp=False):
        return self.resolver.answer(DNSRecord.question(name, kind), peer, tcp)

    def test_given_game_domains_when_queried_then_answer_local_a_and_empty_aaaa(self):
        for name in ('gumi.sg', 'V900-LAPIS.GUMI.SG.', 'exvius.com', 'notice.exvius.com'):
            with self.subTest(name=name):
                reply = self.answer(name)
                self.assertEqual(str(reply.rr[0].rdata), self.network.address)
                self.assertEqual(self.answer(name, 'AAAA').rr, [])
        self.assertEqual(self.forwarded, [])

    def test_given_ordinary_or_suffix_lookalike_domain_when_queried_then_forward(self):
        for tcp in (False, True):
            for name in ('example.com', 'notgumi.sg', 'gumi.sg.evil.example'):
                reply = self.answer(name, tcp=tcp)
                self.assertEqual(str(reply.rr[0].rdata), '203.0.113.9')
        self.assertEqual(len(self.forwarded), 6)

    def test_given_other_subnet_when_queried_then_refuse_without_forwarding(self):
        self.assertEqual(self.answer('example.com', peer='192.168.87.20').header.rcode, RCODE.REFUSED)
        self.assertEqual(self.forwarded, [])

    def test_given_upstream_timeout_when_queried_then_return_servfail(self):
        self.resolver.forward = lambda *_: (_ for _ in ()).throw(TimeoutError('fixture timeout'))
        reply = self.answer('example.com')
        self.assertEqual(reply.header.rcode, RCODE.SERVFAIL)
        self.assertEqual(self.resolver.failures, 1)

    def test_given_mismatched_upstream_response_when_queried_then_return_servfail(self):
        self.resolver.forward = lambda *_: DNSRecord.question('wrong.example').reply()
        self.assertEqual(self.answer('example.com').header.rcode, RCODE.SERVFAIL)


class CertificateBehavior(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.store = CertificateStore(self.root)

    def test_given_unconfigured_store_when_inspected_then_no_writes(self):
        before = list(self.root.iterdir())
        self.assertFalse(self.store.inspect(now=NOW)['ok'])
        self.assertEqual(list(self.root.iterdir()), before)

    def test_given_existing_ca_when_setup_or_leaf_renewal_runs_then_preserve_trust_and_profile_identity(self):
        self.store.prepare(now=NOW)
        identity = self.store.identity.read_bytes()
        profile = self.store.profile.read_bytes()
        leaf = self.store.leaf.read_bytes()
        self.store.prepare(now=NOW + timedelta(days=1))
        self.assertEqual(self.store.identity.read_bytes(), identity)
        self.assertEqual(self.store.profile.read_bytes(), profile)
        self.assertEqual(self.store.leaf.read_bytes(), leaf)
        self.store.prepare(now=NOW + timedelta(days=380))
        self.assertEqual(self.store.identity.read_bytes(), identity)
        self.assertEqual(self.store.profile.read_bytes(), profile)
        self.assertNotEqual(self.store.leaf.read_bytes(), leaf)
        self.assertEqual(self.store.identity.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.store.leaf.stat().st_mode & 0o777, 0o600)
        payload = plistlib.loads(profile)
        self.assertEqual(payload['PayloadContent'][0]['PayloadType'], 'com.apple.security.root')
        self.assertNotIn(b'PRIVATE KEY', profile)

    def test_given_corrupt_identity_when_setup_runs_then_preserve_it_and_fail(self):
        self.store.folder.mkdir()
        self.store.identity.write_bytes(b'broken private identity')
        with self.assertRaises(ValueError):
            self.store.prepare(now=NOW)
        self.assertEqual(self.store.identity.read_bytes(), b'broken private identity')

    def test_given_failed_leaf_install_when_setup_retries_then_keep_the_original_ca(self):
        import os
        replace = os.replace
        def fail_leaf(source, destination):
            if Path(destination) == self.store.leaf:
                raise OSError('fixture write failure')
            return replace(source, destination)
        with patch('ios_server.certificates.os.replace', side_effect=fail_leaf), self.assertRaises(OSError):
            self.store.prepare(now=NOW)
        original = self.store.identity.read_bytes()
        self.assertFalse(list(self.store.folder.glob('.prepare-*')))
        self.store.prepare(now=NOW)
        self.assertEqual(self.store.identity.read_bytes(), original)


class WireBehavior(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.TemporaryDirectory(prefix='ios-wire-')
        cls.addClassCleanup(cls.work.cleanup)
        cls.base = Path(cls.work.name)
        CertificateStore(cls.base).prepare()

    def setUp(self):
        import shutil
        self.work = tempfile.TemporaryDirectory(prefix='ios-wire-')
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        shutil.copytree(self.base / 'certs', self.root / 'certs')
        self.network = Network('192.168.86.40', '192.168.86.0/24', '192.168.86.1',
                               bind='127.0.0.1', dns_port=0, http_port=0, https_port=0)
        def forward(request, tcp):
            reply = request.reply()
            reply.add_answer(RR(request.q.qname, QTYPE.A, rdata=A('203.0.113.9')))
            return reply
        self.service = Service(self.root, self.network, forward=forward)
        self.addCleanup(self.service.close)
        self.modules_before = set(sys.modules)

    def http(self, path, method='GET'):
        connection = http.client.HTTPConnection('127.0.0.1', self.service.ports['http'], timeout=3)
        self.addCleanup(connection.close)
        connection.request(method, path)
        response = connection.getresponse()
        return response.status, response.read(), response.getheaders()

    def https(self, context=None):
        context = context or ssl.create_default_context(cafile=str(self.root / 'certs/ca.pem'))
        raw = socket.create_connection(('127.0.0.1', self.service.ports['https']), timeout=3)
        try:
            with context.wrap_socket(raw, server_hostname=HELLO_HOST) as connection:
                connection.sendall(b'GET /__exvius/hello HTTP/1.0\r\nHost: v900-lapis.gumi.sg\r\n\r\n')
                response = http.client.HTTPResponse(connection)
                response.begin()
                return response.status, response.read()
        finally:
            raw.close()

    def test_given_all_listeners_started_when_dns_http_tls_and_control_are_used_then_connectivity_works(self):
        self.service.start()
        self.assertTrue(self.service.snapshot()['ready'])
        for tcp in (False, True):
            reply = DNSRecord.parse(DNSRecord.question(HELLO_HOST).send(
                '127.0.0.1', self.service.ports['dns'], tcp=tcp, timeout=3))
            self.assertEqual(str(reply.rr[0].rdata), self.network.address)
            ordinary = DNSRecord.parse(DNSRecord.question('example.com').send(
                '127.0.0.1', self.service.ports['dns'], tcp=tcp, timeout=3))
            self.assertEqual(str(ordinary.rr[0].rdata), '203.0.113.9')
        self.assertEqual(self.http('/__exvius/hello')[0], 200)
        self.assertEqual(self.https()[0], 200)
        self.assertTrue(read_service(self.root)['ready'])
        self.assertNotIn('player_state', set(sys.modules) - self.modules_before)
        self.assertFalse((self.root / 'state').exists())

    def test_given_untrusted_client_when_https_connects_then_certificate_validation_fails(self):
        self.service.start()
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.https(ssl.create_default_context())

    def test_given_disallowed_peer_when_http_connects_then_reject_before_serving_a_profile(self):
        self.service.start()
        with patch.object(Network, 'allows', return_value=False):
            with self.assertRaises((http.client.RemoteDisconnected, ConnectionResetError)):
                self.http('/ca.mobileconfig')

    def test_given_file_paths_or_game_requests_when_http_is_used_then_only_public_setup_routes_work(self):
        self.service.start()
        for path in ('/certs/identity.json', '/certs/leaf.pem', '/%2e%2e/certs/identity.json', '/ca.key'):
            with self.subTest(path=path):
                self.assertEqual(self.http(path)[0], 404)
        profile = self.http('/ca.mobileconfig')
        self.assertEqual(profile[0], 200)
        self.assertEqual(plistlib.loads(profile[1])['PayloadType'], 'Configuration')
        self.assertEqual(self.http('/ca.mobileconfig', 'HEAD')[1], b'')
        self.assertEqual(self.http('/game.php', 'POST')[0], 503)

    def test_given_malformed_udp_and_fragmented_tcp_when_dns_is_used_then_server_survives(self):
        self.service.start()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as peer:
            peer.settimeout(3)
            peer.sendto(b'\x12\x34broken', ('127.0.0.1', self.service.ports['dns']))
            reply = DNSRecord.parse(peer.recv(4096))
            self.assertEqual(reply.header.rcode, RCODE.FORMERR)
        request = DNSRecord.question(HELLO_HOST).pack()
        with socket.create_connection(('127.0.0.1', self.service.ports['dns']), timeout=3) as peer:
            frame = len(request).to_bytes(2, 'big') + request
            peer.sendall(frame[:1])
            peer.sendall(frame[1:])
            size = int.from_bytes(peer.recv(2), 'big')
            data = bytearray()
            while len(data) < size:
                data.extend(peer.recv(size - len(data)))
            self.assertEqual(str(DNSRecord.parse(data).rr[0].rdata), self.network.address)

    def test_given_occupied_http_port_when_starting_then_close_dns_and_do_not_report_ready(self):
        from dataclasses import replace
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0))
            occupied.listen()
            self.service.network = replace(self.network, http_port=occupied.getsockname()[1])
            with self.assertRaisesRegex(OSError, 'HTTP'):
                self.service.start()
        self.assertFalse(self.service.snapshot()['ready'])
        self.assertIsNone(read_service(self.root))
        with InstanceLock(self.root):
            pass

    def test_given_occupied_udp_dns_or_https_when_starting_then_release_every_acquired_listener(self):
        from dataclasses import replace
        for kind in ('udp', 'https'):
            with self.subTest(kind=kind), socket.socket(type=socket.SOCK_DGRAM if kind == 'udp' else socket.SOCK_STREAM) as occupied:
                occupied.bind(('127.0.0.1', 0))
                if kind == 'https':
                    occupied.listen()
                options = {'dns_port' if kind == 'udp' else 'https_port': occupied.getsockname()[1]}
                self.service.network = replace(self.network, **options)
                with self.assertRaisesRegex(OSError, 'DNS UDP' if kind == 'udp' else 'HTTPS'):
                    self.service.start()
                self.assertFalse(self.service.snapshot()['ready'])
                self.assertIsNone(read_service(self.root))
                with InstanceLock(self.root):
                    pass

    def test_given_occupied_runtime_when_starting_then_preserve_the_existing_service(self):
        self.service.start()
        other = Service(self.root, self.network)
        self.addCleanup(other.close)
        with self.assertRaisesRegex(RuntimeError, 'Another iOS instance'):
            other.start()
        self.assertTrue(read_service(self.root)['ready'])

    def test_given_non_socket_control_path_when_starting_then_preserve_file_and_close_listeners(self):
        (self.root / 'control.sock').write_text('keep this file')
        with self.assertRaisesRegex(ValueError, 'non-socket'):
            self.service.start()
        self.assertEqual((self.root / 'control.sock').read_text(), 'keep this file')
        self.assertFalse(self.service.snapshot()['ready'])
        with InstanceLock(self.root):
            pass

    def test_given_running_service_when_status_is_queried_then_report_ready_without_save_creation(self):
        from ios_server.config import Configuration
        from ios_server.queries import status
        self.service.start()
        report = status(Configuration(self.root, self.root.parent / 'unconfigured-shared-data'))
        self.assertTrue(report['ready'])
        self.assertEqual(report['hosting'], 'running')
        self.assertEqual(report['mode'], 'connectivity-check')
        self.assertFalse(report['has_save'])

    def test_given_running_service_when_serve_repeats_then_reuse_matching_configuration_and_reject_conflicts(self):
        from contextlib import redirect_stdout
        from dataclasses import replace
        import io
        from ios_server.cli import main
        self.service.start()
        for network, expected in ((self.network, 0), (replace(self.network, https_port=9443), 1)):
            with self.subTest(expected=expected), patch('ios_server.network.discover', return_value=network), redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(['serve', '--root', str(self.root)]), expected)
                result = json.loads(output.getvalue())
                self.assertEqual('error' in result, bool(expected))
        self.assertTrue(read_service(self.root)['ready'])

    def test_given_foreground_process_when_terminated_then_release_socket_and_lock_cleanly(self):
        import subprocess
        import time
        script = '''
import sys
from pathlib import Path
from unittest.mock import patch
sys.path[:0] = sys.argv[1:3]
from ios_server.cli import main
from ios_server.network import Network
network = Network('192.168.86.40', '192.168.86.0/24', '192.168.86.1',
                  bind='127.0.0.1', dns_port=0, http_port=0, https_port=0)
with patch('ios_server.network.discover', return_value=network):
    raise SystemExit(main(['serve', '--root', sys.argv[3]]))
'''
        process = subprocess.Popen([sys.executable, '-B', '-c', script, str(SOURCE), str(SOURCE / 'server'),
                                    str(self.root)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while read_service(self.root) is None:
                if process.poll() is not None or time.monotonic() >= deadline:
                    self.fail('The foreground service did not become ready: ' + str(process.communicate(timeout=2)))
                time.sleep(.05)
            process.terminate()
            output, error = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, error)
            self.assertTrue(json.loads(output)['ready'])
            self.assertIsNone(read_service(self.root))
            with InstanceLock(self.root):
                pass
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=3)

    def test_given_slow_listener_cleanup_when_stop_returns_then_immediate_restart_can_take_the_lock(self):
        from contextlib import redirect_stdout
        import io
        import subprocess
        import time
        from ios_server.cli import main
        script = '''
import sys, time
from unittest.mock import patch
sys.path[:0] = sys.argv[1:3]
from ios_server.cli import main
from ios_server.network import Network
from ios_server.service import Listener
network = Network('192.168.86.40', '192.168.86.0/24', '192.168.86.1',
                  bind='127.0.0.1', dns_port=0, http_port=0, https_port=0)
original = Listener.close
def delayed_close(listener):
    if listener.name == 'DNS TCP':
        time.sleep(.6)
    return original(listener)
with patch('ios_server.network.discover', return_value=network), patch.object(Listener, 'close', delayed_close):
    raise SystemExit(main(['serve', '--root', sys.argv[3]]))
'''
        process = subprocess.Popen([sys.executable, '-B', '-c', script, str(SOURCE), str(SOURCE / 'server'),
                                    str(self.root)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while read_service(self.root) is None:
                if process.poll() is not None or time.monotonic() >= deadline:
                    self.fail('The service did not become ready: ' + str(process.communicate(timeout=2)))
                time.sleep(.05)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(['stop', '--root', str(self.root)]), 0)
            with InstanceLock(self.root):
                pass
            output, error = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, error)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=3)

    def test_given_running_service_when_stop_command_runs_then_release_listeners_and_instance_lock(self):
        self.service.start()
        self.assertTrue(read_service(self.root, stop=True)['stopping'])
        self.assertTrue(self.service.stop_event.wait(2))
        self.service.close()
        self.assertIsNone(read_service(self.root))
        with InstanceLock(self.root):
            pass

    def test_given_due_leaf_when_maintained_then_reload_tls_without_changing_ca_or_stopping_dns(self):
        self.service.start()
        fingerprint = self.service.store.inspect()['ca_sha256']
        self.service.maintain(now=datetime.now(timezone.utc) + timedelta(days=380))
        self.assertEqual(self.service.store.inspect()['ca_sha256'], fingerprint)
        self.assertTrue(self.service.snapshot()['ready'])
        self.assertEqual(self.http('/__exvius/hello')[0], 200)


if __name__ == '__main__':
    unittest.main()
