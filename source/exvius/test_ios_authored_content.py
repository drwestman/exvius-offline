"""BDD for pinned added Vortex areas and isolated Halloween reconstruction data."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import test_ios_summons as harness
import revival_content as content
import revival_events as events
import revival_summons as summons

HALLOWEEN = datetime(2027, 10, 25, 3, tzinfo=timezone.utc)


class ExplorationContentBehavior(unittest.TestCase):
    def test_given_full_explorations_when_loaded_then_retain_the_approved_ten_mission_subset(self):
        import revival_exploration as field
        doc = field.plans()
        approved = json.loads((field.HERE / 'content' / 'exploration_encounters_added.json').read_text())
        self.assertEqual({mid:doc['missions'][mid] for mid in field.ADDED_MISSIONS}, approved['missions'])
        self.assertEqual({gid:doc['groups'][gid] for gid in approved['groups']}, approved['groups'])
        self.assertTrue(all(not doc['missions'][mid]['missing'] for mid in field.ADDED_MISSIONS))

    def test_given_repeated_group_when_projected_then_emit_finite_indexes_for_each_native_field(self):
        import revival_exploration as field
        bundle = {'Bi6hVv34': [{'2fY1IomW': 'g', 'xqartN26': 'p', 'Z0EN6jSh': '1'}]}
        source = SimpleNamespace(load=lambda table: [{'xqartN26': 'p', '9BetM2Ds': '20:106213050:1:50'}])
        rows = field.encounter_rows('7110101', ['g', 'g'], bundle, source)
        self.assertEqual(len(rows), len(field.FIELDS) * 2)
        for native in field.FIELDS:
            self.assertEqual({r['h4Sjf96p'] for r in rows if r['YzGa63QM'] == str(native)}, {'0', '1'})
        self.assertTrue(all(r['9BetM2Ds'] == '20:106213050:1:50' and r['14FMQseU'] == '0' for r in rows))

    def test_given_field_drop_rolls_when_all_miss_then_keep_one_four_field_item_without_mutating_source(self):
        import revival_exploration as field
        source = {field.TAG: [{'9BetM2Ds': '20:1:2:1,20:2:1:1'}]}
        before = copy.deepcopy(source)
        result = field.roll_drops(source, '', lambda low, high: 100)
        self.assertEqual(result[field.TAG][0]['9BetM2Ds'], '20:2:1:1')
        self.assertEqual(source, before)

    def test_given_incomplete_field_packet_when_loaded_then_fail_without_caching(self):
        import revival_exploration as field
        raw = json.loads(field.PACKET.read_text())
        del raw['missions']['7110101']
        field.plans.cache_clear()
        try:
            with patch.object(Path, 'read_text', return_value=json.dumps(raw)), self.assertRaisesRegex(ValueError, 'exploration'):
                field.plans()
            self.assertEqual(field.plans.cache_info().currsize, 0)
        finally:
            field.plans.cache_clear()

    def test_given_empty_or_three_field_drops_when_projected_then_keep_native_parser_safe(self):
        import revival_exploration as field
        spec = {field.TAG: [{'9BetM2Ds': ''}]}
        self.assertNotIn('9BetM2Ds', field.roll_drops(spec, '', lambda low, high: 1)[field.TAG][0])
        self.assertEqual(field.roll_drops(spec, '20:1:2', lambda low, high: 1)[field.TAG][0]['9BetM2Ds'], '20:1:2:100')
        with self.assertRaisesRegex(ValueError, 'drop candidate'):
            field.roll_drops(spec, '20:1', lambda low, high: 1)


class AuthoredContentBehavior(unittest.TestCase):
    def tearDown(self):
        content.encounters.cache_clear()

    def test_given_pinned_packet_when_loaded_then_validate_six_original_mission_battles(self):
        packet = content.encounters()
        self.assertEqual(set(packet), {'9190001', '9190002', '9190003', '9210001', '9210002', '9210003'})
        self.assertEqual([len(packet[m]['bundle']['an6TB4WS']) for m in sorted(packet)], [3, 4, 5, 1, 1, 1])
        self.assertEqual(packet['9210003']['bundle']['bV34YIJQ'][0]['fh31sk7B'], '48750000')

    def test_given_authored_bundle_when_returned_then_mutations_do_not_change_the_pinned_source(self):
        before = copy.deepcopy(content.encounters())
        bundle = content.encounter('9210003')
        bundle['bV34YIJQ'][0]['fh31sk7B'] = '1'
        self.assertEqual(content.encounters(), before)
        self.assertIsNone(content.encounter('1110101'))

    def test_given_corrupt_packet_when_loaded_then_fail_visibly_without_partial_publication(self):
        original = json.loads(content.PACKET.read_text())
        cases = []
        bad = copy.deepcopy(original); bad['version'] = 2; cases.append(bad)
        bad = copy.deepcopy(original); del bad['missions']['9210003']; cases.append(bad)
        bad = copy.deepcopy(original); bad['missions']['1110101'] = bad['missions']['9210003']; cases.append(bad)
        bad = copy.deepcopy(original); bad['missions']['9190001']['bundle']['an6TB4WS'][0]['qo3PECw6'] = '1110101'; cases.append(bad)
        bad = copy.deepcopy(original); bad['missions']['9190001']['bundle']['Bi6hVv34'] = []; cases.append(bad)
        bad = copy.deepcopy(original); bad['missions']['9190001']['bundle']['bV34YIJQ'] = []; cases.append(bad)
        bad = copy.deepcopy(original); bad['missions']['9190001']['bundle']['wbet57nF'] = []; cases.append(bad)
        for value in cases:
            content.encounters.cache_clear()
            with patch.object(Path, 'read_text', return_value=json.dumps(value)), self.assertRaisesRegex(ValueError, 'authored'):
                content.encounters()
            self.assertEqual(content.encounters.cache_info().currsize, 0)

    def test_given_added_catalogue_when_loaded_then_keep_nine_areas_and_118_unique_missions(self):
        rows = content.added_events(events.history()['added'])
        self.assertEqual(len(rows), 9)
        self.assertEqual(len({m for row in rows for m in row['missions']}), 118)
        self.assertTrue({row['area'] for row in rows} <= {row['area'] for row in events.catalogue()})
        original = copy.deepcopy(events.history())
        rows[0]['missions'].clear()
        self.assertEqual(events.history(), original)

    def test_given_invalid_added_metadata_when_loaded_then_do_not_publish_an_unusable_gate(self):
        rows = copy.deepcopy(events.history()['added'])
        for key, value in (('first_mission', '1110101'), ('missions', []), ('dungeons', [])):
            bad = copy.deepcopy(rows)
            bad[0][key] = value
            with self.assertRaisesRegex(ValueError, 'authored'):
                content.added_events(bad)

    def test_given_historical_release_when_rotated_then_include_ordinary_events_and_defer_halloween(self):
        data = harness.campaign()
        data['ios_revival']['replay']['settings']['start'] = '2017-01-06'
        before, rng = copy.deepcopy(data), random.getstate()
        chosen = events.plan(data, harness.NOW)
        self.assertIn('711', chosen.areas)
        self.assertNotIn('712', chosen.areas)
        self.assertEqual(data, before)
        data['ios_revival']['replay']['settings']['start'] = '2017-10-20'
        before = copy.deepcopy(data)
        self.assertFalse({'919', '921'} & events.plan(data, harness.NOW).areas)
        self.assertEqual(data, before)
        data['ios_revival']['replay']['anchor_week'] = __import__('replay_calendar').rotation_week(HALLOWEEN).number
        before = copy.deepcopy(data)
        selected = events.plan(data, HALLOWEEN)
        self.assertTrue({'919', '921'} <= selected.areas)
        self.assertEqual(data, before)
        self.assertEqual(random.getstate(), rng)


SETUP = '''
from player_state import PlayerState
from local_game import LocalGame
from test_ios_authored_content import HALLOWEEN
from replay_calendar import rotation_week
import revival_events as events
import revival_summons as summons
import revival_notices as notices
import battle_content as battle
def calendar(start, now=HALLOWEEN):
    player.data['ios_revival']['replay']['settings']['start'] = start
    player.data['ios_revival']['replay']['anchor_week'] = rotation_week(now).number
    player.save(str(config.state_file))
def call(name, payload=None, now=HALLOWEEN):
    with patch.object(summons, 'clock', return_value=now), patch.object(notices, 'clock', return_value=now):
        return request(name, payload, allow_empty=True)
def load(mid, now=HALLOWEEN):
    return call('DungeonResourceLoadMstListRequest', {'sHGC5c4G': [{'6uIYE15X': mid}]}, now)
def end(mid, now=HALLOWEEN):
    return call('MissionEndRequest', {'jQsE54Iz': [{'qo3PECw6': mid}],
        '09HRWXDf': [{'S4U09svH': '0', 'Wdi3MAs2': '0'}], '2urzfX6d': [{'69ieJGhD': '1:1:3'}]}, now)
calendar('2017-10-20')
'''


class AuthoredContentIntegration(unittest.TestCase):
    setUp = harness.ReplaySummonIntegration.setUp
    prepared_data = harness.ReplaySummonIntegration.prepared_data
    child = harness.ReplaySummonIntegration.child
    run_engine = harness.ReplaySummonIntegration.run_engine
    extra_units = []

    def write_masters(self, masters):
        harness.ReplaySummonIntegration.write_masters(self, masters)
        packet = content.encounters()
        missions = [entry['bundle']['1IfDqR4n'][0] for entry in packet.values()]
        (masters / 'F_MISSION_MST.ndjson').write_text('\n'.join(json.dumps(row) for row in missions))
        (masters / 'F_DUNGEON_MST.ndjson').write_text('\n'.join(json.dumps(
            {'U9iHsau3': did, 'uv60hgDW': area}) for area, did in [('919', '91900'), ('921', '92100')]))
        (masters / 'F_CHALLENGE_MST.ndjson').write_text('\n'.join(json.dumps(
            {'qo3PECw6': row['qo3PECw6'], 'V36ygRYs': row['qo3PECw6'] + '01',
             'Pzn5h0Ga': '68:', 'dX6cor8j': '50:1:20'}) for row in missions))

    def test_given_ios_profile_when_loading_all_six_battles_then_keep_original_phases_and_enemies(self):
        self.run_engine(SETUP + '''
from revival_content import encounters
for mid, entry in encounters().items():
    # Each fixture run is explicitly abandoned before selecting another stage.
    player.data.get('exvius_repeat', {}).get('attempt', {})['status'] = 'completed'
    shown = load(mid)
    assert shown is not None, mid
    assert len(shown['an6TB4WS']) == len(entry['bundle']['an6TB4WS']), mid
    assert {r['xqartN26'] for r in shown['bV34YIJQ']} == {r['xqartN26'] for r in entry['bundle']['bV34YIJQ']}
    assert all(r['qo3PECw6'] == mid for r in shown['an6TB4WS'])
from data_paths import BATTLE_CACHE_ROOT
assert not Path(BATTLE_CACHE_ROOT).exists()
''')

    def test_given_expired_halloween_when_new_load_arrives_then_refuse_without_opening_attempt_or_spending(self):
        self.run_engine(SETUP + '''
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
assert load('9190001', HALLOWEEN + timedelta(weeks=8)) is None
assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_pending_halloween_battle_when_week_ends_then_resume_and_settle_once_after_reload(self):
        self.run_engine(SETUP + '''
assert load('9190001') is not None
player.data = PlayerState.load(str(config.state_file)).data
later = HALLOWEEN + timedelta(weeks=8)
assert load('9190001', later) is not None
before = player.currencies['lapis_free']
end('9190001', later)
assert player.currencies['lapis_free'] == before + 100
assert player.data['exvius_repeat']['attempt']['status'] == 'completed'
player.data = PlayerState.load(str(config.state_file)).data
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
end('9190001', later)
assert load('9190001', later) is None
assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_failed_result_save_when_settling_then_keep_previous_attempt_and_rewards(self):
        self.run_engine(SETUP + '''
assert load('9210003') is not None
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
with patch.object(type(player), 'save', return_value=False):
    try:
        end('9210003')
    except OSError:
        pass
    else:
        raise AssertionError('authored result save failure hidden')
assert player.data == before and config.state_file.read_bytes() == saved
end('9210003')
assert player.data['exvius_repeat']['attempt']['status'] == 'completed'
''')

    def test_given_field_load_drop_rows_when_rolled_then_do_not_credit_unfought_encounters(self):
        self.run_engine(SETUP + '''
import ffbe_state as runtime
from ffbe_battle import roll_drops
mid = '7110101'
spec = {'6v0LPiRe': [{'qo3PECw6': mid, '9BetM2Ds': '20:106213050:1:50'}]}
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
runtime.LAST_DROPS[mid] = ['20:106213050:99']
with patch('ffbe_battle.random.randint', return_value=1):
    result = roll_drops(spec, mid, is_battle_bundle=True)
assert result['6v0LPiRe'][0]['9BetM2Ds'] == '20:106213050:1:50'
assert mid not in runtime.LAST_DROPS
assert player.data == before and config.state_file.read_bytes() == saved
assert spec['6v0LPiRe'][0]['9BetM2Ds'] == '20:106213050:1:50'
''')

    def test_given_halloween_news_and_vortex_when_projected_then_list_both_gates_and_one_campaign_without_writes(self):
        self.run_engine(SETUP + '''
from event_archive import area_ids, menu
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
with patch.object(summons, 'clock', return_value=HALLOWEEN):
    assert {'919', '921'} <= set(area_ids()), 'archive areas'
    assert {'919', '921'} <= set(menu(player)['selected']['ids']), 'archive menu'
    from ffbe_player import serve_event_gate
    from ffbe_config import EVENT_GATE_CARRIERS
    out = serve_event_gate({}, EVENT_GATE_CARRIERS[0])
    assert {'919', '921'} <= {r['uv60hgDW'] for r in out['0xkoNP8U']}, 'native gates'
    assert all(r['4yT7FUqj'] == 'spd_bn_list_dummy.png' for r in out['0xkoNP8U'] if r['uv60hgDW'] in ('919', '921')), [('art', r['uv60hgDW'], r['4yT7FUqj']) for r in out['0xkoNP8U'] if r['uv60hgDW'] in ('919', '921')]
    summary = notices.summary(player.data, 0, HALLOWEEN)
    campaigns = [r for r in summary['events'] if r['area'] in ('919', '921')]
    assert len(campaigns) == 1 and campaigns[0]['name'] == 'Return to the Halloween Castle', 'news campaign'
assert player.data == before and config.state_file.read_bytes() == saved, 'read-only views'
''')

    def test_given_legacy_profile_when_loading_authored_content_then_keep_existing_catalogue_and_unavailable_battles(self):
        static, _ = self.prepared_data()
        self.write_masters(static / 'mst_decoded')
        result = self.child('''
import sys
sys.path[:0] = sys.argv[1:3]
from event_archive import events
import battle_content as battle
from ffbe_battle import roll_drops
assert not {'919', '921', '711'} & {r['area'] for r in events()}
assert battle.event_encounter('9190001') is None
assert battle.event_encounter('9210003') is None
spec = {'6v0LPiRe': [{'qo3PECw6': '7110101', '9BetM2Ds': '20:106213050:1:0'}]}
assert roll_drops(spec, '7110101')['6v0LPiRe'] == spec['6v0LPiRe']
''', env={'FFBE_DATA': str(static)})
        self.assertEqual(result.returncode, 0, result.stdout[-1000:] + result.stderr)


if __name__ == '__main__':
    unittest.main()
