"""BDD for full-CPK foreground promotion, upfront audit, incremental carry-forward, and Launch-1 early catalog."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SOURCE), str(SOURCE / 'server')]

import ffbe_pipeline
import test_ios_incremental_versioning as inc
import test_ios_native_labels as labels
import test_ios_preparation as harness
import test_ios_sounds as audio
import test_ios_vortex_art as vortex
from engine_profile import IOS_REVIVAL, LEGACY
from ios_server import (
    cpk_foreground_policy as policy,
    native_sounds,
    native_tables as rules,
    preparation as prep,
    sound_snapshots,
    upfront_resources,
    vortex_art as art,
)
from ios_server.native_inputs import collect as collect_native_inputs
from ios_server.table_codec import master_rows
import revival_boot


class ForegroundCpkClassification(unittest.TestCase):
    def test_given_resource_rows_when_classified_then_promote_empty_and_define_cpks_and_preserve_sounds(self):
        rows = [
            {'9ZCEWn0z': '1', '3LHdc6Qa': 'resources', 'pJ56sAEo': 'resources_common.cpk', '81fTkEDP': 'PRE_TUTO'},
            {'9ZCEWn0z': '2', '3LHdc6Qa': 'unit', 'pJ56sAEo': 'unit1.cpk', '81fTkEDP': 'TUTO'},
            {'9ZCEWn0z': '3', '3LHdc6Qa': 'area', 'pJ56sAEo': 'area_tuto.cpk', '81fTkEDP': 'tuto'},
            {'9ZCEWn0z': '116002', '3LHdc6Qa': 'banner', 'pJ56sAEo': 'banner2_common.cpk', '81fTkEDP': 'DEFINE'},
            {'9ZCEWn0z': '116501', '3LHdc6Qa': 'banner', 'pJ56sAEo': 'banner_home1.cpk', '81fTkEDP': 'DEFINE'},
            {'9ZCEWn0z': '9400512', '3LHdc6Qa': 'banner', 'pJ56sAEo': 'banner2.cpk', '81fTkEDP': 'DEFINE'},
            {'9ZCEWn0z': '101', '3LHdc6Qa': 'unit', 'pJ56sAEo': 'unit1_sg_common.cpk', '81fTkEDP': ''},
            {'9ZCEWn0z': '102', '3LHdc6Qa': 'monster', 'pJ56sAEo': 'monster1_common.cpk', '81fTkEDP': ''},
            {'9ZCEWn0z': '103', '3LHdc6Qa': 'battleBg', 'pJ56sAEo': 'battlebg1.cpk', '81fTkEDP': ''},
            {'9ZCEWn0z': '104', '3LHdc6Qa': 'area', 'pJ56sAEo': 'area1.cpk', '81fTkEDP': ''},
            {'9ZCEWn0z': '105', '3LHdc6Qa': 'unit', 'pJ56sAEo': 'LBMovie100000225_common.cpk', '81fTkEDP': ''},
            {'9ZCEWn0z': '106', '3LHdc6Qa': 'unit', 'pJ56sAEo': 'movie_sg2_common.cpk', '81fTkEDP': ''},
            {'9ZCEWn0z': '107', '3LHdc6Qa': 'unit', 'pJ56sAEo': 'beastMovie1.cpk', '81fTkEDP': ''},
            {'9ZCEWn0z': '201', '3LHdc6Qa': 'sound/bgm', 'pJ56sAEo': 'Bgm001.acb', '81fTkEDP': 'GAME'},
        ]

        self.assertEqual(policy.POLICY_VERSION, 2)
        phases = {row['9ZCEWn0z']: policy.target_phase(row) for row in rows}
        self.assertEqual(phases['1'], 'PRE_TUTO')
        self.assertEqual(phases['2'], 'TUTO')
        self.assertEqual(phases['3'], 'tuto')
        for promoted_id in ('116002', '116501', '9400512', '101', '102', '103', '104', '105', '106', '107'):
            self.assertEqual(phases[promoted_id], 'TUTO')
        self.assertEqual(phases['201'], 'GAME')

        # ALL_EMPTY_CPKS preserves DEFINE banner CPKs while still promoting empty CPKs and leaving .acb untouched.
        empty_only_phases = {row['9ZCEWn0z']: policy.target_phase(row, policy=policy.ALL_EMPTY_CPKS) for row in rows}
        for define_id in ('116002', '116501', '9400512'):
            self.assertEqual(empty_only_phases[define_id], 'DEFINE')
        self.assertEqual(empty_only_phases['102'], 'TUTO')
        self.assertEqual(empty_only_phases['201'], 'GAME')

        # Legacy policy leaves DEFINE, movies, monsters, and areas untouched while promoting unit art.
        self.assertEqual(policy.target_phase(rows[3], policy=policy.LEGACY_MENU_AND_UNITS), 'DEFINE')
        self.assertEqual(policy.target_phase(rows[6], policy=policy.LEGACY_MENU_AND_UNITS), 'TUTO')
        self.assertEqual(policy.target_phase(rows[7], policy=policy.LEGACY_MENU_AND_UNITS), '')
        self.assertEqual(policy.target_phase(rows[10], policy=policy.LEGACY_MENU_AND_UNITS), '')

        # Upfront audit covers every non-Vortex CPK (including DEFINE and movies), never .acb.
        audited = {
            row['9ZCEWn0z']: policy.should_audit_upfront(row, exclude_resources=('6108101',))
            for row in rows
        }
        self.assertTrue(
            all(audited[rid] for rid in ('1', '2', '3', '116002', '116501', '9400512', '101', '102', '103', '104', '105', '106', '107'))
        )
        self.assertFalse(audited['201'])
        self.assertFalse(policy.should_audit_upfront(
            {'9ZCEWn0z': '6108101', '3LHdc6Qa': 'area', 'pJ56sAEo': 'spdungeon1.cpk', '81fTkEDP': ''},
            exclude_resources=('6108101',),
        ))

    def test_given_policy_matrix_and_none_phase_when_classified_then_preserve_lsp_audit_invariant(self):
        define_only = policy.ForegroundCpkPolicy(
            name='define-only',
            promote_empty_phase=False,
            promote_define_phase=True,
            audit_all_cpks=False,
        )
        define_row = {'9ZCEWn0z': '116002', '3LHdc6Qa': 'banner', 'pJ56sAEo': 'banner2_common.cpk', '81fTkEDP': 'DEFINE'}
        monster_row = {'9ZCEWn0z': '102', '3LHdc6Qa': 'monster', 'pJ56sAEo': 'monster1_common.cpk', '81fTkEDP': ''}
        movie_row = {'9ZCEWn0z': '105', '3LHdc6Qa': 'unit', 'pJ56sAEo': 'LBMovie100000225_common.cpk', '81fTkEDP': ''}
        background_row = {'9ZCEWn0z': '108', '3LHdc6Qa': 'area', 'pJ56sAEo': 'area_bg.cpk', '81fTkEDP': 'BACKGROUND'}
        none_monster = {'9ZCEWn0z': '109', '3LHdc6Qa': 'monster', 'pJ56sAEo': 'monster2_common.cpk', '81fTkEDP': None}
        none_gacha = {'9ZCEWn0z': '110', '3LHdc6Qa': 'gacha', 'pJ56sAEo': 'gacha1_common.cpk', '81fTkEDP': None}
        tuto_row = {'9ZCEWn0z': '2', '3LHdc6Qa': 'unit', 'pJ56sAEo': 'unit1.cpk', '81fTkEDP': 'TUTO'}
        pre_tuto_row = {'9ZCEWn0z': '1', '3LHdc6Qa': 'resources', 'pJ56sAEo': 'resources_common.cpk', '81fTkEDP': 'PRE_TUTO'}
        menu_row = {'9ZCEWn0z': '111', '3LHdc6Qa': 'monster', 'pJ56sAEo': 'monster3_common.cpk', '81fTkEDP': ''}
        unit_art_row = {'9ZCEWn0z': '112', '3LHdc6Qa': 'unit', 'pJ56sAEo': 'unit4_common.cpk', '81fTkEDP': ''}
        sound_row = {'9ZCEWn0z': '201', '3LHdc6Qa': 'sound/bgm', 'pJ56sAEo': 'Bgm001.acb', '81fTkEDP': 'GAME'}

        # Any row promoted to TUTO/PRE_TUTO by target_phase must be audited by should_audit_upfront.
        self.assertEqual(policy.target_phase(define_row, policy=define_only), 'TUTO')
        self.assertTrue(policy.should_audit_upfront(define_row, policy=define_only))
        self.assertEqual(policy.target_phase(monster_row, policy=define_only), '')
        self.assertFalse(policy.should_audit_upfront(monster_row, policy=define_only))

        # phase=None normalizes identically to '' under both policies.
        self.assertEqual(policy.target_phase(none_monster, policy=policy.ALL_CPKS), 'TUTO')
        self.assertIsNone(policy.target_phase(none_monster, policy=policy.LEGACY_MENU_AND_UNITS))
        self.assertEqual(policy.target_phase(none_gacha, policy=policy.LEGACY_MENU_AND_UNITS), 'TUTO')

        # LEGACY_MENU_AND_UNITS excludes movies, monsters, DEFINE, BACKGROUND, and .acb; includes TUTO/PRE_TUTO/MENU/UNIT.
        for excluded in (movie_row, monster_row, define_row, background_row, sound_row):
            self.assertFalse(policy.should_audit_upfront(excluded, policy=policy.LEGACY_MENU_AND_UNITS))
        for included in (pre_tuto_row, tuto_row, menu_row, unit_art_row, none_gacha):
            self.assertTrue(policy.should_audit_upfront(included, policy=policy.LEGACY_MENU_AND_UNITS))

        self.assertEqual(art.MANIFEST_SCHEMA_VERSION, 6)


class ForegroundCpkPreparation(unittest.TestCase):
    setUp = harness.NativePreparation.setUp
    fixture = harness.NativePreparation.fixture
    source = harness.NativePreparation.source
    pointer = harness.NativePreparation.pointer
    assert_shared = harness.NativePreparation.assert_shared
    saved = labels.NativeLabelPreparation.saved
    artwork = vortex.VortexPreparation.artwork
    install_two_sounds = inc.IncrementalVersioning.install_two_sounds

    def add_resource(self, identity, directory, name, locale, version, content, advertised, *, phase=''):
        version_field, size_field = ('OzT5lSz3', 'JwbkKrjA') if locale == 'common_lang' else ('86SWOBTb', 'MLOSu5E0')
        specs = (
            ('F_RESOURCE_MST', {'9ZCEWn0z': identity, '3LHdc6Qa': directory, 'pJ56sAEo': name, '81fTkEDP': phase}),
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

    def _install_early_packs(self):
        t_chk = rules.BY_NAME['F_RESOURCE_CHECKSUM_MST']
        for identity, name, ver in (('1', 'resources.cpk', 8), ('2', 'resources_common.cpk', 9)):
            p = self.native / f'common_lang/sd/resources/Ver{ver}_{name}'
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b'EARLY')
            rows = [r for _, r, _ in master_rows(self.source(t_chk).read_bytes(), t_chk.key)]
            rows = [r for r in rows if r.get('9ZCEWn0z') != identity]
            rows.append({'9ZCEWn0z': identity, 'JwbkKrjA': str(len(b'EARLY')), 'mYtcPkQQ': 'android'})
            self.source(t_chk).write_bytes(harness.master(t_chk.key, rows))

    def test_given_vortex_and_all_cpks_when_prepared_then_audit_all_non_vortex_and_bump_drifted(self):
        self.artwork()
        self._install_early_packs()
        self.add_resource('900', 'monster', 'monster1_common.cpk', 'common_lang', 5, b'DRIFTED-MONSTER', 1, phase='')
        self.add_resource('901', 'unit', 'LBMovie100000225_common.cpk', 'common_lang', 3, b'STOCK-MOVIE', 11, phase='')
        self.add_resource('902', 'banner', 'banner2_common.cpk', 'common_lang', 4, b'BANNER', 6, phase='DEFINE')

        report = prep.prepare_data(self.config, vortex_art=True)
        self.assertEqual(report['preparation']['upfront']['checked'], 5)
        self.assertEqual(report['preparation']['upfront']['corrected'], 1)
        self.assertEqual(report['preparation']['upfront']['missing'], [])

        snap = prep.load_prepared(self.config)
        self.assertEqual(set(snap.manifest['upfront_packs']), {'900:JwbkKrjA'})
        self.assertNotIn(art.RESOURCE_ID + ':MLOSu5E0', snap.manifest['sources']['upfront']['files'])
        res_rows = {
            r['9ZCEWn0z']: r for _, r, _ in master_rows(
                snap.lookup(snap.manifest['tables']['F_RESOURCE_MST']['path']), rules.RESOURCE.key
            )
        }
        self.assertEqual(res_rows['900']['81fTkEDP'], 'TUTO')
        self.assertEqual(res_rows['901']['81fTkEDP'], 'TUTO')
        self.assertEqual(res_rows['902']['81fTkEDP'], 'TUTO')
        self.assertEqual(res_rows[art.RESOURCE_ID]['81fTkEDP'], 'TUTO')

    def test_given_prior_pipeline6_generation_when_upgraded_to_pipeline8_then_reuse_unchanged_artifacts(self):
        self.artwork()
        self.install_two_sounds(v1=2, v2=3)
        self._install_early_packs()
        # Prior drifted unit pack + newly discovered drifted monster pack + stock movie pack
        self.add_resource('900', 'unit', 'unit4_common.cpk', 'common_lang', 15, b'UNIT-DRIFT', 1, phase='TUTO')
        self.add_resource('901', 'monster', 'monster5_common.cpk', 'common_lang', 12, b'MONSTER-DRIFT', 1, phase='')
        self.add_resource('902', 'unit', 'LBMovie1_common.cpk', 'common_lang', 4, b'MOVIE-STOCK', 11, phase='')
        sound_snapshots.prepare(self.config)

        # Build a realistic generation-1 schema-6 pipeline_version=6 snapshot under explicit legacy policy
        with patch.object(rules, 'PIPELINE_VERSION', 6):
            r1 = prep.prepare_data(
                self.config,
                vortex_art=True,
                sounds=True,
                cpk_policy=policy.LEGACY_MENU_AND_UNITS,
            )
        self.assertEqual(r1['generation'], 1)
        g1 = prep.load_prepared(self.config)
        self.assertEqual(g1.manifest['pipeline_version'], 6)
        self.assertEqual(set(g1.manifest['upfront_packs']), {'900:JwbkKrjA'})

        # Upgrade to PIPELINE_VERSION = 8 (ALL_CPKS)
        r2 = prep.prepare_data(self.config)
        self.assertEqual(r2['generation'], 2)
        self.assertEqual(r2['version_reuse']['packs'], {'reused': 1, 'bumped': 0})
        self.assertEqual(r2['version_reuse']['sounds'], {'reused': 2, 'bumped': 0})
        self.assertEqual(r2['version_reuse']['upfront_packs'], {'reused': 1, 'bumped': 1})
        self.assertEqual(r2['version_reuse']['tables'], {'reused': 361, 'bumped': 3})

        g2 = prep.load_prepared(self.config)
        self.assertEqual(g2.manifest['pipeline_version'], 8)
        self.assertEqual(g2.manifest['upfront_packs']['900:JwbkKrjA']['version'], g1.manifest['upfront_packs']['900:JwbkKrjA']['version'])
        self.assertEqual(g2.manifest['upfront_packs']['900:JwbkKrjA']['version_generation'], 1)
        self.assertEqual(g2.manifest['upfront_packs']['901:JwbkKrjA']['version_generation'], 2)
        bumped_tables = {
            name for name, entry in g2.manifest['tables'].items()
            if entry['version_generation'] == 2
        }
        self.assertEqual(
            bumped_tables,
            {'F_RESOURCE_MST', 'F_RESOURCE_VERSION_MST_LOCALIZE', 'F_RESOURCE_CHECKSUM_MST'},
        )
        self.assertTrue(prep.verify_data(self.config)['ok'])

    def test_given_prior_pipeline7_all_empty_generation_when_upgraded_to_pipeline8_then_bump_only_resource_mst(self):
        self.artwork()
        self.install_two_sounds(v1=2, v2=3)
        self._install_early_packs()
        self.add_resource('900', 'unit', 'unit4_common.cpk', 'common_lang', 15, b'UNIT-DRIFT', 1, phase='TUTO')
        self.add_resource('901', 'monster', 'monster5_common.cpk', 'common_lang', 12, b'MONSTER-DRIFT', 1, phase='')
        self.add_resource('902', 'unit', 'LBMovie1_common.cpk', 'common_lang', 4, b'MOVIE-STOCK', 11, phase='')
        self.add_resource('116002', 'banner', 'banner2_common.cpk', 'common_lang', 1, b'BANNER2-COMMON', 14, phase='DEFINE')
        self.add_resource('116501', 'banner', 'banner_home1.cpk', 'en', 17, b'BANNER-HOME1', 12, phase='DEFINE')
        self.add_resource('9400512', 'banner', 'banner2.cpk', 'en', 1, b'BANNER2-EN', 10, phase='DEFINE')
        sound_snapshots.prepare(self.config)

        with patch.object(rules, 'PIPELINE_VERSION', 7):
            r1 = prep.prepare_data(
                self.config,
                vortex_art=True,
                sounds=True,
                cpk_policy=policy.ALL_EMPTY_CPKS,
            )
        self.assertEqual(r1['generation'], 1)
        g1 = prep.load_prepared(self.config)
        self.assertEqual(g1.manifest['pipeline_version'], 7)
        self.assertEqual(set(g1.manifest['upfront_packs']), {'900:JwbkKrjA', '901:JwbkKrjA'})
        res1 = {
            r['9ZCEWn0z']: r for _, r, _ in master_rows(
                g1.lookup(g1.manifest['tables']['F_RESOURCE_MST']['path']), rules.RESOURCE.key
            )
        }
        for define_id in ('116002', '116501', '9400512'):
            self.assertEqual(res1[define_id]['81fTkEDP'], 'DEFINE')

        # Upgrade to PIPELINE_VERSION = 8 (ALL_CPKS with promote_define_phase=True)
        r2 = prep.prepare_data(self.config)
        self.assertEqual(r2['generation'], 2)
        self.assertEqual(r2['version_reuse']['packs'], {'reused': 1, 'bumped': 0})
        self.assertEqual(r2['version_reuse']['sounds'], {'reused': 2, 'bumped': 0})
        self.assertEqual(r2['version_reuse']['upfront_packs'], {'reused': 2, 'bumped': 0})
        self.assertEqual(r2['version_reuse']['tables'], {'reused': 363, 'bumped': 1})

        g2 = prep.load_prepared(self.config)
        self.assertEqual(g2.manifest['pipeline_version'], 8)
        bumped_tables = {
            name for name, entry in g2.manifest['tables'].items()
            if entry['version_generation'] == 2
        }
        self.assertEqual(bumped_tables, {'F_RESOURCE_MST'})
        res2 = {
            r['9ZCEWn0z']: r for _, r, _ in master_rows(
                g2.lookup(g2.manifest['tables']['F_RESOURCE_MST']['path']), rules.RESOURCE.key
            )
        }
        for define_id in ('116002', '116501', '9400512'):
            self.assertEqual(res2[define_id]['81fTkEDP'], 'TUTO')
        self.assertTrue(prep.verify_data(self.config)['ok'])

    def test_given_direct_upfront_collect_when_overlay_missing_audio_and_vortex_present_then_apply_policy_and_precedence(self):
        self.artwork()
        self.add_resource('1', 'resources', 'resources.cpk', 'common_lang', 8, b'PRE-TUTO', 8, phase='PRE_TUTO')
        self.add_resource('2', 'unit', 'unit4_common.cpk', 'common_lang', 9, b'TUTO-UNIT', 9, phase='TUTO')
        self.add_resource('902', 'banner', 'banner2_common.cpk', 'common_lang', 4, b'BANNER', 6, phase='DEFINE')
        self.add_resource('903', 'monster', 'monster1_common.cpk', 'common_lang', 5, b'ROOT-MONSTER', 12, phase='')
        self.add_resource('904', 'area', 'area_bg.cpk', 'common_lang', 6, b'BG-CPK', 6, phase='BACKGROUND')
        self.add_resource('905', 'sound/bgm', 'Bgm001.acb', 'common_lang', 2, b'BGM', 3, phase='GAME')
        # Missing CPK file on disk: register metadata without writing file
        missing_path = self.add_resource('906', 'unit', 'LBMovie99_common.cpk', 'common_lang', 3, b'GONE', 4, phase='')
        missing_path.unlink()
        # Overlay precedence: overlay copy must win over CDN_ROOT for monster1_common.cpk
        overlay_path = self.config.data / 'overlay/common_lang/sd/monster/Ver5_monster1_common.cpk'
        overlay_path.parent.mkdir(parents=True, exist_ok=True)
        overlay_payload = b'OVERLAY-MONSTER-DRIFTED'
        overlay_path.write_bytes(overlay_payload)

        sources, *_ = collect_native_inputs(self.config)
        records_all = upfront_resources.collect(
            self.config,
            sources,
            exclude_resources=(art.RESOURCE_ID,),
            cpk_policy=policy.ALL_CPKS,
        )
        self.assertEqual(set(records_all['files']), {'1:JwbkKrjA', '2:JwbkKrjA', '902:JwbkKrjA', '903:JwbkKrjA', '904:JwbkKrjA'})
        self.assertEqual(records_all['missing'], ['906:JwbkKrjA'])
        self.assertNotIn('905:JwbkKrjA', records_all['files'])
        self.assertNotIn(art.RESOURCE_ID + ':MLOSu5E0', records_all['files'])
        self.assertEqual(
            records_all['files']['903:JwbkKrjA']['path'],
            'overlay/common_lang/sd/monster/Ver5_monster1_common.cpk',
        )
        self.assertEqual(records_all['files']['903:JwbkKrjA']['size'], len(overlay_payload))
        self.assertEqual(
            records_all['files']['903:JwbkKrjA']['sha256'],
            hashlib.sha256(overlay_payload).hexdigest(),
        )
        self.assertEqual(records_all['files']['903:JwbkKrjA']['advertised'], 12)

        records_legacy = upfront_resources.collect(
            self.config,
            sources,
            exclude_resources=(art.RESOURCE_ID,),
            cpk_policy=policy.LEGACY_MENU_AND_UNITS,
        )
        self.assertEqual(set(records_legacy['files']), {'1:JwbkKrjA', '2:JwbkKrjA'})
        self.assertEqual(records_legacy['missing'], [])


class Launch1EarlyResourceCatalog(unittest.TestCase):
    def setUp(self):
        self.profile = patch('engine_profile.current_profile', return_value=IOS_REVIVAL)
        self.profile.start()
        self.addCleanup(self.profile.stop)
        self.player = SimpleNamespace(data={'identity': {'user_id': '123'}}, mode='live', dirty=False)
        self.tables = {
            'F_FUNCTION_MST': {'version': 210010},
            'F_RESOURCE_MST': {'version': 210010},
            'F_RESOURCE_VERSION_MST_LOCALIZE': {'version': 210010},
            'F_RESOURCE_CHECKSUM_MST': {'version': 210010},
        }
        self.state = SimpleNamespace(
            player=self.player,
            state_dirty=False,
            native_tables=SimpleNamespace(manifest={'tables': self.tables}),
        )
        self.req = json.dumps({'LhVz6aD2': [{'9Tbns0eI': '123', '6e4ik6kA': 'iphone-device'}]})

    def test_given_fresh_device_when_early_requested_then_emit_nothing_and_write_nothing(self):
        before = copy.deepcopy(self.player.data)
        out = revival_boot.step({'keep': 1}, 'lEHBdOEf', self.req, self.state)
        self.assertEqual(out, {'keep': 1})
        self.assertEqual(self.player.data, before)
        self.assertFalse(self.player.dirty)
        self.assertFalse(self.state.state_dirty)

    def test_given_returning_device_same_generation_when_early_requested_then_emit_function_and_catalog_read_only(self):
        revival_boot.step({}, '75fYdNxq', self.req, self.state)
        revival_boot.step({}, 'Daud71Hn', self.req, self.state)
        before = copy.deepcopy(self.player.data)
        self.player.dirty = False
        self.state.state_dirty = False

        spec = {'other': 'preserved'}
        out = revival_boot.step(spec, 'lEHBdOEf', self.req, self.state)
        self.assertEqual(spec, {'other': 'preserved'})
        self.assertEqual(
            out['c1qYg84Q'],
            [
                {'a4hXTIm0': 'F_FUNCTION_MST', 'wM9AfX6I': '210010'},
                {'a4hXTIm0': 'F_RESOURCE_MST', 'wM9AfX6I': '210010'},
                {'a4hXTIm0': 'F_RESOURCE_VERSION_MST_LOCALIZE', 'wM9AfX6I': '210010'},
                {'a4hXTIm0': 'F_RESOURCE_CHECKSUM_MST', 'wM9AfX6I': '210010'},
            ],
        )
        self.assertEqual(self.player.data, before)
        self.assertFalse(self.player.dirty)
        self.assertFalse(self.state.state_dirty)

    def test_given_returning_device_after_new_generation_when_early_requested_then_advertise_new_catalog_even_if_function_bumped(self):
        revival_boot.step({}, '75fYdNxq', self.req, self.state)
        revival_boot.step({}, 'Daud71Hn', self.req, self.state)
        # New prepare-data generation bumps all 4 tables.
        self.tables['F_FUNCTION_MST']['version'] = 220010
        self.tables['F_RESOURCE_MST']['version'] = 220010
        self.tables['F_RESOURCE_VERSION_MST_LOCALIZE']['version'] = 220010
        self.tables['F_RESOURCE_CHECKSUM_MST']['version'] = 220010

        out = revival_boot.step({}, 'lEHBdOEf', self.req, self.state)
        self.assertEqual(
            out['c1qYg84Q'],
            [
                {'a4hXTIm0': 'F_RESOURCE_MST', 'wM9AfX6I': '220010'},
                {'a4hXTIm0': 'F_RESOURCE_VERSION_MST_LOCALIZE', 'wM9AfX6I': '220010'},
                {'a4hXTIm0': 'F_RESOURCE_CHECKSUM_MST', 'wM9AfX6I': '220010'},
            ],
        )

    def test_given_rollback_toggle_when_early_requested_then_revert_to_function_only_behavior(self):
        revival_boot.step({}, '75fYdNxq', self.req, self.state)
        revival_boot.step({}, 'Daud71Hn', self.req, self.state)
        with patch.object(revival_boot, 'EARLY_RESOURCE_CATALOG', False):
            out = revival_boot.step({}, 'lEHBdOEf', self.req, self.state)
            self.assertEqual(out['c1qYg84Q'], [{'a4hXTIm0': 'F_FUNCTION_MST', 'wM9AfX6I': '210010'}])
        with patch.dict(os.environ, {'FFBE_IOS_EARLY_RESOURCE_CATALOG': '0'}):
            out = revival_boot.step({}, 'lEHBdOEf', self.req, self.state)
            self.assertEqual(out['c1qYg84Q'], [{'a4hXTIm0': 'F_FUNCTION_MST', 'wM9AfX6I': '210010'}])

    def test_given_non_ios_profile_wrong_user_or_frozen_player_when_boot_runs_then_write_nothing(self):
        revival_boot.step({}, '75fYdNxq', self.req, self.state)
        revival_boot.step({}, 'Daud71Hn', self.req, self.state)
        before = copy.deepcopy(self.player.data)

        with patch('engine_profile.current_profile', return_value=LEGACY):
            self.assertEqual(revival_boot.step({}, 'lEHBdOEf', self.req, self.state), {})
            revival_boot.step({}, '75fYdNxq', self.req, self.state)

        self.assertEqual(revival_boot.step({}, 'lEHBdOEf', self.req.replace('123', '999'), self.state), {})

        self.player.mode = 'frozen'
        revival_boot.step({}, '75fYdNxq', self.req, self.state)
        self.assertEqual(self.player.data, before)

    def test_given_non_home_or_unknown_reply_when_recording_receipt_then_never_promote_pending_to_held(self):
        revival_boot.record_receipt(self.player, self.state, '75fYdNxq', 'dev-hash', '210010')
        before = copy.deepcopy(self.player.data)
        self.player.dirty = False
        self.state.state_dirty = False

        for bad_reply in ('lEHBdOEf', 'UNKNOWN', 'o5sRL2Sa'):
            self.assertFalse(revival_boot.record_receipt(self.player, self.state, bad_reply, 'dev-hash', '210010'))
            next_ledger = revival_boot.next_receipt_ledger(self.player.data[revival_boot.LEDGER], bad_reply, 'dev-hash', '210010')
            self.assertEqual(next_ledger, {'pending': {'dev-hash': '210010'}, 'held': {}})
        self.assertEqual(self.player.data, before)
        self.assertFalse(self.player.dirty)
        self.assertFalse(self.state.state_dirty)

        # Verify bounded 8-entry eviction on both pending and held buckets.
        ledger = {}
        for idx in range(10):
            ledger = revival_boot.next_receipt_ledger(ledger, '75fYdNxq', f'd{idx}', '210010')
            ledger = revival_boot.next_receipt_ledger(ledger, 'Daud71Hn', f'd{idx}', '210010')
        self.assertEqual(list(ledger['held']), [f'd{idx}' for idx in range(2, 10)])
        for idx in range(10):
            ledger = revival_boot.next_receipt_ledger(ledger, '75fYdNxq', f'p{idx}', '210010')
        self.assertEqual(list(ledger['pending']), [f'p{idx}' for idx in range(2, 10)])
        self.assertTrue(revival_boot.record_receipt(self.player, None, 'Daud71Hn', 'dev-hash', '210010'))

    def test_given_existing_spec_rows_or_incomplete_tables_when_projecting_early_versions_then_merge_safely(self):
        spec = {
            'c1qYg84Q': [
                {'a4hXTIm0': 'F_CUSTOM_MST', 'wM9AfX6I': '9'},
                {'a4hXTIm0': 'F_RESOURCE_MST', 'wM9AfX6I': '1'},
            ]
        }
        before_spec = copy.deepcopy(spec)
        ledger = {'held': {'dev-hash': '210010'}}
        out = revival_boot.project_early_versions(spec, self.state.native_tables, ledger, 'dev-hash', early_resource_catalog=True)
        self.assertEqual(spec, before_spec)
        self.assertEqual(
            out['c1qYg84Q'],
            [
                {'a4hXTIm0': 'F_CUSTOM_MST', 'wM9AfX6I': '9'},
                {'a4hXTIm0': 'F_RESOURCE_MST', 'wM9AfX6I': '210010'},
                {'a4hXTIm0': 'F_FUNCTION_MST', 'wM9AfX6I': '210010'},
                {'a4hXTIm0': 'F_RESOURCE_VERSION_MST_LOCALIZE', 'wM9AfX6I': '210010'},
                {'a4hXTIm0': 'F_RESOURCE_CHECKSUM_MST', 'wM9AfX6I': '210010'},
            ],
        )

        # Missing 'version' keys in tables fail safely without KeyError.
        incomplete_prepared = SimpleNamespace(
            manifest={
                'tables': {
                    'F_FUNCTION_MST': {},
                    'F_RESOURCE_MST': {'version': None},
                    'F_RESOURCE_VERSION_MST_LOCALIZE': {'version': 210010},
                    'F_RESOURCE_CHECKSUM_MST': {},
                }
            }
        )
        self.assertEqual(
            revival_boot.build_early_version_rows(
                incomplete_prepared.manifest['tables'], '210010', early_resource_catalog=True
            ),
            [],
        )
        self.assertEqual(
            revival_boot.project_early_versions(spec, incomplete_prepared, ledger, 'dev-hash', early_resource_catalog=True),
            spec,
        )

    def test_given_cqrs_adapters_and_pipeline_when_run_then_segregate_queries_commands_and_rollback(self):
        with tempfile.TemporaryDirectory() as work:
            state_path = Path(work) / 'save.json'
            with patch('revival_battle_commands.settle', side_effect=AssertionError('read-only or persist=False called settle')):
                self.assertEqual(
                    revival_boot.synchronize({'keep': 1}, '75fYdNxq', self.req, self.state, state_path, False),
                    {'keep': 1},
                )
                self.assertEqual(
                    revival_boot.synchronize({'keep': 2}, 'lEHBdOEf', self.req, self.state, state_path, True),
                    {'keep': 2},
                )
                self.assertEqual(revival_boot.project_for_reply({'keep': 3}, '75fYdNxq', self.req, self.state), {'keep': 3})

            # Failed candidate.save() must leave player.data, player.dirty, and state_dirty untouched.
            self.player.save = lambda _path: False
            before_data = copy.deepcopy(self.player.data)
            with self.assertRaises(OSError):
                revival_boot.synchronize({}, '75fYdNxq', self.req, self.state, state_path, True)
            self.assertEqual(self.player.data, before_data)
            self.assertFalse(self.player.dirty)
            self.assertFalse(self.state.state_dirty)

            # Successful atomic settle on 75fYdNxq -> Daud71Hn, then read-only project_for_reply on lEHBdOEf.
            self.player.save = lambda path: (Path(path).write_text(json.dumps(self.player.data)), True)[1]
            revival_boot.synchronize({}, '75fYdNxq', self.req, self.state, state_path, True)
            revival_boot.synchronize({}, 'Daud71Hn', self.req, self.state, state_path, True)
            saved_after_boot = copy.deepcopy(self.player.data)
            self.player.dirty = False
            self.state.state_dirty = False
            with patch('revival_battle_commands.settle', side_effect=AssertionError('project_for_reply called settle')):
                early = revival_boot.project_for_reply({}, 'lEHBdOEf', self.req, self.state)
            self.assertEqual(len(early['c1qYg84Q']), 4)
            self.assertEqual(self.player.data, saved_after_boot)
            self.assertFalse(self.player.dirty)
            self.assertFalse(self.state.state_dirty)

        # Segregated steps & edges pass ffbe_pipeline.validate_pipeline() cleanly.
        self.assertEqual(ffbe_pipeline.validate_pipeline(), [])
        steps = {step.key: step for step in ffbe_pipeline.PIPELINE}
        self.assertEqual(steps['project_revival_boot_early'].writes, 'spec')
        self.assertEqual(steps['synchronize_revival_boot'].writes, 'state')
        edges = {(edge.before, edge.after) for edge in ffbe_pipeline.PIPELINE_EDGES}
        self.assertIn(('serve_version_table', 'project_revival_boot_early'), edges)
        self.assertIn(('serve_version_table', 'synchronize_revival_boot'), edges)


if __name__ == '__main__':
    unittest.main()
