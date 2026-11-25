"""BDD for recorded revival trust rolls and atomic native battle settlement."""
import copy
import json
import os
import random
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import test_ios_summons as harness
import revival_trust as trust


class TrustPolicyBehavior(unittest.TestCase):
    def data(self):
        data = harness.campaign()
        trust.initialize(data)
        return data

    def player(self, data=None):
        units = {'one': {'affinity_points': ['0', ''], 'master_id': '1'},
                 'two': {'affinity_points': ['980', ''], 'master_id': '2'}}
        return SimpleNamespace(data=data or self.data(), mode='live',
            party_instance_ids=lambda: ['one', 'two'], roster_row=units.get,
            _unit_trust_info=lambda unit, channel: ([21, 1, 1, 1000, 1, 1, 50], False))

    def test_given_defaults_when_initialized_then_record_pinned_policy_once(self):
        data = self.data()
        self.assertEqual(trust.settings(data), {'enabled': True, 'chance': 30.0,
            'points': 10, 'big_chance': 5.0, 'big_points': 50})
        before = copy.deepcopy(data)
        with patch.dict(os.environ, {'EXVIUS_QUEST_TRUST': '0', 'EXVIUS_QUEST_TRUST_POINTS': '999'}):
            self.assertFalse(trust.initialize(data))
        self.assertEqual(data, before)

    def test_given_fractional_chances_when_rolled_then_use_hundredths_and_cap_large_hits(self):
        player = self.player()
        player.data['ios_quest_trust']['settings'].update(chance=12.5, big_chance=0.5)
        rng = Mock(side_effect=[1249, 50, 1249, 49])
        before, state = copy.deepcopy(player.data), random.getstate()
        self.assertEqual(trust.roll(player, randbelow=rng), {'one': 10, 'two': 20})
        self.assertEqual(rng.call_args_list, [((10000,),)] * 4)
        self.assertEqual(player.data, before)
        self.assertEqual(random.getstate(), state)

    def test_given_missed_roll_when_planned_then_do_not_roll_a_big_hit(self):
        rng = Mock(side_effect=[3000, 9999])
        self.assertEqual(trust.roll(self.player(), randbelow=rng), {})
        self.assertEqual(rng.call_count, 2)

    def test_given_disabled_zero_or_frozen_policy_when_planned_then_neither_roll_nor_grant(self):
        for setting, value in (('enabled', False), ('points', 0), ('chance', 0)):
            player = self.player()
            player.data['ios_quest_trust']['settings'][setting] = value
            rng = Mock(side_effect=AssertionError('unexpected roll'))
            self.assertEqual(trust.roll(player, randbelow=rng), {})
        player = self.player()
        for mode in ('frozen', 'ephemeral'):
            player.mode = mode
            self.assertEqual(trust.roll(player, randbelow=rng), {})

    def test_given_ineligible_or_duplicate_members_when_planned_then_roll_each_own_unit_once(self):
        player = self.player()
        player.roster_row('two')['affinity_points'][0] = '1000'
        player.party_instance_ids = lambda: ['one', 'one', 'two', 'missing']
        rng = Mock(side_effect=[0, 500])
        self.assertEqual(trust.roll(player, randbelow=rng), {'one': 10})
        self.assertEqual(rng.call_count, 2)
        for descriptor in (None, [71, 1, 1, 1000, 1, 30, 50], [21, 1, 1, 0, 1, 30, 50]):
            player._unit_trust_info = lambda unit, channel: (descriptor, False)
            self.assertEqual(trust.roll(player, randbelow=Mock(side_effect=AssertionError('roll'))), {})

    def test_given_invalid_defaults_when_initialized_then_fail_without_mutation(self):
        for key, value in (('CHANCE', 'nan'), ('BIG_CHANCE', 'inf'), ('CHANCE', '-1'),
                           ('BIG_CHANCE', '101'), ('POINTS', '-1'), ('POINTS', 'bad')):
            data = harness.campaign()
            before = copy.deepcopy(data)
            with patch.dict(os.environ, {'EXVIUS_QUEST_TRUST_' + key: value}), self.assertRaises(ValueError):
                trust.initialize(data)
            self.assertEqual(data, before)

    def test_given_corrupt_saved_policy_when_read_then_fail_without_repair(self):
        for change in ({'version': 2}, {'settings': {}}, {'settings': None}):
            data = self.data()
            data['ios_quest_trust'].update(change)
            before = copy.deepcopy(data)
            with self.assertRaisesRegex(ValueError, 'trust'):
                trust.initialize(data)
            self.assertEqual(data, before)
        with self.assertRaisesRegex(ValueError, 'initialized'):
            trust.roll(self.player(harness.campaign()))


