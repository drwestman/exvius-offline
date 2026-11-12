"""BDD for complete native coverage, snapshot upgrades and exact version delivery."""
import copy
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_ios_preparation as harness
import test_ios_native_labels as label_harness
import test_ios_server as engine_harness
from ios_server import preparation as prep, native_tables as rules, native_registry as registry
from ios_server.table_codec import master_rows, patch_master, normalize_master
from ios_server.table_delivery import serve


class CompleteTableCodecs(unittest.TestCase):
    def test_given_native_registry_when_inspected_then_cover_all_registered_cipher_and_text_families(self):
        doc,digest=registry.definitions()
        self.assertEqual(digest,rules.REGISTRY_SHA256)
        self.assertEqual(len(doc['tables']),364)
        self.assertEqual(sum(t.localized for t in rules.TABLES),145)
        self.assertEqual(sum(not t.localized and t.cipher=='ecb' for t in rules.TABLES),62)
        self.assertEqual(sum(not t.localized and t.cipher=='cbc' for t in rules.TABLES),157)
        for table in rules.LABEL_INPUT_TABLES:
            full=rules.BY_NAME[table.name]
            self.assertEqual((full.token,full.key,full.localized),(table.token,table.key,table.localized))

    def test_given_ecb_json_master_when_patched_then_preserve_padding_and_untouched_lines(self):
        raw=harness.master('fixture1',[{'id':'1','value':'old'},{'id':'2','value':'keep'}],mode='ecb')
        def update(row):
            if row['id']=='1': row['value']='new'
            return row
        out,changed=patch_master(raw,'fixture1',update,mode='ecb')
        rows=master_rows(out,'fixture1',mode='ecb')
        self.assertEqual(changed,1)
        self.assertEqual([row[2] for row in rows],[False,True])
        self.assertEqual(rows[0][1]['value'],'new')
        self.assertEqual(out.splitlines()[1],raw.splitlines()[1])
        self.assertNotIn(b'\r',out)
        with self.assertRaises(ValueError): master_rows(raw,'fixture1',mode='cbc')

    def test_given_passthrough_master_when_normalized_then_retain_encrypted_records_and_reject_mixed_cipher(self):
        for mode in ('cbc','ecb'):
            raw=harness.master('fixture1',[{'id':'1'},{'id':'2'}],mode=mode)
            self.assertEqual(normalize_master(raw,'fixture1',mode=mode).splitlines(),raw.splitlines())
        mixed=harness.master('fixture1',[{'id':'1'}])+harness.master('fixture1',[{'id':'2'}],mode='ecb')
        for mode in ('cbc','ecb'):
            with self.assertRaises(ValueError): normalize_master(mixed,'fixture1',mode=mode)

    def test_given_duplicate_token_or_bad_cipher_when_registry_loads_then_fail_visibly(self):
        doc,_=registry.definitions()
        for change in ('token','cipher'):
            candidate=copy.deepcopy(doc);names=list(candidate['tables'])
            if change=='token': candidate['tables'][names[0]]['token']=candidate['tables'][names[1]]['token']
            else: candidate['tables'][names[0]]['cipher']='unknown'
            with patch.object(Path,'read_bytes',return_value=json.dumps(candidate).encode()),self.assertRaises(ValueError):
                registry.definitions()


