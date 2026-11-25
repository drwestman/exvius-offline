"""BDD for full pinned exploration zones and recorded rare quest loot."""
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import test_ios_summons as harness
import revival_exploration as field
import revival_loot as loot


class ExplorationLootPolicy(unittest.TestCase):
    def test_given_full_pinned_content_when_loaded_then_report_plans_and_declared_gaps(self):
        report = field.coverage()
        self.assertEqual(report['planned'], 248)
        self.assertEqual(len(report['partial']), 5)
        self.assertEqual(report['unresolved'], 189)
        self.assertIn('1110104', field.plans()['missions'])
        self.assertEqual(len(field.plans()['groups']), 285)

    def test_given_saved_loot_settings_when_defaults_change_then_keep_original_policy(self):
        data = harness.campaign()
        self.assertTrue(loot.initialize(data))
        self.assertEqual(loot.settings(data), {'field_encounters': True, 'writ_chance': 0.5})
        before = copy.deepcopy(data)
        with patch.dict(os.environ, {'EXVIUS_FIELD_ENCOUNTERS': '0', 'EXVIUS_CALAMITY_WRIT_DROP': '100'}):
            self.assertFalse(loot.initialize(data))
        self.assertEqual(data, before)

    def test_given_bad_defaults_or_saved_policy_when_read_then_refuse_without_repair(self):
        for raw in ('nan', 'inf', '-1', '101', 'bad'):
            data = harness.campaign()
            before = copy.deepcopy(data)
            with patch.dict(os.environ, {'EXVIUS_CALAMITY_WRIT_DROP': raw}), self.assertRaises(ValueError):
                loot.initialize(data)
            self.assertEqual(data, before)
        data = harness.campaign(); loot.initialize(data)
        data[loot.STATE_KEY]['settings']['field_encounters'] = 'yes'
        before = copy.deepcopy(data)
        with self.assertRaisesRegex(ValueError, 'loot'):
            loot.initialize(data)
        self.assertEqual(data, before)

    def test_given_native_field_ids_when_mapped_then_preserve_pinned_zone_rules(self):
        for native, zone in ((10,1),(14,1),(20,2),(32,3),(50,5),(60,1),(63,4),(64,1),(67,4),
                             (70,1),(75,6),(110,1),(150,5),(210,1),(282,8),(99,0),(100,0)):
            self.assertEqual(field.field_zone(native), zone)

    def test_given_two_zones_when_projected_then_keep_each_budget_on_its_own_fields(self):
        slots = [{'2fY1IomW': g, 'xqartN26': g, 'Z0EN6jSh': '1'} for g in ('a','b')]
        source = SimpleNamespace(load=lambda table: [{'xqartN26': g, '9BetM2Ds': '20:1:1:100'} for g in ('a','b')])
        rows = field.encounter_rows('7070101', [], {'Bi6hVv34': slots}, source,
            zones=[(1,['a','a']), (2,['b'])])
        self.assertTrue(rows)
        self.assertTrue(all(field.field_zone(int(r['YzGa63QM'])) == (1 if r['2fY1IomW']=='a' else 2) for r in rows))
        self.assertEqual({r['h4Sjf96p'] for r in rows if r['YzGa63QM']=='10'}, {'0','1'})
        self.assertEqual({r['YzGa63QM'] for r in rows if int(r['YzGa63QM'])>=70}, {'70','71'})

    def test_given_chance_boundary_when_rolling_writ_then_use_strict_percentage_and_injected_rng(self):
        items = ['20:1:1:100']
        before = list(items)
        self.assertEqual(loot.add_writ(items, 0.5, lambda: 0.004999)[-1], '20:290060400:1:100')
        self.assertEqual(loot.add_writ(items, 0.5, lambda: 0.005), items)
        self.assertEqual(loot.add_writ(items, 0, Mock(side_effect=AssertionError('zero chance rolled'))), items)
        self.assertEqual(items, before)

    def test_given_corrupt_fixed_receipt_when_validated_then_do_not_reset_or_pay_it(self):
        data = {'exvius_repeat': {'attempt': {'mid':'2111201', 'status':'pending',
            loot.FIXED_KEY: {'version':1, 'rows':[], 'writ_count':3}}}}
        before = copy.deepcopy(data)
        with self.assertRaisesRegex(ValueError, 'loot'):
            loot.fixed_receipt(data)
        self.assertEqual(data, before)

    def test_given_disabled_or_unplanned_field_when_derived_then_leave_canonical_path_available(self):
        source = Mock(side_effect=AssertionError('unexpected source read'))
        self.assertIsNone(field.field_bundle({}, {'qo3PECw6':'1110104'}, source, set(), enabled=False))
        self.assertIsNone(field.field_bundle({}, {'qo3PECw6':'1110404'}, source, set()))

    def test_given_conflicting_pinned_zones_when_loaded_then_refuse_without_repair(self):
        doc = copy.deepcopy(field.plans())
        doc['missions']['1110104']['zones'].append(copy.deepcopy(doc['missions']['1110104']['zones'][0]))
        field.plans.cache_clear()
        self.addCleanup(field.plans.cache_clear)
        with patch.object(Path, 'read_text', return_value=json.dumps(doc)):
            with self.assertRaisesRegex(ValueError, 'conflicting zone'):
                field.plans()

    def test_given_nonpersistent_or_unsupported_campaign_when_offering_loot_then_no_bonus(self):
        data = harness.campaign(); loot.initialize(data)
        player = SimpleNamespace(data=data, mode='live', _can_credit=lambda reward: True)
        self.assertEqual(loot.chance(player), 0.5)
        self.assertEqual(loot.chance(player, False), 0)
        for mode in ('frozen', 'ephemeral'):
            player.mode = mode
            self.assertEqual(loot.chance(player), 0)
        player.mode = 'live'; player._can_credit = lambda reward: False
        self.assertEqual(loot.chance(player), 0)


