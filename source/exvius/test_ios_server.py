"""BDD for the first iOS milestone; synthetic data, private saves, no listeners."""
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SOURCE), str(SOURCE / 'server')]

from engine_profile import IOS_REVIVAL, LEGACY
from ios_server.config import Configuration
from ios_server.queries import doctor, rotation, status
from replay_calendar import historical_start, rotation_week
from revival_campaign import initialize_campaign

UTC = timezone.utc
NOW = datetime(2026, 11, 9, 3, 0, tzinfo=UTC)  # Sunday 10 PM Eastern.


class IosServerBehavior(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.config = Configuration(self.root / 'private', self.root / 'content')

    def prepared_data(self, managed=False):
        base = self.config.data / 'static' if managed else self.config.data
        for relative in ('mst_decoded', 'text_decoded', 'cpk_extract', 'client/shared_prefs'):
            (base / relative).mkdir(parents=True)
        (base / 'client/shared_prefs/gamedata.xml').write_text('<map/>')
        native = self.config.data / 'native' if managed else base / 'client/files'
        for relative in ('mst', 'common_lang'):
            (native / relative).mkdir(parents=True)
        return base, native

    def test_given_unconfigured_install_when_queries_run_then_no_writes_or_engine_imports(self):
        before = set(self.root.rglob('*'))
        with patch('pathlib.Path.mkdir', side_effect=AssertionError('query wrote')), \
                patch('subprocess.run', side_effect=AssertionError('query spawned a process')):
            report = doctor(self.config)
            saved = status(self.config)
            preview = rotation(self.config, now=NOW, weeks=2)
        self.assertFalse(report['ok'])
        self.assertFalse(saved['has_save'])
        self.assertFalse(preview['anchored'])
        self.assertEqual(preview['windows'][0]['from'], '2016-12-16')
        self.assertEqual(before, set(self.root.rglob('*')))

    def test_given_each_data_layout_when_inspected_then_shared_inputs_and_private_outputs(self):
        for managed in (False, True):
            with self.subTest(managed=managed):
                if managed:
                    self.config = Configuration(self.root / 'other-private', self.root / 'managed')
                static, native = self.prepared_data(managed)
                env = self.config.engine_environment()
                self.assertEqual(env['MST_DIR'], str(static / 'mst_decoded'))
                self.assertEqual(env['CDN_ROOT'], str(native))
                self.assertEqual(env['FFBE_IOS_ROOT'], str(self.config.root))
                self.assertEqual(env['FFBE_DATA'], str(self.config.root))
                self.assertEqual(env['FFBE_IOS_CONTENT_ROOT'], str(self.config.data))
                self.assertEqual(env['STATE_FILE'], str(self.config.state_file))
                self.assertFalse(self.config.root.exists())
                self.assertEqual(doctor(self.config)['missing_data'], [])

    def test_given_shared_root_or_unsafe_slot_when_configured_then_rejected(self):
        for root, data, slot in ((self.root, self.root, 'campaign'),
                                 (self.root / 'assets/private', self.root / 'assets', 'campaign'),
                                 (self.root / 'private', self.root / 'private/assets', 'campaign'),
                                 (self.root / 'private', self.root / 'assets', '../android')):
            with self.subTest(root=root, data=data, slot=slot), self.assertRaises(ValueError):
                Configuration(root, data, slot)

    def test_given_content_symlink_to_private_state_when_inspected_then_rejected(self):
        static, native = self.prepared_data()
        (static / 'mst_decoded').rmdir()
        self.config.root.mkdir()
        (static / 'mst_decoded').symlink_to(self.config.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.config.engine_environment()

    def test_given_weekly_rollover_when_clock_crosses_boundary_then_calendar_advances(self):
        before = datetime(2026, 11, 9, 2, 59, 59, tzinfo=UTC)
        first, second = rotation_week(before), rotation_week(NOW)
        self.assertEqual(second.number, first.number + 1)
        self.assertEqual(second.starts.hour, 22)
        self.assertEqual(second.starts.weekday(), 6)

    def test_given_dst_transition_when_calendar_advances_then_rollover_stays_at_ten_pm(self):
        for start, hours in ((datetime(2026, 3, 2, 4, tzinfo=UTC), 167),
                             (datetime(2026, 10, 26, 3, tzinfo=UTC), 169)):
            with self.subTest(start=start):
                week = rotation_week(start)
                self.assertEqual(week.starts.hour, 22)
                self.assertEqual(week.ends.hour, 22)
                elapsed = week.ends.astimezone(UTC) - week.starts.astimezone(UTC)
                self.assertEqual(elapsed.total_seconds() / 3600, hours)

    def test_given_nv_era_when_history_crosses_it_then_pace_changes_from_three_to_two(self):
        settings = IOS_REVIVAL.replay
        day, index = settings.start, 0
        from datetime import timedelta
        while day < settings.nv_era:
            self.assertEqual(historical_start(index, settings), day)
            day += timedelta(weeks=3)
            index += 1
        self.assertEqual(historical_start(index, settings), day)
        self.assertEqual(historical_start(index + 1, settings), day + timedelta(weeks=2))

    def test_given_saved_anchor_when_server_was_stopped_then_preview_uses_elapsed_calendar(self):
        state = self.player_state()
        initialize_campaign(state, self.config.state_file, now=NOW, profile=IOS_REVIVAL)
        before = self.config.state_file.read_bytes()
        from datetime import timedelta
        preview = rotation(self.config, now=NOW + timedelta(weeks=4))
        self.assertTrue(preview['anchored'])
        self.assertEqual(preview['windows'][0]['index'], 4)
        self.assertEqual(preview['windows'][0]['from'], '2017-03-10')
        self.assertEqual(before, self.config.state_file.read_bytes())

    def player_state(self):
        import player_state
        masters = self.root / 'fixture-masters'
        masters.mkdir(exist_ok=True)
        self.write_masters(masters)
        # Initialization commands also read masters; keep the real synthetic
        # catalogue bound until this scenario finishes.
        self.enterContext(patch.object(player_state, 'MST_DIR', str(masters)))
        self.enterContext(patch.object(player_state, '_TABLES', {}))
        player = player_state.PlayerState.load('', slot='campaign')
        return SimpleNamespace(player=player, state_dirty=False)

    def write_masters(self, masters):
        source = '\n'.join(p.read_text() for p in (SOURCE / 'server').glob('*.py'))
        for name in set(re.findall(r'F_[A-Z0-9_]+\.ndjson', source)):
            (masters / name).write_text('')
        (masters / 'F_UNIT_MST.ndjson').write_text('\n'.join(json.dumps(
            {'3HriTp6B': mid, 'aU3o2D4t': 100,
             'em5hx4FX': '10,100,0,0'}) for mid in ('100000102', '100000202')))
        (masters / 'F_EQUIP_ITEM_MST.ndjson').write_text('\n'.join(json.dumps({'J1YX9kmM': mid})
            for mid in ('302000100', '404000200', '406000100', '409000100', '403046900')))
        (masters / 'F_IMPORTANT_ITEM_MST.ndjson').write_text('\n'.join(json.dumps({'2dfixko3': mid})
            for mid in ('50', '70')))
        (masters / 'F_DEFINE_MST.ndjson').write_text(json.dumps(
            {'AK8Nn7ta': 'CRAFT_RELEASE_SWITCH_ID', 'YjIUDJ97': 'fixture-locked-crafting'}))

    def test_given_initialization_retries_when_campaign_saved_then_anchor_is_written_once(self):
        state = self.player_state()
        self.assertTrue(initialize_campaign(state, self.config.state_file, now=NOW, profile=IOS_REVIVAL))
        first = self.config.state_file.read_bytes()
        saved_player = state.player
        from datetime import timedelta
        self.assertFalse(initialize_campaign(state, self.config.state_file,
                                            now=NOW + timedelta(weeks=5), profile=IOS_REVIVAL))
        self.assertIs(state.player, saved_player)
        self.assertEqual(first, self.config.state_file.read_bytes())
        self.assertEqual(status(self.config)['profile'], 'ios-revival')
        self.assertTrue(status(self.config)['campaign_initialized'])

    def test_given_save_failure_when_initializing_then_original_state_and_save_survive(self):
        state = self.player_state()
        self.config.state_file.parent.mkdir(parents=True)
        self.config.state_file.write_text('previous save bytes')
        original, before = state.player, copy.deepcopy(state.player.data)
        with patch.object(type(original), 'save', return_value=False), self.assertRaises(OSError):
            initialize_campaign(state, self.config.state_file, now=NOW, profile=IOS_REVIVAL)
        self.assertIs(state.player, original)
        self.assertEqual(before, original.data)
        self.assertEqual(self.config.state_file.read_text(), 'previous save bytes')

    def test_given_legacy_profile_when_initializing_then_no_changes(self):
        state = self.player_state()
        before = copy.deepcopy(state.player.data)
        self.assertFalse(initialize_campaign(state, self.config.state_file, now=NOW, profile=LEGACY))
        self.assertEqual(before, state.player.data)
        self.assertFalse(self.config.root.exists())

    def test_given_bad_save_when_queries_run_then_report_error_and_preserve_bytes(self):
        self.config.state_file.parent.mkdir(parents=True)
        for raw in ('{broken', '[]', '{"ios_revival":{"version":1,"replay":{"anchor_week":"bad"}}}'):
            self.config.state_file.write_text(raw)
            with self.subTest(raw=raw):
                self.assertIn('error', status(self.config))
                self.assertFalse(doctor(self.config)['ok'])
                with self.assertRaises(ValueError):
                    rotation(self.config, now=NOW)
                self.assertEqual(self.config.state_file.read_text(), raw)
        self.assertEqual(list(self.config.state_file.parent.iterdir()), [self.config.state_file])

    def test_given_frozen_player_when_initializing_then_no_save_is_created(self):
        state = self.player_state()
        state.player.mode = 'frozen'
        with self.assertRaises(ValueError):
            initialize_campaign(state, self.config.state_file, now=NOW, profile=IOS_REVIVAL)
        self.assertFalse(self.config.root.exists())

    def test_given_unconfigured_cli_when_queries_run_then_no_disk_or_network_effects(self):
        script = '''
import sys
from pathlib import Path
sys.path[:0] = sys.argv[1:3]
def guard(event, args):
    if event.startswith(('socket.', 'subprocess.')) or event in ('os.mkdir', 'os.rename', 'os.remove'):
        raise AssertionError(event)
    if event == 'open' and len(args) > 2 and isinstance(args[2], int) and args[2] & 0x603:
        raise AssertionError('write: ' + str(args))
sys.addaudithook(guard)
from ios_server.cli import main
for command in ('doctor', 'status', 'rotation'):
    result = main([command, '--root', sys.argv[3], '--data', sys.argv[4]])
    assert result in (0, 1)
assert 'capture_server' not in sys.modules
assert 'player_state' not in sys.modules
assert 'data_paths' not in sys.modules
'''
        result = self.child(script, str(self.config.root), str(self.config.data))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.config.root.exists())

    def child(self, script, *args, env=None):
        clean = {k: v for k, v in os.environ.items() if not k.startswith(
            ('FFBE_', 'EXVIUS_', 'STATE_', 'CDN_', 'OUT_', 'GACHA_', 'EVENT_', 'FRIENDS_'))}
        clean.update(env or {})
        return subprocess.run([sys.executable, '-B', '-c', script, str(SOURCE), str(SOURCE / 'server'),
                               *args], env=clean, capture_output=True, text=True, timeout=30)

    def test_given_profile_bound_when_switching_profiles_then_fail_before_engine_rebinding(self):
        result = self.child('''
import sys, os
sys.path[:0] = sys.argv[1:3]
from engine_profile import select_profile, current_profile
select_profile('ios-revival')
os.environ['EXVIUS_ENGINE_PROFILE'] = 'legacy'
assert current_profile().name == 'ios-revival'
try:
    select_profile('legacy')
except RuntimeError:
    pass
else:
    raise AssertionError('profile switched')
''')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_given_legacy_paths_when_imported_then_original_overrides_still_apply(self):
        result = self.child('''
import sys
sys.path[:0] = sys.argv[1:3]
import data_paths as p
from engine_profile import current_profile
assert current_profile().name == 'legacy'
assert p.STATE_FILE == '/legacy/custom.json'
assert p.REQUESTS_DIR == '/legacy/requests'
''', env={'STATE_FILE': '/legacy/custom.json', 'OUT_REQUESTS': '/legacy/requests'})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_given_ios_paths_when_legacy_write_overrides_escape_then_import_is_rejected(self):
        result = self.child('''
import sys
sys.path[:0] = sys.argv[1:3]
try:
    import data_paths
except ValueError:
    pass
else:
    raise AssertionError('unsafe write path accepted')
''', env={'EXVIUS_ENGINE_PROFILE': 'ios-revival', 'FFBE_IOS_ROOT': str(self.config.root),
          'STATE_FILE': str(self.config.data / 'state/android.json')})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_given_ios_engine_when_encrypted_initialize_retries_then_persisted_anchor_is_stable(self):
        static, _ = self.prepared_data()
        self.write_masters(static / 'mst_decoded')
        legacy = self.config.data / 'state/campaign.json'
        legacy.parent.mkdir()
        legacy.write_bytes(b'precious Android campaign')
        result = self.child('''
import sys, json
from pathlib import Path
sys.path[:0] = sys.argv[1:3]
def guard(event, args):
    if event.startswith('socket.'):
        raise AssertionError('Network side effect: ' + event)
sys.addaudithook(guard)
from ios_server.config import Configuration
from ios_server.engine import Engine
from local_game import LocalGame
from engine_profile import current_profile
config = Configuration(Path(sys.argv[3]), Path(sys.argv[4]))
engine = Engine(config)
try:
    server = engine.initialize()
    assert engine.initialize() is server
    assert current_profile().name == 'ios-revival'
    import data_paths
    assert data_paths.DATA_ROOT == str(config.root)  # auxiliary policies must also be private
    assert data_paths.GAME_FILES == str(config.data / 'client/files')
    assert 'ios_revival' not in server.State.player.data
    import ffbe_config, ffbe_pipeline
    assert not ffbe_config.ANNIVERSARY_TICKET
    assert ffbe_pipeline.validate_pipeline() == []
    import ffbe_crypto as crypto
    endpoint = json.loads((Path(sys.argv[2]) / 'endpoints.json').read_text())['by_class']['InitializeRequest']
    request_id, key = endpoint['request_id'], endpoint['encode_key']
    envelope = {'TEAYk6R1': {'z5hB3P01': request_id, 'ytHoz4E2': '1', '9K0Pzcpd': '1167'},
                't7n6cVWf': {'qrVcDe48': crypto.cbc_encrypt(crypto.key16(key), b'{}', double_pad=True)}}
    for _ in range(2):
        response = LocalGame.request(engine, 'POST', endpoint['url'], json.dumps(envelope))
        assert response.status == 200, response.body
        encrypted = json.loads(response.body)['t7n6cVWf']['qrVcDe48']
        raw = crypto.cbc_decrypt(crypto.key16(key), encrypted)
        if raw and 1 <= raw[-1] <= 16 and raw[-raw[-1]:] == bytes([raw[-1]]) * raw[-1]:
            raw = raw[:-raw[-1]]
        assert isinstance(json.loads(raw), dict)
        saved = json.loads(config.state_file.read_text())
        assert saved['ios_revival'] == server.State.player.data['ios_revival']
        if _ == 0:
            anchor = saved['ios_revival']
        else:
            assert saved['ios_revival'] == anchor
    assert server.State.player.data['meta']['engine_profile'] == 'ios-revival'
    assert not list(config.data.rglob('*.tmp'))
    from unittest.mock import patch
    with patch.object(server, 'load_state', side_effect=AssertionError('unsafe flag loaded a campaign')):
        for flags in (['--state-file', str(config.data / 'android.json')],
                      ['--state', '../escape'], ['--state-save', '../../escape']):
            try:
                server.main(flags, in_process=True)
            except ValueError:
                pass
            else:
                raise AssertionError('unsafe state CLI override accepted')
finally:
    engine.close()
''', str(self.config.root), str(self.config.data))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        self.assertEqual(legacy.read_bytes(), b'precious Android campaign')
        self.assertTrue(status(self.config)['campaign_initialized'])
        anchor = json.loads(self.config.state_file.read_text())['ios_revival']
        restart = self.child('''
import sys
sys.path[:0] = sys.argv[1:3]
from ios_server.cli import main
raise SystemExit(main(['init-campaign', '--root', sys.argv[3], '--data', sys.argv[4]]))
''', str(self.config.root), str(self.config.data))
        self.assertEqual(restart.returncode, 0, restart.stdout + restart.stderr)
        self.assertFalse(json.loads(restart.stdout)['initialized_now'])
        self.assertEqual(json.loads(self.config.state_file.read_text())['ios_revival'], anchor)

    def test_given_ios_view_when_battle_cache_misses_then_only_explicit_preparation_writes(self):
        script = '''
import sys, os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path[:0] = sys.argv[1:3]
import battle_content as battle
fixture = {'1IfDqR4n': [{'qo3PECw6': 'fixture'}]}
source = SimpleNamespace(area_of=lambda mid: 'fixture-area')
cache = Path(sys.argv[3]) / 'cache/battles'
with patch.object(battle, 'derive_mission', return_value=fixture):
    if os.environ.get('EXVIUS_ENGINE_PROFILE') == 'ios-revival':
        assert Path(battle.CACHE_ROOT) == cache
        with patch.object(battle.os, 'makedirs', side_effect=AssertionError('view wrote cache')):
            assert battle.assemble('fixture', authored={}, source=source, log=lambda msg: None) == fixture
        assert not cache.exists()
        assert battle.assemble('fixture', authored={}, source=source, write_cache=True,
                               log=lambda msg: None) == fixture
    else:
        assert battle.assemble('fixture', authored={}, source=source, cache_root=str(cache),
                               log=lambda msg: None) == fixture
assert (cache / 'fixture-area.json').is_file()
'''
        for profile in ('ios-revival', 'legacy'):
            with self.subTest(profile=profile):
                root = self.root / profile
                result = self.child(script, str(root), env={
                    'EXVIUS_ENGINE_PROFILE': profile, 'FFBE_IOS_ROOT': str(root)})
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_given_occupied_instance_lock_when_initializing_then_no_engine_import_or_save(self):
        import fcntl
        self.prepared_data()
        self.config.root.mkdir()
        with (self.config.root / 'instance.lock').open('a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.child('''
import sys
from pathlib import Path
sys.path[:0] = sys.argv[1:3]
from ios_server.config import Configuration
from ios_server.engine import Engine
config = Configuration(Path(sys.argv[3]), Path(sys.argv[4]))
def forbidden(name):
    raise AssertionError('Imported engine while instance is occupied: ' + name)
try:
    Engine(config, import_module=forbidden).initialize()
except RuntimeError as error:
    assert 'Another iOS instance' in str(error), error
else:
    raise AssertionError('Instance lock ignored')
''', str(self.config.root), str(self.config.data))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.config.state_file.exists())

    def test_given_failed_engine_initialization_when_retried_then_instance_lock_was_released(self):
        self.prepared_data()
        result = self.child('''
import sys, fcntl
from pathlib import Path
sys.path[:0] = sys.argv[1:3]
from ios_server.config import Configuration
from ios_server.engine import Engine
config = Configuration(Path(sys.argv[3]), Path(sys.argv[4]))
class Broken:
    @staticmethod
    def main(*args, **kwargs):
        return 3
try:
    Engine(config, import_module=lambda name: Broken).initialize()
except RuntimeError as error:
    assert 'failed (3)' in str(error), error
else:
    raise AssertionError('Engine failure ignored')
with (config.root / 'instance.lock').open('a+b') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
assert not config.state_file.exists()
''', str(self.config.root), str(self.config.data))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_given_encoded_paths_and_symlink_fallbacks_when_fetched_then_private_files_are_not_served(self):
        static, native = self.prepared_data()
        self.write_masters(static / 'mst_decoded')
        self.config.root.mkdir()
        secret = self.config.root / 'private-key.pem'
        secret.write_bytes(b'private key must never reach a phone')
        (native / 'mst/Ver1_fixture.dat').symlink_to(secret)
        (native / 'mst/Ver2_publicfixture.dat').write_bytes(b'public token fixture')
        (native / 'public.dat').write_bytes(b'public fixture')
        art = static / 'cpk_extract/en/banner'
        art.mkdir(parents=True)
        (art / 'public.png').write_bytes(b'public art fixture')
        result = self.child('''
import sys
from pathlib import Path
from unittest.mock import patch
sys.path[:0] = sys.argv[1:3]
from ios_server.config import Configuration
from ios_server.engine import Engine
from local_game import LocalGame
config = Configuration(Path(sys.argv[3]), Path(sys.argv[4]))
engine = Engine(config)
try:
    server = engine.initialize()
    secret = config.root / 'private-key.pem'
    for path in ('/%2e%2e/private/private-key.pem', '/mst/Ver1_fixture.dat', '/mst/Ver999_fixture.dat',
                 '/%2F' + str(secret)):
        for method in ('GET', 'HEAD'):
            response = LocalGame.request(engine, method, path)
            assert response.status in (400, 404), (path, response.status, response.body)
            assert secret.read_bytes() not in response.body
    response = LocalGame.request(engine, 'GET', '/public.dat')
    assert (response.status, response.body) == (200, b'public fixture')
    response = LocalGame.request(engine, 'GET', '/mst/Ver999_publicfixture.dat')
    assert (response.status, response.body) == (200, b'public token fixture')
    with patch.object(server, 'banner_art_index', return_value={'secret.png': str(secret)}), \
         patch.object(server, 'area_art_index', return_value={}):
        response = LocalGame.request(engine, 'GET', '/banner/en/secret.png')
        assert response.status == 404, response.body
    with patch.object(server, 'banner_art_index', return_value={
            'public.png': str(config.data / 'cpk_extract/en/banner/public.png')}):
        response = LocalGame.request(engine, 'GET', '/banner/en/public.png')
        assert (response.status, response.body) == (200, b'public art fixture')
finally:
    engine.close()
''', str(self.config.root), str(self.config.data))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_given_managed_data_when_initializing_campaign_then_use_native_assets_and_private_save(self):
        static, native = self.prepared_data(managed=True)
        self.write_masters(static / 'mst_decoded')
        result = self.child('''
import sys
from pathlib import Path
sys.path[:0] = sys.argv[1:3]
from ios_server.cli import main
code = main(['init-campaign', '--root', sys.argv[3], '--data', sys.argv[4]])
assert code == 0
import data_paths
assert data_paths.GAME_FILES == str(Path(sys.argv[4]) / 'native')
assert data_paths.DATA_ROOT == sys.argv[3]
''', str(self.config.root), str(self.config.data))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)['initialized_now'])
        self.assertTrue(self.config.state_file.is_file())
        self.assertFalse((self.config.data / 'state').exists())

    def test_given_corrupt_campaign_when_initializing_then_canonical_loader_preserves_original(self):
        static, _ = self.prepared_data()
        self.write_masters(static / 'mst_decoded')
        self.config.state_file.parent.mkdir(parents=True)
        self.config.state_file.write_bytes(b'{corrupt campaign bytes')
        result = self.child('''
import sys
sys.path[:0] = sys.argv[1:3]
from ios_server.cli import main
raise SystemExit(main(['init-campaign', '--root', sys.argv[3], '--data', sys.argv[4]]))
''', str(self.config.root), str(self.config.data))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        backups = list(self.config.state_file.parent.glob('campaign.json.corrupt-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b'{corrupt campaign bytes')
        self.assertTrue(status(self.config)['campaign_initialized'])


if __name__ == '__main__':
    unittest.main()
