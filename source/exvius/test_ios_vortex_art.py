"""BDD for explicit native Vortex packs and atomic table/asset publication."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import unittest
from unittest.mock import patch
import zlib

import test_ios_preparation as harness
import test_ios_native_labels as labels
import test_ios_server as engine_harness
from ios_server import cpk, vortex_art as art, preparation as prep, native_tables as rules
from ios_server.config import Configuration
from ios_server.runtime import InstanceLock
from ios_server.table_codec import master_rows, patch_master
from ios_server.table_delivery import serve


def png(value=1):
    def chunk(kind, raw):
        return struct.pack('>I', len(raw)) + kind + raw + struct.pack('>I', zlib.crc32(kind + raw))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(bytes([0, value, value, value]))) + chunk(b'IEND', b''))


def fixture_pack(*, alignment=8, directory='', crc=0, indexed=0, fixed_sizes=False):
    """Tiny native layout with compressed payload metadata and duplicate shipped names."""
    blobs = [('Original.png', b'original-compressed', 100), ('original.PNG', b'other-original', 101)]
    blobs.append(('spd_bn_list_dummy.png', png(), len(png())))
    columns = [('DirName', 0x30, 10, directory), ('FileName', 0x50, 10, 0),
               ('FileSize', 0x50, 4, 0), ('ExtractSize', 0x50, 4, 0),
               ('FileOffset', 0x50, 6, 0), ('ID', 0x50, 4, 0), ('UserString', 0x30, 10, '<NULL>')]
    if fixed_sizes: columns[2] = ('FileSize', 0x30, 4, 0)
    content, rows = bytearray(), []
    for index, (name, blob, extract) in enumerate(blobs):
        content.extend(b'\0' * (-len(content) % 8))
        rows.append({'FileName': name, 'FileSize': len(blob), 'ExtractSize': extract,
                     'FileOffset': 2048 + len(content), 'ID': index})
        content.extend(blob)
    toc = cpk.encode_table('CpkTocInfo', columns, rows)
    values = {'FileSize': 0, 'TotalDataSize': 0, 'ContentOffset': 4096, 'ContentSize': len(content),
              'TocOffset': 2048, 'TocSize': len(toc) + 16, 'Files': len(rows), 'Align': alignment,
              'ItocOffset': indexed, 'EnableFileCrc': crc, 'EnabledPackedSize': 0, 'EnabledDataSize': 0}
    hcols = [(name, 0x10 if name in ('FileSize', 'TotalDataSize') else 0x50, 6, 0) for name in values]
    header = cpk.encode_table('CpkHeader', hcols, [values])
    out = b'CPK ' + struct.pack('<IQ', 0, len(header)) + cpk.mask(header)
    out += b'\0' * (2048 - len(out)) + b'TOC ' + struct.pack('<IQ', 0, len(toc)) + cpk.mask(toc)
    return out + b'\0' * (4096 - len(out)) + content


def payloads(raw):
    head, _, _, rows = cpk.inspect(raw)
    return [(row['FileName'], row['ExtractSize'], row['ID'],
             raw[head['TocOffset'] + row['FileOffset']:head['TocOffset'] + row['FileOffset'] + row['FileSize']]) for row in rows]


class BannerCpk(unittest.TestCase):
    def test_given_native_utf_columns_when_round_tripped_then_keep_zero_constant_and_row_values(self):
        columns = [('zero', 0x10, 6, 0), ('name', 0x30, 10, 'constant'),
                   ('id', 0x50, 4, 0), ('data', 0x50, 11, 0)]
        raw = cpk.encode_table('Fixture', columns, [{'id': 7, 'data': b'bytes'}, {'id': 9, 'data': b''}])
        self.assertEqual(cpk.mask(cpk.mask(raw)), raw)
        name, result, rows = cpk.table(cpk.mask(raw))
        self.assertEqual((name, result), ('Fixture', columns))
        self.assertEqual(rows, [{'zero': 0, 'name': 'constant', 'id': 7, 'data': b'bytes'},
                                {'zero': 0, 'name': 'constant', 'id': 9, 'data': b''}])

    def test_given_flat_pack_when_extended_then_preserve_original_duplicates_compression_and_payloads(self):
        source = fixture_pack()
        out, added = cpk.rebuild(source, {'new.png': png(2), 'ORIGINAL.PNG': png(3)})
        header, _, _, rows = cpk.inspect(out)
        self.assertEqual(added, ['new.png'])
        self.assertEqual(header['FileSize'], len(out))
        self.assertEqual(header['TotalDataSize'], header['ContentSize'])
        self.assertEqual([row['FileName'].upper() for row in rows], sorted(row['FileName'].upper() for row in rows))
        self.assertEqual([row for row in payloads(out) if row[0] != 'new.png'], payloads(source))
        self.assertEqual(next(row[3] for row in payloads(out) if row[0] == 'new.png'), png(2))
        self.assertEqual(out[16:20], cpk.mask(b'@UTF'))

    def test_given_truncated_or_unsupported_pack_when_inspected_then_fail_visibly(self):
        raw = fixture_pack()
        cases = [b'', raw[:15], raw[:-1], raw.replace(b'TOC ', b'BAD ', 1),
                 fixture_pack(alignment=16), fixture_pack(directory='nested'),
                 fixture_pack(crc=1), fixture_pack(indexed=64), fixture_pack(fixed_sizes=True)]
        for data in cases:
            with self.subTest(size=len(data)), self.assertRaises(ValueError): cpk.inspect(data)
        with self.assertRaises(ValueError): cpk.rebuild(raw, {'bad/name.png': png()})
        with self.assertRaises(ValueError): cpk.rebuild(raw, {'same.png': png(), 'SAME.PNG': png()})


class VortexPreparation(unittest.TestCase):
    setUp = harness.NativePreparation.setUp
    fixture = harness.NativePreparation.fixture
    source = harness.NativePreparation.source
    pointer = harness.NativePreparation.pointer
    saved = labels.NativeLabelPreparation.saved
    child = engine_harness.IosServerBehavior.child

    def artwork(self, managed=False):
        self.fixture(managed)
        self.docs = self.root/'documents'; self.docs.mkdir(exist_ok=True)
        documents = {'event_art.json': {'events': {'1': {'filename': 'event_one.png'}},
                                      'dungeons': {'1': {'filename': 'Original.png'}}},
                     'event_archive.json': {'events': [{'filename': 'event_one.png'}]},
                     'event_history.json': {'added': [{'filename': 'event_missing.png'}]},
                     'raid_archive.json': {'events': [{'menu_background': 'raid.png'}]}}
        for name, doc in documents.items(): (self.docs/name).write_text(json.dumps(doc))
        self.enterContext(patch.object(art, 'HERE', self.docs))
        self.area = self.native/'en/sd/area'; self.area.mkdir(parents=True)
        (self.area/'event_one.png').write_bytes(png())
        (self.area/'raid.png').write_bytes(png(2))
        (self.area/'Original.png').write_bytes(png(3))
        raw = fixture_pack(); (self.native/art.pack_path(461)).write_bytes(raw)
        entries = {art.RESOURCE.name: {'9ZCEWn0z': art.RESOURCE_ID, '81fTkEDP': '',
                                     'pJ56sAEo': art.PACK, '3LHdc6Qa': 'area', 'unrelated': 'keep'},
                   art.VERSIONS.name: {'9ZCEWn0z': art.RESOURCE_ID, 'OzT5lSz3': '0', '86SWOBTb': '461', 'japanese': '100'},
                   art.CHECKSUM.name: {'9ZCEWn0z': art.RESOURCE_ID, 'MLOSu5E0': str(len(raw)), 'other_size': '100'}}
        for table in art.TABLES:
            rows = [row for _, row, _ in master_rows(self.source(table).read_bytes(), table.key)]
            self.source(table).write_bytes(harness.master(table.key, rows + [entries[table.name]]))

    def edit_manifest(self, pack, modify):
        doc = copy.deepcopy(pack.manifest); modify(doc)
        raw = prep._json(doc); (pack.directory/'manifest.json').write_bytes(raw)
        ref = json.loads(self.pointer().read_bytes()); ref['manifest_sha256'] = prep._sha(raw)
        self.pointer().write_bytes(prep._json(ref))

    def test_given_both_layouts_when_art_prepared_then_pack_and_three_tables_publish_together_without_query_writes(self):
        for managed in (False, True):
            with self.subTest(managed=managed):
                self.config = Configuration(self.root/('private-'+str(managed)), self.root/('content-'+str(managed)))
                self.artwork(managed)
                before = {p:p.read_bytes() for p in self.config.data.rglob('*') if p.is_file()}
                modules = set(sys.modules)
                report = prep.prepare_data(self.config, vortex_art=True); pack = prep.load_prepared(self.config)
                self.assertEqual((report['tables'], report['packs'], pack.manifest['version']), (364, 1, 4))
                self.assertEqual(report['preparation']['art'], {'named': 4, 'available': 3, 'missing_added': ['event_missing.png']})
                entry = pack.manifest['packs'][art.PACK]
                self.assertEqual(entry['added'], ['event_one.png', 'raid.png'])
                self.assertEqual(art.resource(pack.lookup(pack.manifest['tables'][art.RESOURCE.name]['path']), art.RESOURCE)['unrelated'], 'keep')
                self.assertEqual(art.resource(pack.lookup(pack.manifest['tables'][art.VERSIONS.name]['path']), art.VERSIONS)['japanese'], '100')
                with patch.object(cpk, 'rebuild', side_effect=AssertionError('query built pack')), \
                     patch.object(Path, 'mkdir', side_effect=AssertionError('query wrote')):
                    self.assertTrue(prep.verify_data(self.config)['ok'])
                self.assertEqual(before, {p:p.read_bytes() for p in self.config.data.rglob('*') if p.is_file()})
                self.assertFalse({'capture_server','ffbe_state','player_state','data_paths'} & (set(sys.modules)-modules))
                self.assertFalse(self.config.state_file.exists())

    def test_given_schema_three_when_upgraded_and_refreshed_then_retain_old_bytes_and_keep_art_enabled(self):
        self.artwork(); prep.prepare_data(self.config); old = prep.load_prepared(self.config)
        prep.prepare_data(self.config, vortex_art=True); pack = prep.load_prepared(self.config)
        self.assertEqual((pack.manifest['generation'], len(pack.files)), (2, 365))
        for relative, raw in old.files.items(): self.assertEqual((old.directory/relative).read_bytes(), raw)
        before = self.pointer().read_bytes()
        self.assertFalse(prep.prepare_data(self.config)['prepared_now'])
        self.assertEqual(self.pointer().read_bytes(), before)
        source = self.area/'event_one.png'; self.assertEqual(len(source.read_bytes()), len(png(2)))
        source.write_bytes(png(2)); self.assertFalse(prep.verify_data(self.config)['ok'])
        self.assertTrue(prep.prepare_data(self.config)['prepared_now']); new = prep.load_prepared(self.config)
        self.assertEqual(new.manifest['version'], 4)
        self.assertGreater(new.manifest['packs'][art.PACK]['version'], pack.manifest['packs'][art.PACK]['version'])
        self.assertTrue(prep.verify_data(self.config)['ok'])

    def test_given_missing_required_image_or_pack_when_preparing_then_preserve_active_generation(self):
        self.artwork(); prep.prepare_data(self.config, vortex_art=True); before = self.pointer().read_bytes()
        for path in (self.area/'event_one.png', self.native/art.pack_path(461)):
            raw = path.read_bytes(); path.unlink()
            with self.assertRaisesRegex(ValueError, 'Missing'): prep.prepare_data(self.config)
            self.assertEqual(self.pointer().read_bytes(), before); self.assertIsNotNone(prep.load_prepared(self.config))
            path.write_bytes(raw)

    def test_given_source_size_mismatch_when_preparing_then_refuse_before_publication(self):
        self.artwork(); prep.prepare_data(self.config); before = self.pointer().read_bytes()
        path = self.native/art.pack_path(461); path.write_bytes(path.read_bytes()+b'extra')
        with self.assertRaisesRegex(ValueError, 'size disagrees'): prep.prepare_data(self.config, vortex_art=True)
        self.assertEqual(self.pointer().read_bytes(), before)

    def test_given_source_symlink_escape_or_invalid_image_when_preparing_then_refuse_without_fallback(self):
        self.artwork(); prep.prepare_data(self.config); before = self.pointer().read_bytes()
        path = self.area/'event_one.png'; path.unlink()
        private = self.config.root/'private.png'; private.write_bytes(png())
        path.symlink_to(private)
        with self.assertRaisesRegex(ValueError, 'escapes'): prep.prepare_data(self.config, vortex_art=True)
        path.unlink(); path.write_bytes(b'invalid PNG')
        with self.assertRaisesRegex(ValueError, 'Invalid Vortex PNG'): prep.prepare_data(self.config, vortex_art=True)
        self.assertEqual(self.pointer().read_bytes(), before)

    def test_given_unsafe_metadata_name_when_preparing_then_do_not_open_it(self):
        self.artwork(); path = self.docs/'event_art.json'
        path.write_text(json.dumps({'events': {'1': {'filename': '../private.png'}}, 'dungeons': {}}))
        with self.assertRaisesRegex(ValueError, 'filename'): prep.prepare_data(self.config, vortex_art=True)
        self.assertFalse(self.pointer().exists())

    def test_given_png_with_corrupt_chunk_when_prepared_then_refuse_despite_valid_signature_and_ending(self):
        self.artwork(); path = self.area/'event_one.png'; raw = bytearray(path.read_bytes())
        raw[45] ^= 1; path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'PNG chunk'): prep.prepare_data(self.config, vortex_art=True)
        self.assertFalse(self.pointer().exists())

    def test_given_missing_added_image_when_it_arrives_then_publish_it_and_clear_the_gap(self):
        self.artwork(); prep.prepare_data(self.config, vortex_art=True)
        (self.area/'event_missing.png').write_bytes(png(5))
        self.assertFalse(prep.verify_data(self.config)['ok'])
        report = prep.prepare_data(self.config); pack = prep.load_prepared(self.config)
        self.assertEqual(report['preparation']['art']['missing_added'], [])
        self.assertIn('event_missing.png', pack.manifest['packs'][art.PACK]['added'])

    def test_given_pack_version_decrease_or_overflow_when_preparing_then_advance_or_refuse_atomically(self):
        self.artwork(); version_file = self.source(art.VERSIONS)
        source = version_file.read_bytes()
        def use(version):
            raw, _ = patch_master(source, art.VERSIONS.key, lambda row:
                dict(row, **{'86SWOBTb': str(version)}) if str(row.get('9ZCEWn0z')) == art.RESOURCE_ID else row)
            version_file.write_bytes(raw)
            (self.native/art.pack_path(version)).write_bytes(fixture_pack())
        use(230461); prep.prepare_data(self.config, vortex_art=True); old = prep.load_prepared(self.config)
        use(461); prep.prepare_data(self.config); new = prep.load_prepared(self.config)
        self.assertGreater(new.manifest['packs'][art.PACK]['version'], old.manifest['packs'][art.PACK]['version'])
        self.assertTrue(prep.verify_data(self.config)['ok'])
        before = self.pointer().read_bytes(); use(2147483647)
        with patch.object(cpk, 'rebuild', side_effect=AssertionError('overflow built pack')), self.assertRaisesRegex(ValueError, 'out of range'):
            prep.prepare_data(self.config)
        self.assertEqual(self.pointer().read_bytes(), before)

    def test_given_pack_write_or_pointer_failure_when_preparing_then_keep_old_generation_and_allow_retry(self):
        self.artwork(); prep.prepare_data(self.config); before = self.pointer().read_bytes()
        original_open = Path.open
        def write(path, *args, **kwargs):
            if path.suffix == '.cpk' and args and args[0] == 'wb': raise OSError('pack disk full')
            return original_open(path, *args, **kwargs)
        with patch.object(Path, 'open', write), self.assertRaisesRegex(OSError, 'disk full'):
            prep.prepare_data(self.config, vortex_art=True)
        self.assertEqual(self.pointer().read_bytes(), before)
        replace = os.replace
        def publish(source, target):
            if Path(target) == self.pointer(): raise OSError('pointer failure')
            return replace(source, target)
        with patch.object(prep.os, 'replace', publish), self.assertRaisesRegex(OSError, 'pointer failure'):
            prep.prepare_data(self.config, vortex_art=True)
        self.assertEqual(self.pointer().read_bytes(), before)
        self.assertTrue(prep.prepare_data(self.config, vortex_art=True)['prepared_now'])
        self.assertTrue(prep.verify_data(self.config)['ok'])

    def test_given_busy_runtime_when_art_preparation_runs_then_refuse(self):
        self.artwork()
        with InstanceLock(self.config.root), self.assertRaisesRegex(RuntimeError, 'Another iOS'):
            prep.prepare_data(self.config, vortex_art=True)
        self.assertFalse(self.pointer().exists())

    def test_given_corrupt_or_escaping_published_pack_when_verified_then_fail_without_repair(self):
        self.artwork(); prep.prepare_data(self.config, vortex_art=True); pack = prep.load_prepared(self.config)
        path = pack.directory/pack.manifest['packs'][art.PACK]['path']; raw = path.read_bytes()
        path.write_bytes(raw[:-1]+b'X')
        self.assertFalse(prep.verify_data(self.config)['ok']); self.assertEqual(path.read_bytes(), raw[:-1]+b'X')
        path.unlink(); outside = self.config.root/'outside.cpk'; outside.write_bytes(raw); path.symlink_to(outside)
        self.assertFalse(prep.verify_data(self.config)['ok'])

    def test_given_rehashed_wrong_checksum_table_when_loaded_then_refuse_pack_disagreement(self):
        self.artwork(); prep.prepare_data(self.config, vortex_art=True); pack = prep.load_prepared(self.config)
        entry = pack.manifest['tables'][art.CHECKSUM.name]
        raw, _ = patch_master(pack.lookup(entry['path']), art.CHECKSUM.key,
            lambda row: dict(row, MLOSu5E0='1') if str(row.get('9ZCEWn0z')) == art.RESOURCE_ID else row)
        (pack.directory/entry['path']).write_bytes(raw)
        def modify(doc): doc['tables'][art.CHECKSUM.name].update(size=len(raw), sha256=prep._sha(raw), md5=hashlib.md5(raw).hexdigest())
        self.edit_manifest(pack, modify)
        with self.assertRaisesRegex(ValueError, 'disagrees'): prep.load_prepared(self.config)

    def test_given_prepared_pack_get_and_head_when_served_then_return_exact_bytes_and_refuse_stock_versions(self):
        self.artwork(); prep.prepare_data(self.config, vortex_art=True); pack = prep.load_prepared(self.config)
        entry = pack.manifest['packs'][art.PACK]
        for method in ('GET', 'HEAD'):
            handler = type('Handler', (), {'command':method, 'wfile':io.BytesIO(), 'headers':{}})()
            handler.send_response = lambda value: setattr(handler, 'status', value)
            handler.send_header = lambda key, value: handler.headers.update({key:value})
            handler.end_headers = lambda: None
            self.assertTrue(serve(handler, pack, entry['path'])); self.assertEqual(handler.status, 200)
            self.assertEqual(handler.wfile.getvalue(), pack.lookup(entry['path']) if method == 'GET' else b'')
            self.assertEqual(handler.headers['Content-Length'], str(entry['size']))
            self.assertTrue(serve(handler, pack, art.pack_path(461))); self.assertEqual(handler.status, 404)
            self.assertFalse(serve(handler, pack, 'common_lang/sd/other.cpk'))

    def test_given_cli_art_option_when_prepared_and_verified_then_emit_one_json_document_and_retain_choice(self):
        self.artwork()
        script = '''
import json,sys,io
from contextlib import redirect_stdout
from pathlib import Path
sys.path[:0]=sys.argv[1:3]
from ios_server import vortex_art
from ios_server.cli import main
vortex_art.HERE=Path(sys.argv[5])
for command,extra in [('prepare-data',['--vortex-art']),('verify-data',[]),('prepare-data',[])]:
    out=io.StringIO()
    with redirect_stdout(out):code=main([command,'--root',sys.argv[3],'--data',sys.argv[4],*extra])
    result=json.loads(out.getvalue());assert code==0 and result['packs']==1,result
assert not {'capture_server','data_paths','player_state'} & set(sys.modules)
'''
        done = self.child(script, str(self.config.root), str(self.config.data), str(self.docs))
        self.assertEqual(done.returncode, 0, done.stdout+done.stderr)
        self.assertFalse(self.config.state_file.exists())

    def test_given_art_engine_when_initialized_then_encrypted_versions_and_native_pack_get_head_agree_without_writes(self):
        self.artwork()
        for relative in ('mst_decoded','text_decoded','client/files/common_lang'):
            (self.config.data/relative).mkdir(parents=True, exist_ok=True)
        engine_harness.IosServerBehavior.write_masters(self, self.config.data/'mst_decoded')
        prefix = '''
import json,os,sys
from pathlib import Path
sys.path[:0]=sys.argv[1:3]
from ios_server.config import Configuration
from ios_server.engine import Engine
from ios_server import vortex_art
vortex_art.HERE=Path(sys.argv[5])
config=Configuration(Path(sys.argv[3]),Path(sys.argv[4]))
'''
        done = self.child(prefix+'''
engine=Engine(config)
try:engine.initialize_campaign()
finally:engine.close()
''', str(self.config.root), str(self.config.data), str(self.docs))
        self.assertEqual(done.returncode, 0, done.stdout+done.stderr)
        prep.prepare_data(self.config, vortex_art=True)
        done = self.child(prefix+'''
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
        if event=='open' and len(args)>2 and isinstance(args[2],int) and args[2] & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):raise AssertionError('query write')
        if event in ('os.mkdir','os.rename','os.remove'):raise AssertionError('query mutation')
    sys.addaudithook(guard)
    for name,entry in pack.manifest['tables'].items():
        assert versions[name]==entry['version']
        response=LocalGame.request(engine,'GET','/'+entry['path'])
        assert response.status==200 and response.body==pack.lookup(entry['path'])
    entry=pack.manifest['packs'][vortex_art.PACK]
    for method in ('GET','HEAD'):
        response=LocalGame.request(engine,method,'/'+entry['path'])
        assert response.status==200 and response.headers['Content-Length']==str(entry['size'])
        assert response.body==(pack.lookup(entry['path']) if method=='GET' else b'')
    assert LocalGame.request(engine,'GET','/'+vortex_art.pack_path(461)).status==404
    assert LocalGame.request(engine,'GET','/en/sd/area/%2e%2e/private.cpk').status==400
    assert config.state_file.read_bytes()==saved
finally:engine.close()
''', str(self.config.root), str(self.config.data), str(self.docs))
        self.assertEqual(done.returncode, 0, done.stdout[-4000:]+done.stderr)


if __name__ == '__main__': unittest.main()
