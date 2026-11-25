"""BDD for recorded iOS daily quests and earned-Lapis conversion boundaries."""
import copy
from datetime import datetime, timedelta, timezone
import json
import os
import random
import unittest
from unittest.mock import patch

import test_ios_summons as harness
import revival_daily as daily
import revival_economy as economy

NOW = harness.NOW
SETUP = '''
import revival_daily as daily
import revival_economy as economy
from player_state import PlayerState
from ffbe_config import DQ_ID, DQ_REWARD, DQ_STATUS, DAILY_QUEST_TAG
def select(ids):
    today = daily.day(player.data)[0]
    player.roll_daily_quests(today, ids, ['test'], force=True)
    player.data['daily_quest']['ios'] = daily.snapshot(player.data, ids, today)
    player.save(str(config.state_file))
def complete():
    for qid, q in daily.read(player.data)['quests'].items():
        player.bump_progress(player.daily_progress_key(qid), q['target'], cap=q['target'])
    player.save(str(config.state_file))
def claim(qid):
    return request('DailyQuestClaimRewardRequest', {'vj87UqEd': [{DQ_ID: qid}]})
'''


class DailyPolicyBehavior(unittest.TestCase):
    def data(self):
        data = harness.campaign()
        economy.initialize(data)
        return data

    def test_given_defaults_when_recorded_then_keep_economy_across_environment_changes(self):
        data = self.data()
        before = copy.deepcopy(data)
        with patch.dict(os.environ, {'EXVIUS_LAPIS_MULTIPLIER': '99'}):
            self.assertFalse(economy.initialize(data))
        self.assertEqual(economy.earned(data, 50), 250)
        self.assertEqual(economy.earned(data, -50), -50)
        self.assertEqual(data, before)

    def test_given_invalid_multiplier_when_recorded_then_fail_without_inserting_settings(self):
        for value in ('nan', 'inf', '-1', 'bad'):
            data = harness.campaign()
            before = copy.deepcopy(data)
            with patch.dict(os.environ, {'EXVIUS_LAPIS_MULTIPLIER': value}), self.assertRaises(ValueError):
                economy.initialize(data)
            self.assertEqual(data, before)

    def test_given_custom_catalogue_when_selected_then_offer_five_distinct_actions_and_preserve_rng(self):
        data = self.data()
        before, rng = copy.deepcopy(data), random.getstate()
        ids, pools = daily.choose(data, '2026-11-08')
        defs = {q['id']: q for q in daily.catalogue(data)['quests']}
        self.assertEqual(len(ids), 5)
        self.assertEqual(len({defs[qid]['action'] for qid in ids}), 5)
        self.assertEqual((ids, pools), daily.choose(data, '2026-11-08'))
        self.assertNotEqual(ids, daily.choose(data, '2026-11-09')[0])
        self.assertEqual(random.getstate(), rng)
        self.assertEqual(data, before)

    def test_given_dst_when_counting_down_then_measure_actual_hours_to_saved_local_midnight(self):
        data = self.data()
        for start, hours in ((datetime(2027, 3, 14, 5, tzinfo=timezone.utc), 23),
                             (datetime(2026, 11, 1, 4, tzinfo=timezone.utc), 25)):
            self.assertEqual(daily.day(data, start)[1], hours * 3600)

    def test_given_master_rewards_and_custom_text_when_prepared_then_leave_shared_sources_unchanged(self):
        data = self.data()
        original = [{'dX6cor8j': '50:1:20,23:50:1'}]
        self.assertEqual(economy.transform_master(data, 'F_CHALLENGE_MST', original)[0]['dX6cor8j'], '50:1:100,23:50:1')
        self.assertEqual(original, [{'dX6cor8j': '50:1:20,23:50:1'}])
        texts = daily.text_rows()
        self.assertTrue(any(r['key'] == 'MST_DAILY_QUEST_DETAIL_6900503' for r in texts['F_TEXT_DAILY_QUEST_DETAIL']))

    def test_given_result_reward_wrappers_when_displayed_then_preserve_source_state_and_unit_metadata(self):
        data = self.data()
        raw = '0@50:1:50@0,10:904000105:1:100:1:0:100000050,23:50:1'
        self.assertEqual(economy.display(data, raw),
            '0@50:1:250@0,10:904000105:1:100:1:0:100000050,23:50:1')

    def test_given_dated_bundle_when_replay_changes_then_filter_sale_windows_and_expired_runs(self):
        data = self.data()
        dated = next(b for b in economy.bundles() if b['id'] == '990000115')
        self.assertFalse(economy.bundle_active(data, dated, NOW))
        data['ios_revival']['replay']['settings']['start'] = '2022-04-14'
        self.assertTrue(economy.bundle_active(data, dated, NOW))
        self.assertFalse(economy.bundle_active(data, dated, NOW + timedelta(weeks=1)))
        self.assertFalse(economy.bundle_active(data, dated, NOW + timedelta(weeks=250)))

    def test_given_corrupt_snapshot_or_missing_economy_when_read_then_refuse_without_repair(self):
        data = self.data()
        data['daily_quest'] = {'day': '2026-11-08', 'set': ['6000505'],
            'ios': {'version': 1, 'day': '2026-11-08', 'bonus': 1000, 'quests': {}}}
        before = copy.deepcopy(data)
        with self.assertRaisesRegex(ValueError, 'daily quests'):
            daily.read(data)
        self.assertEqual(data, before)
        del data['ios_economy']
        with self.assertRaisesRegex(ValueError, 'economy'):
            economy.initialize(data)