SETUP = '''
import revival_loot as loot
import revival_exploration as field
import ffbe_state as runtime
from ffbe_battle import roll_drops, credit_mission_rewards
from exvius_repeat import observe_load
from player_state import PlayerState
MID = '2111201'
def configured(chance=100):
    player.data[loot.STATE_KEY]['settings']['writ_chance'] = chance
    player.save(str(config.state_file))
def waves(mid=MID):
    return {'an6TB4WS': [{'qo3PECw6':mid,'6v7y3QcJ':'1','gou39JeI':'2','2fY1IomW':'g'}],
            'Bi6hVv34': [{'2fY1IomW':'g','xqartN26':'111051000'}],
            'y35YvQjZ': [{'qo3PECw6':mid,'6v7y3QcJ':'1','9BetM2Ds':'20:106213050:1:100'}]}
def load_fixed(mid=MID):
    spec = observe_load(roll_drops(waves(mid), mid, True), mid, True)
    player.save(str(config.state_file))
    return spec
def end(mid=MID, cleared=True):
    body = {'jQsE54Iz':[{'qo3PECw6':mid}], '09HRWXDf':[{'S4U09svH':'0','Wdi3MAs2':'0',
        'xF9Sr1a6':'20:290060400:999'}]}
    if cleared:
        body['2urzfX6d']=[{'69ieJGhD':'1:1:3'}]
    return request('MissionEndRequest',body)
'''