SETUP = '''
import revival_trust as trust
import revival_daily as daily
from player_state import PlayerState
from exvius_repeat import begin_attempt
from ffbe_pipeline import reply_pipeline
from ffbe_config import RESULT_TAG
MID = '1110101'
ids = player.party_instance_ids()
for iid in ids:
    player.roster_row(iid)['affinity_points'] = ['0', '']
def arm():
    begin_attempt(player, MID)
    player.save(str(config.state_file))
def payload(cleared=True, exp='0'):
    body = {'jQsE54Iz': [{'qo3PECw6': MID}], RESULT_TAG: [{'S4U09svH': exp, 'Wdi3MAs2': '0'}]}
    if cleared:
        body['2urzfX6d'] = [{'69ieJGhD': '1:1:3'}]
    return body
def end(cleared=True, exp='0'):
    return request('MissionEndRequest', payload(cleared, exp))
def points():
    return [int(player.roster_row(iid)['affinity_points'][0] or 0) for iid in ids]
def equipment():
    return sum(int(row['Qy5EvcK1']) for row in player.equip_item_rows() if row['J1YX9kmM'] == '409000100')
def lv(out, iid):
    rows = dict(r.split('@', 1) for r in out[RESULT_TAG][0]['Qic38SuC'].split(','))
    return [half.split(':') for half in rows[iid].split('_')]
player.save(str(config.state_file))
'''


