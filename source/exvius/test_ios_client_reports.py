"""BDD for native-only, bounded diagnostic reports from the real encrypted wire."""
import json
import os
import socket
import http.client
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_ios_hosting as hosting_fixture

SOURCE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SOURCE), str(SOURCE / 'server')]


class ClientReportWire(unittest.TestCase):
    setUp = hosting_fixture.NativeGameplayWire.setUp
    fixture = hosting_fixture.NativeGameplayWire.fixture
    source = hosting_fixture.NativeGameplayWire.source
    artwork = hosting_fixture.NativeGameplayWire.artwork
    install = hosting_fixture.NativeGameplayWire.install
    child = hosting_fixture.NativeGameplayWire.child
    prepare = hosting_fixture.NativeGameplayWire.prepare
    start = hosting_fixture.NativeGameplayWire.start
    stop = hosting_fixture.NativeGameplayWire.stop
    request = hosting_fixture.NativeGameplayWire.request

    def post(self, name, document):
        import ffbe_crypto as crypto
        endpoint = json.loads((SOURCE / 'server/endpoints.json').read_bytes())['by_class'][name]
        key = crypto.key16(endpoint['encode_key'])
        envelope = {'TEAYk6R1': {'z5hB3P01': endpoint['request_id'], 'ytHoz4E2': '1', '9K0Pzcpd': '1167'},
                    't7n6cVWf': {'qrVcDe48': crypto.cbc_encrypt(key, json.dumps(document).encode(), double_pad=True)}}
        code, raw, _ = self.request(endpoint['url'], 'POST', json.dumps(envelope).encode(), secure=True)
        self.assertEqual(code, 200, raw[:200])
        cipher = json.loads(raw)['t7n6cVWf']['qrVcDe48']
        self.assertTrue(cipher, 'The native report upload must receive an encrypted acknowledgement')
        return json.JSONDecoder().raw_decode(crypto.cbc_decrypt(key, cipher).decode())[0]

    def test_given_queued_report_when_diagnostics_off_then_ack_without_saving_or_changing_campaign(self):
        self.prepare()
        with patch.dict(os.environ, {'EXVIUS_CLIENT_REPORTS': '0'}):
            self.start()
        before = self.config.state_file.read_bytes()
        reply = self.post('sgStoreLogReportRequest', {'a8035010': [{'FPGJbL8x': 'private client log'}]})
        self.assertEqual(reply, {'cd87bd8b': [{'950510b8': '0'}]})
        self.assertEqual(self.config.state_file.read_bytes(), before)
        self.assertFalse((self.config.root / 'client-reports').exists())
        record = json.loads(max((self.config.root / 'requests').glob('*.json')).read_bytes())
        self.assertIsNone(record['plaintext']); self.assertIsNone(record['body_raw'])
        self.assertNotIn('private client log', self.errors.read_text())
        # A gameplay request ID cannot use the report route's larger body allowance.
        import ffbe_crypto as crypto
        endpoint = json.loads((SOURCE / 'server/endpoints.json').read_bytes())['by_class']['UpdateSwitchInfoRequest']
        document = {'0jqUZuT1': [{'dIPkNn61': '10000153'}], 'padding': 'x' * (4 * 1024 * 1024)}
        envelope = {'TEAYk6R1': {'z5hB3P01': endpoint['request_id']},
                    't7n6cVWf': {'qrVcDe48': crypto.cbc_encrypt(crypto.key16(endpoint['encode_key']), json.dumps(document).encode(), double_pad=True)}}
        code, raw, _ = self.request('/lapisProd/app/php/gme/actionSymbol/6611dc2f.php?test=1', 'POST', json.dumps(envelope).encode())
        self.assertEqual(code, 200)
        self.assertEqual(bool(json.loads(raw)['t7n6cVWf']['qrVcDe48']), False)
        self.assertEqual(self.config.state_file.read_bytes(), before)

    def test_given_enabled_reports_when_launched_then_request_only_on_boot_and_accept_large_private_upload(self):
        from ios_server import client_reports as reports
        import ffbe_crypto as crypto
        self.prepare()
        with patch.dict(os.environ, {'EXVIUS_CLIENT_REPORTS': '1'}):
            self.start()
        self.assertTrue(self.report['gameplay']['client_reports'])
        boot = self.post('GameSettingRequest', {})
        self.assertEqual(boot[reports.REPORT_BACK][0]['da99ba05'], '0')
        self.assertNotIn(reports.REPORT_BACK, self.post('RoutineHomeUpdateRequest', {}))
        before = self.config.state_file.read_bytes()
        message = 'Error loading native texture: LoadingIndicator.png'
        log = crypto.cbc_encrypt(b'FFBE2020DevsRGod', message.encode(), double_pad=True)
        document = {'a8035010': [{'FPGJbL8x': log}], 'padding': 'x' * (4 * 1024 * 1024)}
        self.assertEqual(self.post('sgStoreLogReportRequest', document), reports.ACK)
        self.assertEqual(self.config.state_file.read_bytes(), before)
        files = list((self.config.root / 'client-reports').glob('*.json'))
        self.assertEqual(len(files), 1)
        self.assertEqual(list(reports.decode(files[0])), [message])
        self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)
        self.assertEqual(files[0].parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.request('/client-reports/' + files[0].name)[0], 404)
        record = json.loads(max((self.config.root / 'requests').glob('*.json')).read_bytes())
        self.assertIsNone(record['plaintext']); self.assertIsNone(record['body_raw'])
        self.assertLess(len(json.dumps(record)), 10000)
        for path, length in (('/lapisProd/app/php/gme/actionSymbol/6611dc2f.php', reports.MAX_BODY + 1),
                             ('/actionSymbol/other.php', 4 * 1024 * 1024 + 1)):
            with self.subTest(path=path), socket.create_connection(('127.0.0.1', self.report['ports']['http']), timeout=3) as peer:
                peer.sendall((f'POST {path} HTTP/1.1\r\nHost: fixture\r\nContent-Length: {length}\r\nExpect: 100-continue\r\n\r\n').encode())
                response = http.client.HTTPResponse(peer); response.begin()
                self.assertEqual(response.status, 413); response.read()


