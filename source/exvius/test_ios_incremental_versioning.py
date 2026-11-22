"""BDD for content-preserving native versioning and drifted upfront CPK re-versioning."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SOURCE), str(SOURCE / 'server')]

import test_ios_native_labels as labels
import test_ios_preparation as harness
import test_ios_sounds as audio
import test_ios_vortex_art as vortex
from ios_server import (
    cpk,
    native_sounds,
    native_tables as rules,
    preparation as prep,
    sound_inputs,
    sound_snapshots,
    upfront_resources,
    upfront_store,
    version_policy,
    vortex_art as art,
)
from ios_server.config import Configuration
from ios_server.table_codec import master_rows, patch_master
from ios_server.table_delivery import serve


def _handler(method='GET'):
    result = SimpleNamespace(command=method, wfile=io.BytesIO(), headers={}, close_connection=False)
    result.send_response = lambda status: setattr(result, 'status', status)
    result.send_header = lambda key, value: result.headers.update({key: value})
    result.end_headers = lambda: None
    return result


class IncrementalVersioning(unittest.TestCase):
    setUp = harness.NativePreparation.setUp
    fixture = harness.NativePreparation.fixture
    source = harness.NativePreparation.source
    pointer = harness.NativePreparation.pointer
    assert_shared = harness.NativePreparation.assert_shared
    saved = labels.NativeLabelPreparation.saved
    artwork = vortex.VortexPreparation.artwork
    edit_manifest = vortex.VortexPreparation.edit_manifest

    def install_two_sounds(self, v1=2, v2=3):
        self.sound_specs = {
            '12': ('sound/se', 'System.acb', f'common_lang/sound/se/ios/Ver{v1}_System.acb', str(v1), audio.acb()),
            '13': ('sound/bgm', 'Bgm001.acb', f'common_lang/sound/bgm/ios/Ver{v2}_Bgm001.acb', str(v2), audio.acb()),
        }
        for _id, (_folder, _name, stock, _ver, raw) in self.sound_specs.items():
            android = self.native / stock.replace('/ios/', '/android/')
            android.parent.mkdir(parents=True, exist_ok=True)
            android.write_bytes(raw)
        for prefix, id_column in sound_inputs.FAMILIES:
            for suffix in ('_MST', '_VERSION_MST_LOCALIZE', '_CHECKSUM_MST'):
                table = rules.BY_NAME[prefix + suffix]
                rows = [row for _, row, _ in master_rows(self.source(table).read_bytes(), table.key, mode=table.cipher)
                        if sound_inputs.positive(row.get(id_column)) and row[id_column] not in self.sound_specs]
                for sid, (folder, name, _stock, ver, _raw) in self.sound_specs.items():
                    row = {id_column: sid, 'unrelated': 'preserved'}
                    if suffix == '_MST':
                        row.update({'3LHdc6Qa': folder, 'pJ56sAEo': name, '81fTkEDP': 'GAME'})
                    elif suffix == '_VERSION_MST_LOCALIZE':
                        row.update({'OzT5lSz3': ver, '86SWOBTb': '17', 'japanese': '29'})
                    else:
                        row.update({'JwbkKrjA': '0', 'mYtcPkQQ': '999999', 'MLOSu5E0': '83'})
                    rows.append(row)
                self.source(table).write_bytes(harness.master(table.key, rows, mode=table.cipher))

    def add_upfront(self, identity, directory, name, locale, version, content, advertised):
        version_field, size_field = ('OzT5lSz3', 'JwbkKrjA') if locale == 'common_lang' else ('86SWOBTb', 'MLOSu5E0')
        specs = (
            ('F_RESOURCE_MST', {'9ZCEWn0z': identity, '3LHdc6Qa': directory, 'pJ56sAEo': name, '81fTkEDP': 'TUTO'}),
            ('F_RESOURCE_VERSION_MST_LOCALIZE', {'9ZCEWn0z': identity, version_field: str(version)}),
            ('F_RESOURCE_CHECKSUM_MST', {'9ZCEWn0z': identity, size_field: str(advertised), 'mYtcPkQQ': 'android'}),
        )
        for table_name, new_row in specs:
            table = rules.BY_NAME[table_name]
            rows = [row for _, row, _ in master_rows(self.source(table).read_bytes(), table.key, mode=table.cipher)
                    if row.get('9ZCEWn0z') != identity]
            rows.append(new_row)
            self.source(table).write_bytes(harness.master(table.key, rows, mode=table.cipher))
        path = self.native / f'{locale}/sd/{directory}/Ver{version}_{name}'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_given_single_master_table_edit_when_prepared_then_only_changed_table_bumps(self):
        self.fixture()
        r1 = prep.prepare_data(self.config)
        self.assertEqual(r1['version_reuse']['tables'], {'reused': 0, 'bumped': 364})
        old = prep.load_prepared(self.config)

        quest_path = self.source(rules.QUEST)
        rows = [dict(row, keep='updated') for _, row, _ in master_rows(quest_path.read_bytes(), rules.QUEST.key)]
        quest_path.write_bytes(harness.master(rules.QUEST.key, rows))

        r2 = prep.prepare_data(self.config)
        self.assertEqual(r2['generation'], 2)
        self.assertEqual(r2['version_reuse']['tables'], {'reused': 363, 'bumped': 1})
        self.assertTrue(prep.verify_data(self.config)['ok'])

        new = prep.load_prepared(self.config)
        for name, entry in new.manifest['tables'].items():
            if name == rules.QUEST.name:
                self.assertGreater(entry['version'], old.manifest['tables'][name]['version'])
                self.assertEqual(entry['version_generation'], 2)
            else:
                self.assertEqual(entry['version'], old.manifest['tables'][name]['version'])
                self.assertEqual(entry['version_generation'], 1)

    def test_given_localized_text_edit_when_prepared_then_only_edited_text_and_index_bump(self):
        self.fixture()
        prep.prepare_data(self.config)
        old = prep.load_prepared(self.config)

        # Edit F_TEXT_DAILY_QUEST_NAME and update F_LOCALIZED_TEXT_MST checksums
        target = rules.DAILY_NAME
        edited_text = harness.text(target.key, ['original^Changed^Changed'])
        self.source(target).write_bytes(edited_text)
        idx_rows = [row for _, row, _ in master_rows(self.source(rules.INDEX).read_bytes(), rules.INDEX.key)]
        for row in idx_rows:
            if row.get('a4hXTIm0') == target.name:
                row['zptmZGqa'] = hashlib.md5(edited_text).hexdigest()
                row['MLOSu5E0'] = str(len(edited_text))
        self.source(rules.INDEX).write_bytes(harness.master(rules.INDEX.key, idx_rows))

        report = prep.prepare_data(self.config)
        self.assertEqual(report['version_reuse']['tables'], {'reused': 362, 'bumped': 2})
        new = prep.load_prepared(self.config)
        for name, entry in new.manifest['tables'].items():
            if name in (target.name, rules.INDEX.name):
                self.assertGreater(entry['version'], old.manifest['tables'][name]['version'])
                self.assertEqual(entry['version_generation'], 2)
            else:
                self.assertEqual(entry['version'], old.manifest['tables'][name]['version'])
                self.assertEqual(entry['version_generation'], 1)
        self.assertTrue(prep.verify_data(self.config)['ok'])

    def test_given_raised_gamedata_floor_with_identical_bytes_when_prepared_then_bump_monotonically(self):
        self.fixture()
        prep.prepare_data(self.config)
        old = prep.load_prepared(self.config)
        target = rules.ECONOMY_TABLES[0]
        xml = Path(self.config.engine_environment()['VERSION_TABLE_XML'])
        xml.write_text(xml.read_text().replace(f'name="key{target.name}">10', f'name="key{target.name}">230010'))

        report = prep.prepare_data(self.config)
        new = prep.load_prepared(self.config)
        self.assertEqual(report['version_reuse']['tables'], {'reused': 363, 'bumped': 1})
        self.assertGreater(new.manifest['tables'][target.name]['version'], old.manifest['tables'][target.name]['version'])
        self.assertEqual(new.manifest['tables'][target.name]['version'], 450010)
        self.assertEqual(new.manifest['tables'][target.name]['version_generation'], 2)
        self.assertTrue(prep.verify_data(self.config)['ok'])

    def test_given_two_sound_banks_when_one_or_none_changes_then_preserve_unchanged_bank_versions(self):
        self.fixture()
        self.install_two_sounds(v1=2, v2=3)
        sound_snapshots.prepare(self.config)
        r1 = prep.prepare_data(self.config, sounds=True)
        self.assertEqual(r1['version_reuse']['sounds'], {'reused': 0, 'bumped': 2})
        g1 = prep.load_prepared(self.config)

        # Change only an unrelated table: ALL sound banks and sound resource tables keep gen-1 versions
        quest_path = self.source(rules.QUEST)
        quest_path.write_bytes(harness.master(rules.QUEST.key, [{'Z34jU7ue': '1', 'dX6cor8j': '', 'keep': 'v2'}]))
        r2 = prep.prepare_data(self.config)
        self.assertEqual(r2['version_reuse']['sounds'], {'reused': 2, 'bumped': 0})
        g2 = prep.load_prepared(self.config)
        for src in g2.manifest['sounds']['banks']:
            self.assertEqual(g2.manifest['sounds']['banks'][src]['version'], g1.manifest['sounds']['banks'][src]['version'])
            self.assertEqual(g2.manifest['sounds']['banks'][src]['version_generation'], 1)
        for prefix, _ in sound_inputs.FAMILIES:
            for suffix in ('_MST', '_VERSION_MST_LOCALIZE', '_CHECKSUM_MST'):
                self.assertEqual(g2.manifest['tables'][prefix + suffix]['version_generation'], 1)

        # Modify only bank B (Bgm001.acb); bank A (System.acb) keeps gen-1 version
        bank_b = self.native / 'common_lang/sound/bgm/android/Ver3_Bgm001.acb'
        bank_b.write_bytes(audio.acb([audio.hca(0), audio.hca(0)]))
        sound_snapshots.prepare(self.config)
        r3 = prep.prepare_data(self.config)
        self.assertEqual(r3['version_reuse']['sounds'], {'reused': 1, 'bumped': 1})
        g3 = prep.load_prepared(self.config)
        bank_a_key = 'common_lang/sound/se/ios/Ver2_System.acb'
        bank_b_key = 'common_lang/sound/bgm/ios/Ver3_Bgm001.acb'
        self.assertEqual(g3.manifest['sounds']['banks'][bank_a_key]['version'],
                         g1.manifest['sounds']['banks'][bank_a_key]['version'])
        self.assertEqual(g3.manifest['sounds']['banks'][bank_a_key]['version_generation'], 1)
        self.assertGreater(g3.manifest['sounds']['banks'][bank_b_key]['version'],
                           g1.manifest['sounds']['banks'][bank_b_key]['version'])
        self.assertEqual(g3.manifest['sounds']['banks'][bank_b_key]['version_generation'], 3)
        self.assertTrue(prep.verify_data(self.config)['ok'])

    def test_given_unchanged_and_changed_vortex_inputs_when_prepared_then_preserve_or_bump_and_guard_overflow(self):
        self.artwork()
        prep.prepare_data(self.config, vortex_art=True)
        g1 = prep.load_prepared(self.config)

        # Unrelated table change -> Vortex pack & resource tables retain gen-1 version
        quest_path = self.source(rules.QUEST)
        quest_path.write_bytes(harness.master(rules.QUEST.key, [{'Z34jU7ue': '1', 'dX6cor8j': '', 'keep': 'v2'}]))
        r2 = prep.prepare_data(self.config)
        self.assertEqual(r2['version_reuse']['packs'], {'reused': 1, 'bumped': 0})
        g2 = prep.load_prepared(self.config)
        self.assertEqual(g2.manifest['packs'][art.PACK]['version'], g1.manifest['packs'][art.PACK]['version'])
        self.assertEqual(g2.manifest['packs'][art.PACK]['version_generation'], 1)
        self.assertEqual(g2.manifest['tables'][art.CHECKSUM.name]['version_generation'], 1)

        # Modify Vortex artwork -> pack & resource tables bump
        (self.area / 'event_one.png').write_bytes(vortex.png(7))
        r3 = prep.prepare_data(self.config)
        self.assertEqual(r3['version_reuse']['packs'], {'reused': 0, 'bumped': 1})
        g3 = prep.load_prepared(self.config)
        self.assertGreater(g3.manifest['packs'][art.PACK]['version'], g1.manifest['packs'][art.PACK]['version'])
        self.assertEqual(g3.manifest['packs'][art.PACK]['version_generation'], 3)

        # Overflowing Vortex source version fails before cpk.rebuild
        ver_raw, _ = patch_master(self.source(art.VERSIONS).read_bytes(), art.VERSIONS.key,
            lambda row: dict(row, **{'86SWOBTb': '2147483647'}) if str(row.get('9ZCEWn0z')) == art.RESOURCE_ID else row)
        self.source(art.VERSIONS).write_bytes(ver_raw)
        (self.native / art.pack_path(2147483647)).write_bytes(vortex.fixture_pack())
        with patch.object(cpk, 'rebuild', side_effect=AssertionError('overflow rebuilt pack')), \
                self.assertRaisesRegex(ValueError, 'out of range'):
            prep.prepare_data(self.config)

    def test_given_upfront_cpk_drift_carry_forward_and_same_size_edit_when_prepared_and_served(self):
        self.artwork()
        drifted_bytes = b'DRIFTED-MONSTER-CPK-V1'
        stock_bytes = b'STOCK-GACHA-CPK'
        drifted_src = self.add_upfront('902', 'monster', 'monster3_common.cpk', 'common_lang', 36, drifted_bytes, 10)
        stock_src = self.add_upfront('900', 'gacha', 'gacha1_common.cpk', 'common_lang', 7, stock_bytes, len(stock_bytes))
        # Also mark Vortex 6108101 TUTO in source F_RESOURCE_MST to verify vortex_art excludes it from upfront_resources
        res_raw, _ = patch_master(self.source(art.RESOURCE).read_bytes(), art.RESOURCE.key,
            lambda row: dict(row, **{'81fTkEDP': 'TUTO'}) if str(row.get('9ZCEWn0z')) == art.RESOURCE_ID else row)
        self.source(art.RESOURCE).write_bytes(res_raw)

        before_data = {p: p.read_bytes() for p in self.config.data.rglob('*') if p.is_file()}
        r1 = prep.prepare_data(self.config, vortex_art=True)
        self.assertEqual(r1['upfront_packs'], 1)
        self.assertEqual(r1['version_reuse']['upfront_packs'], {'reused': 0, 'bumped': 1})
        g1 = prep.load_prepared(self.config)
        self.assertEqual(set(g1.manifest['upfront_packs']), {'902:JwbkKrjA'})
        self.assertNotIn(art.RESOURCE_ID + ':MLOSu5E0', g1.manifest['sources']['upfront']['files'])
        self.assertNotIn(art.RESOURCE_ID + ':MLOSu5E0', g1.manifest['upfront_packs'])

        entry = g1.manifest['upfront_packs']['902:JwbkKrjA']
        self.assertEqual(entry['version'], 210036)
        self.assertEqual(entry['version_generation'], 1)
        self.assertEqual(entry['path'], 'common_lang/sd/monster/Ver210036_monster3_common.cpk')
        blob_path = self.config.root / entry['blob']
        self.assertTrue(blob_path.is_file())
        self.assertEqual(stat.S_IMODE(blob_path.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(blob_path.stat().st_mode), 0o600)
        self.assertEqual(blob_path.stat().st_nlink, 1)
        self.assertEqual(blob_path.read_bytes(), drifted_bytes)
        self.assertEqual(before_data, {p: p.read_bytes() for p in self.config.data.rglob('*') if p.is_file()})

        # Verify F_RESOURCE_VERSION_MST_LOCALIZE and F_RESOURCE_CHECKSUM_MST both reflect bumped version/size
        v_rows = {r['9ZCEWn0z']: r for _, r, _ in master_rows(g1.lookup(g1.manifest['tables'][art.VERSIONS.name]['path']), art.VERSIONS.key) if '9ZCEWn0z' in r}
        c_rows = {r['9ZCEWn0z']: r for _, r, _ in master_rows(g1.lookup(g1.manifest['tables'][art.CHECKSUM.name]['path']), art.CHECKSUM.key) if '9ZCEWn0z' in r}
        self.assertEqual(v_rows['902']['OzT5lSz3'], '210036')
        self.assertEqual(c_rows['902']['JwbkKrjA'], str(len(drifted_bytes)))
        self.assertEqual(v_rows['900']['OzT5lSz3'], '7')

        # Delivery checks on gen 1: bumped 200 GET/HEAD, stock version of bumped CPK -> 404, unbumped stock -> False
        for method in ('GET', 'HEAD'):
            h = _handler(method)
            self.assertTrue(serve(h, g1, entry['path']))
            self.assertEqual(h.status, 200)
            self.assertEqual(h.headers['Content-Length'], str(len(drifted_bytes)))
            self.assertEqual(h.wfile.getvalue(), drifted_bytes if method == 'GET' else b'')
            h_old = _handler(method)
            self.assertTrue(serve(h_old, g1, 'common_lang/sd/monster/Ver36_monster3_common.cpk'))
            self.assertEqual(h_old.status, 404)
            self.assertFalse(serve(_handler(method), g1, 'common_lang/sd/gacha/Ver7_gacha1_common.cpk'))

        # Gen 2: unrelated table edits -> bumped upfront CPK carries forward with zero re-copy
        quest_path = self.source(rules.QUEST)
        quest_path.write_bytes(harness.master(rules.QUEST.key, [{'Z34jU7ue': '1', 'dX6cor8j': '', 'keep': 'v2'}]))
        blob_inode = blob_path.stat().st_ino
        with patch.object(upfront_store, 'tempfile', SimpleNamespace(
                NamedTemporaryFile=lambda *a, **kw: (_ for _ in ()).throw(AssertionError('re-copied unchanged blob')))):
            r2 = prep.prepare_data(self.config)
        self.assertEqual(blob_path.stat().st_ino, blob_inode)
        self.assertEqual(r2['version_reuse']['upfront_packs'], {'reused': 1, 'bumped': 0})
        g2 = prep.load_prepared(self.config)
        self.assertEqual(g2.manifest['upfront_packs']['902:JwbkKrjA']['version'], 210036)
        self.assertEqual(g2.manifest['upfront_packs']['902:JwbkKrjA']['version_generation'], 1)
        self.assertEqual(g2.manifest['tables'][art.VERSIONS.name]['version_generation'], 1)

        # Gen 3: same-size edit to BOTH previously bumped (902) and previously stock-matching (900) CPKs!
        drifted_same_len = b'DRIFTED-MONSTER-CPK-V2'
        self.assertEqual(len(drifted_same_len), len(drifted_bytes))
        drifted_src.write_bytes(drifted_same_len)
        stock_same_len = b'EDITED-GACHA-PK'
        self.assertEqual(len(stock_same_len), len(stock_bytes))
        stock_src.write_bytes(stock_same_len)

        r3 = prep.prepare_data(self.config)
        self.assertEqual(r3['generation'], 3)
        self.assertEqual(r3['upfront_packs'], 2)
        self.assertEqual(r3['version_reuse']['upfront_packs'], {'reused': 0, 'bumped': 2})
        g3 = prep.load_prepared(self.config)
        self.assertEqual(g3.manifest['upfront_packs']['902:JwbkKrjA']['version'], 230036)
        self.assertEqual(g3.manifest['upfront_packs']['902:JwbkKrjA']['version_generation'], 3)
        self.assertEqual(g3.manifest['upfront_packs']['900:JwbkKrjA']['version'], 230007)
        self.assertEqual(g3.manifest['upfront_packs']['900:JwbkKrjA']['version_generation'], 3)
        # Superseded v1 path now returns 404, new v3 path returns 200
        h_superseded = _handler('GET')
        self.assertTrue(serve(h_superseded, g3, entry['path']))
        self.assertEqual(h_superseded.status, 404)
        h_new = _handler('GET')
        self.assertTrue(serve(h_new, g3, g3.manifest['upfront_packs']['902:JwbkKrjA']['path']))
        self.assertEqual((h_new.status, h_new.wfile.getvalue()), (200, drifted_same_len))

        # Corrupt / truncated / grown / symlink-escaping / missing blob -> 500 on GET and HEAD
        new_entry = g3.manifest['upfront_packs']['902:JwbkKrjA']
        new_blob = self.config.root / new_entry['blob']
        for damaged in (drifted_same_len[:-1] + b'X', drifted_same_len[:-1], drifted_same_len + b'X'):
            new_blob.write_bytes(damaged)
            for method in ('GET', 'HEAD'):
                h_err = _handler(method)
                self.assertTrue(serve(h_err, g3, new_entry['path']))
                self.assertEqual((h_err.status, h_err.headers['Content-Length'], h_err.wfile.getvalue()), (500, '0', b''))
        new_blob.unlink()
        outside = self.root / 'outside.cpk'
        outside.write_bytes(drifted_same_len)
        new_blob.symlink_to(outside)
        for method in ('GET', 'HEAD'):
            h_esc = _handler(method)
            self.assertTrue(serve(h_esc, g3, new_entry['path']))
            self.assertEqual((h_esc.status, h_esc.wfile.getvalue()), (500, b''))
        new_blob.unlink()
        for method in ('GET', 'HEAD'):
            h_miss = _handler(method)
            self.assertTrue(serve(h_miss, g3, new_entry['path']))
            self.assertEqual((h_miss.status, h_miss.wfile.getvalue()), (500, b''))
        with self.assertRaises(ValueError):
            prep.load_prepared(self.config)

    def test_given_schema5_gen8_snapshot_with_drifted_upfront_cpk_when_upgraded_to_schema6_then_preserve_tables_sounds_art(self):
        self.artwork()
        self.install_two_sounds(v1=2, v2=3)
        drifted = b'GEN8-DRIFTED-MONSTER-CPK'
        stock = b'GEN8-STOCK-GACHA'
        self.add_upfront('902', 'monster', 'monster3_common.cpk', 'common_lang', 36, drifted, 10)
        self.add_upfront('900', 'gacha', 'gacha1_common.cpk', 'common_lang', 7, stock, len(stock))
        sound_snapshots.prepare(self.config)

        # Construct a realistic generation-8 schema-5 snapshot matching pre-schema-6 production state
        gen8 = 8
        sources, records, fingerprint, context, labels_map, art_inputs, sound_inputs_obj = prep._complete_inputs(
            self.config, vortex_art=True, sounds=True)
        # Convert policy=2 upfront records to schema-5 policy=1 format as gen 8 had
        records['upfront'] = {
            'policy': 1,
            'files': {k: {fk: fv for fk, fv in v.items() if fk not in ('relative', 'source_version')}
                      for k, v in records['upfront']['files'].items()},
            'missing': records['upfront']['missing'],
        }
        floors = records['registry']['versions']
        outputs, versions, changes = rules.build(
            sources, gen8, labels=labels_map, economy=context['economy']['settings'], floors=floors)
        upfront_resources.project(records['upfront'], outputs)
        pack_entry, pack_raw, pack_ch = art.prepare(art_inputs, gen8, outputs)
        pack_entry.pop('version_generation')
        for k, c in pack_ch.items():
            changes[k] += c
        outputs[art.PACK] = pack_raw
        sound_banks = native_sounds.inventory(sound_inputs_obj.snapshot, gen8, include_generation=False)
        sound_ch = native_sounds._project(sound_inputs_obj.snapshot, sound_banks, outputs)
        for k, c in sound_ch.items():
            changes[k] += c
        rules.validate(outputs, versions)
        manifest8 = {
            'version': 5,
            'scope': prep.SCOPE,
            'reference_commit': prep.REVIVAL_COMMIT,
            'source_root': str(self.config.data),
            'pipeline_version': 5,
            'generation': gen8,
            'fingerprint': '8' * 64,
            'sources': records,
            'preparation': context,
            'tables': {
                t.name: {
                    'path': t.path(versions[t.name]),
                    'version': versions[t.name],
                    'source_version': sources[t.name][0],
                    'size': len(outputs[t.name]),
                    'sha256': prep._sha(outputs[t.name]),
                    'md5': hashlib.md5(outputs[t.name]).hexdigest(),
                    'changed_rows': changes[t.name],
                    'version_floor': max(sources[t.name][0], floors[t.name]),
                }
                for t in rules.TABLES
            },
            'packs': {art.PACK: pack_entry},
            'sounds': {'snapshot': sound_inputs_obj.provenance['snapshot'], 'banks': sound_banks},
        }
        prep._publish(self.config, manifest8, outputs)

        # Schema 5 loads cleanly and verify_data reports stale due to PIPELINE_VERSION=6
        old = prep.load_prepared(self.config)
        self.assertEqual((old.manifest['version'], old.manifest['generation']), (5, 8))
        self.assertFalse(prep.verify_data(self.config)['ok'])

        # Upgrade to gen 9 (schema 6)
        report = prep.prepare_data(self.config)
        self.assertEqual(report['generation'], 9)
        self.assertEqual(report['version_reuse']['tables'], {'reused': 363, 'bumped': 1})
        self.assertEqual(report['version_reuse']['packs'], {'reused': 1, 'bumped': 0})
        self.assertEqual(report['version_reuse']['sounds'], {'reused': 2, 'bumped': 0})
        self.assertEqual(report['version_reuse']['upfront_packs'], {'reused': 0, 'bumped': 1})
        self.assertTrue(prep.verify_data(self.config)['ok'])

        new = prep.load_prepared(self.config)
        self.assertEqual(new.manifest['version'], 6)
        for name, entry in new.manifest['tables'].items():
            if name == art.VERSIONS.name:
                self.assertGreater(entry['version'], old.manifest['tables'][name]['version'])
                self.assertEqual(entry['version_generation'], 9)
            else:
                self.assertEqual(entry['version'], old.manifest['tables'][name]['version'])
                self.assertEqual(entry['version_generation'], 8)
        self.assertEqual(new.manifest['packs'][art.PACK]['version'], old.manifest['packs'][art.PACK]['version'])
        self.assertEqual(new.manifest['packs'][art.PACK]['version_generation'], 8)
        for src in new.manifest['sounds']['banks']:
            self.assertEqual(new.manifest['sounds']['banks'][src]['version'], old.manifest['sounds']['banks'][src]['version'])
            self.assertEqual(new.manifest['sounds']['banks'][src]['version_generation'], 8)
        up = new.manifest['upfront_packs']['902:JwbkKrjA']
        self.assertEqual(up['version'], 290036)
        self.assertEqual(up['version_generation'], 9)
        h = _handler('GET')
        self.assertTrue(serve(h, new, up['path']))
        self.assertEqual((h.status, h.wfile.getvalue()), (200, drifted))
        self.assertFalse(serve(_handler('GET'), new, 'common_lang/sd/gacha/Ver7_gacha1_common.cpk'))

    def test_given_tampered_schema6_manifest_when_loaded_then_reject_all_violations(self):
        self.artwork()
        self.install_two_sounds(v1=2, v2=3)
        self.add_upfront('902', 'monster', 'monster3_common.cpk', 'common_lang', 36, b'DRIFTED', 1)
        sound_snapshots.prepare(self.config)
        prep.prepare_data(self.config, vortex_art=True, sounds=True)
        pack = prep.load_prepared(self.config)

        # 1. version_generation > generation
        def bad_vg(doc):
            doc['tables'][rules.QUEST.name]['version_generation'] = doc['generation'] + 1
        self.edit_manifest(pack, bad_vg)
        with self.assertRaises(ValueError):
            prep.load_prepared(self.config)

        # 2. version_generation == generation with wrong formula
        def bad_formula(doc):
            doc['tables'][rules.QUEST.name]['version'] += 1
        self.edit_manifest(pack, bad_formula)
        with self.assertRaises(ValueError):
            prep.load_prepared(self.config)

        # 3. version < floor
        def bad_floor(doc):
            doc['tables'][rules.QUEST.name]['version'] = 5
            doc['tables'][rules.QUEST.name]['version_generation'] = 0
        self.edit_manifest(pack, bad_floor)
        with self.assertRaises(ValueError):
            prep.load_prepared(self.config)

        # 4. drifted upfront CPK omitted from upfront_packs
        def missing_upfront(doc):
            doc.pop('upfront_packs')
        self.edit_manifest(pack, missing_upfront)
        with self.assertRaises(ValueError):
            prep.load_prepared(self.config)

    def test_given_interrupted_blob_or_dir_staging_when_retried_then_recover_deterministically(self):
        self.fixture()
        self.add_upfront('902', 'monster', 'monster3_common.cpk', 'common_lang', 36, b'GEN1-DRIFT', 1)
        prep.prepare_data(self.config)
        before_ptr = self.pointer().read_bytes()

        self.add_upfront('902', 'monster', 'monster3_common.cpk', 'common_lang', 36, b'GEN2-DRIFT', 1)
        original_replace = os.replace

        def fail_pointer(src, dst):
            if Path(dst) == self.pointer():
                raise OSError('injected pointer failure')
            return original_replace(src, dst)

        with patch('ios_server.preparation.os.replace', side_effect=fail_pointer), self.assertRaises(OSError):
            prep.prepare_data(self.config)
        self.assertEqual(self.pointer().read_bytes(), before_ptr)
        self.assertEqual(prep.load_prepared(self.config).manifest['generation'], 1)

        report = prep.prepare_data(self.config)
        self.assertEqual(report['generation'], 2)
        self.assertTrue(prep.verify_data(self.config)['ok'])
        self.assertEqual(prep.load_prepared(self.config).manifest['upfront_packs']['902:JwbkKrjA']['version'], 220036)

    def test_given_read_only_queries_when_run_then_perform_zero_writes(self):
        self.fixture()
        self.add_upfront('902', 'monster', 'monster3_common.cpk', 'common_lang', 36, b'DRIFT', 1)
        prep.prepare_data(self.config)
        snapshot_before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch('pathlib.Path.mkdir', side_effect=AssertionError('query mkdir')), \
                patch('ios_server.upfront_store.BlobStore.stage', side_effect=AssertionError('query staged blob')):
            self.assertTrue(prep.verify_data(self.config)['ok'])
            loaded = prep.load_prepared(self.config)
            self.assertIsNotNone(loaded.upfront)
            self.assertEqual(loaded.upfront.verified_size(loaded.manifest['upfront_packs']['902:JwbkKrjA']['path']), 5)
        self.assertEqual(snapshot_before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_given_tampered_existing_blob_when_staged_then_fail_without_overwriting(self):
        self.fixture()
        src = self.add_upfront('902', 'monster', 'monster3_common.cpk', 'common_lang', 36, b'ORIGINAL-BLOB', 1)
        prep.prepare_data(self.config)
        loaded = prep.load_prepared(self.config)
        blob = self.config.root / loaded.manifest['upfront_packs']['902:JwbkKrjA']['blob']
        blob.write_bytes(b'TAMPERED-BLOB')
        store = upfront_store.BlobStore(self.config.root, self.config.data)
        with self.assertRaisesRegex(ValueError, 'Corrupt private upfront CPK blob'):
            store.stage(src, hashlib.sha256(b'ORIGINAL-BLOB').hexdigest(), len(b'ORIGINAL-BLOB'))
        self.assertEqual(blob.read_bytes(), b'TAMPERED-BLOB')

    def test_given_large_upfront_blob_when_head_served_then_verify_with_bounded_memory(self):
        import tracemalloc
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve()
        data = root / 'data'
        data.mkdir()
        private = root / 'private'
        src = data / 'common_lang/sd/monster/Ver36_big.cpk'
        src.parent.mkdir(parents=True)
        block = bytes(range(256)) * 4096  # 1 MiB
        digest = hashlib.sha256()
        with src.open('wb') as stream:
            for _ in range(4):
                stream.write(block)
                digest.update(block)
        size = src.stat().st_size
        sha = digest.hexdigest()
        blob_rel = upfront_store.BlobStore(private, data).stage(src, sha, size)
        delivery = upfront_store.UpfrontDelivery.from_manifest(private, {
            '902:JwbkKrjA': {
                'path': 'common_lang/sd/monster/Ver210036_big.cpk',
                'version': 210036, 'source_version': 36, 'version_generation': 1,
                'size': size, 'sha256': sha, 'advertised': 1, 'blob': blob_rel,
            }
        })
        snap = SimpleNamespace(manifest={'version': 6}, upfront=delivery, sounds=None)
        tracemalloc.start()
        try:
            h = _handler('HEAD')
            self.assertTrue(serve(h, snap, 'common_lang/sd/monster/Ver210036_big.cpk'))
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual((h.status, h.headers['Content-Length'], h.wfile.getvalue()), (200, str(size), b''))
        self.assertLess(peak, 1024 * 1024)


if __name__ == '__main__':
    unittest.main()
