"""BDD for iOS arena policy, durable commands, and encrypted native requests."""
import copy
from datetime import datetime, timedelta, timezone
import json
import unittest

import test_ios_summons as harness
import revival_friends
import revival_arena as arena

NOW = harness.NOW

FLOW = '''
import revival_arena as arena
from player_state import PlayerState
def enter():
    return request('RbEntryRequest')
def selection(entry, *, all_orbs=False):
    target = entry['Tr9m32i1'][0]['TI6deE8P'].split(',')[0].split(':')[0]
    node = dict(entry['yT12twnc'][0], Q03VHyjm='1' if all_orbs else '0')
    return {'yT12twnc': [node], 'N7Bd3IuL': [{'fP8Nv0KZ': target}]}
def report(req, *, win=True, retire=False):
    active = player.data['exvius_arena']['active']
    req = copy.deepcopy(req)
    req['g3JFd0y7'] = [{
        'GA1D6XIC': ','.join(mid + ':' + iid + (':1:0' if win else ':0:1') for iid, mid in active['own'].items()),
        'Pch7J9Ty': ','.join(mid + ':' + iid + (':0:1' if win else ':1:0') for iid, mid in active['members'].items()),
        '3S8pMym0': '100', 'bB69ZWQY': '0', 'z8uj9TAU': '1', 'g9t7dBCH': '1' if retire else '0'}]
    return req
'''


class ArenaPolicyBehavior(unittest.TestCase):
    def data(self):
        data = harness.campaign()
        revival_friends.initialize(data, yaml_friends=[])
        return data

    def test_given_history_when_selecting_season_then_use_started_season_and_last_after_history(self):
        rows = [{'6Z9DxQFf': '0', 'VjJQ51uG': '2016-01-01 00:00:00'},
                {'6Z9DxQFf': '1', 'VjJQ51uG': '2016-12-15 04:00:00'},
                {'6Z9DxQFf': '2', 'VjJQ51uG': '2016-12-22 04:00:00'}]
        self.assertEqual(arena.select_season(rows, '2016-12-16'), '1')
        self.assertEqual(arena.select_season(rows, None), '2')

    def test_given_saved_crowd_when_scores_grow_then_keep_rng_and_campaign_unchanged(self):
        import random
        data = self.data()
        before, rng = copy.deepcopy(data), random.getstate()
        first = arena.Ladder(data, NOW)
        second = arena.Ladder(data, NOW + timedelta(days=3))
        for fid in first.directory.ids():
            self.assertGreaterEqual(second.points(fid), first.points(fid))
        self.assertEqual(first.rank_of(0), 201)
        self.assertEqual(second.rank_of(100000), 1)
        self.assertEqual(data, before)
        self.assertEqual(random.getstate(), rng)

    def test_given_dst_when_scores_finish_then_use_actual_elapsed_week_seconds(self):
        data = self.data()
        for moment in (datetime(2027, 3, 8, 4, tzinfo=timezone.utc),
                       datetime(2026, 10, 26, 3, tzinfo=timezone.utc)):
            ladder = arena.Ladder(data, moment)
            end = ladder.week.ends.astimezone(timezone.utc) - timedelta(microseconds=1)
            final = arena.Ladder(data, end)
            self.assertEqual(final.week.number, ladder.week.number)
            self.assertGreater(max(final.points(fid) for fid in final.directory.ids()), 10000)

    def test_given_local_rank_when_mapped_to_global_scale_then_choose_original_brackets(self):
        self.assertEqual(arena.placement(1, 201), 1493)
        self.assertEqual(arena.placement(2, 201), 2986)
        self.assertEqual(arena.placement(201, 201), 300000)

    def test_given_corrupt_week_or_settings_when_read_then_fail_without_repair(self):
        data = self.data()
        data['exvius_arena'] = {'ladder': {'version': 1, 'top_score': 12000, 'rivals': 5}}
        data['exvius_arena'].update(week=44, week_starts='broken', week_ends='2026-11-16T03:00:00+00:00')
        before = copy.deepcopy(data)
        with self.assertRaisesRegex(ValueError, 'Invalid iOS arena week'):
            arena.for_model(data, data['exvius_arena'], NOW)
        self.assertEqual(before, data)
        data['exvius_arena']['ladder']['version'] = 99
        before = copy.deepcopy(data)
        with self.assertRaisesRegex(ValueError, 'Invalid iOS arena ladder'):
            arena.Ladder(data, NOW)
        self.assertEqual(before, data)


