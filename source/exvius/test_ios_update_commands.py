"""Encrypted-request checks for the updated iOS command boundary."""
import unittest
import test_ios_summons as _fixtures


class UpdatedUnitCommands(unittest.TestCase):
    setUp = _fixtures.ReplaySummonIntegration.setUp
    prepared_data = _fixtures.ReplaySummonIntegration.prepared_data
    write_masters = _fixtures.ReplaySummonIntegration.write_masters
    child = _fixtures.ReplaySummonIntegration.child
    run_engine = _fixtures.ReplaySummonIntegration.run_engine
    extra_items = ('90', '91')

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


if __name__ == '__main__':
    unittest.main()
