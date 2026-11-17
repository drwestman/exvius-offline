"""Encrypted-request checks for the updated iOS command boundary."""
import unittest
import test_ios_summons as _fixtures


class UpdatedUnitCommands(unittest.TestCase):
    setUp = _fixtures.ReplaySummonIntegration.setUp
    prepared_data = _fixtures.ReplaySummonIntegration.prepared_data
    write_masters = _fixtures.ReplaySummonIntegration.write_masters
    child = _fixtures.ReplaySummonIntegration.child
    run_engine = _fixtures.ReplaySummonIntegration.run_engine
    extra_items = ('90', '91', '204000100')

    def test_given_prism_request_when_encrypted_then_only_prism_is_saved(self):
        self.run_engine('''
masters = Path(config.engine_environment()['MST_DIR'])
(masters / 'F_SACRIFICE_MST.ndjson').write_text(json.dumps({'woghJa61':'100000315', 'jBVop84T':'5',
    'tL6G9egd':'90','q1PJQ3eE':'20:91:25'}))
unit = player.grant_unit('100000315')
player.save(str(config.state_file))
out = request('SacrificeRequest', {'6kvFj2Kw':[{'og2GHy49':str(unit['instance_id']),'ijEey5f7':'0'}]})
assert player.item_count(20,90) == 1 and player.item_count(20,91) == 0
assert out['6kvFj2Kw'][0]['1swM3H4T'] == ''
saved = json.loads(config.state_file.read_bytes())
assert str(unit['instance_id']) not in {str(r['instance_id']) for r in saved['roster']}
before = config.state_file.read_bytes()
request('SacrificeRequest', {'6kvFj2Kw':[{'og2GHy49':str(unit['instance_id']),'ijEey5f7':'0'}]})
assert config.state_file.read_bytes() == before
''')

    def test_given_failed_save_when_converting_then_publish_neither_debit_nor_reward(self):
        self.run_engine('''
from player_state import PlayerState
masters = Path(config.engine_environment()['MST_DIR'])
(masters / 'F_SACRIFICE_MST.ndjson').write_text(json.dumps({'woghJa61':'100000315', 'jBVop84T':'5',
    'tL6G9egd':'90','q1PJQ3eE':'20:91:25'}))
unit = player.grant_unit('100000315')
player.save(str(config.state_file))
before = copy.deepcopy(player.data)
raw = config.state_file.read_bytes()
with patch.object(PlayerState,'save',return_value=False):
    try:
        request('SacrificeRequest', {'6kvFj2Kw':[{'og2GHy49':str(unit['instance_id']),'ijEey5f7':'1'}]})
    except OSError:
        pass
    else:
        raise AssertionError('failed persistence returned a success')
assert player.data == before and config.state_file.read_bytes() == raw
''')

    def test_given_completed_updated_attempt_when_settled_then_grant_first_clear_and_bounded_collection_once(self):
        self.run_engine('''
from revival_update import initialize
from revival_battle_updates import settle as rewards
initialize(player.data)
player.data['ios_revival_update']['settings']['lb_exp'] = False
player.data['ios_reward_claims'] = {'version':1,'baseline':[],'paid':{}}
player.data['exvius_repeat'] = {'attempt':{'mid':'999','sequence':1,'status':'completed','cleared':True,
    'normal_rewards_recorded':True,'ios_update':{'version':1,'settled':False,'first_clear':'20:90:2',
        'gil':12,'collection':{'100':'20:91:3'}}}}
old_gil = player.currencies['gil']
req = json.dumps({'09HRWXDf':[{'EWmQy52k':'20:91:999'}]})
out = rewards({'09HRWXDf':[{}]}, '999', req, server.State)
assert player.item_count(20,90) == 2 and player.item_count(20,91) == 3
assert player.currencies['gil'] == old_gil + 12
assert out['09HRWXDf'][0]['p1K5NecV'] == '20:90:2'
before = copy.deepcopy(player.data)
rewards(out,'999',req,server.State)
assert player.data == before
''')

    def test_given_pending_exploration_when_upgraded_and_reloaded_then_pay_recorded_rewards_once(self):
        self._assert_pending_upgrade_rewards('1110404')

    def test_given_saved_collection_placeholders_when_upgraded_then_backfill_rewards_without_reroll(self):
        self._assert_pending_upgrade_rewards('1110204', placeholders=True)

    def _assert_pending_upgrade_rewards(self, mid, placeholders=False):
        self.run_engine(f'mid, placeholders = {mid!r}, {placeholders!r}\n' + '''
from types import SimpleNamespace
import player_state
from ios_server.campaign_upgrade import build
from revival_battle_updates import prepare, settle
from revival_economy import earned
mission = {'qo3PECw6':mid, 'Y4VoF8yu':'2', '1x4bG2J8':'50:0:100:100', '7UR4J2SE':'24'}
player.data.pop('ios_revival_update', None)
player.data.pop('ios_reward_claims', None)
player.data['exvius_repeat'] = {'attempt':{'mid':mid, 'sequence':1, 'status':'pending'}}
rng = SimpleNamespace(choices=lambda entries, weights=None: [next(e for e in entries if e[1] == '204000100')], randint=lambda a, b: a)
with patch.object(player_state, 'mission_row', return_value=mission):
    loaded = prepare({}, mid, True, server.State, rng=rng)
if placeholders:
    player.data['exvius_repeat']['attempt']['ios_update'].update(first_clear='', gil=0)
before_upgrade = copy.deepcopy(player.data)
candidate, _ = build(player.data, units={}, steps={}, switches={}, missions={mid:mission}, experience=[])
assert player.data == before_upgrade
candidate['ios_revival_update']['settings']['lb_exp'] = False
player.data = candidate
player.dirty = True
assert player.save(str(config.state_file))
player = server.State.player = player_state.PlayerState.load(str(config.state_file), slot=config.slot)
with patch.object(player_state, 'mission_row', return_value=mission), patch.object(rng, 'choices', side_effect=AssertionError('rerolled collection')):
    resumed = prepare({}, mid, True, server.State, rng=rng)
assert resumed == loaded
facts = player.data['exvius_repeat']['attempt']['ios_update']
assert facts['collection'] == before_upgrade['exvius_repeat']['attempt']['ios_update']['collection']
assert facts.get('first_clear') == '50:0:100:100', facts
assert facts.get('gil') == 24, facts
snapshot = copy.deepcopy(player.data)
with patch.object(player_state, 'mission_row', return_value=dict(mission, **{'1x4bG2J8':'50:0:999:100', '7UR4J2SE':'999'})):
    assert prepare({}, mid, True, server.State) == resumed
assert player.data == snapshot
attempt = player.data['exvius_repeat']['attempt']
attempt.update(status='completed', cleared=True, normal_rewards_recorded=True)
old_lapis, old_gil = player.currencies['lapis_free'], player.currencies['gil']
req = json.dumps({'09HRWXDf':[{'EWmQy52k':'20:204000100:999'}]})
out = settle({'09HRWXDf':[{}]}, mid, req, server.State)
assert player.currencies['lapis_free'] == old_lapis + earned(player.data, 100)
assert player.currencies['gil'] == old_gil + 24
assert out['09HRWXDf'][0]['p1K5NecV'] == '50:0:' + str(earned(player.data, 100))
assert out['09HRWXDf'][0]['16LQuC5r'] == '24'
expected_collection = 3 if mid == '1110204' else 0
assert player.item_count(20, 204000100) == expected_collection
assert player.save(str(config.state_file))
player = server.State.player = player_state.PlayerState.load(str(config.state_file), slot=config.slot)
before_retry = copy.deepcopy(player.data)
retried = settle({'09HRWXDf':[{}]}, mid, req, server.State)
assert retried['09HRWXDf'][0]['p1K5NecV'] == out['09HRWXDf'][0]['p1K5NecV']
assert player.data == before_retry
''')

    def test_given_recorded_empty_update_rewards_when_reloading_then_preserve_snapshot(self):
        self.run_engine('''
import player_state
from ios_server.campaign_upgrade import build
from revival_update import initialize
from revival_battle_updates import prepare
initialize(player.data)
player.data['exvius_repeat'] = {'attempt':{'mid':'1110404', 'sequence':1, 'status':'pending',
    'ios_update':{'version':1, 'first_clear':'', 'gil':0, 'collection':{}, 'exploration':True, 'settled':False}}}
before = copy.deepcopy(player.data)
with patch.object(player_state, 'mission_row', side_effect=AssertionError('replaced recorded rewards')):
    assert prepare({}, '1110404', True, server.State) == {'vM21k0do':[]}
assert player.data == before
candidate, report = build(player.data, units={}, steps={}, switches={}, missions={}, experience=[])
assert candidate == before and report['already_upgraded']
''')

    def test_given_two_fusion_rows_when_encrypted_then_both_bases_consume_their_materials(self):
        self.run_engine('''
units = [player.grant_unit(uid) for uid in ('100000315','100000315','100000337','100000337')]
player.save(str(config.state_file))
req = {'f08du6EW':[{'og2GHy49':str(units[0]['instance_id']),'WbGYcN17':str(units[1]['instance_id'])},
                   {'og2GHy49':str(units[2]['instance_id']),'WbGYcN17':str(units[3]['instance_id'])}]}
out = request('UnitMixRequest',req)
assert len(out['f08du6EW']) == 2
assert player.roster_row(units[1]['instance_id']) is None
assert player.roster_row(units[3]['instance_id']) is None
assert player.roster_row(units[0]['instance_id']) is not None
assert player.roster_row(units[2]['instance_id']) is not None
''')

    def test_given_campaign_without_update_marker_when_exiting_exploration_then_settle_lumber_collection_once_and_reproject_retry(self):
        self.run_engine('''
from types import SimpleNamespace
import player_state
from ffbe_battle import mission_end_echo
from revival_battle_updates import prepare, settle
masters = Path(config.engine_environment()['MST_DIR'])
(masters / 'F_MISSION_MST.ndjson').write_text('\\n'.join((
    json.dumps({'qo3PECw6':'1110101', 'Y4VoF8yu':'1', '8xi6Xvyk':'3'}),
    json.dumps({'qo3PECw6':'1110204', 'Y4VoF8yu':'2', '8xi6Xvyk':'0'}),
)))
for key in [k for k in player_state._TABLES if k[0] == 'F_MISSION_MST.ndjson']:
    player_state._TABLES.pop(key)
player.data.pop('ios_revival_update', None)
player.data.pop('ios_reward_claims', None)
rng = SimpleNamespace(choices=lambda entries, weights=None: [next(e for e in entries if e[1] == '204000100')], randint=lambda a, b: a)

player.data['exvius_repeat'] = {'attempt':{'mid':'1110101','sequence':1,'status':'pending'}}
before_non_exp = copy.deepcopy(player.data)
assert prepare({}, '1110101', True, server.State, rng=rng) == {}
assert player.data == before_non_exp

player.data['exvius_repeat'] = {'attempt':{'mid':'1110204','sequence':2,'status':'pending'}}
prepared = prepare({}, '1110204', True, server.State, rng=rng)
assert [(row['N3hB0CwE'], row['9GIvAQC2'], row['1Fa7rL5R']) for row in prepared['vM21k0do']] == [
    ('10100', '1', '20:204000100:1'),
    ('10101', '1', '20:204000100:1'),
    ('10102', '1', '20:204000100:1'),
]
assert 'ios_reward_claims' not in player.data

attempt = player.data['exvius_repeat']['attempt']
attempt.update(status='completed', cleared=False, normal_rewards_recorded=True)
req = json.dumps({'jQsE54Iz':[{'qo3PECw6':'1110204'}],'09HRWXDf':[{'S4U09svH':'0','Wdi3MAs2':'0','EWmQy52k':'20:204000100:1'}]})
echoed = mission_end_echo({'09HRWXDf':[{'EWmQy52k':'20:1:1'}]}, req)
assert 'EWmQy52k' not in echoed['09HRWXDf'][0]
out = settle(echoed, '1110204', req, server.State)
assert player.item_count(20, 204000100) == 1, (player.item_count(20, 204000100), out, player.data.get('exvius_repeat'), player.data.get('inventory'))
assert out['09HRWXDf'][0]['EWmQy52k'] == '20:204000100:1', out
assert 'ios_reward_claims' not in player.data

before_retry = copy.deepcopy(player.data)
echoed_retry = mission_end_echo({'09HRWXDf':[{'EWmQy52k':'20:1:1'}]}, req)
retried = settle(echoed_retry, '1110204', req, server.State)
assert retried['09HRWXDf'][0]['EWmQy52k'] == '20:204000100:1', retried
assert player.item_count(20, 204000100) == 1
assert player.data == before_retry
''')


if __name__ == '__main__':
    unittest.main()
