"""BDD for shared town-quest defeat progress, using the shipped quest masters."""
import copy
import json
import unittest
from unittest.mock import patch

from ffbe_state import State
from player_state import PlayerState, _normalise, _serialise
from exvius_actions_expedition import mission_update
from exvius_repeat import observe_load, complete_attempt
from ffbe_player import score_completed_quest_mission


SID = '100100401'
WOLF = '1010250'
MID = '1110301'
BUNDLE = {'wbet57nF': [
    {'xqartN26': '101025000', 'V9j8wJcC': WOLF},
    {'xqartN26': '101025001', 'V9j8wJcC': WOLF},
    {'xqartN26': '105001001', 'V9j8wJcC': '1050010'}]}


class MapQuestBehavior(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, State, 'player', State.player)
        self.addCleanup(setattr, State, 'state_dirty', State.state_dirty)
        self.player = PlayerState.load('/nonexistent', slot='map-quest-test')
        State.player = self.player
        mission_update({}, {'JcxS6A8N': [{'Gh92V3Tx': '1101'}],
                           '1sGiqV9T': [{'i9han5Sz': f'1001004:{SID}'}]})

    def progress(self):
        return self.player.data['exvius_map']['quests'][SID]['0G7J2vfD']

    def end(self, counts='101025000:4', mid=MID, cleared=True, bundle=BUNDLE):
        observe_load(bundle, mid, True)
        complete_attempt(self.player, mid, cleared, [], {}, {})
        report = {'jQsE54Iz': [{'qo3PECw6': mid}],
                  '09HRWXDf': [{'f6M1cJgk': counts}],
                  '2urzfX6d': [{'69ieJGhD': '1:111030107:2' if cleared else ''}]}
        self.report = json.dumps(report)
        return score_completed_quest_mission(self.report)

    def reload(self):
        self.player = PlayerState(_normalise(json.loads(json.dumps(_serialise(self.player.data)))))
        State.player = self.player

    def test_given_active_wolf_quest_when_four_wolves_defeated_then_persist_four(self):
        self.assertTrue(self.end('101025000:4,105001001:4'))
        self.assertEqual(self.progress(), f'{WOLF}:4')
        self.reload()
        self.assertEqual(self.progress(), f'{WOLF}:4')

    def test_given_exploration_when_wolf_variants_defeated_then_sum_family_and_cap(self):
        self.end('101025000:4,101025001:2', mid='1110304')
        self.assertEqual(self.progress(), f'{WOLF}:6')
        self.end('101025000:7', mid='1110304')
        self.assertEqual(self.progress(), f'{WOLF}:10')
        self.assertEqual(self.player.data['exvius_map']['quests'][SID]['4kcAD9fW'], '1')
        self.assertNotIn('1001004', self.player.data['exvius_map'].get('rewarded', []))

    def test_given_recorded_result_when_retried_after_reload_then_no_second_credit(self):
        self.end()
        self.reload()
        before = copy.deepcopy(self.player.data)
        self.assertFalse(score_completed_quest_mission(self.report))
        self.assertEqual(self.player.data, before)
        self.assertEqual(self.progress(), f'{WOLF}:4')

    def test_given_pending_reload_when_bundle_changes_then_keep_recorded_family(self):
        observe_load(BUNDLE, MID, True)
        self.reload()
        changed = {'wbet57nF': [{'xqartN26': '101025000', 'V9j8wJcC': '999'}]}
        self.end(bundle=changed)
        self.assertEqual(self.progress(), f'{WOLF}:4')

    def test_given_bad_or_unrelated_reports_when_settled_then_preserve_progress(self):
        self.end()
        for raw in ('105001001:9', '999999999:10', '101025000:0', '', None,
                    '101025000:-1', '101025000:1,101025000:2', '101025000:1,broken',
                    '101025000:2147483648', '101025000:1:2', [], '１０１０２５０００:4'):
            with self.subTest(raw=raw):
                self.end(raw)
                self.assertEqual(self.progress(), f'{WOLF}:4')

    def test_given_inactive_or_other_task_when_defeating_wolves_then_no_progress(self):
        for state in ('0', '2'):
            self.player.data['exvius_map']['quests'][SID]['4kcAD9fW'] = state
            self.end()
            self.assertEqual(self.progress(), '')
        self.player.data['exvius_map']['quests'][SID]['4kcAD9fW'] = '1'
        from player_state import _load_ndjson
        steps = copy.deepcopy(_load_ndjson('F_QUEST_SUB_MST.ndjson', '7Svg2kdT'))
        steps[SID]['siLGXq94'] = '3'
        with patch('player_state._load_ndjson', return_value=steps):
            from exvius_map_quests import score_defeats
            score_defeats(self.player, '101025000:4')
        self.assertEqual(self.progress(), '')
        self.player.data['exvius_map']['quests'].clear()
        self.end()
        self.assertEqual(self.player.data['exvius_map']['quests'], {})

    def test_given_loss_frozen_or_wrong_mission_when_reported_then_no_credit(self):
        self.assertFalse(self.end(cleared=False))
        self.assertEqual(self.progress(), '')
        observe_load(BUNDLE, MID, True)
        complete_attempt(self.player, MID, True, [], {}, {})
        wrong = json.dumps({'jQsE54Iz': [{'qo3PECw6': '1110304'}],
                            '09HRWXDf': [{'f6M1cJgk': '101025000:4'}],
                            '2urzfX6d': [{'69ieJGhD': '1:111030107:1'}]})
        before = copy.deepcopy(self.player.data)
        self.assertFalse(score_completed_quest_mission(wrong))
        self.assertEqual(self.player.data, before)
        self.player.mode = 'frozen'
        self.assertFalse(self.end())
        self.assertEqual(self.player.data, before)

    def test_given_old_attempt_without_mapping_when_reported_then_never_guess_family(self):
        from exvius_repeat import begin_attempt
        begin_attempt(self.player, MID)
        self.end()  # A repeated pending load must not rewrite an old receipt.
        self.assertEqual(self.progress(), '')

    def test_given_finished_target_when_returning_to_npc_then_reward_once(self):
        self.end('101025000:10')
        request = {'JcxS6A8N': [{'Gh92V3Tx': '1101'}],
                   '1sGiqV9T': [{'9YPZuB2i': f'1001004:{SID}'}]}
        mission_update({}, request)
        self.assertIn('1001004', self.player.data['exvius_map']['rewarded'])
        self.reload()
        before = copy.deepcopy(self.player.data)
        mission_update({}, request)
        self.assertEqual(self.player.data, before)

    def test_given_saved_progress_when_projected_then_queries_are_read_only(self):
        self.end()
        before = copy.deepcopy(self.player.data)
        groups = self.player.groups()
        sub = next(row for row in groups['hQKAwj18'] if row['7Svg2kdT'] == SID)
        self.assertEqual(sub['0G7J2vfD'], f'{WOLF}:4')
        self.assertIn({'Z34jU7ue': '1001004', '4kcAD9fW': '1'}, self.player.quest_info_rows())
        self.assertEqual(self.player.data, before)

    def test_given_multiple_targets_when_counted_then_keep_original_order_and_caps(self):
        from exvius_map_quests import plan_progress
        from player_state import _load_ndjson
        sid = '104600101'
        step = _load_ndjson('F_QUEST_SUB_MST.ndjson', '7Svg2kdT')[sid]
        saved = {sid: {'Z34jU7ue': step['Z34jU7ue'], '7Svg2kdT': sid,
                       '4kcAD9fW': '1', '0G7J2vfD': '1011310:1,1042010:0'}}
        before = copy.deepcopy(saved)
        updates = plan_progress(saved, {sid: step}, {'1042010': 9, '1011310': 1})
        self.assertEqual(updates, {sid: '1011310:2,1042010:2'})
        self.assertEqual(saved, before)

    def test_given_one_corrupt_saved_quest_when_planned_then_other_quests_still_progress(self):
        from exvius_map_quests import plan_progress
        from player_state import _load_ndjson
        steps = _load_ndjson('F_QUEST_SUB_MST.ndjson', '7Svg2kdT')
        good, bad = steps[SID], steps['104600101']
        quests = {
            '104600101': {'Z34jU7ue': bad['Z34jU7ue'], '7Svg2kdT': '104600101',
                          '4kcAD9fW': '1', '0G7J2vfD': '999:1'},  # unknown target
            SID: {'Z34jU7ue': good['Z34jU7ue'], '7Svg2kdT': SID,
                  '4kcAD9fW': '1', '0G7J2vfD': ''}}
        notes = []
        updates = plan_progress(quests, steps, {WOLF: 3, '1011310': 1}, note=notes.append)
        self.assertEqual(updates, {SID: f'{WOLF}:3'})
        self.assertEqual(len(notes), 1)

    def test_given_verified_history_when_recovered_twice_then_keep_total_and_handin_pending(self):
        from exvius_map_quests import plan_progress
        from player_state import _load_ndjson
        quests = self.player.data['exvius_map']['quests']
        steps = _load_ndjson('F_QUEST_SUB_MST.ndjson', '7Svg2kdT')
        quests[SID]['0G7J2vfD'] = f'{WOLF}:4'
        updates = plan_progress(quests, steps, {WOLF: 10}, floor=True)
        self.assertEqual(updates, {SID: f'{WOLF}:10'})
        quests[SID]['0G7J2vfD'] = updates[SID]
        before = copy.deepcopy(self.player.data)
        self.assertEqual(plan_progress(quests, steps, {WOLF: 10}, floor=True), {})
        self.assertEqual(plan_progress(quests, steps, {WOLF: 4}, floor=True), {})
        self.assertEqual(self.player.data, before)
        self.assertEqual(quests[SID]['4kcAD9fW'], '1')


if __name__ == '__main__':
    unittest.main()
