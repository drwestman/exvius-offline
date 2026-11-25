"""Encrypted iOS quest defeat settlement, publication and failure rollback."""
import json
import unittest

import test_ios_summons as harness


SETUP = '''
from exvius_repeat import observe_load
from ffbe_pipeline import reply_pipeline
from ffbe_config import RESULT_TAG
from player_state import PlayerState
SID, MID = '100100401', '1110301'
player.data['exvius_map'] = {'quests': {SID: {'Z34jU7ue': '1001004',
    '7Svg2kdT': SID, '4kcAD9fW': '1', '0G7J2vfD': ''}}}
bundle = {'wbet57nF': [{'xqartN26': '101025000', 'V9j8wJcC': '1010250'}]}
observe_load(bundle, MID, True)
player.save(str(config.state_file))
payload = {'jQsE54Iz': [{'qo3PECw6': MID}],
           RESULT_TAG: [{'S4U09svH': '0', 'Wdi3MAs2': '0', 'f6M1cJgk': '101025000:4'}],
           '2urzfX6d': [{'69ieJGhD': '1:111030107:2'}]}
def progress():
    return player.data['exvius_map']['quests'][SID]['0G7J2vfD']
'''


class IosMapQuestIntegration(unittest.TestCase):
    setUp = harness.ReplaySummonIntegration.setUp
    prepared_data = harness.ReplaySummonIntegration.prepared_data
    child = harness.ReplaySummonIntegration.child
    run_engine = harness.ReplaySummonIntegration.run_engine

    def write_masters(self, masters):
        harness.ReplaySummonIntegration.write_masters(self, masters)
        (masters / 'F_MISSION_MST.ndjson').write_text(json.dumps({
            'qo3PECw6': '1110301', 'gQR24kST': '1', 'B6H34Mea': '0'}))
        (masters / 'F_QUEST_SUB_MST.ndjson').write_text(json.dumps({
            '7Svg2kdT': '100100401', 'Z34jU7ue': '1001004',
            '89EvGKHx': '2', 'siLGXq94': '2', '25oxcKwN': '1010250:10'}))

    def test_given_encrypted_victory_when_settled_then_publish_and_save_once(self):
        self.run_engine(SETUP + '''
out = request('MissionEndRequest', payload)
assert progress() == '1010250:4', progress()
assert out['hQKAwj18'][0]['0G7J2vfD'] == '1010250:4'
loaded = PlayerState.load(str(config.state_file))
assert loaded.data['exvius_map'] == player.data['exvius_map']
player.data = loaded.data
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
request('MissionEndRequest', payload)
assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_save_or_projection_failure_when_settled_then_preserve_progress_and_receipt(self):
        self.run_engine(SETUP + '''
before, saved, dirty = copy.deepcopy(player.data), config.state_file.read_bytes(), player.dirty
for method, error in [('save', OSError), ('apply_to_reply', ValueError)]:
    kwargs = {'return_value': False} if method == 'save' else {'side_effect': ValueError('projection')}
    with patch.object(type(player), method, **kwargs):
        try:
            reply_pipeline({RESULT_TAG: [{}]}, endpoints['MissionEndRequest']['request_id'], json.dumps(payload), MID, None)
        except error:
            pass
        else:
            raise AssertionError('failure hidden')
    assert server.State.player is player and player.data == before and player.dirty == dirty
    assert config.state_file.read_bytes() == saved
request('MissionEndRequest', payload)
assert progress() == '1010250:4'
''')


if __name__ == '__main__':
    unittest.main()
