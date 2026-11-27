"""BDD for SOLID/CQRS iOS data updater, flat & managed layouts, and compatibility normalization."""
import copy
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

SOURCE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SOURCE), str(SOURCE / 'server')]

import test_ios_preparation as prep_harness
from ios_server import (
    cli,
    managed_content as content,
    native_inputs,
    native_tables as rules,
    pack_install,
    pack_layers,
    pack_manifest as policy,
)
from ios_server.config import Configuration
from ios_server.update_commands import DefaultSnapshotPreparer, UpdateCommandHandler
from ios_server.update_layouts import FlatBrowserDataStrategy, ManagedPackStrategy, detect_layout
from ios_server.update_normalize import DefaultCompatibilityInspector, DefaultCompatibilityNormalizer
from ios_server.update_queries import UpdateQueryHandler, check_update
from ios_server.update_types import SnapshotCheck


def zip_bytes(files: dict[str, bytes]) -> bytes:
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            entry = zipfile.ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, value)
    return raw.getvalue()


def _build_native_files(*, managed: bool, include_unregistered_mst: bool = False, corrupt_quest_index: bool = False,
                        stale_xml: bool = False) -> dict[str, bytes]:
    """Build a complete 364-table pack payload using test_ios_preparation fixtures."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        holder = SimpleNamespace(config=Configuration(root / 'runtime', root / 'content'))
        prep_harness.NativePreparation.fixture(holder, managed=True)
        files = {
            path.relative_to(holder.config.data).as_posix(): path.read_bytes()
            for path in holder.config.data.rglob('*')
            if path.is_file()
        }
        xml = ET.fromstring(files['static/client/shared_prefs/gamedata.xml'])
        reg = {row.get('name'): row.text for row in xml}
        files['metadata/registry.json'] = policy.encoded(reg)
        files['static/mst_decoded/fixture.ndjson'] = b'{}\n'
        files['static/text_decoded/fixture.ndjson'] = b'{}\n'
        files['native/common_lang/fixture.dat'] = b'fixture'
        if include_unregistered_mst:
            files['native/mst/Ver1_UNREG999.dat'] = b'unregistered'
        if corrupt_quest_index:
            quest_table = rules.BY_NAME['F_TEXT_QUEST']
            quest_rel = 'native/' + quest_table.path(10)
            quest_bytes = prep_harness.text(quest_table.key, ['MST_QUEST_1^Updated Quest^Updated Quest'])
            files[quest_rel] = quest_bytes
            # Leave Ver10_i5QEJpua.dat with the stale MD5/length from before quest_bytes changed.
        if stale_xml:
            # Drop one registered key from gamedata.xml while keeping registry.json complete.
            broken = ET.Element('map')
            for row in list(xml)[:-1]:
                broken.append(row)
            files['static/client/shared_prefs/gamedata.xml'] = ET.tostring(broken, encoding='utf-8', xml_declaration=True)
        if not managed:
            # Keep client-assets separate just like data/latest.json.
            pass
        return files


class UpdaterQueryPurityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='ios-updater-query-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.config = Configuration(self.root / 'runtime', self.root / 'data')
        self.config.data.mkdir(parents=True)
        self.manifest = self.root / 'latest.json'
        self.payload = {'native/mst/Ver1_ZQqB38Ns.dat': b'table'}
        archive = zip_bytes(self.payload)
        self.doc = {
            'schema': 1,
            'revision': 5,
            'version': '2026.11.21.5',
            'packs': [
                {
                    'id': 'base',
                    'url': 'https://example.test/base.zip',
                    'size': len(archive),
                    'unpackedSize': len(self.payload['native/mst/Ver1_ZQqB38Ns.dat']),
                    'sha256': policy.digest(archive),
                }
            ],
        }
        self.manifest.write_bytes(policy.encoded(self.doc))

    def _snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_given_outdated_flat_tree_when_check_update_runs_then_pure_read_only_exit_2(self):
        # Create a minimal flat marker so detect_layout selects 'flat', but leave receipt missing.
        (self.config.data / 'client/files/mst').mkdir(parents=True)
        (self.config.data / 'client/shared_prefs').mkdir(parents=True)
        (self.config.data / 'client/shared_prefs/gamedata.xml').write_text('<map/>')
        before = self._snapshot()
        modules = set(sys.modules)

        with patch.object(Path, 'mkdir', side_effect=AssertionError('query wrote directory')), \
                patch('socket.socket', side_effect=AssertionError('query opened socket')):
            status = check_update(self.config, self.manifest)

        self.assertTrue(status['ok'])
        self.assertTrue(status['update_needed'])
        self.assertEqual(status['layout'], 'flat')
        self.assertEqual(len(status['packs_needed']), 1)
        self.assertEqual(status['packs_needed'][0]['id'], 'base')
        self.assertFalse(status['snapshots']['sounds']['ok'])
        self.assertFalse(status['snapshots']['data']['ok'])
        self.assertEqual(self._snapshot(), before)
        self.assertFalse({'capture_server', 'player_state', 'data_paths'} & (set(sys.modules) - modules))

        stdout, stderr = io.StringIO(), io.StringIO()
        with patch('sys.stdout', stdout), patch('sys.stderr', stderr):
            rc = cli.main(['check-update', '--root', str(self.config.root), '--data', str(self.config.data),
                           '--manifest', str(self.manifest), '--summary'])
        self.assertEqual(rc, 2)
        self.assertIn('iOS data update needed', stderr.getvalue())
        self.assertTrue(json.loads(stdout.getvalue())['update_needed'])

    def test_given_outdated_managed_tree_when_check_update_runs_then_pure_read_only_exit_2(self):
        # Uninstalled directory maps to managed strategy on check-update.
        before = self._snapshot()
        with patch.object(Path, 'mkdir', side_effect=AssertionError('query wrote directory')), \
                patch('socket.socket', side_effect=AssertionError('query opened socket')):
            status = check_update(self.config, self.manifest)
        self.assertTrue(status['ok'])
        self.assertTrue(status['update_needed'])
        self.assertEqual(status['layout'], 'uninstalled')
        self.assertEqual(len(status['packs_needed']), 1)
        self.assertEqual(self._snapshot(), before)

    def test_given_missing_manifest_when_check_update_runs_then_exit_1(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch('sys.stdout', stdout), patch('sys.stderr', stderr):
            rc = cli.main(['check-update', '--root', str(self.config.root), '--data', str(self.config.data),
                           '--manifest', str(self.root / 'nonexistent.json')])
        self.assertEqual(rc, 1)
        self.assertFalse(json.loads(stdout.getvalue())['ok'])


class FlatIncrementalAndNormalizationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='ios-updater-flat-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.config = Configuration(self.root / 'runtime', self.root / 'data')
        self.config.data.mkdir(parents=True)
        self.archives = self.root / 'archives'
        self.archives.mkdir()
        self.manifest = self.root / 'latest.json'

    def _write_manifest(self, revision: int, version: str, packs: list[tuple[str, dict[str, bytes]]]) -> None:
        rows = []
        for pack_id, files in packs:
            raw = zip_bytes(files)
            (self.archives / f'{pack_id}.zip').write_bytes(raw)
            rows.append({
                'id': pack_id,
                'url': f'https://example.test/{pack_id}.zip',
                'size': len(raw),
                'unpackedSize': sum(len(v) for v in files.values()),
                'sha256': policy.digest(raw),
            })
        self.manifest.write_bytes(policy.encoded({
            'schema': 1,
            'revision': revision,
            'version': version,
            'packs': rows,
        }))

    def test_given_flat_packs_with_unchanged_changed_and_new_when_updated_then_incremental_and_idempotent(self):
        client_assets = {'static/client/game-assets.apk': b'apk-bytes'}
        base_files = _build_native_files(managed=False)
        patch_v1 = {
            'native/mst/Ver1_OLD99999.dat': b'old-table',
            'native/en/shared.dat': b'v1',
        }
        # Seed flat layout marker so detect_layout selects 'flat'.
        (self.config.data / 'client/shared_prefs').mkdir(parents=True)
        (self.config.data / 'client/shared_prefs/gamedata.xml').write_text('<map/>')
        self._write_manifest(1, '2026.11.21.1', [('client-assets', client_assets), ('base', base_files), ('patch', patch_v1)])

        # Stub snapshot verifier/preparer so we test flat layout + normalization end-to-end cleanly.
        always_ok_verifier = SimpleNamespace(verify_all=lambda _cfg: {
            name: SnapshotCheck(name, True, None)
            for name in ('sounds', 'banners', 'home_banners', 'data')
        })
        handler = UpdateCommandHandler(
            query_handler=UpdateQueryHandler(snapshot_verifier=always_ok_verifier),
            service_stopper=lambda _cfg: {'stopping': False},
            snapshot_preparer=SimpleNamespace(
                prepare_stale=lambda _cfg, _checks, **_kw: {
                    'prepared': {},
                    'skipped': ['sounds', 'banners', 'home_banners', 'data'],
                }
            ),
        )
        first = handler.execute(self.config, self.manifest, archive_dir=self.archives, emit=lambda _m: None)
        self.assertTrue(first['ok'])
        self.assertTrue(first['updated_now'])
        self.assertEqual(detect_layout(self.config), 'flat')
        self.assertEqual((self.config.data / 'client/game-assets.apk').read_bytes(), b'apk-bytes')
        self.assertEqual((self.config.data / 'client/files/en/shared.dat').read_bytes(), b'v1')
        # Unregistered mst file from patch_v1 was pruned by normalization.
        self.assertFalse((self.config.data / 'client/files/mst/Ver1_OLD99999.dat').exists())
        receipt = json.loads((self.config.data / '.web_setup/installed.json').read_bytes())
        self.assertNotIn('client/files/mst/Ver1_OLD99999.dat', receipt['files'])

        # Now update: base is UNCHANGED, patch is CHANGED (superseding Ver1_ZQqB38Ns or another .dat), and extra is NEW.
        # Add an allowed mst file in patch v1b and replace it in patch v2 to verify superseded .dat cleanup.
        mst_token = rules.RESOURCE.token  # ZQqB38Ns
        patch_v1b = {
            f'native/mst/Ver99_{mst_token}.dat': b'superseded-mst',
            'native/en/shared.dat': b'v1b',
        }
        self._write_manifest(2, '2026.11.21.2', [('client-assets', client_assets), ('base', base_files), ('patch', patch_v1b)])
        handler.execute(self.config, self.manifest, archive_dir=self.archives, emit=lambda _m: None)
        self.assertTrue((self.config.data / f'client/files/mst/Ver99_{mst_token}.dat').is_file())

        patch_v2 = {'native/en/shared.dat': b'v2'}
        extra_v2 = {'native/exvius/equipment-enhancement/1010/top.html': b'<html>ok</html>'}
        self._write_manifest(3, '2026.11.21.3', [('client-assets', client_assets), ('base', base_files), ('patch', patch_v2), ('extra', extra_v2)])

        # Remove client-assets.zip and base.zip from archives to prove unchanged packs are skipped without archive/network.
        (self.archives / 'client-assets.zip').unlink()
        (self.archives / 'base.zip').unlink()
        second = handler.execute(
            self.config,
            self.manifest,
            archive_dir=self.archives,
            opener=lambda *_a, **_k: self.fail('unexpected network call'),
            emit=lambda _m: None,
        )
        self.assertTrue(second['ok'])
        self.assertTrue(second['updated_now'])
        self.assertEqual(second['packs_result']['updated_packs'], ['patch', 'extra'])
        self.assertFalse((self.config.data / f'client/files/mst/Ver99_{mst_token}.dat').exists())
        self.assertEqual((self.config.data / 'client/files/en/shared.dat').read_bytes(), b'v2')
        self.assertEqual(
            (self.config.data / 'client/files/exvius/equipment-enhancement/1010/top.html').read_bytes(),
            b'<html>ok</html>',
        )

        # Rerunning is idempotent.
        third = handler.execute(self.config, self.manifest, archive_dir=self.archives, emit=lambda _m: None)
        self.assertTrue(third['ok'])
        self.assertFalse(third['updated_now'])

    def test_given_android_pack_drift_when_normalized_then_native_inputs_passes_while_remaining_strict(self):
        dirty = _build_native_files(
            managed=False,
            include_unregistered_mst=True,
            corrupt_quest_index=True,
            stale_xml=True,
        )
        (self.config.data / 'client/shared_prefs').mkdir(parents=True)
        (self.config.data / 'client/shared_prefs/gamedata.xml').write_text('<map/>')
        self._write_manifest(1, '2026.11.21.1', [('dirty', dirty)])

        FlatBrowserDataStrategy().apply(self.config, self.manifest, archive_dir=self.archives)

        # Before normalization, native_inputs.collect strictly rejects the dirty tree.
        with self.assertRaises(ValueError):
            native_inputs.collect(self.config)

        report = DefaultCompatibilityInspector().inspect(self.config)
        self.assertTrue(report.any_needed)
        self.assertIn('client/files/mst/Ver1_UNREG999.dat', report.unregistered_mst_files)
        self.assertIn('F_TEXT_QUEST', report.localized_index_mismatches)
        self.assertTrue(report.registry_sync_needed)

        norm_result = DefaultCompatibilityNormalizer().normalize(self.config)
        self.assertTrue(norm_result['normalized_now'])
        self.assertEqual(norm_result['reconciled_localized_tables'], ['F_TEXT_QUEST'])
        self.assertTrue(norm_result['registry_synced'])

        # After normalization, strict native_inputs.collect succeeds!
        _, provenance, _, context, _ = native_inputs.collect(self.config)
        self.assertEqual(context['coverage']['registered'], 364)
        self.assertIn('F_TEXT_QUEST', provenance['tables'])

        # Receipt was updated in sync so check-update is clean (aside from unbuilt snapshots).
        flat_check = FlatBrowserDataStrategy().inspect(self.config, self.manifest)
        self.assertTrue(flat_check.valid)
        self.assertFalse(DefaultCompatibilityInspector().inspect(self.config).any_needed)


class ManagedUpdaterTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='ios-updater-managed-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.config = Configuration(self.root / 'runtime', self.root / 'data')
        self.config.data.mkdir(parents=True)
        self.archives = self.root / 'archives'
        self.archives.mkdir()
        self.manifest = self.root / 'latest.json'

    def test_given_new_pack_paths_when_destination_checked_then_allow_new_and_reject_unsafe(self):
        self.assertEqual(
            policy.destination('native/exvius/equipment-enhancement/1010/top.html'),
            'native/exvius/equipment-enhancement/1010/top.html',
        )
        self.assertEqual(
            policy.destination('static/prepared_tables/Ver100_abc.utf8'),
            'static/prepared_tables/Ver100_abc.utf8',
        )
        for bad in (
            'static/client/game-assets.apk',
            'static/state/campaign.json',
            'native/exvius/other/secret.txt',
            'native/exvius/equipment-enhancement/../secret.txt',
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                policy.destination(bad)

    def test_given_managed_dirty_pack_when_applied_then_stage_normalized_and_verify_packs_clean(self):
        dirty = _build_native_files(
            managed=True,
            include_unregistered_mst=True,
            corrupt_quest_index=True,
            stale_xml=True,
        )
        dirty['native/exvius/equipment-enhancement/1010/top.html'] = b'<html>item</html>'
        dirty['static/prepared_tables/Ver1_sample.utf8'] = b'prepared'
        raw = zip_bytes(dirty)
        (self.archives / 'base.zip').write_bytes(raw)
        self.manifest.write_bytes(policy.encoded({
            'schema': 1,
            'revision': 1,
            'version': '2026.11.21.1',
            'packs': [{
                'id': 'base',
                'url': 'https://example.test/base.zip',
                'size': len(raw),
                'unpackedSize': sum(len(v) for v in dirty.values()),
                'sha256': policy.digest(raw),
            }],
        }))

        result = ManagedPackStrategy().apply(self.config, self.manifest, archive_dir=self.archives, emit=lambda _m: None)
        self.assertTrue(result['installed_now'])
        self.assertTrue(pack_install.verify(self.config, self.manifest)['ok'])
        fresh = Configuration(self.config.root, self.config.data)
        self.assertFalse(DefaultCompatibilityInspector().inspect(fresh).any_needed)
        # Strict native_inputs.collect succeeds on the published immutable generation.
        native_inputs.collect(fresh)
        # Source layer remains untouched and still contains the original unregistered file.
        pack = policy.read(self.manifest).packs[0]
        layer_dir, _, _ = pack_layers.load(self.config.data, pack, verify=True)
        self.assertTrue((layer_dir / 'native/mst/Ver1_UNREG999.dat').is_file())


class SnapshotOrchestrationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='ios-updater-orch-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.config = Configuration(self.root / 'runtime', self.root / 'data')
        self.config.data.mkdir(parents=True)
        self.manifest = self.root / 'latest.json'
        self.manifest.write_bytes(b'{}')

    def test_given_valid_sounds_and_stale_banners_when_updated_then_skip_sounds_and_run_in_order(self):
        calls = []
        state = {'sounds': True, 'banners': False, 'home_banners': False, 'data': False}

        class FakeReader:
            def inspect(self, _cfg, _m):
                from ios_server.update_types import LayoutInspection
                return LayoutInspection('flat', '1', '1', 1, (), 0, 0, True, None)

        class FakeNormInspector:
            def inspect(self, _cfg):
                from ios_server.update_types import NormalizationReport
                return NormalizationReport((), (), False)

        class FakeVerifier:
            def verify_all(self, _cfg):
                return {name: SnapshotCheck(name, ok, None if ok else 'stale') for name, ok in state.items()}

        def fake_prepare_sounds(_cfg):
            calls.append('prepare-sounds')
            state['sounds'] = True
            return {'ok': True, 'prepared_now': True}

        def fake_prepare_banners(_cfg):
            calls.append('prepare-banners')
            state['banners'] = True
            return {'ok': True, 'prepared_now': True}

        def fake_prepare_home(_cfg):
            calls.append('prepare-home-banners')
            state['home_banners'] = True
            return {'ok': True, 'prepared_now': True}

        def fake_prepare_data(_cfg, *, vortex_art, sounds):
            calls.append(('prepare-data', vortex_art, sounds))
            state['data'] = True
            return {'ok': True, 'prepared_now': True}

        handler = UpdateCommandHandler(
            query_handler=UpdateQueryHandler(FakeReader(), FakeNormInspector(), FakeVerifier()),
            service_stopper=lambda _cfg: calls.append('stop') or {},
        )
        with patch('ios_server.sound_snapshots.prepare', side_effect=fake_prepare_sounds), \
                patch('ios_server.banner_snapshots.prepare', side_effect=fake_prepare_banners), \
                patch('ios_server.home_banners.prepare', side_effect=fake_prepare_home), \
                patch('ios_server.preparation.prepare_data', side_effect=fake_prepare_data):
            result = handler.execute(self.config, self.manifest, emit=lambda _m: None)

        self.assertTrue(result['ok'])
        self.assertTrue(result['updated_now'])
        self.assertEqual(calls, ['stop', 'prepare-banners', 'prepare-home-banners', ('prepare-data', True, True)])

    def test_given_failing_final_gate_when_updated_then_fail_with_diagnostics(self):
        class FakeReader:
            def inspect(self, _cfg, _m):
                from ios_server.update_types import LayoutInspection
                return LayoutInspection('flat', '1', '1', 1, (), 0, 0, True, None)

        class FakeNormInspector:
            def inspect(self, _cfg):
                from ios_server.update_types import NormalizationReport
                return NormalizationReport((), (), False)

        class FakeVerifier:
            def verify_all(self, _cfg):
                return {
                    'sounds': SnapshotCheck('sounds', True, None),
                    'banners': SnapshotCheck('banners', True, None),
                    'home_banners': SnapshotCheck('home_banners', True, None),
                    'data': SnapshotCheck('data', False, 'checksum gate failed'),
                }

        handler = UpdateCommandHandler(
            query_handler=UpdateQueryHandler(FakeReader(), FakeNormInspector(), FakeVerifier()),
            service_stopper=lambda _cfg: {},
        )
        with patch('ios_server.preparation.prepare_data', return_value={'ok': True}):
            result = handler.execute(self.config, self.manifest, emit=lambda _m: None)
        self.assertFalse(result['ok'])
        self.assertIn('checksum gate failed', result['error'])

    def test_given_successful_or_failed_update_when_invoked_via_cli_then_stderr_reports_only_real_failures(self):
        out, err = io.StringIO(), io.StringIO()
        ok_status = {'ok': True, 'update_needed': True, 'updated_now': True, 'error': None}
        with patch('ios_server.update_commands.run_update', return_value=ok_status), \
                redirect_stdout(out), redirect_stderr(err):
            code = cli.main(['update', '--root', str(self.config.root), '--data', str(self.config.data),
                             '--manifest', str(self.manifest)])
        self.assertEqual(code, 0)
        self.assertEqual(err.getvalue(), '')
        self.assertTrue(json.loads(out.getvalue())['ok'])

        out, err = io.StringIO(), io.StringIO()
        fail_status = {'ok': False, 'update_needed': True, 'updated_now': True, 'error': 'Final gate failed'}
        with patch('ios_server.update_commands.run_update', return_value=fail_status), \
                redirect_stdout(out), redirect_stderr(err):
            code = cli.main(['update', '--root', str(self.config.root), '--data', str(self.config.data),
                             '--manifest', str(self.manifest)])
        self.assertEqual(code, 1)
        self.assertEqual(err.getvalue().strip(), 'Final gate failed')


if __name__ == '__main__':
    unittest.main()