class TrustIntegration(unittest.TestCase):
    setUp = harness.ReplaySummonIntegration.setUp
    prepared_data = harness.ReplaySummonIntegration.prepared_data
    child = harness.ReplaySummonIntegration.child
    run_engine = harness.ReplaySummonIntegration.run_engine
    unit_fields = {uid: {'9mu4boy7': '21:409000100:1:1000:10:30:50'}
                   for uid in ('100000102', '100000202')}

    def write_masters(self, masters):
        harness.ReplaySummonIntegration.write_masters(self, masters)
        (masters / 'F_MISSION_MST.ndjson').write_text(json.dumps({
            'qo3PECw6': '1110101', 'gQR24kST': '1', 'B6H34Mea': '10'}))

    def test_given_zero_exp_clear_when_rolled_then_show_saved_normal_and_large_trust_gains(self):
        self.run_engine(SETUP + '''
arm()
with patch.object(trust.secrets, 'randbelow', side_effect=[0, 500, 0, 499]):
    out = end()
assert points() == [10, 50], points()
for iid, expected in zip(ids, (10, 50)):
    before, after = lv(out, iid)
    assert (before[9], after[9], after[12]) == ('0', str(expected), '0')
loaded = PlayerState.load(str(config.state_file))
assert loaded.data['roster'] == player.data['roster'], 'saved trust differs'
assert loaded.data['exvius_repeat'] == player.data['exvius_repeat'], 'saved attempt differs'
''')

    def test_given_successful_clear_when_retried_after_reload_then_no_second_roll_or_reward(self):
        self.run_engine(SETUP + '''
arm()
with patch.object(trust.secrets, 'randbelow', return_value=0):
    end()
player.data = PlayerState.load(str(config.state_file)).data
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
with patch.object(trust.secrets, 'randbelow', side_effect=AssertionError('retry rolled')):
    end()
assert player.data == before and config.state_file.read_bytes() == saved
arm()
with patch.object(trust.secrets, 'randbelow', return_value=0):
    end()
assert points() == [100, 100]
''')

    def test_given_failed_clear_or_story_scene_when_settled_then_do_not_roll_trust(self):
        self.run_engine(SETUP + '''
arm()
with patch.object(trust.secrets, 'randbelow', side_effect=AssertionError('defeat rolled')):
    end(cleared=False)
assert points() == [0, 0]
arm()
with patch('ffbe_battle.mission_wave_count', return_value=0), \
     patch('ffbe_battle.mission_row', return_value={'gQR24kST': '5'}), \
     patch.object(trust.secrets, 'randbelow', side_effect=AssertionError('story rolled')):
    end()
assert points() == [0, 0]
''')

    def test_given_mastery_threshold_when_cleared_then_grant_original_reward_and_daily_progress_once(self):
        self.run_engine(SETUP + '''
from test_ios_daily_economy import SETUP as daily_setup
exec(daily_setup)
select(['6900402'])
for iid in ids:
    player.roster_row(iid)['affinity_points'][0] = '995'
arm()
owned = equipment()
with patch.object(trust.secrets, 'randbelow', return_value=0):
    out = end()
assert points() == [1000, 1000], ('points', points())
assert equipment() == owned + 2, ('equipment', owned, equipment())
assert player.progress_value(player.daily_progress_key('6900402')) == 2, ('daily', player.data['daily_quest'])
assert all(lv(out, iid)[1][9] == '1000' for iid in ids)
arm()
with patch.object(trust.secrets, 'randbelow', side_effect=AssertionError('mastered rolled')):
    end()
assert equipment() == owned + 2
assert player.progress_value(player.daily_progress_key('6900402')) == 2
''')

    def test_given_save_failure_when_settling_then_preserve_attempt_inventory_and_echo_for_retry(self):
        self.run_engine(SETUP + '''
for iid in ids:
    player.roster_row(iid)['affinity_points'][0] = '995'
arm()
before, dirty, saved = copy.deepcopy(player.data), player.dirty, config.state_file.read_bytes()
with patch.object(type(player), 'save', return_value=False), patch.object(trust.secrets, 'randbelow', return_value=0):
    try:
        reply_pipeline({RESULT_TAG: [{}]}, endpoints['MissionEndRequest']['request_id'], json.dumps(payload()), MID, None)
    except OSError:
        pass
    else:
        raise AssertionError('save failure hidden')
assert server.State.player is player
assert player.data == before and player.dirty == dirty and config.state_file.read_bytes() == saved
with patch.object(trust.secrets, 'randbelow', return_value=0):
    end()
assert points() == [1000, 1000]
assert player.data['exvius_repeat']['attempt']['status'] == 'completed', player.data['exvius_repeat']
assert 'echo' in player.data['exvius_repeat']
loaded = PlayerState.load(str(config.state_file))
assert loaded.data['exvius_repeat'] == player.data['exvius_repeat'], 'saved attempt differs'
''')

    def test_given_partial_mastery_grant_when_settling_then_discard_candidate_and_all_receipts(self):
        self.run_engine(SETUP + '''
for iid in ids:
    player.roster_row(iid)['affinity_points'][0] = '995'
arm()
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
original = type(player)._grant_items
def partial(candidate, rows, **kwargs):
    original(candidate, rows, **kwargs)
    return []
with patch.object(type(player), '_grant_items', partial), patch.object(trust.secrets, 'randbelow', return_value=0):
    try:
        reply_pipeline({RESULT_TAG: [{}]}, endpoints['MissionEndRequest']['request_id'], json.dumps(payload()), MID, None)
    except ValueError:
        pass
    else:
        raise AssertionError('partial mastery accepted')
assert server.State.player is player
assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_projection_failure_after_trust_when_settling_then_preserve_all_previous_facts(self):
        self.run_engine(SETUP + '''
arm()
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
with patch.object(type(player), 'apply_to_reply', side_effect=ValueError('projection failed')), \
     patch.object(trust.secrets, 'randbelow', return_value=0):
    try:
        end()
    except ValueError as exc:
        assert str(exc) == 'projection failed'
    else:
        raise AssertionError('projection failure hidden')
assert server.State.player is player
assert player.data == before and config.state_file.read_bytes() == saved
original_save = type(player).save
with patch.object(type(player), 'save', autospec=True) as saved_call:
    saved_call.side_effect = lambda candidate, *args, **kwargs: original_save(candidate, *args, **kwargs)
    with patch.object(trust.secrets, 'randbelow', return_value=0):
        end()
    assert saved_call.call_count == 1, saved_call.call_count
assert points() == [50, 50]
''')

    def test_given_nonpersistent_player_when_result_arrives_then_reject_without_any_change(self):
        self.run_engine(SETUP + '''
import ffbe_state as runtime
arm()
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
for mode in ('frozen', 'ephemeral'):
    player.mode = mode
    try:
        end()
    except ValueError:
        pass
    else:
        raise AssertionError('nonpersistent settlement accepted')
    assert player.data == before and config.state_file.read_bytes() == saved
player.mode = 'live'
with patch.object(runtime, 'STATE_PERSIST', False):
    try:
        end()
    except ValueError:
        pass
    else:
        raise AssertionError('disabled persistence accepted')
assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_old_campaign_when_backfilled_then_keep_anchor_and_settings_across_reload(self):
        self.run_engine(SETUP + '''
from revival_campaign import initialize_campaign
anchor = copy.deepcopy(player.data['ios_revival'])
del player.data['ios_quest_trust']
player.save(str(config.state_file))
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
with patch.object(type(player), 'save', return_value=False):
    try:
        initialize_campaign(server.State, config.state_file)
    except OSError:
        pass
    else:
        raise AssertionError('backfill failure hidden')
assert player.data == before and config.state_file.read_bytes() == saved
with patch.dict(__import__('os').environ, {'EXVIUS_QUEST_TRUST_CHANCE': '12.5'}):
    assert initialize_campaign(server.State, config.state_file)
player = server.State.player
assert player.data['ios_revival'] == anchor
player.data = PlayerState.load(str(config.state_file)).data
with patch.dict(__import__('os').environ, {'EXVIUS_QUEST_TRUST_CHANCE': '99'}):
    assert not initialize_campaign(server.State, config.state_file)
assert trust.settings(player.data)['chance'] == 12.5
''')

    def test_given_corrupt_trust_settings_when_diagnosed_then_preserve_save_and_report_error(self):
        self.run_engine(SETUP + '''
from ios_server.queries import doctor, rotation, status
player.data['ios_quest_trust']['settings']['chance'] = 'bad'
player.save(str(config.state_file))
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
assert 'trust' in status(config)['error']
assert not doctor(config)['ok']
try:
    rotation(config, now=NOW)
except ValueError:
    pass
else:
    raise AssertionError('corrupt trust accepted')
assert player.data == before and config.state_file.read_bytes() == saved
''')


if __name__ == '__main__':
    unittest.main()
