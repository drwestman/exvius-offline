"""BDD for explicit resumable managed-pack installation and read-only verification."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from types import SimpleNamespace

import test_ios_preparation as harness
from ios_server import managed_content as content, pack_manifest as policy, pack_download, pack_layers, pack_install
from ios_server.config import Configuration
from ios_server.runtime import InstanceLock


def zip_bytes(files):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            entry = zipfile.ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED; entry.external_attr = 0o100644 << 16
            archive.writestr(entry, value)
    return raw.getvalue()


def response(raw, *, status=200, start=0, size=None, headers=None, url='https://example.test/pack.zip'):
    result = io.BytesIO(raw); result.status = status; result.geturl = lambda: url
    result.headers = {'Content-Length': str(len(raw))}
    if status == 206: result.headers['Content-Range'] = f'bytes {start}-{(size or len(raw)) - 1}/{size or len(raw)}'
    result.headers.update(headers or {})
    return result


class ManifestPolicy(unittest.TestCase):
    def test_given_bundled_manifest_when_parsed_then_keep_android_metadata_and_skip_only_client_assets(self):
        raw = policy.DEFAULT.read_bytes(); manifest = policy.parse(raw)
        self.assertEqual(len(manifest.packs), 18)
        self.assertEqual(sum(p.size for p in manifest.packs), 14575874619)
        self.assertEqual(sum(p.unpacked_size for p in manifest.packs), 14876694385)
        self.assertNotIn('client-assets', {p.id for p in manifest.packs})
        self.assertEqual(manifest.document['app'], json.loads(raw)['app'])
        self.assertEqual(policy.DEFAULT.read_bytes(), raw)

    def test_given_bad_schema_duplicate_id_size_hash_or_url_when_parsed_then_reject(self):
        original = json.loads(policy.DEFAULT.read_bytes())
        for field, value in (('size', True), ('size', -1), ('sha256', 'bad'), ('url', 'file:///secret')):
            doc = copy.deepcopy(original); doc['packs'][1][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): policy.parse(policy.encoded(doc))
        for doc in ({}, {**original, 'schema': True}, {**original, 'packs': []},
                    {**original, 'packs': original['packs'] + [original['packs'][0]]}):
            with self.assertRaises(ValueError): policy.parse(policy.encoded(doc))

    def test_given_pack_destinations_when_mapped_then_allow_content_and_exclude_saves_and_app_resources(self):
        self.assertEqual(policy.destination('metadata/registry.json'), 'registry.json')
        for name in ('native/en/a.cpk', 'native/homeMarquee/a.png', 'static/mst_decoded/a.ndjson',
                     'static/gacha_community/art/a.png', 'static/client/shared_prefs/gamedata.xml'):
            self.assertEqual(policy.destination(name), name)
        for name in ('../save', '/absolute', 'native/en/../save', 'native/en//a', 'native/en/./a', 'native/en/a\\b',
                     'static/state/campaign.json', 'native/state/campaign.json', 'static/client/game-assets.apk', 'C:/file'):
            with self.subTest(name=name), self.assertRaises(ValueError): policy.destination(name)


class DownloadBehavior(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name); self.target = self.root / 'pack.zip'; self.raw = b'abcdefgh' * 4096
        self.pack = policy.Pack('base', 'https://example.test/pack.zip', len(self.raw), 1, policy.digest(self.raw))

    def test_given_partial_when_server_supports_ranges_then_resume_and_check_complete_hash(self):
        self.target.with_suffix('.part').write_bytes(self.raw[:20]); calls = []
        def opener(request, **_):
            calls.append(request.get_header('Range'))
            return response(self.raw[20:], status=206, start=20, size=len(self.raw))
        self.assertEqual(pack_download.fetch(self.pack, self.target, opener=opener), self.target)
        self.assertEqual(calls, ['bytes=20-']); self.assertEqual(self.target.read_bytes(), self.raw)
        self.assertFalse(self.target.with_suffix('.part').exists())

    def test_given_ignored_range_when_server_returns_200_then_restart_instead_of_appending(self):
        self.target.with_suffix('.part').write_bytes(b'incorrect prefix')
        pack_download.fetch(self.pack, self.target, opener=lambda *_a, **_k: response(self.raw))
        self.assertEqual(self.target.read_bytes(), self.raw)

    def test_given_truncated_response_when_retried_then_keep_partial_and_resume(self):
        with self.assertRaises(OSError):
            pack_download.fetch(self.pack, self.target, opener=lambda *_a, **_k: response(self.raw[:100], headers={'Content-Length': str(len(self.raw))}))
        self.assertEqual(self.target.with_suffix('.part').read_bytes(), self.raw[:100])
        pack_download.fetch(self.pack, self.target, opener=lambda *_a, **_k: response(self.raw[100:], status=206, start=100, size=len(self.raw)))
        self.assertEqual(self.target.read_bytes(), self.raw)

    def test_given_wrong_ranges_lengths_or_redirect_when_received_then_reject_without_appending(self):
        partial = self.target.with_suffix('.part'); partial.write_bytes(self.raw[:20])
        cases = (dict(status=206, start=19, size=len(self.raw)), dict(status=206, start=20, size=len(self.raw) + 1),
                 dict(status=206, start=20, size=len(self.raw), headers={'Content-Length': '1'}),
                 dict(status=500), dict(url='http://outside.test/pack.zip'))
        for options in cases:
            with self.subTest(options=options), self.assertRaises(ValueError):
                pack_download.fetch(self.pack, self.target, opener=lambda *_a, **_k: response(self.raw[20:], **options))
            self.assertEqual(partial.read_bytes(), self.raw[:20])

    def test_given_oversize_or_wrong_hash_when_received_then_do_not_publish_archive(self):
        with self.assertRaises(ValueError):
            pack_download.fetch(self.pack, self.target, opener=lambda *_a, **_k: response(self.raw + b'x', headers={'Content-Length': str(len(self.raw))}))
        self.assertFalse(self.target.exists())
        self.target.with_suffix('.part').unlink(missing_ok=True)
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            pack_download.fetch(self.pack, self.target, opener=lambda *_a, **_k: response(b'x' * len(self.raw)))
        self.assertFalse(self.target.exists()); self.assertFalse(self.target.with_suffix('.part').exists())

    def test_given_complete_partial_or_cached_archive_when_fetched_then_verify_without_network(self):
        with patch('socket.socket', side_effect=AssertionError('network')):
            self.target.with_suffix('.part').write_bytes(self.raw)
            pack_download.fetch(self.pack, self.target, opener=lambda *_a, **_k: self.fail('network'))
            pack_download.fetch(self.pack, self.target, opener=lambda *_a, **_k: self.fail('network'))
        self.assertEqual(self.target.read_bytes(), self.raw)


class ManagedInstallation(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='ios-install-'); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name); self.config = Configuration(self.root / 'runtime', self.root / 'data')
        self.archives = self.root / 'archives'; self.archives.mkdir()
        self.manifest = self.root / 'latest.json'
        self.base = {'static/mst_decoded/F_TEST.ndjson': b'{"id":"1"}\n', 'static/text_decoded/F_TEST.ndjson': b'{}\n',
                     'static/client/shared_prefs/gamedata.xml': b'<map><string name="keyF_TEST">1</string></map>',
                     'metadata/registry.json': b'{"keyF_TEST":"1"}', 'native/mst/Ver1_test.dat': b'table',
                     'native/common_lang/sd/common.cpk': b'common', 'native/en/shared.dat': b'base'}
        self.patch = {'native/en/shared.dat': b'override', 'native/en/removed.dat': b'old'}
        self.document = {'schema': 1, 'revision': 1, 'version': 'test.1', 'app': {'keep': 'Android metadata'}, 'packs': []}
        self.update()

    def update(self, order=None):
        rows = []
        for identity, files in (order or [('base', self.base), ('patch', self.patch)]):
            raw = zip_bytes(files); (self.archives / (identity + '.zip')).write_bytes(raw)
            rows.append({'id': identity, 'url': 'https://example.test/' + identity + '.zip', 'size': len(raw),
                         'unpackedSize': sum(map(len, files.values())), 'sha256': policy.digest(raw)})
        self.document['packs'] = rows
        self.manifest.write_bytes(policy.encoded(self.document))

    def fetch(self, **kwargs):
        return pack_install.fetch(self.config, self.manifest, archive_dir=self.archives, emit=lambda _msg: None, **kwargs)

    def tree(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_given_fresh_data_when_installed_then_publish_ordered_content_without_touching_manifest_or_save(self):
        self.config.state_file.parent.mkdir(parents=True); self.config.state_file.write_bytes(b'{"keep":"save"}')
        original_manifest = self.manifest.read_bytes(); originals = {p: p.read_bytes() for p in self.archives.iterdir()}
        result = self.fetch(); installed = content.load(self.config.data_root, verify=True)
        self.assertTrue(result['installed_now']); self.assertFalse(result['gameplay_ready'])
        self.assertEqual((installed.directory / 'native/en/shared.dat').read_bytes(), b'override')
        self.assertEqual(self.manifest.read_bytes(), original_manifest)
        self.assertEqual(originals, {p: p.read_bytes() for p in self.archives.iterdir()})
        self.assertEqual(installed.manifest.document['app'], self.document['app'])
        self.assertEqual(self.config.state_file.read_bytes(), b'{"keep":"save"}')
        self.assertTrue(pack_install.verify(self.config, self.manifest)['ok'])
        fresh = Configuration(self.config.root, self.config.data_root)
        self.assertEqual(fresh.content_root, installed.directory); self.assertEqual(fresh.missing_data(), [])

    def test_given_same_manifest_when_fetched_again_then_reuse_generation_without_download_or_writes(self):
        self.fetch(); before = self.tree()
        with patch.object(pack_layers, 'extract', side_effect=AssertionError('re-extracted')):
            self.assertFalse(self.fetch()['installed_now'])
        self.assertEqual(self.tree(), before)

    def test_given_published_archive_names_when_supplied_locally_then_reuse_without_network(self):
        for row in self.document['packs']:
            name = 'exvius-' + row['id'] + '.zip'
            (self.archives / (row['id'] + '.zip')).rename(self.archives / name)
            row['url'] = 'https://example.test/' + name
        self.manifest.write_bytes(policy.encoded(self.document))
        self.assertTrue(self.fetch(opener=lambda *_a, **_k: self.fail('network'))['installed_now'])

    def test_given_missing_installation_when_planned_or_verified_then_no_writes_network_or_engine_imports(self):
        before = self.tree(); modules = set(sys.modules)
        with patch.object(Path, 'mkdir', side_effect=AssertionError('query wrote')), patch('socket.socket', side_effect=AssertionError('network')):
            result = pack_install.plan(self.config, self.manifest)
            self.assertEqual(result['packs_to_fetch'], 2); self.assertFalse(result['installed'])
            self.assertFalse(pack_install.verify(self.config, self.manifest)['ok'])
        self.assertEqual(self.tree(), before)
        self.assertFalse({'capture_server', 'player_state', 'data_paths'} & (set(sys.modules) - modules))

    def test_given_installed_data_when_verified_then_hash_files_without_writes(self):
        self.fetch(); before = self.tree()
        with patch.object(Path, 'mkdir', side_effect=AssertionError('query wrote')), patch('socket.socket', side_effect=AssertionError('network')):
            self.assertTrue(pack_install.verify(self.config, self.manifest)['ok'])
        self.assertEqual(self.tree(), before)

    def test_given_changed_override_when_updated_then_restore_base_and_remove_deleted_files(self):
        self.fetch(); old = content.load(self.config.data_root); old_config = Configuration(self.config.root, self.config.data_root)
        self.patch = {'native/en/new.dat': b'new'}; self.document['revision'] = 2; self.update()
        calls = []; extract = pack_layers.extract
        def track(root, pack, archive): calls.append(pack.id); return extract(root, pack, archive)
        with patch.object(pack_layers, 'extract', side_effect=track): result = self.fetch()
        new = content.load(self.config.data_root, verify=True)
        self.assertEqual(calls, ['patch']); self.assertTrue(result['installed_now'])
        self.assertEqual((new.directory / 'native/en/shared.dat').read_bytes(), b'base')
        self.assertFalse((new.directory / 'native/en/removed.dat').exists())
        self.assertEqual((old.directory / 'native/en/shared.dat').read_bytes(), b'override')
        self.assertEqual(old_config.content_root, old.directory)
        self.assertEqual(Configuration(self.config.root, self.config.data_root).content_root, new.directory)

    def test_given_reordered_packs_when_updated_then_rebuild_overlay_from_layers_without_extraction(self):
        self.fetch(); self.document['revision'] = 2; self.update([('patch', self.patch), ('base', self.base)])
        with patch.object(pack_layers, 'extract', side_effect=AssertionError('re-extracted')): self.fetch()
        installed = content.load(self.config.data_root, verify=True)
        self.assertEqual((installed.directory / 'native/en/shared.dat').read_bytes(), b'base')

    def test_given_stale_manifest_when_verified_then_report_without_mutating_installation(self):
        self.fetch(); self.document['revision'] = 2; self.update(); before = self.tree()
        self.assertFalse(pack_install.verify(self.config, self.manifest)['ok']); self.assertEqual(self.tree(), before)
        self.assertFalse(pack_install.plan(self.config, self.manifest)['current'])

    def test_given_failed_pointer_replacement_when_retried_then_preserve_active_generation_and_reuse_layers(self):
        self.fetch(); pointer = self.config.data_root / content.POINTER; old = pointer.read_bytes()
        self.patch = {'native/en/new.dat': b'new'}; self.document['revision'] = 2; self.update()
        replace = os.replace
        def fail(source, destination):
            if Path(destination) == pointer: raise OSError('publish interrupted')
            return replace(source, destination)
        with patch('ios_server.pack_install.os.replace', side_effect=fail), self.assertRaises(OSError): self.fetch()
        self.assertEqual(pointer.read_bytes(), old); self.assertIsNotNone(content.load(self.config.data_root, verify=True))
        with patch.object(pack_layers, 'extract', side_effect=AssertionError('re-extracted')): self.fetch()
        self.assertTrue(pack_install.verify(self.config, self.manifest)['ok'])
        self.assertFalse(list((self.config.data_root / content.GENERATIONS).glob('.building-*')))
        self.assertFalse(list(self.config.data_root.glob('.ios-current-*')))

    def test_given_later_bad_zip_when_installing_then_keep_completed_layer_for_retry_without_activation(self):
        self.patch = {'static/state/campaign.json': b'forbidden'}; self.update()
        with self.assertRaises(ValueError): self.fetch()
        self.assertFalse((self.config.data_root / content.POINTER).exists())
        manifest = policy.read(self.manifest)
        self.assertIsNotNone(pack_layers.load(self.config.data_root, manifest.packs[0], verify=True))
        self.patch = {'native/en/fixed.dat': b'fixed'}; self.update(); calls = []; extract = pack_layers.extract
        def track(root, pack, archive): calls.append(pack.id); return extract(root, pack, archive)
        with patch.object(pack_layers, 'extract', side_effect=track): self.fetch()
        self.assertEqual(calls, ['patch'])

    def test_given_unsafe_duplicate_special_or_case_colliding_zip_when_installing_then_reject(self):
        for kind in ('duplicate', 'symlink', 'case', 'parent'):
            raw = io.BytesIO()
            with zipfile.ZipFile(raw, 'w') as archive:
                archive.writestr('native/en/a', b'a')
                if kind == 'duplicate':
                    with self.assertWarns(UserWarning): archive.writestr('native/en/a', b'b')
                elif kind == 'symlink':
                    info = zipfile.ZipInfo('native/en/link'); info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(info, b'/outside')
                elif kind == 'case': archive.writestr('native/en/A', b'b')
                else: archive.writestr('native/en/a/child', b'b')
            data = raw.getvalue(); path = self.archives / 'bad.zip'; path.write_bytes(data)
            pack = policy.Pack('bad', 'https://example.test/a', len(data), 2 if kind != 'symlink' else 9, policy.digest(data))
            with self.subTest(kind=kind), self.assertRaises(ValueError): pack_layers.extract(self.config.data_root, pack, path)

    def test_given_cross_pack_case_collision_when_merging_then_refuse_without_pointer(self):
        self.patch = {'native/en/SHARED.dat': b'collision'}; self.update()
        with self.assertRaisesRegex(ValueError, 'collision'): self.fetch()
        self.assertFalse((self.config.data_root / content.POINTER).exists())

    def test_given_bad_expanded_size_or_registry_when_installing_then_refuse(self):
        for kind in ('size', 'registry', 'layout'):
            if kind == 'size':
                self.document['packs'][0]['unpackedSize'] += 1; self.manifest.write_bytes(policy.encoded(self.document))
            else:
                self.base['metadata/registry.json'] = b'{"private_save":"99"}'
                if kind == 'layout': self.base.pop('native/mst/Ver1_test.dat')
                self.update()
            with self.subTest(kind=kind), self.assertRaises(ValueError): self.fetch()
            self.assertFalse((self.config.data_root / content.POINTER).exists())

    def test_given_missing_or_corrupt_installed_files_when_verified_then_fail_without_repair(self):
        self.fetch(); installed = content.load(self.config.data_root)
        target = installed.directory / 'native/en/shared.dat'; target.chmod(0o644); target.write_bytes(b'corrupt')
        before = self.tree(); self.assertFalse(pack_install.verify(self.config, self.manifest)['ok']); self.assertEqual(self.tree(), before)

    def test_given_newer_patch_registry_when_installed_then_project_versions_without_mutating_source_layers(self):
        import xml.etree.ElementTree as ET
        self.fetch(); old = content.load(self.config.data_root)
        self.patch = {'metadata/registry.json': b'{"keyF_TEST":"2"}'}
        self.document['revision'] = 2; self.update(); self.fetch()
        new = content.load(self.config.data_root, verify=True)
        relative = 'static/client/shared_prefs/gamedata.xml'
        self.assertEqual(ET.fromstring((new.directory / relative).read_bytes())[0].text, '2')
        self.assertEqual(ET.fromstring((old.directory / relative).read_bytes())[0].text, '1')
        base = policy.read(self.manifest).packs[0]
        layer = pack_layers.load(self.config.data_root, base, verify=True)
        self.assertEqual((layer[0] / relative).read_bytes(), self.base[relative])

    def test_given_escaping_symlinks_or_corrupt_pointer_when_read_then_refuse(self):
        self.fetch(); pointer = self.config.data_root / content.POINTER; before = pointer.read_bytes()
        pointer.write_bytes(b'bad json')
        with self.assertRaises(ValueError): Configuration(self.config.root, self.config.data_root)
        pointer.write_bytes(before); pointer.unlink(); pointer.symlink_to(self.manifest)
        with self.assertRaises(ValueError): Configuration(self.config.root, self.config.data_root)

    def test_given_existing_prepared_or_flat_managed_tree_when_fetched_then_preserve_it(self):
        for folder in ('mst_decoded', 'static'):
            path = self.config.data_root / folder; path.mkdir(parents=True); (path / 'keep').write_bytes(b'original')
            before = self.tree()
            with self.assertRaisesRegex(ValueError, 'separate managed'): self.fetch()
            self.assertEqual(self.tree(), before)
            (path / 'keep').unlink(); path.rmdir()

    def test_given_busy_runtime_or_shared_install_lock_when_fetched_then_refuse(self):
        with InstanceLock(self.config.root), self.assertRaises(RuntimeError): self.fetch()
        with InstanceLock(self.config.data_root / '.ios-installer'), self.assertRaises(RuntimeError): self.fetch()

    def test_given_insufficient_space_when_fetched_then_refuse_before_transfer(self):
        usage = type('Usage', (), {'free': 0})()
        with patch('ios_server.pack_install.shutil.disk_usage', return_value=usage), self.assertRaises(OSError): self.fetch()
        self.assertFalse((self.config.data_root / content.POINTER).exists())

    def test_given_cli_from_base_python_when_used_then_emit_json_and_reuse_isolated_runtime(self):
        command = [str(Path(sys.base_prefix) / 'bin/python3.12'), '-B', str(harness.SOURCE / 'exvius/macos_ios_server.py')]
        options = ['--root', str(self.config.root), '--data', str(self.config.data_root), '--manifest', str(self.manifest)]
        before = self.tree()
        result = subprocess.run([*command, 'plan-data', *options], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr); self.assertEqual(json.loads(result.stdout)['packs_to_fetch'], 2)
        self.assertEqual(self.tree(), before)
        result = subprocess.run([*command, 'fetch-data', *options, '--archive-dir', str(self.archives)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr); self.assertTrue(json.loads(result.stdout)['installed_now'])
        before = self.tree()
        result = subprocess.run([*command, 'verify-packs', *options], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr); self.assertTrue(json.loads(result.stdout)['verified'])
        self.assertEqual(self.tree(), before)

    def test_given_installed_registered_tables_when_prepared_then_pin_provenance_and_refresh_after_install_update(self):
        from ios_server import preparation
        from xml.etree import ElementTree as ET
        holder = SimpleNamespace(config=Configuration(self.root / 'source-runtime', self.root / 'source'))
        harness.NativePreparation.fixture(holder, managed=True)
        import test_ios_server as engine_harness
        masters = holder.config.data / 'static/mst_decoded'; masters.mkdir(parents=True)
        engine_harness.IosServerBehavior.write_masters(holder, masters)
        files = {path.relative_to(holder.config.data).as_posix(): path.read_bytes()
                 for path in holder.config.data.rglob('*') if path.is_file()}
        xml = ET.fromstring(files['static/client/shared_prefs/gamedata.xml'])
        files.update({'metadata/registry.json': policy.encoded({row.get('name'): row.text for row in xml}),
                      'static/mst_decoded/fixture.ndjson': b'{}\n', 'static/text_decoded/fixture.ndjson': b'{}\n',
                      'native/common_lang/fixture.dat': b'fixture'})
        self.update([('base', files)]); self.fetch()
        old_config = Configuration(self.config.root, self.config.data_root)
        script = '''
import sys
from pathlib import Path
sys.path[:0]=sys.argv[1:3]
from ios_server.config import Configuration
from ios_server.engine import Engine
config=Configuration(Path(sys.argv[3]),Path(sys.argv[4]))
engine=Engine(config)
try:
    engine.initialize_campaign()
    import data_paths
    assert data_paths.CONTENT_ROOT==str(config.content_root)
    assert Path(data_paths.MST_DIR)==config.content_root/'static/mst_decoded'
finally:engine.close()
'''
        done = engine_harness.IosServerBehavior.child(self, script, str(self.config.root), str(self.config.data_root))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        preparation.prepare_data(old_config); old = preparation.load_prepared(old_config)
        self.assertTrue(preparation.verify_data(old_config)['ok'])
        self.assertTrue(all(row['path'].startswith(content.GENERATIONS + '/') for row in old.manifest['sources']['tables'].values()))
        self.document['revision'] += 1; self.update([('base', files)]); self.fetch()
        new_config = Configuration(self.config.root, self.config.data_root)
        self.assertNotEqual(new_config.content_root, old_config.content_root)
        self.assertFalse(preparation.verify_data(new_config)['ok'])
        preparation.prepare_data(new_config)
        self.assertGreater(preparation.load_prepared(new_config).manifest['generation'], old.manifest['generation'])
        self.assertTrue(preparation.verify_data(new_config)['ok'])
        self.assertTrue(old.directory.is_dir())


class HttpDownload(unittest.TestCase):
    def test_given_real_http_range_response_when_resuming_then_fetch_exact_wire_bytes(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading
        payload = b'wire bytes' * 4096; calls = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                header = self.headers.get('Range'); calls.append(header)
                offset = int(header.split('=')[1].split('-')[0]) if header else 0
                self.send_response(206 if offset else 200)
                if offset: self.send_header('Content-Range', f'bytes {offset}-{len(payload) - 1}/{len(payload)}')
                self.send_header('Content-Length', str(len(payload) - offset)); self.end_headers()
                self.wfile.write(payload[offset:])
            def log_message(self, *_args): pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / 'wire.zip'; target.with_suffix('.part').write_bytes(payload[:23])
                pack = policy.Pack('wire', f'http://127.0.0.1:{server.server_port}/pack.zip', len(payload), 1, policy.digest(payload))
                pack_download.fetch(pack, target)
                self.assertEqual(target.read_bytes(), payload); self.assertEqual(calls, ['bytes=23-'])
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__': unittest.main()