class ArenaIntegration(unittest.TestCase):
    setUp = harness.ReplaySummonIntegration.setUp
    prepared_data = harness.ReplaySummonIntegration.prepared_data
    child = harness.ReplaySummonIntegration.child
    run_engine = harness.ReplaySummonIntegration.run_engine
    extra_units = [('100000115', 5), ('100000215', 5), ('203000205', 5),
                   ('204000115', 5), ('206000905', 5)]

    def write_masters(self, masters):
        harness.ReplaySummonIntegration.write_masters(self, masters)
        def table(name, rows):
            (masters / (name + '.ndjson')).write_text('\n'.join(json.dumps(row) for row in rows))
        table('F_RB_SS_MST', [{'6Z9DxQFf': str(sid), 'VjJQ51uG': start, 'uo0xmn8b': '',
                              'dJ1g6p8h': '50:1:20,50:1:20,50:1:20,50:1:20,50:1:20'}
                             for sid, start in ((1, '2016-12-15 04:00:00'), (2, '2017-01-05 04:00:00'))])
        table('F_RB_SS_REWARD_MST', [{'6Z9DxQFf': str(sid), 'vs48LZrt': '0', 'ip94Nqb7': low,
                                     'XM4Ca3PF': high, 'dX6cor8j': '50:1:' + count}
                                    for sid in (1, 2) for low, high, count in
                                    (('1', '3000', '100'), ('3001', '300000', '10'))])
        table('F_RB_AI_PATTERN_MST', [{'UE3vKA5y': '1', 'ixDq7yJ8': '100'}])
        table('F_RB_TRADE_BOARD_MST', [{'6m4Rn5jd': '1', 'dX6cor8j': '50:1:20'}])
        table('F_RB_TRADE_BOARD_PIECE_MST', [
            {'AyCR5h7s': '11', '6m4Rn5jd': '1', 'pgS67dFz': '0', '1XRtI2d9': '0:0',
             '3h9XCMqj': '12', 'mRY52Tib': '1', 'i9w6ZCFM': '50:1:20'},
            {'AyCR5h7s': '12', '6m4Rn5jd': '1', 'pgS67dFz': '1', '1XRtI2d9': '1:0',
             '3h9XCMqj': '11', 'mRY52Tib': '2', 'i9w6ZCFM': '50:1:5'}])

    def test_given_native_entry_when_retried_then_initialize_once_and_rank_without_writes(self):
        self.run_engine('''
import revival_arena as arena
with patch.object(arena, 'clock', return_value=NOW):
    entered = request('RbEntryRequest')
    assert entered['yT12twnc'][0]['S3rek7hC'] == '1'
    candidates = entered['Tr9m32i1'][0]['TI6deE8P'].split(',')
    assert len(candidates) == 5, candidates
    assert all(50 <= int(row.split(':')[7]) <= 150 for row in candidates)
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    request('RbEntryRequest')
    payload = {'yT12twnc': entered['yT12twnc'], 'e7n2P5IJ': [{'3HbFrqo5': '1'}]}
    ranking = request('RbRankingRequest', payload)['YQN6zx3R'][0]['CLg9j1sh'].split(',')
    assert len(ranking) == 101
    request('RbReStartRequest', payload)
    assert player.data == before and config.state_file.read_bytes() == saved
with patch.object(arena, 'clock', return_value=NOW + timedelta(seconds=599)):
    same = request('RbEntryRequest')['Tr9m32i1'][0]['TI6deE8P'].split(',')
    assert [r.split(':')[0] for r in same] == [r.split(':')[0] for r in candidates]
with patch.object(arena, 'clock', return_value=NOW + timedelta(seconds=600)):
    changed = request('RbEntryRequest')['Tr9m32i1'][0]['TI6deE8P'].split(',')
    assert [r.split(':')[0] for r in changed] != [r.split(':')[0] for r in candidates]
    assert config.state_file.read_bytes() == saved
''')

    def test_given_full_rival_when_matching_starting_and_finishing_then_charge_and_credit_once(self):
        self.run_engine(FLOW + '''
with patch.object(arena, 'clock', return_value=NOW):
    entered = enter()
    req = selection(entered)
    before = player.orb_view('clsm')[0]
    match = request('RbMatchingRequest', req)
    packed = match['DW0rgk3C'][0]['Jc4udh7x']
    assert len(packed.split(';')) == 5, packed
    assert all(len(row.split(':')) == 18 for row in packed.split(';'))
    saved = config.state_file.read_bytes()
    again = request('RbMatchingRequest', req)
    assert again['DW0rgk3C'] == match['DW0rgk3C']
    assert config.state_file.read_bytes() == saved
    request('RbStartRequest', req)
    assert player.orb_view('clsm')[0] == before - 1
    active = copy.deepcopy(player.data['exvius_arena']['active'])
    request('RbStartRequest', req)
    assert player.orb_view('clsm')[0] == before - 1
    assert player.data['exvius_arena']['active'] == active
    result_req = report(req)
    done = request('RbEndRequest', result_req)['g3JFd0y7'][0]
    assert done['2q7sZreS'] == '1'
    assert int(done['42GLsTok'].split(',')[1]) == active['rate']
    assert int(done['PDi5wos8'].split(',')[1]) > 0
    assert player.archive_value('ARENA_WIN_CNT') == 1
    player.data = PlayerState.load(str(config.state_file)).data
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    assert request('RbEndRequest', result_req)['g3JFd0y7'][0] == done
    assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_all_orbs_when_winning_or_losing_then_keep_original_reservation_rules(self):
        self.run_engine(FLOW + '''
with patch.object(arena, 'clock', return_value=NOW):
    fresh = copy.deepcopy(player.data)
    for win in (True, False):
        player.data = copy.deepcopy(fresh)
        entered = enter()
        req = selection(entered, all_orbs=True)
        request('RbMatchingRequest', req)
        before = player.orb_view('clsm')[0]
        request('RbStartRequest', req)
        rate = player.data['exvius_arena']['active']['rate']
        assert player.orb_view('clsm')[0] == 0
        done = request('RbEndRequest', report(req, win=win))['g3JFd0y7'][0]
        used = before if win else 1
        assert player.orb_view('clsm')[0] == before - used
        assert int(done['42GLsTok'].split(',')[1]) == (rate * used if win else 10)
        assert player.data['exvius_arena']['daily'] == {'2026-11-09': used}
        assert player.data['exvius_arena']['user']['5svT7qLR'] == ('1' if win else '0')
''')

    def test_given_pending_battle_when_week_changes_then_resume_snapshot_and_roll_only_after_settlement(self):
        self.run_engine(FLOW + '''
with patch.object(arena, 'clock', return_value=NOW):
    entered = enter()
    req = selection(entered)
    request('RbMatchingRequest', req)
    request('RbStartRequest', req)
    active = copy.deepcopy(player.data['exvius_arena']['active'])
    old_week = player.data['exvius_arena']['week']
    result_req = report(req)
    orbs = player.orb_view('clsm')[0]
player.data = PlayerState.load(str(config.state_file)).data
with patch.object(arena, 'clock', return_value=NOW + timedelta(weeks=3)):
    old = enter()
    assert old['yT12twnc'][0]['S3rek7hC'] == '1'
    assert player.data['exvius_arena']['week'] == old_week
    assert player.data['exvius_arena']['active'] == active
    resumed = request('RbReStartRequest', req)
    assert resumed['DW0rgk3C'][0]['Jc4udh7x'] == active['rival']
    assert player.orb_view('clsm')[0] == orbs
    request('RbEndRequest', result_req)
    points = int(player.data['exvius_arena']['user']['UbQ26oH4'])
    rolled = enter()
    assert rolled['yT12twnc'][0]['S3rek7hC'] == '2'
    assert player.data['exvius_arena']['week'] == old_week + 3
    assert player.data['exvius_arena']['user']['UbQ26oH4'] == '0'
    assert player.data['exvius_arena']['last_week_result']['points'] == points
''')

    def test_given_played_week_when_away_for_weeks_then_pay_original_placement_once_on_entry(self):
        self.run_engine(FLOW + '''
with patch.object(arena, 'clock', return_value=NOW):
    entered = enter()
    player.data['exvius_arena']['user']['UbQ26oH4'] = '20000'
    player.dirty = True
    player.save(str(config.state_file))
    old = copy.deepcopy(player.data['exvius_arena'])
baseline = player.currencies['lapis_free']
with patch.object(arena, 'clock', return_value=NOW + timedelta(weeks=4)):
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    ranking_req = {'yT12twnc': entered['yT12twnc'], 'e7n2P5IJ': [{'3HbFrqo5': '1'}]}
    request('RbRankingRequest', ranking_req)
    request('RbReStartRequest', ranking_req)
    assert player.data == before and config.state_file.read_bytes() == saved
    enter()
    assert player.currencies['lapis_free'] == baseline + 500
    rolled = player.data['exvius_arena']
    assert rolled['ladder_last_paid'] == old['week']
    assert rolled['last_week_result']['rank'] == 1
    assert rolled['lifetime_points'] == 20000
    assert rolled['user']['UbQ26oH4'] == '0'
    assert len([m for m in player.mailbox if m['title'] == 'Arena Weekly Ranking']) == 1
    player.data = PlayerState.load(str(config.state_file)).data
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    enter()
    assert player.data == before and config.state_file.read_bytes() == saved
with patch.object(arena, 'clock', return_value=NOW + timedelta(weeks=20)):
    enter()
    assert player.currencies['lapis_free'] == baseline + 500
''')

    def test_given_save_failure_when_entering_starting_or_finishing_then_publish_no_partial_campaign(self):
        self.run_engine(FLOW + '''
from exvius_actions_arena import rb_entry
from exvius_arena import start, end
def fails(callback, req):
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    with patch.object(type(player), 'save', return_value=False):
        try:
            callback({}, req)
        except OSError:
            pass
        else:
            raise AssertionError('save failure hidden')
    assert server.State.player is player
    assert player.data == before and config.state_file.read_bytes() == saved
with patch.object(arena, 'clock', return_value=NOW):
    fails(rb_entry, {})
    entered = enter()
    req = selection(entered)
    request('RbMatchingRequest', req)
    fails(start, req)
    request('RbStartRequest', req)
    done = report(req)
    fails(end, done)
    request('RbEndRequest', done)
with patch.object(arena, 'clock', return_value=NOW + timedelta(weeks=1)):
    fails(rb_entry, {})
    enter()
''')

    def test_given_invalid_enemy_or_frozen_player_when_mutating_then_preserve_save_and_orbs(self):
        self.run_engine(FLOW + '''
with patch.object(arena, 'clock', return_value=NOW):
    entered = enter()
    req = selection(entered)
    request('RbMatchingRequest', req)
    request('RbStartRequest', req)
    good = report(req)
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    bad = copy.deepcopy(good)
    bad['g3JFd0y7'][0]['Pch7J9Ty'] = bad['g3JFd0y7'][0]['Pch7J9Ty'].split(',')[0]
    request('RbEndRequest', bad, allow_empty=True)
    assert player.data == before and config.state_file.read_bytes() == saved
    player.mode = 'frozen'
    request('RbEndRequest', good, allow_empty=True)
    request('RbEntryRequest', allow_empty=True)
    request('RbReStartRequest', req)
    assert player.data == before and config.state_file.read_bytes() == saved
    player.mode = 'live'
    request('RbEndRequest', good)
''')

    def test_given_snapshot_when_retiring_then_account_for_every_enemy_and_consume_one_orb(self):
        self.run_engine(FLOW + '''
with patch.object(arena, 'clock', return_value=NOW):
    req = selection(enter(), all_orbs=True)
    request('RbMatchingRequest', req)
    before = player.orb_view('clsm')[0]
    request('RbStartRequest', req)
    done = request('RbEndRequest', report(req, retire=True))['g3JFd0y7'][0]
    assert done['2q7sZreS'] == '2'
    assert len(done['Pch7J9Ty'].split(',')) == 5
    assert player.orb_view('clsm')[0] == before - 1
''')

    def test_given_medals_when_opening_board_then_save_grants_and_retry_without_double_payment(self):
        self.run_engine(FLOW + '''
from exvius_actions_arena import rb_board_open
with patch.object(arena, 'clock', return_value=NOW):
    enter()
    player.data['exvius_arena']['user']['mRY52Tib'] = '100'
    player.dirty = True
    player.save(str(config.state_file))
    payload = {'7GUQtmb3': [{'CIE1rky2': '1', '6m4Rn5jd': '1', 'mvc31xSV': '11'}]}
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    with patch.object(type(player), 'save', return_value=False):
        try:
            rb_board_open({}, payload)
        except OSError:
            pass
        else:
            raise AssertionError('board save failure hidden')
    assert player.data == before and config.state_file.read_bytes() == saved
    request('RbBoardPieceOpenRequest', payload)
    assert player.data['exvius_arena']['user']['mRY52Tib'] == '99'
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    request('RbBoardPieceOpenRequest', payload)
    assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_missing_reward_when_rollover_runs_then_keep_the_unpaid_week_for_retry(self):
        self.run_engine(FLOW + '''
with patch.object(arena, 'clock', return_value=NOW):
    enter()
    player.data['exvius_arena']['user']['UbQ26oH4'] = '20000'
    player.dirty = True
    player.save(str(config.state_file))
with patch.object(arena, 'clock', return_value=NOW + timedelta(weeks=1)):
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    with patch.object(arena, 'reward_row', return_value=None):
        request('RbEntryRequest', allow_empty=True)
    assert player.data == before and config.state_file.read_bytes() == saved
    enter()
    assert player.data['exvius_arena']['last_week_result']['points'] == 20000
''')

    def test_given_saved_settings_or_stale_selection_when_environment_or_week_changes_then_preserve_contract(self):
        self.run_engine(FLOW + '''
import os
with patch.object(arena, 'clock', return_value=NOW):
    first = enter()
    req = selection(first)
    request('RbMatchingRequest', req)
    config_before = copy.deepcopy(player.data['exvius_arena']['ladder'])
    with patch.dict(os.environ, {'EXVIUS_ARENA_TOP': '10', 'EXVIUS_ARENA_RIVALS': '1'}):
        assert len(enter()['Tr9m32i1'][0]['TI6deE8P'].split(',')) == 5
        assert player.data['exvius_arena']['ladder'] == config_before
with patch.object(arena, 'clock', return_value=NOW + timedelta(weeks=1)):
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    request('RbStartRequest', req, allow_empty=True)
    assert player.data == before and config.state_file.read_bytes() == saved
    new = enter()
    assert new['yT12twnc'][0]['S3rek7hC'] == '2'
    assert player.data['exvius_arena']['matched'] is None
with patch.object(arena, 'clock', return_value=NOW):
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    request('RbEntryRequest', allow_empty=True)
    assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_disabled_crowd_when_entering_then_keep_curated_single_unit_opponents(self):
        self.run_engine(FLOW + '''
import ffbe_friends
player.data['exvius_friends']['simulation']['count'] = 0
player.data['exvius_friends']['relations'] = {}
yaml = config.root / 'arena-test-friends.yaml'
yaml.write_text('friends:\\n  - display_name: Kupo\\n    friend_id: 900000003\\n    unit:\\n      master_id: 100000315\\n      level: 80\\n')
with patch.object(ffbe_friends, 'FRIENDS_FILE', str(yaml)), patch.object(ffbe_friends, '_cache', {'mtime': None, 'friends': []}), patch.object(arena, 'clock', return_value=NOW):
    entered = enter()
    assert entered['yT12twnc'][0]['S3rek7hC'] == '2'
    rows = entered['Tr9m32i1'][0]['TI6deE8P'].split(',')
    assert len(rows) == 1 and rows[0].split(':')[7] == '100'
    assert rows[0].split(':')[2:4] == ['100000315', '80']
    # The same identity lends an owned, level-capped replacement outside Arena.
    from revival_friends import catalogue
    companion = catalogue(player.data, NOW)['900000003']['unit']
    assert companion['master_id'] in (100000102, 100000202) and companion['level'] == 1
    req = selection(entered)
    matched = request('RbMatchingRequest', req)
    assert len(matched['DW0rgk3C'][0]['Jc4udh7x'].split(';')) == 1
    request('RbStartRequest', req)
    assert set(player.data['exvius_arena']['active']['members'].values()) == {'100000315'}
    done = request('RbEndRequest', report(req))['g3JFd0y7'][0]
    assert done['42GLsTok'] == '0,100,0,0'
''')

    def test_given_roster_changes_when_arena_projects_then_keep_original_generated_rivals(self):
        self.run_engine('''
import revival_arena as arena
from revival_friends import catalogue
data = copy.deepcopy(player.data)
first = arena.Ladder(data, NOW)
original = [(first.directory.by_id(fid), first.team(first.directory.by_id(fid)))
            for fid in first.directory.ids()]
assert catalogue(data, NOW)
data['roster'] = []
assert catalogue(data, NOW) == {}
later = arena.Ladder(data, NOW)
assert [(later.directory.by_id(fid), later.team(later.directory.by_id(fid)))
        for fid in later.directory.ids()] == original
assert first.standings(0) == later.standings(0)
''')

    def test_given_pre_ladder_pending_battle_when_restarted_then_finish_snapshot_before_migrating_points(self):
        self.run_engine(FLOW + '''
with patch.object(arena, 'clock', return_value=NOW):
    req = selection(enter())
    request('RbMatchingRequest', req)
    request('RbStartRequest', req)
    model = player.data['exvius_arena']
    # The canonical pre-port save contained one neutral-ratio rival and no ladder metadata.
    for key in ('ladder', 'week', 'week_starts', 'week_ends'):
        model.pop(key, None)
    active = model['active']
    active['rival'] = active['rival'].split(';')[0]
    first = next(iter(active['members'].items()))
    active['members'] = {first[0]: first[1]}
    done_req = report(req)
    active.pop('members')
    active.pop('rate')
    model['matched'] = None
    player.dirty = True
    player.save(str(config.state_file))
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    request('RbReStartRequest', req)
    assert player.data == before and config.state_file.read_bytes() == saved
    done = request('RbEndRequest', done_req)['g3JFd0y7'][0]
    assert done['42GLsTok'] == '0,100,0,0'
    enter()
    assert player.data['exvius_arena']['lifetime_points'] == 100
    assert player.data['exvius_arena']['user']['UbQ26oH4'] == '0'
''')