class CompleteTablePreparation(unittest.TestCase):
    setUp=harness.NativePreparation.setUp
    fixture=harness.NativePreparation.fixture
    source=harness.NativePreparation.source
    pointer=harness.NativePreparation.pointer
    assert_shared=harness.NativePreparation.assert_shared
    saved=label_harness.NativeLabelPreparation.saved

    def version_file(self): return Path(self.config.engine_environment()['VERSION_TABLE_XML'])

    def test_given_complete_snapshot_when_projected_then_advertise_only_unique_published_versions(self):
        self.fixture();prep.prepare_data(self.config);pack=prep.load_prepared(self.config)
        spec={'c1qYg84Q':[{'a4hXTIm0':rules.INDEX.name,'wM9AfX6I':'999'},
            {'a4hXTIm0':rules.INDEX.name,'wM9AfX6I':'1'},{'a4hXTIm0':'F_UNKNOWN','wM9AfX6I':'2'}]}
        original=copy.deepcopy(spec);out=pack.project_versions(spec)
        self.assertEqual(spec,original)
        self.assertEqual(len(out['c1qYg84Q']),364)
        self.assertEqual({row['a4hXTIm0'] for row in out['c1qYg84Q']},rules.BY_NAME.keys())
        for row in out['c1qYg84Q']:
            self.assertIsNotNone(pack.lookup(rules.BY_NAME[row['a4hXTIm0']].path(row['wM9AfX6I'])))
        self.assertEqual(pack.manifest['preparation']['coverage']['unregistered_localized'],['F_TEXT_CRAFT'])

    def test_given_global_version_rows_when_prepared_versions_project_then_preserve_bootstrap_metadata(self):
        self.fixture(); prep.prepare_data(self.config); pack = prep.load_prepared(self.config)
        globals = [{'a4hXTIm0': name, 'wM9AfX6I': value, 'keep': 'canonical'} for name, value in (
            ('F_MST_VERSION', '1'), ('F_RSC_VERSION', '2'),
            ('F_APP_VERSION_IOS', '1167'), ('F_APP_VERSION_AND', '0'))]
        spec = {'c1qYg84Q': globals + [{'a4hXTIm0': 'F_UNKNOWN', 'wM9AfX6I': '99'}]}
        original = copy.deepcopy(spec)
        out = pack.project_versions(spec)
        self.assertEqual(spec, original)
        by_name = {row['a4hXTIm0']: row for row in out['c1qYg84Q']}
        for row in globals:
            self.assertEqual(by_name.get(row['a4hXTIm0']), row)
        self.assertEqual(set(by_name), set(rules.BY_NAME) | {row['a4hXTIm0'] for row in globals})
        self.assertEqual(len(by_name), len(out['c1qYg84Q']))
        for name, row in pack.manifest['tables'].items():
            self.assertEqual(by_name[name]['wM9AfX6I'], str(row['version']))

    def test_given_upfront_pack_size_differs_when_prepared_then_match_served_bytes_and_detect_source_changes(self):
        self.fixture()
        def write(name, rows):
            table = rules.BY_NAME[name]
            self.source(table).write_bytes(harness.master(table.key, rows, mode=table.cipher))
        resource = rules.BY_NAME['F_RESOURCE_MST']
        rows = [row for _, row, _ in master_rows(self.source(resource).read_bytes(), resource.key)]
        rows.append({'9ZCEWn0z': '900', '81fTkEDP': 'PRE_TUTO', '3LHdc6Qa': 'resources', 'pJ56sAEo': 'patched.cpk'})
        write(resource.name, rows)
        versions = rules.BY_NAME['F_RESOURCE_VERSION_MST_LOCALIZE']
        rows = [row for _, row, _ in master_rows(self.source(versions).read_bytes(), versions.key)]
        rows.append({'9ZCEWn0z': '900', 'OzT5lSz3': '5', '86SWOBTb': '6'})
        write(versions.name, rows)
        checksum = rules.BY_NAME['F_RESOURCE_CHECKSUM_MST']
        write(checksum.name, [{'9ZCEWn0z': '900', 'JwbkKrjA': '1', 'MLOSu5E0': '2', 'mYtcPkQQ': 'unchanged'}])
        base = self.native / 'common_lang/sd/resources/Ver5_patched.cpk'
        english = self.native / 'en/sd/resources/Ver6_patched.cpk'
        for path, raw in ((base, b'CPK base'), (english, b'CPK english')):
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        prep.prepare_data(self.config); snapshot = prep.load_prepared(self.config)
        row = master_rows(snapshot.lookup(snapshot.manifest['tables'][checksum.name]['path']), checksum.key)[0][1]
        self.assertEqual(row, {'9ZCEWn0z': '900', 'JwbkKrjA': '8', 'MLOSu5E0': '11', 'mYtcPkQQ': 'unchanged'})
        self.assertEqual(base.read_bytes(), b'CPK base'); self.assertEqual(english.read_bytes(), b'CPK english')
        english.write_bytes(b'CPK changed')  # same length; freshness must include bytes
        self.assertFalse(prep.verify_data(self.config)['ok'])

    def upfront_pack(self):
        self.fixture()
        checksum = rules.BY_NAME['F_RESOURCE_CHECKSUM_MST']
        self.source(checksum).write_bytes(harness.master(checksum.key,
            [{'9ZCEWn0z': '1', 'JwbkKrjA': '1', 'MLOSu5E0': '0', 'mYtcPkQQ': '991'}]))
        path = self.native / 'common_lang/sd/resources/Ver8_resources.cpk'
        path.parent.mkdir(parents=True); path.write_bytes(b'CPK base')
        return path, checksum

    def test_given_background_summon_dependencies_when_prepared_then_preload_exact_packs_and_bind_sizes(self):
        self.fixture()
        resource, versions, checksums = (rules.BY_NAME[name] for name in
            ('F_RESOURCE_MST', 'F_RESOURCE_VERSION_MST_LOCALIZE', 'F_RESOURCE_CHECKSUM_MST'))
        rows = {t.name: [row for _, row, _ in master_rows(self.source(t).read_bytes(), t.key)]
                for t in (resource, versions, checksums)}
        cases = (('900', 'gacha', 'gacha1_common.cpk', 'common_lang', 'OzT5lSz3', 'JwbkKrjA'),
                 ('901', 'gacha', 'gacha1.cpk', 'en', '86SWOBTb', 'MLOSu5E0'),
                 ('902', 'monster', 'monster3_common.cpk', 'common_lang', 'OzT5lSz3', 'JwbkKrjA'),
                 ('903', 'gacha', 'unrelated.cpk', 'common_lang', 'OzT5lSz3', 'JwbkKrjA'))
        for identity, directory, name, locale, version_field, size_field in cases:
            rows[resource.name].append({'9ZCEWn0z': identity, '3LHdc6Qa': directory,
                                       'pJ56sAEo': name, '81fTkEDP': 'BACKGROUND'})
            rows[versions.name].append({'9ZCEWn0z': identity, version_field: '7'})
            rows[checksums.name].append({'9ZCEWn0z': identity, size_field: '1', 'mYtcPkQQ': 'android'})
            path = self.native / f'{locale}/sd/{directory}/Ver7_{name}'
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'CPK fixture')
        for table in (resource, versions, checksums):
            self.source(table).write_bytes(harness.master(table.key, rows[table.name]))
        before = {p: p.read_bytes() for p in self.config.data.rglob('*') if p.is_file()}
        prep.prepare_data(self.config); pack = prep.load_prepared(self.config)
        def published(table):
            return {row['9ZCEWn0z']: row for _, row, _ in
                    master_rows(pack.lookup(pack.manifest['tables'][table.name]['path']), table.key)
                    if '9ZCEWn0z' in row}
        resources, sizes = published(resource), published(checksums)
        for identity, _directory, _name, _locale, _version, field in cases[:3]:
            self.assertEqual(resources[identity]['81fTkEDP'], 'TUTO')
            self.assertEqual(sizes[identity][field], str(len(b'CPK fixture')))
            self.assertEqual(sizes[identity]['mYtcPkQQ'], 'android')
            self.assertIn(identity + ':' + field, pack.manifest['sources']['upfront']['files'])
        self.assertEqual(resources['903']['81fTkEDP'], 'BACKGROUND')
        self.assertEqual(sizes['903']['JwbkKrjA'], '1')
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_given_exact_overlay_pack_when_prepared_then_size_and_provenance_follow_served_overlay(self):
        base, checksum = self.upfront_pack()
        overlay = self.config.data / 'overlay/common_lang/sd/resources/Ver8_resources.cpk'
        overlay.parent.mkdir(parents=True); overlay.write_bytes(b'CPK overlay')
        prep.prepare_data(self.config); snapshot = prep.load_prepared(self.config)
        row = master_rows(snapshot.lookup(snapshot.manifest['tables'][checksum.name]['path']), checksum.key)[0][1]
        self.assertEqual((row['JwbkKrjA'], row['mYtcPkQQ']), ('11', '991'))
        record = snapshot.manifest['sources']['upfront']['files']['1:JwbkKrjA']
        self.assertEqual(record['path'], overlay.relative_to(self.config.data).as_posix())
        self.assertEqual(record['sha256'], hashlib.sha256(b'CPK overlay').hexdigest())
        self.assertEqual(base.read_bytes(), b'CPK base')

    def test_given_escaping_upfront_pack_when_preparing_then_preserve_current_snapshot(self):
        base, _ = self.upfront_pack()
        prep.prepare_data(self.config); before = self.pointer().read_bytes()
        outside = self.root / 'outside.cpk'; outside.write_bytes(b'private')
        base.unlink(); base.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'escapes shared content'):
            prep.prepare_data(self.config)
        self.assertEqual(self.pointer().read_bytes(), before)
        self.assertEqual(outside.read_bytes(), b'private')

    def test_given_higher_registered_floor_when_prepared_then_advance_above_it_without_changing_source_identity(self):
        self.fixture();target=rules.ECONOMY_TABLES[0]
        path=self.version_file();text=path.read_text()
        path.write_text(text.replace('name="key'+target.name+'">10','name="key'+target.name+'">230010'))
        prep.prepare_data(self.config);pack=prep.load_prepared(self.config);entry=pack.manifest['tables'][target.name]
        self.assertEqual((entry['source_version'],entry['version_floor'],entry['version']),(10,230010,440010))
        self.assertTrue(prep.verify_data(self.config)['ok'])
        path.write_text(text)
        prep.prepare_data(self.config);new=prep.load_prepared(self.config)
        self.assertGreater(new.manifest['tables'][target.name]['version'],entry['version'])
        self.assertTrue(prep.verify_data(self.config)['ok'])

    def test_given_invalid_registrations_when_prepared_then_keep_active_snapshot(self):
        self.fixture();prep.prepare_data(self.config);before=self.pointer().read_bytes()
        path=self.version_file();original=path.read_text();name=rules.TABLES[0].name
        cases=[original.replace('<string name="key'+name+'">10</string>',''),
            original.replace('</map>','<string name="keyF_UNKNOWN">1</string></map>'),
            original.replace('</map>','<string name="key'+name+'">10</string></map>'),'<map>broken']
        for raw in cases:
            path.write_text(raw)
            with self.assertRaisesRegex(ValueError,'registry'):prep.prepare_data(self.config)
            self.assertFalse(prep.verify_data(self.config)['ok'])
            self.assertEqual(self.pointer().read_bytes(),before)
            self.assertIsNotNone(prep.load_prepared(self.config))

    def test_given_overflowing_version_floor_when_prepared_then_refuse_without_publishing(self):
        self.fixture();prep.prepare_data(self.config);before=self.pointer().read_bytes()
        path=self.version_file();name=rules.TABLES[0].name
        path.write_text(path.read_text().replace('name="key'+name+'">10','name="key'+name+'">2147483647'))
        with self.assertRaisesRegex(ValueError,'out of range'):prep.prepare_data(self.config)
        self.assertEqual(self.pointer().read_bytes(),before)

    def test_given_missing_passthrough_table_when_prepared_then_refuse_incomplete_coverage(self):
        self.fixture();prep.prepare_data(self.config);before=self.pointer().read_bytes()
        table=next(t for t in rules.TABLES if not t.localized and t.cipher=='ecb')
        self.source(table).unlink()
        with self.assertRaisesRegex(ValueError,'Missing native'):prep.prepare_data(self.config)
        self.assertEqual(self.pointer().read_bytes(),before)

    def test_given_unknown_source_token_when_prepared_then_do_not_silently_omit_it(self):
        self.fixture();prep.prepare_data(self.config);before=self.pointer().read_bytes()
        (self.native/'mst/Ver10_unknown0.dat').write_bytes(b'not an allowed table')
        with self.assertRaisesRegex(ValueError,'Unmapped native'):prep.prepare_data(self.config)
        self.assertEqual(self.pointer().read_bytes(),before)

    def test_given_undeclared_localized_index_entry_when_prepared_then_refuse_new_unknown_metadata(self):
        self.fixture();prep.prepare_data(self.config);before=self.pointer().read_bytes()
        rows=[row for _,row,_ in master_rows(self.source(rules.INDEX).read_bytes(),rules.INDEX.key)]
        rows.append({'a4hXTIm0':'F_TEXT_FUTURE','00zAYGYS':'1'})
        self.source(rules.INDEX).write_bytes(harness.master(rules.INDEX.key,rows))
        with self.assertRaisesRegex(ValueError,'Unmapped localized'):prep.prepare_data(self.config)
        self.assertEqual(self.pointer().read_bytes(),before)

    def label_snapshot(self):
        sources,records,_,context,labels=prep._inputs(self.config)
        outputs,versions,changes=rules.build(sources,1,tables=rules.LABEL_TABLES,labels=labels,economy=context['economy']['settings'])
        context={key:context[key] for key in ('economy','labels')}
        sources={'tables':{table.name:records['tables'][table.name] for table in rules.LABEL_INPUT_TABLES},'documents':records['documents']}
        manifest={'version':2,'scope':'native-tables','reference_commit':prep.REVIVAL_COMMIT,'source_root':str(self.config.data),
            'pipeline_version':2,'generation':1,'fingerprint':'b'*64,'sources':sources,'preparation':context,'tables':{}}
        for table in rules.LABEL_TABLES:
            raw=outputs[table.name]
            manifest['tables'][table.name]={'path':table.path(versions[table.name]),'version':versions[table.name],
                'source_version':10,'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                'md5':hashlib.md5(raw).hexdigest(),'changed_rows':changes[table.name]}
        prep._publish(self.config,manifest,outputs)

    def test_given_35_table_snapshot_when_upgraded_then_preserve_old_bytes_and_publish_complete_generation(self):
        self.fixture();self.label_snapshot();old=prep.load_prepared(self.config)
        self.assertEqual(len(old.files),35)
        partial=old.project_versions({'c1qYg84Q':[{'a4hXTIm0':'F_UNKNOWN','wM9AfX6I':'7'}]})
        self.assertIn({'a4hXTIm0':'F_UNKNOWN','wM9AfX6I':'7'},partial['c1qYg84Q'])
        with self.assertRaisesRegex(ValueError,'Complete native'):prep.open_prepared(self.config)
        report=prep.prepare_data(self.config);new=prep.load_prepared(self.config)
        self.assertEqual((report['generation'],report['tables']),(2,364))
        for name,row in old.manifest['tables'].items():
            self.assertGreater(new.manifest['tables'][name]['version'],row['version'])
            self.assertEqual((old.directory/row['path']).read_bytes(),old.files[row['path']])

    def test_given_prepared_consumer_when_policy_is_provisional_or_stale_then_require_explicit_preparation(self):
        self.fixture();prep.prepare_data(self.config)
        with self.assertRaisesRegex(ValueError,'Initialize this campaign'):prep.open_prepared(self.config)
        self.saved(5);prep.prepare_data(self.config);self.assertEqual(len(prep.open_prepared(self.config).files),364)
        self.saved(2)
        with self.assertRaisesRegex(ValueError,'stale'):prep.open_prepared(self.config)

    def test_given_exact_table_get_and_head_when_served_then_preserve_headers_and_never_fallback(self):
        self.fixture();prep.prepare_data(self.config);pack=prep.load_prepared(self.config)
        relative=pack.manifest['tables'][rules.INDEX.name]['path'];raw=pack.lookup(relative)
        for method in ('GET','HEAD'):
            handler=SimpleNamespace(command=method,wfile=io.BytesIO(),headers={})
            handler.send_response=lambda status:setattr(handler,'status',status)
            handler.send_header=lambda name,value:handler.headers.update({name:value})
            handler.end_headers=lambda:None
            self.assertTrue(serve(handler,pack,relative));self.assertEqual(handler.status,200)
            self.assertEqual(handler.headers['Content-Length'],str(len(raw)))
            self.assertEqual(handler.wfile.getvalue(),raw if method=='GET' else b'')
            self.assertTrue(serve(handler,pack,rules.INDEX.path(10)));self.assertEqual(handler.status,404)
            self.assertFalse(serve(handler,pack,'common_lang/sd/pack.cpk'))
        handler.command='POST';self.assertFalse(serve(handler,pack,relative))


class PreparedEngineDelivery(unittest.TestCase):
    setUp=harness.NativePreparation.setUp
    fixture=harness.NativePreparation.fixture
    source=harness.NativePreparation.source
    pointer=harness.NativePreparation.pointer
    assert_shared=harness.NativePreparation.assert_shared
    child=engine_harness.IosServerBehavior.child

    def test_given_missing_or_provisional_snapshot_when_engine_starts_then_refuse_before_loading_state_and_release_lock(self):
        self.fixture()
        for relative in ('mst_decoded','text_decoded','client/files/common_lang'):
            (self.config.data/relative).mkdir(parents=True,exist_ok=True)
        script='''
import sys
from pathlib import Path
sys.path[:0]=sys.argv[1:3]
from ios_server.config import Configuration
from ios_server.engine import Engine
from ios_server.runtime import InstanceLock
config=Configuration(Path(sys.argv[3]),Path(sys.argv[4]))
def unexpected(name):raise AssertionError('engine imported before snapshot validation')
engine=Engine(config,prepared=True,import_module=unexpected)
try:engine.initialize()
except ValueError as exc:assert sys.argv[5] in str(exc),str(exc)
else:raise AssertionError('unready snapshot accepted')
assert not {'capture_server','data_paths','player_state'} & set(sys.modules)
assert not config.state_file.exists()
assert engine.tables is None
with InstanceLock(config.root):pass
'''
        for message in ('Complete native','Initialize this campaign'):
            if message.startswith('Initialize'):prep.prepare_data(self.config)
            done=self.child(script,str(self.config.root),str(self.config.data),message)
            self.assertEqual(done.returncode,0,done.stdout+done.stderr)

    def test_given_prepared_engine_when_initialized_then_deliver_every_advertised_version_without_writes(self):
        self.fixture()
        static=self.config.data
        for relative in ('mst_decoded','text_decoded','cpk_extract','client/files/common_lang'):
            (static/relative).mkdir(parents=True,exist_ok=True)
        engine_harness.IosServerBehavior.write_masters(self,static/'mst_decoded')
        prefix='''
import sys,json
from pathlib import Path
sys.path[:0]=sys.argv[1:3]
from ios_server.config import Configuration
from ios_server.engine import Engine
config=Configuration(Path(sys.argv[3]),Path(sys.argv[4]))
'''
        done=self.child(prefix+'''
engine=Engine(config)
try: engine.initialize_campaign()
finally: engine.close()
''',str(self.config.root),str(self.config.data))
        self.assertEqual(done.returncode,0,done.stdout[-4000:]+done.stderr)
        prep.prepare_data(self.config)
        done=self.child(prefix+'''
from local_game import LocalGame
import os
import ffbe_crypto as crypto
engine=Engine(config,prepared=True)
try:
    server=engine.initialize()
    assert server.State.native_tables is engine.tables
    ep=json.loads((Path(sys.argv[2])/'endpoints.json').read_text())['by_class']['InitializeRequest']
    key=crypto.key16(ep['encode_key'])
    body={'TEAYk6R1':{'z5hB3P01':ep['request_id'],'ytHoz4E2':'1','9K0Pzcpd':'1167'},
          't7n6cVWf':{'qrVcDe48':crypto.cbc_encrypt(key,b'{}',double_pad=True)}}
    response=LocalGame.request(engine,'POST',ep['url'],json.dumps(body))
    assert response.status==200
    encoded=json.loads(response.body)['t7n6cVWf']['qrVcDe48']
    out=json.JSONDecoder().raw_decode(crypto.cbc_decrypt(key,encoded).decode())[0]
    versions={row['a4hXTIm0']:int(row['wM9AfX6I']) for row in out['c1qYg84Q']}
    assert len(versions)==len(out['c1qYg84Q'])==len(engine.tables.manifest['tables'])+2
    assert {name:value for name,value in versions.items() if name not in engine.tables.manifest['tables']}=={'F_MST_VERSION':1,'F_RSC_VERSION':1}
    saved=config.state_file.read_bytes()
    def guard(event,args):
        if event.startswith('socket.'):raise AssertionError('asset query opened network')
        if event=='open' and len(args)>2 and isinstance(args[2],int) and args[2] & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):
            raise AssertionError('asset query wrote a file')
        if event in ('os.mkdir','os.remove','os.rename'):raise AssertionError('asset query mutated filesystem')
    sys.addaudithook(guard)
    for name,entry in engine.tables.manifest['tables'].items():
        assert versions[name]==entry['version']
        for method in ('GET','HEAD'):
            response=LocalGame.request(engine,method,'/'+entry['path'])
            assert response.status==200,(method,name,response.status)
            assert response.headers['Content-Length']==str(entry['size'])
            assert response.body==(engine.tables.lookup(entry['path']) if method=='GET' else b'')
    entry=engine.tables.manifest['tables']['F_LOCALIZED_TEXT_MST']
    token=Path(entry['path']).name.split('_',1)[1]
    assert LocalGame.request(engine,'GET','/mst/Ver10_'+token).status==404
    assert LocalGame.request(engine,'GET','/mst/%2e%2e/private.json').status==400
    assert config.state_file.read_bytes()==saved
finally:
    engine.close()
assert server.State.native_tables is None
''',str(self.config.root),str(self.config.data))
        self.assertEqual(done.returncode,0,done.stdout[-5000:]+done.stderr)


if __name__=='__main__':unittest.main()
