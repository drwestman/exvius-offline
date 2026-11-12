"""BDD for prepared replay home images, campaign policy and native carousel views."""
import copy
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import random
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_ios_preparation as native
import test_ios_server as engine_harness
import test_ios_summons as calendar
import test_ios_events as events
from test_ios_vortex_art import png
from ios_server import home_banners as homes, preparation, banner_delivery
from ios_server.config import Configuration
from ios_server.runtime import InstanceLock
import revival_marquee as policy

NOW = calendar.NOW


class Images:
    manifest = {'generation': 8}
    def __init__(self, areas=None):
        self.areas = areas if areas is not None else {str(i): f'event{i}.png' for i in range(100, 110)}
    def image(self, area):
        name = self.areas.get(area)
        return {'source': name, 'url': homes.image_url(area, 'a' * 64)} if name else None


class HomePolicy(unittest.TestCase):
    def data(self):
        data = calendar.campaign(); policy.initialize(data); return data

    def selected(self, data, rows, now=NOW):
        summons = calendar.summons.plan(data, now, banners=(), families=set())
        return events.events.plan(data, now, rows=rows, summons=summons, art={}), summons

    def test_given_defaults_when_initialized_then_persist_once_and_ignore_later_environment_changes(self):
        data = self.data(); before = copy.deepcopy(data)
        self.assertEqual(policy.settings(data), {'enabled': True, 'limit': 6, 'tap': True})
        with patch.dict(os.environ, {'EXVIUS_REPLAY_MARQUEE': '0', 'EXVIUS_REPLAY_MARQUEE_MAX': '1'}):
            self.assertFalse(policy.initialize(data))
        self.assertEqual(data, before)

    def test_given_invalid_defaults_or_saved_policy_when_read_then_fail_without_repair(self):
        for value in ('0', '53', 'bad'):
            data = calendar.campaign(); before = copy.deepcopy(data)
            with patch.dict(os.environ, {'EXVIUS_REPLAY_MARQUEE_MAX': value}), self.assertRaises(ValueError): policy.initialize(data)
            self.assertEqual(data, before)
        for value in (None, {}, {'version': 2, 'settings': {'enabled': True, 'limit': 6, 'tap': True}}):
            data = self.data(); data[policy.STATE_KEY] = value; before = copy.deepcopy(data)
            with self.assertRaises(ValueError): policy.initialize(data)
            self.assertEqual(data, before)

    def test_given_active_events_when_selected_then_newest_first_deduplicate_filenames_and_apply_limit(self):
        data = self.data(); data[policy.STATE_KEY]['settings']['limit'] = 2
        art = Images({'100': 'shared.png', '101': 'shared.png', '102': 'new.png'})
        rows = [events.event(100, '2016-12-16'), events.event(101, '2016-12-17'),
                events.event(102, '2016-12-18'), events.event(103, '2016-12-19'),
                events.event(104, '2016-12-20', group='permanent')]
        selected = policy.entries(data, art, now=NOW, events=rows, summons=SimpleNamespace(anchored=True, finished=False))
        self.assertEqual([r['event']['area'] for r in selected], ['102', '101'])

    def test_given_replay_rollover_when_selected_then_follow_active_event_policy_without_mutation(self):
        data = self.data(); rows = [events.event(100, '2016-12-16'), events.event(101, '2017-01-06')]
        before = copy.deepcopy(data); rng = random.getstate()
        for moment, expected in ((NOW, ['100']), (NOW + timedelta(weeks=1), ['101'])):
            selected, summons = self.selected(data, rows, moment)
            found = policy.entries(data, Images(), now=moment, events=selected.events, summons=summons)
            self.assertEqual([r['event']['area'] for r in found], expected)
        self.assertEqual(data, before); self.assertEqual(random.getstate(), rng)

    def test_given_disabled_unanchored_finished_or_unprepared_when_selected_then_use_era_fallback(self):
        data = self.data(); art = Images()
        for selected in (SimpleNamespace(anchored=False, finished=False), SimpleNamespace(anchored=True, finished=True)):
            self.assertIsNone(policy.entries(data, art, now=NOW, summons=selected))
        self.assertIsNone(policy.entries({}, art, now=NOW))
        self.assertIsNone(policy.entries(data, None, now=NOW))
        data[policy.STATE_KEY]['settings']['enabled'] = False
        self.assertIsNone(policy.entries(data, art, now=NOW))

    def test_given_active_week_without_art_when_selected_then_return_empty_instead_of_era(self):
        self.assertEqual(policy.entries(self.data(), Images({}), now=NOW, events=[events.event(100)],
                                       summons=SimpleNamespace(anchored=True, finished=False)), [])

    def test_given_many_available_events_when_selected_then_default_to_six(self):
        rows = [events.event(i, '2016-12-16') for i in range(100, 110)]
        result = policy.entries(self.data(), Images(), now=NOW, events=rows, summons=SimpleNamespace(anchored=True, finished=False))
        self.assertEqual(len(result), 6)

    def test_given_eligible_and_native_modes_when_tapped_then_link_only_valid_stage_coordinates(self):
        row = events.event(100, '2016-12-16')
        self.assertEqual(policy.event_link(row), '6:2,0,100,10001,1000101')
        for change in ({'native_mode': 'clash'}, {'first_mission': '0'}, {'first_dungeon': 'invalid'}, {'area': '-1'}):
            self.assertIsNone(policy.event_link({**row, **change}))
        data = self.data(); data[policy.STATE_KEY]['settings']['tap'] = False
        found = policy.rows(data, Images(), now=NOW, events=[row], summons=SimpleNamespace(anchored=True, finished=False))
        self.assertEqual(found[0]['uP4695k3'], '10:601')

    def test_given_native_rows_when_built_then_keep_cache_ids_versions_utc_window_and_exact_url(self):
        row = events.event(100, '2016-12-16'); data = self.data()
        for now in (datetime(2027, 3, 8, 3, tzinfo=timezone.utc), datetime(2027, 11, 1, 2, tzinfo=timezone.utc)):
            found = policy.rows(data, Images(), now=now, events=[row], summons=SimpleNamespace(anchored=True, finished=False))[0]
            self.assertEqual(found['nZfbucEw'], '7000100'); self.assertEqual(found['JZryxaYY'], '8')
            self.assertTrue(found['TsZhcqbT'].endswith('/HomeBanner_7000100.png'))
            self.assertEqual(found['twb8TQPx'], (now - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S'))
            self.assertEqual(found['ZkGp8XbQ'], (now + timedelta(days=21)).strftime('%Y-%m-%d %H:%M:%S'))
            self.assertEqual(found['uP4695k3'], '6:2,0,100,10001,1000101')


class HomeSnapshots(unittest.TestCase):
    setUp = native.NativePreparation.setUp
    child = engine_harness.IosServerBehavior.child

    def artwork(self, managed=False):
        self.docs = self.root / 'documents'; self.docs.mkdir(exist_ok=True)
        self.documents = {'event_art.json': {'events': {'100': {'filename': 'one.png'}, '101': {'filename': 'one.png'},
                                                       '102': {'filename': 'two.png'}}},
                          'event_history.json': {'version': 1, 'added': [{'area': '103', 'filename': 'missing.png'}]}}
        for name, document in self.documents.items(): (self.docs / name).write_text(json.dumps(document))
        self.enterContext(patch.object(homes, 'HERE', self.docs))
        static = self.config.data / 'static' if managed else self.config.data
        static.mkdir(parents=True, exist_ok=True)
        self.native = self.config.data / 'native' if managed else static / 'client/files'
        self.area = self.native / 'en/sd/area'; self.area.mkdir(parents=True, exist_ok=True)
        (self.area / 'one.png').write_bytes(png(1)); (self.area / 'two.png').write_bytes(png(2))

    def tree(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_given_both_layouts_when_prepared_then_keep_source_pixels_and_report_missing_art_without_saves(self):
        for managed in (False, True):
            self.config = Configuration(self.root / ('private-' + str(managed)), self.root / ('data-' + str(managed)))
            self.artwork(managed); before = {p: p.read_bytes() for p in self.config.data.rglob('*') if p.is_file()}
            result = homes.prepare(self.config); pack = homes.load(self.config)
            self.assertEqual((result['areas'], result['images'], result['missing']), (4, 2, ['missing.png']))
            for area in ('100', '101', '102'):
                image = pack.image(area)
                self.assertEqual(pack.lookup(image['url']), (self.area / image['source']).read_bytes())
            self.assertEqual(before, {p: p.read_bytes() for p in self.config.data.rglob('*') if p.is_file()})
            self.assertFalse(self.config.state_file.exists())

    def test_given_repeated_inputs_when_prepared_then_reuse_generation_and_files(self):
        self.artwork(); homes.prepare(self.config); before = self.tree()
        self.assertFalse(homes.prepare(self.config)['prepared_now']); self.assertEqual(self.tree(), before)

    def test_given_missing_snapshot_when_verified_then_report_without_creating_directories(self):
        before = self.tree(); self.assertFalse(homes.verify(self.config)['ok'])
        self.assertEqual(self.tree(), before); self.assertFalse(self.config.root.exists())

    def test_given_current_snapshot_when_verified_then_no_writes_processes_or_engine_imports(self):
        self.artwork(); homes.prepare(self.config); before = self.tree(); modules = set(sys.modules)
        with patch.object(Path, 'mkdir', side_effect=AssertionError('query wrote')), patch('subprocess.run', side_effect=AssertionError('query spawned')):
            self.assertTrue(homes.verify(self.config)['ok'])
        self.assertEqual(self.tree(), before)
        self.assertFalse({'capture_server', 'player_state', 'ffbe_state', 'data_paths'} & (set(sys.modules) - modules))

    def test_given_changed_image_or_metadata_when_verified_then_report_stale_and_publish_new_identity(self):
        self.artwork(); homes.prepare(self.config); old = homes.load(self.config)
        (self.area / 'one.png').write_bytes(png(3)); before = self.tree()
        self.assertFalse(homes.verify(self.config)['ok']); self.assertEqual(self.tree(), before)
        self.assertEqual(homes.prepare(self.config)['generation'], 2); new = homes.load(self.config)
        self.assertNotEqual(old.image('100')['url'], new.image('100')['url']); self.assertTrue(old.directory.is_dir())
        self.documents['event_art.json']['events']['105'] = {'filename': 'one.png'}
        (self.docs / 'event_art.json').write_text(json.dumps(self.documents['event_art.json']))
        self.assertFalse(homes.verify(self.config)['ok'])

    def test_given_newly_available_gap_when_refreshed_then_include_it_and_clear_report(self):
        self.artwork(); homes.prepare(self.config); (self.area / 'missing.png').write_bytes(png(4))
        result = homes.prepare(self.config)
        self.assertEqual((result['generation'], result['images'], result['missing']), (2, 3, []))

    def test_given_all_source_images_missing_when_prepared_then_report_gaps_without_inventing_art(self):
        self.artwork(); (self.area / 'one.png').unlink(); (self.area / 'two.png').unlink()
        result = homes.prepare(self.config)
        self.assertEqual((result['images'], result['files']), (0, 0))
        self.assertEqual(result['missing'], ['missing.png', 'one.png', 'two.png'])
        self.assertTrue(homes.verify(self.config)['ok'])

    def test_given_overlay_when_prepared_then_prefer_its_exact_bytes(self):
        self.artwork(); overlay = self.config.data / 'overlay/en/sd/area'; overlay.mkdir(parents=True)
        (overlay / 'one.png').write_bytes(png(9)); homes.prepare(self.config); pack = homes.load(self.config)
        self.assertEqual(pack.lookup(pack.image('100')['url']), png(9))

    def test_given_bad_png_or_escaping_source_when_prepared_then_preserve_active_pointer(self):
        self.artwork(); homes.prepare(self.config); pointer = self.config.root / homes.POINTER; original = pointer.read_bytes()
        path = self.area / 'one.png'; path.write_bytes(b'corrupt')
        with self.assertRaises(ValueError): homes.prepare(self.config)
        path.unlink(); outside = self.root / 'outside.png'; outside.write_bytes(png()); path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'escapes'): homes.prepare(self.config)
        self.assertEqual(pointer.read_bytes(), original)

    def test_given_bad_metadata_when_prepared_then_fail_visibly_without_publication(self):
        self.artwork()
        for document in ({}, {'events': {'0': {'filename': 'one.png'}}}, {'events': {'1': {'filename': '../one.png'}}}):
            (self.docs / 'event_art.json').write_text(json.dumps(document))
            with self.assertRaises(ValueError): homes.prepare(self.config)
            self.assertFalse((self.config.root / homes.POINTER).exists())

    def test_given_busy_runtime_when_prepared_then_refuse(self):
        self.artwork()
        with InstanceLock(self.config.root), self.assertRaises(RuntimeError): homes.prepare(self.config)

    def test_given_failed_publication_when_retried_then_keep_old_pointer_and_reuse_complete_generation(self):
        self.artwork(); homes.prepare(self.config); pointer = self.config.root / homes.POINTER; before = pointer.read_bytes()
        (self.area / 'one.png').write_bytes(png(6)); replace = os.replace
        def fail(source, target):
            if Path(target) == pointer: raise OSError('publication failed')
            return replace(source, target)
        with patch('ios_server.preparation.os.replace', side_effect=fail), self.assertRaises(OSError): homes.prepare(self.config)
        self.assertEqual(pointer.read_bytes(), before); self.assertEqual(homes.load(self.config).manifest['generation'], 1)
        self.assertEqual(homes.prepare(self.config)['generation'], 2)
        self.assertFalse(list(pointer.parent.glob('.building-*')))

    def test_given_corrupt_or_escaping_published_file_when_verified_then_fail_without_repair(self):
        self.artwork(); homes.prepare(self.config); pack = homes.load(self.config); image = pack.image('100')
        path = pack.directory / image['path']; path.write_bytes(b'corrupt')
        self.assertFalse(homes.verify(self.config)['ok']); self.assertEqual(path.read_bytes(), b'corrupt')
        path.unlink(); outside = self.config.root / 'outside.png'; outside.write_bytes(png()); path.symlink_to(outside)
        with self.assertRaises(ValueError): homes.load(self.config)

    def test_given_bound_home_and_summon_images_when_requested_then_keep_png_get_head_and_projection_contracts(self):
        self.artwork(); homes.prepare(self.config); pack = homes.load(self.config)
        summons = SimpleNamespace(project=lambda spec: {**spec, 'summons': True}, lookup=lambda path: b'summon')
        bound = homes.bind(summons, pack)
        self.assertEqual(bound.project({}), {'summons': True}); self.assertIs(homes.bind(summons, None), summons)
        image = pack.image('100')
        for method in ('GET', 'HEAD'):
            for prefix in ('banner/en', 'en', 'banner/common_lang', 'common_lang'):
                path = image['url'].replace('banner/en', prefix, 1)
                response = SimpleNamespace(command=method, wfile=io.BytesIO(), headers={})
                response.send_response = lambda status: setattr(response, 'status', status)
                response.send_header = lambda key, value: response.headers.update({key: value})
                response.end_headers = lambda: None
                self.assertTrue(banner_delivery.serve(response, bound, path)); self.assertEqual(response.status, 200)
                self.assertEqual(response.wfile.getvalue(), png(1) if method == 'GET' else b'')
                self.assertEqual(response.headers['Content-Length'], str(len(png(1))))
                self.assertEqual(response.headers['Content-Type'], 'image/png')
                self.assertIn('immutable', response.headers['Cache-Control'])
        self.assertEqual(homes.bind(None, pack).project({'keep': 1}), {'keep': 1})
        for path in (image['url'].replace('a', 'z'), homes.image_url('999', '0' * 64),
                     image['url'].replace('7000100', '9' * 5000), image['url'].replace('7000100', '7000103')):
            self.assertIsNone(pack.lookup(path))

    def test_given_cli_from_base_python_when_run_then_dispatch_isolated_runtime_and_emit_one_json_result(self):
        self.artwork()
        # Inject only the fixture metadata location; launcher still must re-exec the dedicated interpreter.
        script = '''
import io,json,sys
from pathlib import Path
from contextlib import redirect_stdout
sys.path[:0]=sys.argv[1:3]
from ios_server import home_banners
from ios_server.cli import main
home_banners.HERE=Path(sys.argv[5])
for command in ('prepare-home-banners','verify-home-banners'):
    out=io.StringIO()
    with redirect_stdout(out):code=main([command,'--root',sys.argv[3],'--data',sys.argv[4]])
    assert code==0 and json.loads(out.getvalue())['images']==2,out.getvalue()
assert not {'capture_server','player_state','data_paths'}&set(sys.modules)
'''
        done = self.child(script, str(self.config.root), str(self.config.data), str(self.docs))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        command = [str(Path(sys.base_prefix) / 'bin/python3.12'), '-B', str(native.SOURCE / 'exvius/macos_ios_server.py'),
                   'verify-home-banners', '--root', str(self.root / 'empty'), '--data', str(self.config.data)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('No home artwork', json.loads(result.stdout)['error'])


class HomeEngine(unittest.TestCase):
    setUp = native.NativePreparation.setUp
    fixture = native.NativePreparation.fixture
    artwork = HomeSnapshots.artwork
    child = engine_harness.IosServerBehavior.child

    def test_given_anchored_campaign_missing_carousel_policy_when_initialized_then_backfill_atomically(self):
        self.fixture()
        for relative in ('mst_decoded', 'text_decoded', 'cpk_extract', 'client/files/common_lang'):
            (self.config.data / relative).mkdir(parents=True, exist_ok=True)
        engine_harness.IosServerBehavior.write_masters(self, self.config.data / 'mst_decoded')
        script = '''
import copy,json,sys
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=sys.argv[1:3]
from ios_server.config import Configuration
from ios_server.engine import Engine
from revival_marquee import STATE_KEY
config=Configuration(Path(sys.argv[3]),Path(sys.argv[4]))
engine=Engine(config)
try:
    engine.initialize_campaign();state=engine.server.State;player=state.player
    del player.data[STATE_KEY];assert player.save(str(config.state_file),force=True)
    before=copy.deepcopy(player.data);saved=config.state_file.read_bytes()
    with patch.object(type(player),'save',return_value=False):
        try:engine.initialize_campaign()
        except OSError:pass
        else:raise AssertionError('failed save accepted')
    assert state.player is player and player.data==before and config.state_file.read_bytes()==saved
    assert engine.initialize_campaign()
    assert state.player.data['ios_revival']==before['ios_revival']
    assert {key:value for key,value in state.player.data.items() if key!=STATE_KEY}==before
    assert state.player.data[STATE_KEY]['settings']=={'enabled':True,'limit':6,'tap':True}
finally:engine.close()
'''
        done = self.child(script, str(self.config.root), str(self.config.data))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_given_prepared_engine_when_home_views_run_then_select_replay_rows_and_exact_urls_without_query_writes(self):
        self.fixture(); self.artwork()
        for relative in ('mst_decoded', 'text_decoded', 'cpk_extract', 'client/files/common_lang'):
            (self.config.data / relative).mkdir(parents=True, exist_ok=True)
        engine_harness.IosServerBehavior.write_masters(self, self.config.data / 'mst_decoded')
        prefix = '''
import copy,json,os,sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path[:0]=sys.argv[1:3]
from ios_server.config import Configuration
from ios_server.engine import Engine
from ios_server import home_banners
home_banners.HERE=Path(sys.argv[5])
config=Configuration(Path(sys.argv[3]),Path(sys.argv[4]))
'''
        done = self.child(prefix + '''
engine=Engine(config)
try:
    assert engine.initialize_campaign()
    before=config.state_file.read_bytes()
    assert not engine.initialize_campaign() and config.state_file.read_bytes()==before
finally:engine.close()
''', str(self.config.root), str(self.config.data), str(self.docs))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        homes.prepare(self.config); preparation.prepare_data(self.config)
        done = self.child(prefix + '''
from local_game import LocalGame
from urllib.parse import urlsplit
engine=Engine(config,prepared=True)
try:
    server=engine.initialize()
    import ffbe_banner as banner
    import revival_marquee as marquee
    import revival_summons as summons
    import revival_events as events
    import ffbe_crypto as crypto
    saved=config.state_file.read_bytes(); state=copy.deepcopy(server.State.player.data)
    def guard(event,args):
        if event.startswith('socket.'):raise AssertionError('query network')
        paths=[]
        if event=='open' and len(args)>2 and isinstance(args[2],int) and args[2]&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):paths=[args[0]]
        elif event in ('os.mkdir','os.rename','os.remove'):paths=args[:1]
        for path in paths:
            if not Path(path).resolve().is_relative_to(config.root/'requests'):raise AssertionError('query write '+str(path))
    sys.addaudithook(guard)
    active=SimpleNamespace(anchored=True,finished=False)
    event={'area':'100','name':'Home event','release':'2016-12-16','group':'historical','first_dungeon':'10001','first_mission':'1000101'}
    with patch.object(summons,'plan',return_value=active),patch.object(events,'plan',return_value=SimpleNamespace(events=[event])):
        spec={'DxCN9SNZ':[], 'PJm9d197':[{'P_GS_FEATURE_HOME_MARQUEE':'0'}]};before=copy.deepcopy(spec)
        out=banner.serve_home_marquee(spec)
        assert spec==before and out['PJm9d197'][0]['P_GS_FEATURE_HOME_MARQUEE']=='1'
        row=out['DxCN9SNZ'][0];assert row['uP4695k3']=='6:2,0,100,10001,1000101'
        for method in ('GET','HEAD'):
            response=LocalGame.request(engine,method,urlsplit(row['TsZhcqbT']).path);assert response.status==200
            assert response.body==(engine.banners.home.lookup(row['TsZhcqbT'].split('gumi.sg/',1)[1]) if method=='GET' else b'')
        bad=row['TsZhcqbT'].replace('7000100','7000999')
        assert LocalGame.request(engine,'GET',urlsplit(bad).path).status==404
        assert LocalGame.request(engine,'GET','/banner/en/sd/static_banner/marquee/ios-home-a/%2e%2e/private.png').status==400
        original_flag=banner.MARQUEE_FLAG
        with patch.object(banner,'MARQUEE_FLAG','0'):assert banner.serve_home_marquee(spec)['DxCN9SNZ']==[]
        with patch.object(banner,'MARQUEE_FLAG','flag'):
            flag=banner.serve_home_marquee(spec);assert flag['DxCN9SNZ'] and flag['PJm9d197'][0]['P_GS_FEATURE_HOME_MARQUEE']=='1'
    assert config.state_file.read_bytes()==saved and server.State.player.data==state
finally:engine.close()
assert server.State.native_banners is None
''', str(self.config.root), str(self.config.data), str(self.docs))
        self.assertEqual(done.returncode, 0, done.stdout[-5000:] + done.stderr)
        done = self.child(prefix + '''
engine=Engine(config,prepared=True)
try:
    engine.initialize()
    import ffbe_banner
    assert ffbe_banner.MARQUEE_FLAG=='0'
finally:engine.close()
''', str(self.config.root), str(self.config.data), str(self.docs), env={'MARQUEE_FLAG': '0'})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


if __name__ == '__main__':
    unittest.main()
