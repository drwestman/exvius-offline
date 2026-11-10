"""BDD for explicit core native table preparation and immutable verified snapshots."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SOURCE), str(SOURCE/'server')]

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from ffbe_crypto import cbc_encrypt, key16
from ios_server.config import Configuration
from ios_server import native_tables as rules
from ios_server import preparation as prep
from ios_server.runtime import InstanceLock
from ios_server.table_codec import master_rows, patch_master, patch_text, text_lines


def master(key, rows, *, mode='cbc'):
    lines=[]
    for i,row in enumerate(rows):
        plain=json.dumps(row).encode()
        if mode=='cbc':
            lines.append(cbc_encrypt(key16(key),plain,double_pad=bool(i%2)))
        else:
            for _ in range(2 if i%2 else 1):
                n=16-len(plain)%16; plain+=bytes([n])*n
            op=Cipher(algorithms.AES(key16(key)),modes.ECB()).encryptor()
            lines.append(base64.b64encode(op.update(plain)+op.finalize()).decode())
    return ('\r\n'.join(lines)+'\r\n').encode()


def text(key, records, layers=2):
    plain = ('\n'.join(records)+'\n').encode()
    for _ in range(layers):
        n=16-len(plain)%16; plain+=bytes([n])*n
    op=Cipher(algorithms.AES(key16(key)),modes.ECB()).encryptor()
    return base64.b64encode(op.update(plain)+op.finalize())+b'\r\n'


class NativeTableCodec(unittest.TestCase):
    def test_given_mixed_master_padding_when_patched_then_preserve_shapes_and_untouched_lines(self):
        raw=master('abcdefgh',[{'id':'1','reward':'old'},{'id':'2','reward':'keep'}])
        def update(row):
            if row['id']=='1': row['reward']='new'
            return row
        out,changed=patch_master(raw,'abcdefgh',update)
        self.assertEqual(changed,1)
        rows=master_rows(out,'abcdefgh')
        self.assertEqual([row[2] for row in rows],[False,True])
        self.assertEqual(rows[0][1]['reward'],'new')
        self.assertEqual(out.splitlines()[1],raw.splitlines()[1])
        self.assertNotIn(b'\r',out)

    def test_given_multicolumn_text_and_duplicate_shipped_keys_when_extended_then_retain_native_shape(self):
        raw=text('abcdefgh',['original^one^two','original^three^four','custom^old^old'])
        out,changed=patch_text(raw,'abcdefgh',{'custom':'new','added':'Fresh text'})
        lines=text_lines(out,'abcdefgh')
        self.assertEqual(changed,2)
        self.assertEqual(lines[0][1],['original^one^two','original^three^four','custom^new^new'])
        self.assertEqual(lines[1][1],['added^Fresh text^Fresh text'])
        self.assertEqual([row[2] for row in lines],[2,2])
        self.assertNotIn(b'\r',out)

    def test_given_invalid_encrypted_tables_when_read_then_fail_without_synthesizing_rows(self):
        for raw in (b'',b'not-base64\n',b'AAAA\n'):
            with self.subTest(raw=raw), self.assertRaises(ValueError): master_rows(raw,'abcdefgh')
            with self.subTest(raw=raw), self.assertRaises(ValueError): text_lines(raw,'abcdefgh')

    def test_given_non_base64_character_in_otherwise_valid_master_when_read_then_reject_it(self):
        raw=master('abcdefgh',[{'id':'1'}])
        with self.assertRaises(ValueError): master_rows(raw[:4]+b'!'+raw[4:],'abcdefgh')


class NativePreparation(unittest.TestCase):
    def setUp(self):
        work=tempfile.TemporaryDirectory(); self.addCleanup(work.cleanup)
        self.root=Path(work.name)
        self.config=Configuration(self.root/'private',self.root/'content')

    def fixture(self, managed=False):
        static=self.config.data/'static' if managed else self.config.data
        static.mkdir(parents=True,exist_ok=True)
        native=self.config.data/'native' if managed else static/'client/files'
        rows={rules.RESOURCE.name:[
            {'9ZCEWn0z':'1','pJ56sAEo':'resources.cpk','81fTkEDP':''},
            {'9ZCEWn0z':'2','pJ56sAEo':'resources_common.cpk','81fTkEDP':'TUTO'},
            {'9ZCEWn0z':'3','pJ56sAEo':'unversioned.cpk','81fTkEDP':''}],
            rules.VERSIONS.name:[{'9ZCEWn0z':str(i),'OzT5lSz3':v,'86SWOBTb':'0'} for i,v in ((1,'8'),(2,'9'),(3,'0'))],
            rules.QUEST.name:[{'Z34jU7ue':'1','dX6cor8j':'50:1:20:100:0:extra,20:1:3:100:1','keep':'original'}],
            rules.URL.name:[{'gu8McTA6':'GACHA_RATE_URL','G4L0YIB2':'original','en':'<WEB>/old','empty':''},
                            {'gu8McTA6':'OTHER','en':'unchanged'}],
            rules.INDEX.name:[{'a4hXTIm0':t.name,'00zAYGYS':'10','zptmZGqa':'old','MLOSu5E0':'1',
                               '7aj3QkBT':'99'} for t in rules.INPUT_TABLES if t.localized] +
                             [{'a4hXTIm0':'F_TEXT_CRAFT','00zAYGYS':'2','zptmZGqa':'other','MLOSu5E0':'5'}]}
        for table in rules.INPUT_TABLES:
            path=native/table.path(10); path.parent.mkdir(parents=True,exist_ok=True)
            fallback=[{'id':'1','dX6cor8j':'50:1:20:100:1,20:1:3:100:1',
                       'dJ1g6p8h':'50:1:20','6Emk0agT':'50:1:2'}]
            raw=text(table.key,['original^Keep^Keep']) if table.localized else master(table.key,rows.get(table.name,fallback),mode=table.cipher)
            path.write_bytes(raw)
        for row in rows[rules.INDEX.name][:-1]:
            table=next(table for table in rules.INPUT_TABLES if table.name==row['a4hXTIm0'])
            raw=(native/table.path(10)).read_bytes()
            row['zptmZGqa']=hashlib.md5(raw).hexdigest(); row['MLOSu5E0']=str(len(raw))
        (native/rules.INDEX.path(10)).write_bytes(master(rules.INDEX.key,rows[rules.INDEX.name]))
        version_path=static/'client/shared_prefs/gamedata.xml'
        version_path.parent.mkdir(parents=True,exist_ok=True)
        version_path.write_text('<map>'+''.join('<string name="key'+table.name+'">10</string>' for table in rules.TABLES)+'</map>')
        self.native=native
        self.shared={str(p.relative_to(self.config.data)):p.read_bytes() for p in self.config.data.rglob('*') if p.is_file()}
        return native

    def source(self, table): return self.native/table.path(10)

    def pointer(self): return self.config.root/prep.POINTER

    def assert_shared(self):
        self.assertEqual({str(p.relative_to(self.config.data)):p.read_bytes() for p in self.config.data.rglob('*') if p.is_file()},self.shared)

    def test_given_each_layout_when_prepared_then_publish_consistent_tables_without_engine_or_campaign(self):
        for managed in (False,True):
            with self.subTest(managed=managed):
                self.config=Configuration(self.root/('private-'+str(managed)),self.root/('content-'+str(managed)))
                self.fixture(managed)
                with patch('subprocess.run',side_effect=AssertionError('preparation spawned')):
                    report=prep.prepare_data(self.config)
                    self.assertTrue(prep.verify_data(self.config)['ok'])
                snapshot=prep.load_prepared(self.config)
                self.assertTrue(report['prepared_now']); self.assertFalse(report['gameplay_ready'])
                self.assertEqual(report['tables'],364)
                self.assertFalse(self.config.state_file.exists())
                resource=[r for _,r,_ in master_rows(snapshot.lookup(rules.RESOURCE.path(210010)),rules.RESOURCE.key)]
                self.assertEqual({r['9ZCEWn0z'] for r in resource},{'1','2'})
                self.assertTrue(all(r['81fTkEDP']=='TUTO' for r in resource))
                quest=master_rows(snapshot.lookup(rules.QUEST.path(210010)),rules.QUEST.key)[0][1]
                self.assertEqual(quest['dX6cor8j'],'50:1:20:100:1:extra,20:1:3:100:1')
                urls=[r for _,r,_ in master_rows(snapshot.lookup(rules.URL.path(210010)),rules.URL.key)]
                self.assertEqual(urls[0]['en'],rules.RATE_URL); self.assertEqual(urls[1]['en'],'unchanged')
                self.assertEqual(urls[0]['G4L0YIB2'],'original'); self.assertEqual(urls[0]['empty'],'')
                index=[r for _,r,_ in master_rows(snapshot.lookup(rules.INDEX.path(210010)),rules.INDEX.key)]
                self.assertEqual(index[-1],{'a4hXTIm0':'F_TEXT_CRAFT','00zAYGYS':'2','zptmZGqa':'other','MLOSu5E0':'5'})
                for table in (rules.DAILY_NAME,rules.DAILY_DETAIL):
                    raw=snapshot.lookup(table.path(210010))
                    keys={r.split('^')[0] for _,rows,_ in text_lines(raw,table.key) for r in rows}
                    self.assertTrue(rules.additions()[table.name].keys()<=keys)
                saved=self.pointer().read_bytes(); listing=set(self.config.root.rglob('*'))
                self.assertFalse(prep.prepare_data(self.config)['prepared_now'])
                self.assertEqual(self.pointer().read_bytes(),saved); self.assertEqual(set(self.config.root.rglob('*')),listing)
                self.assert_shared()

    def test_given_unconfigured_runtime_when_verified_then_no_files_processes_or_engine_import(self):
        before=set(sys.modules)
        with patch('pathlib.Path.mkdir',side_effect=AssertionError('query wrote')), \
                patch('subprocess.run',side_effect=AssertionError('query spawned')):
            self.assertFalse(prep.verify_data(self.config)['ok'])
        self.assertFalse(self.config.root.exists())
        self.assertFalse({'capture_server','ffbe_state','player_state','data_paths'} & (set(sys.modules)-before))

    def test_given_changed_inputs_when_prepared_then_increase_versions_and_keep_old_generation(self):
        self.fixture(); prep.prepare_data(self.config)
        old=prep.load_prepared(self.config); before=copy.deepcopy(old.files)
        with patch.object(rules,'PIPELINE_VERSION',rules.PIPELINE_VERSION+1):
            self.assertIn('inputs changed',prep.verify_data(self.config)['error'])
            report=prep.prepare_data(self.config)
            self.assertEqual(report['generation'],2)
            self.assertTrue(prep.verify_data(self.config)['ok'])
        new=prep.load_prepared(self.config)
        self.assertTrue(all(new.manifest['tables'][name]['version']>entry['version'] for name,entry in old.manifest['tables'].items()))
        self.assertEqual({rel:(old.directory/rel).read_bytes() for rel in before},before)

    def test_given_snapshot_when_projected_then_versions_and_exact_asset_bytes_agree_without_mutation(self):
        self.fixture(); prep.prepare_data(self.config); pack=prep.load_prepared(self.config)
        spec={'c1qYg84Q':[{'a4hXTIm0':rules.INDEX.name,'wM9AfX6I':'1'},{'a4hXTIm0':'OTHER','wM9AfX6I':'7'}]}
        original=copy.deepcopy(spec); out=pack.project_versions(spec)
        self.assertEqual(spec,original)
        self.assertEqual({row['a4hXTIm0'] for row in out['c1qYg84Q']},rules.BY_NAME.keys())
        for row in out['c1qYg84Q']:
            if row['a4hXTIm0'] in rules.BY_NAME:
                table=rules.BY_NAME[row['a4hXTIm0']]
                self.assertIsNotNone(pack.lookup(table.path(int(row['wM9AfX6I']))))
        for bad in ('../manifest.json','/mst/Ver210010_i5QEJpua.dat','mst/Ver1_i5QEJpua.dat'):
            self.assertIsNone(pack.lookup(bad))

    def test_given_malformed_source_when_prepared_then_preserve_current_snapshot(self):
        self.fixture(); prep.prepare_data(self.config); before=self.pointer().read_bytes()
        self.source(rules.RESOURCE).write_bytes(b'invalid\r\n')
        with self.assertRaises(ValueError): prep.prepare_data(self.config)
        self.assertEqual(self.pointer().read_bytes(),before)
        self.assertIsNotNone(prep.load_prepared(self.config))

    def test_given_missing_localized_version_when_prepared_then_fail_without_publishing(self):
        self.fixture(); self.source(rules.DAILY_DETAIL).unlink()
        with self.assertRaisesRegex(ValueError,'Missing native'): prep.prepare_data(self.config)
        self.assertFalse(self.pointer().exists())

    def test_given_wrong_english_source_checksum_when_prepared_then_refuse_to_relabel_it_as_valid(self):
        self.fixture()
        self.source(rules.DAILY_NAME).write_bytes(text(rules.DAILY_NAME.key,['other^Unexpected source']))
        with self.assertRaisesRegex(ValueError,'source checksum'): prep.prepare_data(self.config)
        self.assertFalse(self.pointer().exists())

    def test_given_failed_table_write_when_preparing_then_keep_previous_generation_and_remove_stage(self):
        self.fixture(); prep.prepare_data(self.config); before=self.pointer().read_bytes()
        with patch.object(rules,'PIPELINE_VERSION',rules.PIPELINE_VERSION+1), \
                patch('ios_server.preparation.os.fsync',side_effect=OSError('injected write failure')):
            with self.assertRaises(OSError): prep.prepare_data(self.config)
        self.assertEqual(self.pointer().read_bytes(),before)
        self.assertFalse(list(self.pointer().parent.glob('.building-*')))
        self.assertEqual(prep.load_prepared(self.config).manifest['generation'],1)

    def test_given_failed_publish_when_retried_then_old_pointer_survives_and_orphan_can_be_reused(self):
        self.fixture(); prep.prepare_data(self.config); saved=self.pointer().read_bytes()
        original=os.replace
        def fail_pointer(source,destination):
            if Path(destination)==self.pointer(): raise OSError('injected pointer failure')
            return original(source,destination)
        with patch.object(rules,'PIPELINE_VERSION',rules.PIPELINE_VERSION+1):
            with patch('ios_server.preparation.os.replace',side_effect=fail_pointer),self.assertRaises(OSError):
                prep.prepare_data(self.config)
            self.assertEqual(self.pointer().read_bytes(),saved)
            self.assertEqual(prep.load_prepared(self.config).manifest['generation'],1)
            self.assertEqual(prep.prepare_data(self.config)['generation'],2)
            self.assertTrue(prep.verify_data(self.config)['ok'])

    def test_given_corrupt_published_bytes_when_verified_then_report_without_repair(self):
        self.fixture(); prep.prepare_data(self.config); pack=prep.load_prepared(self.config)
        path=pack.directory/rules.QUEST.path(210010); path.write_bytes(b'broken')
        listing={str(p):p.read_bytes() for p in self.config.root.rglob('*') if p.is_file()}
        self.assertIn('checksum',prep.verify_data(self.config)['error'])
        with self.assertRaisesRegex(ValueError,'checksum'): prep.prepare_data(self.config)
        self.assertEqual({str(p):p.read_bytes() for p in self.config.root.rglob('*') if p.is_file()},listing)

    def test_given_escaping_shared_symlink_when_prepared_then_refuse_private_file_input(self):
        self.fixture(); secret=self.root/'secret.dat'; secret.write_bytes(self.source(rules.QUEST).read_bytes())
        self.source(rules.QUEST).unlink(); self.source(rules.QUEST).symlink_to(secret)
        with self.assertRaisesRegex(ValueError,'escapes shared'): prep.prepare_data(self.config)
        self.assertFalse(self.pointer().exists())

    def test_given_escaping_private_symlink_when_prepared_then_do_not_write_outside_runtime(self):
        self.fixture(); outside=self.root/'outside'; outside.mkdir()
        self.config.root.mkdir(); (self.config.root/'assets').symlink_to(outside,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'escapes'): prep.prepare_data(self.config)
        self.assertEqual(list(outside.iterdir()),[])

    def test_given_busy_runtime_when_prepared_then_preserve_current_generation(self):
        self.fixture(); prep.prepare_data(self.config); before=self.pointer().read_bytes()
        with InstanceLock(self.config.root), self.assertRaisesRegex(RuntimeError,'Another iOS instance'):
            prep.prepare_data(self.config)
        self.assertEqual(self.pointer().read_bytes(),before)

    def test_given_tampered_manifest_path_or_provenance_when_loaded_then_reject_even_with_updated_checksum(self):
        self.fixture(); prep.prepare_data(self.config); pack=prep.load_prepared(self.config)
        for changed in ('path','provenance'):
            manifest=copy.deepcopy(pack.manifest)
            if changed=='path': manifest['tables'][rules.QUEST.name]['path']='../../secret'
            else: manifest['source_root']='/wrong-source'
            raw=json.dumps(manifest).encode(); (pack.directory/'manifest.json').write_bytes(raw)
            ref=json.loads(self.pointer().read_bytes()); ref['manifest_sha256']=hashlib.sha256(raw).hexdigest()
            self.pointer().write_text(json.dumps(ref))
            self.assertFalse(prep.verify_data(self.config)['ok'])
            with self.assertRaises(ValueError): prep.prepare_data(self.config)

    def test_given_real_entrypoint_when_preparing_and_verifying_then_stdout_is_one_json_document(self):
        self.fixture()
        for command in ('prepare-data','verify-data'):
            done=subprocess.run([sys.executable,'-B',str(SOURCE/'exvius/macos_ios_server.py'),command,
                '--root',str(self.config.root),'--data',str(self.config.data)],capture_output=True,text=True,timeout=20)
            self.assertEqual(done.returncode,0,done.stderr+done.stdout)
            self.assertTrue(json.loads(done.stdout)['ok'])
        self.assertFalse(self.config.state_file.exists()); self.assert_shared()


if __name__=='__main__': unittest.main()