class ClientReportPolicy(unittest.TestCase):
    def test_given_report_policy_when_projected_then_never_repeat_on_home_or_mutate_input(self):
        from ios_server import client_reports as reports
        original = {'383e98ad': [{'86f76840': 'old'}], 'other': []}
        before = json.dumps(original)
        for enabled, reply_id in ((False, 'OTX6Fmvu'), (True, 'Daud71Hn'), (True, 'rj6dxU9w')):
            self.assertNotIn(reports.REPORT_BACK, reports.project(original, reply_id, enabled=enabled))
        self.assertEqual(json.dumps(original), before)
        self.assertIsNone(reports.project(None, 'OTX6Fmvu', enabled=True))

    def test_given_private_reports_when_retained_then_bound_count_and_bytes_and_preserve_other_files(self):
        from ios_server import client_reports as reports
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'private'; root.mkdir()
            store = reports.ClientReports(root, enabled=True)
            folder = root / 'client-reports'; folder.mkdir()
            outside = Path(tmp) / 'outside'; outside.write_bytes(b'unchanged')
            (folder / ('report-' + 'f' * 32 + '.json')).symlink_to(outside)
            (folder / 'keep.json').write_bytes(b'keep')
            with patch.object(reports, 'MAX_STORED', 20):
                for _ in range(4): store.save(b'x' * 10)
            files = [p for p in folder.glob('report-*.json') if not p.is_symlink()]
            self.assertEqual(len(files), 2)
            self.assertEqual(outside.read_bytes(), b'unchanged')
            self.assertEqual((folder / 'keep.json').read_bytes(), b'keep')
            for _ in range(4): store.save(b'x')
            self.assertEqual(len([p for p in folder.glob('report-*.json') if not p.is_symlink()]), 3)

    def test_given_symlink_or_failed_publication_when_saving_then_preserve_private_and_outside_files(self):
        from ios_server import client_reports as reports
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'private'; root.mkdir()
            outside = Path(tmp) / 'outside'; outside.mkdir()
            folder = root / 'client-reports'; folder.symlink_to(outside)
            store = reports.ClientReports(root, enabled=True)
            with self.assertRaises(ValueError): store.save(b'private')
            self.assertFalse(list(outside.iterdir()))
            folder.unlink()
            with patch.object(reports.os, 'replace', side_effect=OSError('failed')):
                with self.assertRaises(OSError): store.save(b'private')
            self.assertFalse(list(folder.iterdir()))

    def test_given_off_or_malformed_report_when_received_then_never_create_storage(self):
        from ios_server import client_reports as reports
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = reports.ClientReports(root)
            self.assertEqual(store.receive('queued'), reports.ACK)
            self.assertIsNone(store.receive(None))
            enabled = reports.ClientReports(root, enabled=True)
            self.assertIsNone(enabled.receive('{}'))
            self.assertIsNone(enabled.receive('invalid'))
            self.assertFalse(list(root.iterdir()))


if __name__ == '__main__':
    unittest.main()