class DailyEconomyIntegration(unittest.TestCase):
    setUp = harness.ReplaySummonIntegration.setUp
    prepared_data = harness.ReplaySummonIntegration.prepared_data
    child = harness.ReplaySummonIntegration.child
    run_engine = harness.ReplaySummonIntegration.run_engine
    extra_units = [('904000105', 5), ('900020201', 3), ('900020301', 4), ('900020401', 5)]
    extra_items = ('1209001319',)

    def write_masters(self, masters):
        harness.ReplaySummonIntegration.write_masters(self, masters)
        with (masters / 'F_IMPORTANT_ITEM_MST.ndjson').open('a') as source:
            source.write('\n' + json.dumps({'2dfixko3': '260'}))

    def test_given_early_bird_bundle_when_purchased_then_credit_listed_lapis_once_without_multiplier(self):
        self.run_engine(SETUP + '''
from ffbe_player import serve_lapis_shop
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
shown = request('BundleStatusRequest')
offer = next(r for r in shown['fMohhKK8'] if r['EzXXHtTY'] == '990000101')
assert not any(r['EzXXHtTY'] == '990000115' for r in shown['fMohhKK8'])
assert player.data == before and config.state_file.read_bytes() == saved
payload = {'blmGz1EI': [{'EzXXHtTY': '990000101'}]}
request('BundlePurchaseRequest', payload)
assert player.currencies['lapis_free'] == before['currencies']['lapis_free'] - int(offer['AOHRcCC2']) + 5000
assert player.item_count(20, 1209001319) == 1
assert len([u for u in player.data['roster'] if u['master_id'] == '900020401']) == 35
player.data = PlayerState.load(str(config.state_file)).data
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
for bid in ('990000101', '990000115'):
    try:
        serve_lapis_shop({}, 'w6Z9a6tD', json.dumps({'blmGz1EI': [{'EzXXHtTY': bid}]}))
    except ValueError:
        pass
    else:
        raise AssertionError('sold-out or expired bundle accepted')
assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_bundle_save_failure_when_purchasing_then_preserve_wallet_inventory_and_limit(self):
        self.run_engine(SETUP + '''
from ffbe_player import serve_lapis_shop
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
payload = {'blmGz1EI': [{'EzXXHtTY': '990000101'}]}
with patch.object(type(player), 'save', return_value=False):
    try:
        serve_lapis_shop({}, 'w6Z9a6tD', json.dumps(payload))
    except OSError:
        pass
    else:
        raise AssertionError('bundle save failure hidden')
assert server.State.player is player
assert player.data == before and config.state_file.read_bytes() == saved
request('BundlePurchaseRequest', payload)
assert player.data['bundle_purchases']['990000101']['count'] == 1
''')

    def test_given_daily_rollover_save_failure_when_updating_then_preserve_yesterdays_facts(self):
        self.run_engine(SETUP + '''
from revival_daily_commands import synchronize
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
with patch.object(daily, 'clock', return_value=NOW + timedelta(days=1)), patch.object(type(player), 'save', return_value=False):
    try:
        synchronize(server.State, config.state_file)
    except OSError:
        pass
    else:
        raise AssertionError('rollover save failure hidden')
assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_daily_screens_when_read_then_project_frozen_rewards_without_writing(self):
        self.run_engine(SETUP + '''
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
shown = request('DailyQuestUpdateRequest')[DAILY_QUEST_TAG]
assert len(shown) == 5
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
request('SpChallengeEntryRequest')
request('sgExpdQuestInfoRequest')
assert player.data == before and config.state_file.read_bytes() == saved
with patch.object(daily, 'clock', return_value=NOW + timedelta(days=1)):
    request('SpChallengeEntryRequest')
    assert player.data == before and config.state_file.read_bytes() == saved
    request('DailyQuestUpdateRequest')
    assert player.daily_quest_day() != before['daily_quest']['day']
''')

    def test_given_lapis_daily_when_claimed_then_match_display_and_pay_completion_bonus_once(self):
        self.run_engine(SETUP + '''
select(['6000505'])
row = request('DailyQuestUpdateRequest')[DAILY_QUEST_TAG][0]
assert row[DQ_REWARD] == '50:1:750', row
complete()
before = player.currencies['lapis_free']
done = claim('6000505')
assert player.currencies['lapis_free'] == before + 750 + 1000
assert done[DAILY_QUEST_TAG][0][DQ_STATUS] == '2'
player.data = PlayerState.load(str(config.state_file)).data
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
claim('6000505')
request('DailyQuestClaimAllRewardRequest')
assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_incomplete_or_unknown_daily_when_claimed_then_grant_nothing(self):
        self.run_engine(SETUP + '''
select(['6000505'])
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
claim('6000505')
claim('6900503')
claim('unknown')
assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_save_failure_when_claiming_then_preserve_progress_balance_and_retry(self):
        self.run_engine(SETUP + '''
from revival_daily_commands import claim as command
select(['6000505'])
complete()
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
with patch.object(type(player), 'save', return_value=False):
    try:
        command({}, 'Zy8fYJ5e', json.dumps({'vj87UqEd': [{DQ_ID: '6000505'}]}))
    except OSError:
        pass
    else:
        raise AssertionError('daily save failure hidden')
assert server.State.player is player
assert player.data == before and config.state_file.read_bytes() == saved
claim('6000505')
assert player.currencies['lapis_free'] == before['currencies']['lapis_free'] + 1750
''')

    def test_given_custom_reward_when_claimed_then_keep_native_metadata_and_snapshot(self):
        self.run_engine(SETUP + '''
select(['6900402'])
snapshot = copy.deepcopy(daily.read(player.data))
complete()
reward = snapshot['quests']['6900402']['reward']
with patch.dict(__import__('os').environ, {'EXVIUS_LAPIS_MULTIPLIER': '100'}):
    shown = request('DailyQuestUpdateRequest')[DAILY_QUEST_TAG][0]
    before = copy.deepcopy(player.data)
    claim('6900402')
assert daily.read(player.data) == snapshot
assert all(r['count'] >= 0 for r in reward)
if reward[0]['kind'] == 50:
    assert player.currencies['lapis_free'] == before['currencies']['lapis_free'] + reward[0]['count'] + snapshot['bonus']
''')

    def test_given_earned_purchase_and_refund_lapis_when_credited_then_scale_earned_rewards_only(self):
        self.run_engine(SETUP + '''
before = player.currencies['lapis_free']
raw = [{'kind': 50, 'id': 1, 'count': 100}]
assert player._grant_items(raw) == raw
assert player.currencies['lapis_free'] == before + 500
player._grant_items(raw, earned=False)
assert player.currencies['lapis_free'] == before + 600
player.add_currency('lapis_free', 100)
assert player.currencies['lapis_free'] == before + 700
mail = player.deliver_mail('Earned fixture', [(50, 1, 100)])
row = next(r for r in player.mail_rows() if r['ynP26rjD'] == mail['mail_id'])
assert row['7iJpH5zZ'] == '50:1:500'
player.receive_mail(mail['mail_id'])
assert player.currencies['lapis_free'] == before + 1200
''')

    def test_given_successful_and_refused_summons_when_scoring_then_count_only_successes(self):
        self.run_engine(SETUP + '''
select(['6900502'])
offered = banner(9800001, '2016-12-16', purchase_limit=1)
payload = {'5yLD4dYI': [{'X1IuZnj2': offered['id'], 'nqzG3b2v': offered['detail_id'], '2RtVPS3b': '1'}]}
with patch.object(summons, 'catalogue', return_value=(offered,)), patch.object(summons, 'clock', return_value=NOW):
    request('GachaExeRequest', payload)
    assert player.progress_value(player.daily_progress_key('6900502')) == 1
    request('GachaExeRequest', payload)
    assert player.progress_value(player.daily_progress_key('6900502')) == 1
''')

    def test_given_real_gifts_when_retried_then_count_only_new_recipients(self):
        self.run_engine(SETUP + '''
select(['6900501'])
friends = request('FriendListRequest')['56gJBnVh'][:10]
payload = {'WSH38iMI': [{'Utx8P1Qo': '20', '2L0dxwuN': ','.join(r['m3Wghr1j'] + ':10' for r in friends)}]}
request('GiftUpdateRequest', payload)
assert player.progress_value(player.daily_progress_key('6900501')) == 10
request('GiftUpdateRequest', payload)
assert player.progress_value(player.daily_progress_key('6900501')) == 10
''')

    def test_given_failed_completion_bonus_when_claiming_all_then_roll_back_every_reward(self):
        self.run_engine(SETUP + '''
from revival_daily_commands import claim as command
select(['6000505'])
complete()
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
original = type(player)._grant_items
def fail_bonus(candidate, rows, **kwargs):
    if rows and rows[0].get('count') == 1000:
        return []
    return original(candidate, rows, **kwargs)
with patch.object(type(player), '_grant_items', fail_bonus):
    try:
        command({}, 'DCmya9WD', '{}')
    except ValueError:
        pass
    else:
        raise AssertionError('partial completion bonus accepted')
assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_midnight_or_frozen_state_when_claiming_then_do_not_spend_stale_progress(self):
        self.run_engine(SETUP + '''
select(['6000505'])
complete()
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
with patch.object(daily, 'clock', return_value=NOW + timedelta(days=1)):
    claim('6000505')
    assert player.data == before and config.state_file.read_bytes() == saved
for mode in ('frozen', 'ephemeral'):
    player.mode = mode
    claim('6000505')
    assert player.data == before and config.state_file.read_bytes() == saved
player.mode = 'live'
''')

    def test_given_moogle_daily_when_claimed_then_deliver_the_recorded_trust_percentage(self):
        self.run_engine(SETUP + '''
for offset in range(30):
    moment = NOW + timedelta(days=offset)
    with patch.object(daily, 'clock', return_value=moment):
        today = daily.day(player.data)[0]
        snap = daily.snapshot(player.data, ['6900402'], today)
        r = snap['quests']['6900402']['reward'][0]
        if r['kind'] != 10 or r['id'] != 904000105:
            continue
        player.roll_daily_quests(today, ['6900402'], ['test'], force=True)
        player.data['daily_quest']['ios'] = snap
        complete()
        old = {u['instance_id'] for u in player.data['roster']}
        claim('6900402')
        new = next(u for u in player.data['roster'] if u['instance_id'] not in old)
        assert new['affinity_points'] == r['affinity_points']
        assert r['affinity_points'][0] == '100'
        break
else:
    raise AssertionError('no moogle day in the deterministic reward cycle')
''')


if __name__ == '__main__':
    unittest.main()
