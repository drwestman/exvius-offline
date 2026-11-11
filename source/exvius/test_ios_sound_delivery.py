"""BDD for atomic sound/table coordination and exact file-backed native delivery."""
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_ios_preparation as harness
import test_ios_native_labels as labels
import test_ios_server as engine_harness
import test_ios_sounds as audio
import test_ios_vortex_art as vortex
from ios_server import preparation as prep, native_tables as rules, native_sounds
from ios_server import sound_codec, sound_inputs, sound_snapshots
from ios_server.config import Configuration
from ios_server.runtime import InstanceLock
from ios_server.table_codec import master_rows, patch_master
from ios_server.table_delivery import serve


def handler(method='GET'):
    result = SimpleNamespace(command=method, wfile=io.BytesIO(), headers={})
    result.send_response = lambda status: setattr(result, 'status', status)
    result.send_header = lambda key, value: result.headers.update({key: value})
    result.end_headers = lambda: None
    return result


class SoundTableDelivery(unittest.TestCase):
    setUp = harness.NativePreparation.setUp
    fixture = harness.NativePreparation.fixture
    source = harness.NativePreparation.source
    pointer = harness.NativePreparation.pointer
    saved = labels.NativeLabelPreparation.saved
    artwork = vortex.VortexPreparation.artwork
    edit_manifest = vortex.VortexPreparation.edit_manifest
    child = engine_harness.IosServerBehavior.child

    def install(self, version=2):
        self.original = audio.acb()
        self.stock = f'common_lang/sound/se/ios/Ver{version}_System.acb'
        self.android = self.native / self.stock.replace('/ios/', '/android/')
        self.android.parent.mkdir(parents=True, exist_ok=True)
        self.android.write_bytes(self.original)
        for prefix, id_column in sound_inputs.FAMILIES:
            for suffix in ('_MST', '_VERSION_MST_LOCALIZE', '_CHECKSUM_MST'):
                table = rules.BY_NAME[prefix + suffix]
                rows = [row for _, row, _ in master_rows(self.source(table).read_bytes(), table.key, mode=table.cipher)
                        if sound_inputs.positive(row.get(id_column)) and row[id_column] != '12']
                row = {id_column: '12', 'unrelated': 'preserved'}
                row.update({'3LHdc6Qa': 'sound/se', 'pJ56sAEo': 'System.acb', '81fTkEDP': 'GAME'} if suffix == '_MST' else
                           {'OzT5lSz3': str(version), '86SWOBTb': '17', 'japanese': '29'} if suffix == '_VERSION_MST_LOCALIZE' else
                           {'JwbkKrjA': '0', 'mYtcPkQQ': '999999', 'MLOSu5E0': '83'})
                self.source(table).write_bytes(harness.master(table.key, rows + [row], mode=table.cipher))

    def prepared(self, *, art=False):
        if art: self.artwork()
        else: self.fixture()
        self.install(); sound_snapshots.prepare(self.config)
        prep.prepare_data(self.config, sounds=True)
        return prep.load_prepared(self.config)

    def bytes(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def decoded(self, pack, name):
        table = rules.BY_NAME[name]
        return [row for _, row, _ in master_rows(pack.files[pack.manifest['tables'][name]['path']], table.key, mode=table.cipher)]

    def test_given_both_layouts_when_bound_then_publish_364_tables_and_sound_facts_without_copying_banks(self):
        for managed in (False, True):
            self.config = Configuration(self.root / ('private-' + str(managed)), self.root / ('content-' + str(managed)))
            self.fixture(managed); self.install(); sound_snapshots.prepare(self.config)
            original = {t.name: self.source(t).read_bytes() for t in sound_inputs.TABLES}
            report = prep.prepare_data(self.config, sounds=True); pack = prep.load_prepared(self.config)
            self.assertEqual((report['tables'], report['sounds'], pack.manifest['version']), (364, 1, 5))
            self.assertTrue(report['sound_delivery_ready']); self.assertFalse(report['gameplay_ready'])
            self.assertEqual(len(pack.files), 364); self.assertFalse(list(pack.directory.rglob('*.acb')))
            target = pack.manifest['sounds']['banks'][self.stock]
            expected = sound_codec.prepare(self.original)[0]
            self.assertEqual(pack.sounds.read(target['path']), expected)
            for prefix, id_column in sound_inputs.FAMILIES:
                for suffix in ('_VERSION_MST_LOCALIZE', '_CHECKSUM_MST'):
                    name = prefix + suffix; table = rules.BY_NAME[name]
                    before = next(row for _, row, _ in master_rows(original[name], table.key, mode=table.cipher) if row[id_column] == '12')
                    after = next(row for row in self.decoded(pack, name) if row[id_column] == '12')
                    field = 'OzT5lSz3' if suffix.startswith('_VERSION') else 'JwbkKrjA'
                    value = target['version'] if field == 'OzT5lSz3' else len(expected)
                    self.assertEqual(after, {**before, field: str(value)})
            self.assertTrue(prep.verify_data(self.config)['ok'])
            self.assertEqual(original, {t.name: self.source(t).read_bytes() for t in sound_inputs.TABLES})
            self.assertFalse(self.config.state_file.exists())

    def test_given_missing_or_stale_sound_preparation_when_binding_then_preserve_table_pointer(self):
        self.fixture(); self.install(); prep.prepare_data(self.config); before = self.pointer().read_bytes()
        with self.assertRaisesRegex(ValueError, 'prepare-sounds'): prep.prepare_data(self.config, sounds=True)
        sound_snapshots.prepare(self.config)
        self.android.write_bytes(audio.acb([audio.hca(0), audio.hca(0)]))
        with self.assertRaisesRegex(ValueError, 'prepare-sounds'): prep.prepare_data(self.config, sounds=True)
        self.assertEqual(self.pointer().read_bytes(), before)

    def test_given_current_bound_snapshot_when_refreshed_then_retain_feature_and_reuse_generation(self):
        self.prepared(); before = self.bytes()
        self.assertFalse(prep.prepare_data(self.config)['prepared_now'])
        self.assertEqual(self.bytes(), before)

    def test_given_vortex_and_sound_when_upgraded_then_retain_both_features_on_later_refresh(self):
        self.artwork(); self.install(); prep.prepare_data(self.config, vortex_art=True)
        old = prep.load_prepared(self.config); self.assertEqual(old.manifest['version'], 4)
        sound_snapshots.prepare(self.config); prep.prepare_data(self.config, sounds=True)
        pack = prep.load_prepared(self.config)
        self.assertEqual((pack.manifest['version'], len(pack.manifest['packs']), len(pack.manifest['sounds']['banks'])), (5, 1, 1))
        self.assertTrue(old.directory.is_dir())
        self.assertFalse(prep.prepare_data(self.config)['prepared_now'])
        self.assertTrue(prep.verify_data(self.config)['ok'])

    def test_given_source_version_decrease_when_refreshed_then_keep_sound_and_table_versions_monotonic(self):
        self.fixture(); self.install(50000); sound_snapshots.prepare(self.config); prep.prepare_data(self.config, sounds=True)
        old = prep.load_prepared(self.config); previous = next(iter(old.manifest['sounds']['banks'].values()))
        self.android.unlink(); self.install(1); sound_snapshots.prepare(self.config)
        prep.prepare_data(self.config); new = prep.load_prepared(self.config)
        self.assertGreater(new.manifest['sounds']['banks'][self.stock]['version'], previous['version'])
        self.assertTrue(all(row['version'] > old.manifest['tables'][name]['version'] for name, row in new.manifest['tables'].items()))
        self.assertTrue(old.directory.is_dir()); self.assertTrue(prep.verify_data(self.config)['ok'])

    def test_given_overflowing_sound_version_when_binding_then_refuse_before_publication(self):
        self.fixture(); self.install(2147483647); sound_snapshots.prepare(self.config)
        prep.prepare_data(self.config); before = self.pointer().read_bytes()
        with self.assertRaisesRegex(ValueError, 'out of range'): prep.prepare_data(self.config, sounds=True)
        self.assertEqual(self.pointer().read_bytes(), before)

    def test_given_failed_pointer_publish_when_retried_then_preserve_old_binding_and_reuse_complete_generation(self):
        self.prepared(); before = self.pointer().read_bytes(); pointer = self.pointer()
        self.android.write_bytes(audio.acb([audio.hca(0), audio.hca(0)])); sound_snapshots.prepare(self.config)
        replace = os.replace
        def fail(source, destination):
            if Path(destination) == pointer: raise OSError('publication failed')
            return replace(source, destination)
        with patch.object(prep.os, 'replace', side_effect=fail), self.assertRaises(OSError): prep.prepare_data(self.config)
        self.assertEqual(self.pointer().read_bytes(), before)
        self.assertEqual(prep.load_prepared(self.config).manifest['generation'], 1)
        self.assertEqual(prep.prepare_data(self.config)['generation'], 2)
        self.assertTrue(prep.verify_data(self.config)['ok'])

    def test_given_changed_current_sound_pointer_when_loading_then_use_pinned_binding_and_report_stale_freshness(self):
        pack = self.prepared(); entry = pack.manifest['sounds']['banks'][self.stock]
        (self.config.root / sound_snapshots.POINTER).write_bytes(b'bad pointer')
        loaded = prep.load_prepared(self.config)
        self.assertEqual(loaded.sounds.read(entry['path']), pack.sounds.read(entry['path']))
        self.assertFalse(prep.verify_data(self.config)['ok'])

    def test_given_pinned_generation_and_replaced_pointer_when_loaded_then_ignore_even_escaping_current_symlink(self):
        pack = self.prepared(); pointer = self.config.root / sound_snapshots.POINTER
        pointer.unlink(); pointer.symlink_to(self.config.data / 'outside.json')
        self.assertIsNotNone(prep.load_prepared(self.config).sounds)
        self.assertEqual(pack.sounds.read(next(iter(pack.manifest['sounds']['banks'].values()))['path']), sound_codec.prepare(self.original)[0])

    def test_given_bound_snapshot_when_verified_then_no_conversion_writes_or_campaign_imports(self):
        self.prepared(); before = self.bytes(); modules = set(__import__('sys').modules)
        with patch.object(sound_codec, 'prepare', side_effect=AssertionError('query converted')), \
             patch.object(Path, 'mkdir', side_effect=AssertionError('query wrote')):
            self.assertTrue(prep.verify_data(self.config)['ok'])
        self.assertEqual(self.bytes(), before)
        self.assertFalse({'capture_server', 'ffbe_state', 'data_paths'} & (set(__import__('sys').modules) - modules))

    def test_given_busy_runtime_when_binding_then_refuse(self):
        self.fixture(); self.install(); sound_snapshots.prepare(self.config)
        with InstanceLock(self.config.root), self.assertRaises(RuntimeError): prep.prepare_data(self.config, sounds=True)

    def test_given_unbound_table_snapshot_when_sounds_exist_then_retain_existing_delivery_behavior(self):
        self.fixture(); self.install(); sound_snapshots.prepare(self.config); prep.prepare_data(self.config)
        pack = prep.load_prepared(self.config)
        self.assertEqual(pack.manifest['version'], 3); self.assertIsNone(pack.sounds)
        self.assertFalse(serve(handler(), pack, self.stock))

    def test_given_exact_get_and_head_when_served_then_use_pinned_bytes_lengths_and_no_query_writes(self):
        pack = self.prepared(); entry = pack.manifest['sounds']['banks'][self.stock]; before = self.bytes()
        expected = sound_codec.prepare(self.original)[0]
        with patch.object(sound_codec, 'prepare', side_effect=AssertionError('query converted')):
            for method in ('GET', 'HEAD'):
                response = handler(method)
                self.assertTrue(serve(response, pack, entry['path'])); self.assertEqual(response.status, 200)
                self.assertEqual(response.headers['Content-Length'], str(entry['size']))
                self.assertEqual(response.wfile.getvalue(), expected if method == 'GET' else b'')
                self.assertTrue(response.close_connection)
                self.assertTrue(serve(response, pack, self.stock)); self.assertEqual(response.status, 404)
                self.assertTrue(serve(response, pack, 'common_lang/sound/bgm/ios/Ver999_unknown.acb'))
                self.assertEqual(response.status, 404)
        self.assertEqual(self.bytes(), before)
        self.assertFalse(serve(handler('POST'), pack, entry['path']))
        self.assertFalse(serve(handler(), pack, entry['path'].replace('/ios/', '/android/')))

    def test_given_corrupt_replaced_or_escaping_bank_after_binding_when_requested_then_fail_without_fallback(self):
        pack = self.prepared(); entry = pack.manifest['sounds']['banks'][self.stock]
        original = pack.sounds.snapshot.manifest['banks'][self.stock]
        path = pack.sounds.snapshot.directory / original['path']; raw = path.read_bytes()
        for contents in (raw[:-1] + b'X', raw[:-1], raw + b'X'):
            path.write_bytes(contents)
            for method in ('GET', 'HEAD'):
                response = handler(method); self.assertTrue(serve(response, pack, entry['path']))
                self.assertEqual(response.status, 500); self.assertEqual(response.wfile.getvalue(), b'')
        path.unlink(); outside = self.config.root / 'other.acb'; outside.write_bytes(raw); path.symlink_to(outside)
        response = handler(); self.assertTrue(serve(response, pack, entry['path'])); self.assertEqual(response.status, 500)
        with self.assertRaises(ValueError): prep.load_prepared(self.config)

    def test_given_rehashed_wrong_resource_tables_when_loaded_then_refuse_disagreement(self):
        pack = self.prepared()
        for name, field in (('F_RESOURCE_VERSION_MST_LOCALIZE', 'OzT5lSz3'), ('F_RESOURCE_MAP_CHECKSUM_MST', 'JwbkKrjA')):
            table = rules.BY_NAME[name]; entry = pack.manifest['tables'][name]
            path = pack.directory / entry['path']; original = path.read_bytes()
            key = 'Nnb20keZ' if '_MAP_' in name else '9ZCEWn0z'
            raw, _ = patch_master(original, table.key, lambda row: {**row, field: '1'} if row.get(key) == '12' else row, mode=table.cipher)
            path.write_bytes(raw)
            self.edit_manifest(pack, lambda doc: doc['tables'][name].update(size=len(raw), sha256=prep._sha(raw), md5=hashlib.md5(raw).hexdigest()))
            with self.assertRaisesRegex(ValueError, 'disagrees'): prep.load_prepared(self.config)
            path.write_bytes(original); self.edit_manifest(pack, lambda doc: None)

    def test_given_rehashed_invalid_binding_when_loaded_then_refuse(self):
        pack = self.prepared()
        for kind in ('missing', 'version', 'size', 'hash', 'snapshot'):
            def change(doc):
                banks = doc['sounds']['banks']
                if kind == 'missing': banks.clear()
                if kind == 'version': banks[self.stock]['version'] += 1
                if kind == 'size': banks[self.stock]['size'] += 1
                if kind == 'hash': banks[self.stock]['sha256'] = '0' * 64
                if kind == 'snapshot': doc['sounds']['snapshot']['directory'] = '../other'
            self.edit_manifest(pack, change)
            with self.subTest(kind=kind), self.assertRaises(ValueError): prep.load_prepared(self.config)
        self.edit_manifest(pack, lambda doc: None)

    def test_given_cli_binding_when_run_then_emit_json_and_require_flag_only_for_prepare_data(self):
        self.fixture(); self.install(); sound_snapshots.prepare(self.config)
        script = '''
import io,json,sys
from contextlib import redirect_stdout,redirect_stderr
sys.path[:0]=sys.argv[1:3]
from ios_server.cli import main
out=io.StringIO()
with redirect_stdout(out):code=main(['prepare-data','--sounds','--root',sys.argv[3],'--data',sys.argv[4]])
assert code==0 and json.loads(out.getvalue())['sound_delivery_ready']
with redirect_stderr(io.StringIO()):
    try:main(['verify-data','--sounds'])
    except SystemExit as exc:assert exc.code==2
    else:raise AssertionError('query accepted preparation flag')
assert not {'capture_server','data_paths','player_state'}&set(sys.modules)
'''
        result = self.child(script, str(self.config.root), str(self.config.data))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_given_stale_or_corrupt_bound_sound_when_engine_starts_then_refuse_before_state_import_and_unlock(self):
        pack = self.prepared(); self.saved(1000)
        prep.prepare_data(self.config)
        for relative in ('mst_decoded', 'text_decoded'):
            (self.config.data / relative).mkdir(parents=True, exist_ok=True)
        script = '''
import sys
from pathlib import Path
sys.path[:0]=sys.argv[1:3]
from ios_server.config import Configuration
from ios_server.engine import Engine
from ios_server.runtime import InstanceLock
config=Configuration(Path(sys.argv[3]),Path(sys.argv[4]))
before=config.state_file.read_bytes()
def unexpected(name):raise AssertionError('state imported before sound validation')
engine=Engine(config,prepared=True,import_module=unexpected)
try:engine.initialize()
except ValueError:pass
else:raise AssertionError('invalid sounds accepted')
assert engine.tables is None and config.state_file.read_bytes()==before
assert not {'capture_server','player_state','data_paths'}&set(sys.modules)
with InstanceLock(config.root):pass
'''
        source = self.android.read_bytes()
        self.android.write_bytes(audio.acb([audio.hca(0)]))
        done = self.child(script, str(self.config.root), str(self.config.data))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.android.write_bytes(source)
        entry = pack.sounds.snapshot.manifest['banks'][self.stock]
        (pack.sounds.snapshot.directory / entry['path']).write_bytes(b'corrupt')
        done = self.child(script, str(self.config.root), str(self.config.data))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_given_prepared_engine_when_initialized_then_advertised_sound_tables_and_exact_assets_agree(self):
        self.fixture(); self.install()
        for relative in ('mst_decoded', 'text_decoded', 'cpk_extract'):
            (self.config.data / relative).mkdir(parents=True, exist_ok=True)
        engine_harness.IosServerBehavior.write_masters(self, self.config.data / 'mst_decoded')
        prefix = '''
import json,os,sys
from pathlib import Path
sys.path[:0]=sys.argv[1:3]
from ios_server.config import Configuration
from ios_server.engine import Engine
config=Configuration(Path(sys.argv[3]),Path(sys.argv[4]))
'''
        done = self.child(prefix + '''
engine=Engine(config)
try:engine.initialize_campaign()
finally:engine.close()
''', str(self.config.root), str(self.config.data))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        sound_snapshots.prepare(self.config); prep.prepare_data(self.config, sounds=True)
        done = self.child(prefix + '''
from local_game import LocalGame
import ffbe_crypto as crypto
engine=Engine(config,prepared=True)
try:
    server=engine.initialize();pack=engine.tables
    ep=json.loads((Path(sys.argv[2])/'endpoints.json').read_text())['by_class']['InitializeRequest']
    key=crypto.key16(ep['encode_key'])
    body={'TEAYk6R1':{'z5hB3P01':ep['request_id'],'ytHoz4E2':'1','9K0Pzcpd':'1167'},
          't7n6cVWf':{'qrVcDe48':crypto.cbc_encrypt(key,b'{}',double_pad=True)}}
    response=LocalGame.request(engine,'POST',ep['url'],json.dumps(body));assert response.status==200
    out=json.JSONDecoder().raw_decode(crypto.cbc_decrypt(key,json.loads(response.body)['t7n6cVWf']['qrVcDe48']).decode())[0]
    versions={row['a4hXTIm0']:int(row['wM9AfX6I']) for row in out['c1qYg84Q']}
    assert len(versions)==len(out['c1qYg84Q'])==364
    saved=config.state_file.read_bytes()
    def guard(event,args):
        if event.startswith('socket.'):raise AssertionError('query network')
        if event=='open' and len(args)>2 and isinstance(args[2],int) and args[2]&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):raise AssertionError('query write')
        if event in ('os.mkdir','os.rename','os.remove'):raise AssertionError('query mutation')
    sys.addaudithook(guard)
    for name in ('F_RESOURCE_VERSION_MST_LOCALIZE','F_RESOURCE_CHECKSUM_MST','F_RESOURCE_MAP_VERSION_MST_LOCALIZE','F_RESOURCE_MAP_CHECKSUM_MST'):
        entry=pack.manifest['tables'][name];assert versions[name]==entry['version']
        response=LocalGame.request(engine,'GET','/'+entry['path']);assert response.body==pack.files[entry['path']]
    for stock,entry in pack.manifest['sounds']['banks'].items():
        for method in ('GET','HEAD'):
            response=LocalGame.request(engine,method,'/'+entry['path']);assert response.status==200
            assert response.headers['Content-Length']==str(entry['size'])
            assert response.body==(pack.sounds.read(entry['path']) if method=='GET' else b'')
        assert LocalGame.request(engine,'GET','/'+stock).status==404
    assert LocalGame.request(engine,'GET','/common_lang/sound/se/ios/Ver999_unknown.acb').status==404
    assert LocalGame.request(engine,'GET','/common_lang/sound/se/ios/%2e%2e/private.acb').status==400
    assert config.state_file.read_bytes()==saved
finally:engine.close()
assert server.State.native_tables is None
''', str(self.config.root), str(self.config.data))
        self.assertEqual(done.returncode, 0, done.stdout[-4000:] + done.stderr)


if __name__ == '__main__':
    unittest.main()