class ExplorationLootIntegration(unittest.TestCase):
    setUp = harness.ReplaySummonIntegration.setUp
    prepared_data = harness.ReplaySummonIntegration.prepared_data
    child = harness.ReplaySummonIntegration.child
    run_engine = harness.ReplaySummonIntegration.run_engine
    extra_units = [('900020101', 3)]
    extra_items = ('290060400','1209001000')

    def write_masters(self, masters):
        harness.ReplaySummonIntegration.write_masters(self, masters)
        (masters/'F_MISSION_MST.ndjson').write_text('\n'.join(json.dumps({'qo3PECw6':mid,
            '8xi6Xvyk':'1','Y4VoF8yu':'1','gQR24kST':'0'}) for mid in ('2111201','9690101','1110101')))

    def test_given_normal_waves_and_field_rows_when_rolled_then_offer_writ_without_granting_it(self):
        self.run_engine(SETUP + '''
configured()
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
normal = roll_drops(waves('1110101'), '1110101', True)
assert normal['y35YvQjZ'][0]['9BetM2Ds'].endswith('20:290060400:1:100')
field_rows = {'6v0LPiRe':[{'qo3PECw6':'1110104','9BetM2Ds':'20:106213050:1:100'}]}
shown = roll_drops(field_rows, '1110104', True)
assert shown['6v0LPiRe'][0]['9BetM2Ds'].endswith('20:290060400:1:100')
assert '1110104' not in runtime.LAST_DROPS
assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_capture_chamber_when_retried_after_reload_then_keep_original_roll_and_pay_writ_once(self):
        self.run_engine(SETUP + '''
configured()
shown = load_fixed()
assert '20:290060400:1:100' in shown['y35YvQjZ'][0]['9BetM2Ds']
player.data = PlayerState.load(str(config.state_file), slot=config.slot).data
saved = config.state_file.read_bytes()
with patch('ffbe_battle.random.random', side_effect=AssertionError('reload rerolled writ')):
    assert load_fixed()['y35YvQjZ'] == shown['y35YvQjZ']
assert config.state_file.read_bytes() == saved, 'fixed reload save bytes'
owned = player.item_count(20,290060400)
result = end()
assert player.item_count(20,290060400) == owned+1, 'capture Writ count'
assert result['09HRWXDf'][0]['xF9Sr1a6'] == '20:290060400:1', result['09HRWXDf']
saved = config.state_file.read_bytes()
end()
assert player.item_count(20,290060400) == owned+1 and config.state_file.read_bytes()==saved
''')

    def test_given_fixed_enlightenment_clear_when_receipted_then_preserve_fixed_quantity_and_add_one_writ(self):
        self.run_engine(SETUP + '''
configured()
load_fixed('9690101')
owned, stones = player.item_count(20,290060400), player.item_count(20,1209001000)
end('9690101')
assert player.item_count(20,290060400) == owned+1
assert player.item_count(20,1209001000) == stones+350
saved = config.state_file.read_bytes()
end('9690101')
assert config.state_file.read_bytes()==saved
''')

    def test_given_uncleared_capture_when_client_claims_writ_then_do_not_pay_fixed_bonus(self):
        self.run_engine(SETUP + '''
configured()
load_fixed()
owned = player.item_count(20,290060400)
end(cleared=False)
assert player.item_count(20,290060400)==owned
''')

    def test_given_fixed_result_save_failure_when_settling_then_preserve_roll_for_retry(self):
        self.run_engine(SETUP + '''
configured()
load_fixed()
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
with patch.object(type(player),'save',return_value=False):
    try: end()
    except OSError: pass
    else: raise AssertionError('fixed loot save failure hidden')
assert player.data==before and config.state_file.read_bytes()==saved
end()
assert player.item_count(20,290060400)==1
''')

    def test_given_pending_fixed_attempt_from_before_port_when_resumed_then_do_not_invent_writ(self):
        self.run_engine(SETUP + '''
configured(0)
load_fixed()
del player.data['exvius_repeat']['attempt'][loot.FIXED_KEY]
configured(100)
with patch('ffbe_battle.random.random', side_effect=AssertionError('old attempt rolled writ')):
    shown = load_fixed()
assert '20:290060400:' not in shown['y35YvQjZ'][0]['9BetM2Ds']
end()
assert player.item_count(20,290060400)==0
''')

    def test_given_disabled_fields_or_missing_policy_when_rolling_then_do_not_add_new_loot(self):
        self.run_engine(SETUP + '''
configured()
player.data[loot.STATE_KEY]['settings']['field_encounters']=False
spec={'6v0LPiRe':[{'9BetM2Ds':'20:106213050:1:100'}]}
assert '6v0LPiRe' not in roll_drops(spec,'1110104',True)
del player.data[loot.STATE_KEY]
shown=roll_drops(waves('1110101'),'1110101',True)
assert '20:290060400:' not in shown['y35YvQjZ'][0]['9BetM2Ds']
''')

    def test_given_recorded_bonus_when_grant_is_incomplete_then_roll_back_entire_result(self):
        self.run_engine(SETUP + '''
configured()
load_fixed('9690101')
before, saved=copy.deepcopy(player.data),config.state_file.read_bytes()
grant=type(player)._grant_items
def incomplete(self,rewards):
    return [] if any(r['id']==290060400 for r in rewards) else grant(self,rewards)
with patch.object(type(player),'_grant_items',incomplete):
    try: end('9690101')
    except ValueError as exc: assert 'completely' in str(exc)
    else: raise AssertionError('partial protected reward accepted')
assert player.data==before and config.state_file.read_bytes()==saved
end('9690101')
assert player.item_count(20,290060400)==1 and player.item_count(20,1209001000)==350
''')

    def test_given_normal_wave_writ_when_reported_then_credit_once_across_reload(self):
        self.run_engine(SETUP + '''
configured()
observe_load(roll_drops(waves('1110101'),'1110101',True),'1110101',True)
player.save(str(config.state_file))
body={'jQsE54Iz':[{'qo3PECw6':'1110101'}], '09HRWXDf':[{'S4U09svH':'0',
    'Wdi3MAs2':'0','xF9Sr1a6':'20:290060400:1'}], '2urzfX6d':[{'69ieJGhD':'1:1:3'}]}
request('MissionEndRequest',body)
assert player.item_count(20,290060400)==1
saved=config.state_file.read_bytes()
player.data=PlayerState.load(str(config.state_file),slot=config.slot).data
request('MissionEndRequest',body)
assert player.item_count(20,290060400)==1 and config.state_file.read_bytes()==saved
''')

    def test_given_uninitialized_new_settings_when_backfilled_then_preserve_anchor_and_failed_save(self):
        self.run_engine(SETUP + '''
from revival_campaign import initialize_campaign
del player.data[loot.STATE_KEY]
player.save(str(config.state_file))
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
with patch.object(type(player),'save',return_value=False):
    try: initialize_campaign(server.State,config.state_file)
    except OSError: pass
    else: raise AssertionError('loot backfill save failure hidden')
assert player.data==before and config.state_file.read_bytes()==saved
assert initialize_campaign(server.State,config.state_file)
player=server.State.player
assert player.data['ios_revival']==before['ios_revival']
assert loot.settings(player.data)['writ_chance']==0.5
''')

    def test_given_read_only_status_when_loot_facts_are_corrupt_then_report_without_repair(self):
        self.run_engine(SETUP + '''
from ios_server.queries import status
player.data[loot.STATE_KEY]['settings']['writ_chance']='bad'
player.save(str(config.state_file))
saved=config.state_file.read_bytes()
assert 'loot' in status(config)['error']
assert config.state_file.read_bytes()==saved
''')

    def test_given_pending_fixed_loot_when_doctor_runs_then_report_coverage_and_validate_receipt_read_only(self):
        self.run_engine(SETUP + '''
from ios_server.queries import doctor
configured()
load_fixed()
saved=config.state_file.read_bytes()
report=doctor(config)
assert report['exploration_content']['planned']==248
assert len(report['exploration_content']['partial'])==5
assert report['exploration_content']['unresolved']==189
assert config.state_file.read_bytes()==saved
player.data['exvius_repeat']['attempt'][loot.FIXED_KEY]['writ_count']=99
player.save(str(config.state_file))
saved=config.state_file.read_bytes()
assert 'fixed loot' in doctor(config)['error']
assert config.state_file.read_bytes()==saved
''')


if __name__ == '__main__':
    unittest.main()
