"""BDD for iOS weekly/replay delivery and native inbox command persistence."""
import copy
from datetime import date, datetime, timedelta, timezone
import os
import unittest
from unittest.mock import patch

import test_ios_summons as harness
import revival_mail_rewards as rewards

NOW = harness.NOW


class MailRewardPolicyBehavior(unittest.TestCase):
    def data(self):
        data = harness.campaign()
        rewards.initialize(data)
        return data

    def test_given_missing_initialization_when_read_then_offer_no_delivery_and_write_nothing(self):
        data = harness.campaign()
        before = copy.deepcopy(data)
        self.assertEqual(rewards.plan(data, NOW), ())
        self.assertEqual(data, before)

    def test_given_new_campaign_when_configured_then_record_defaults_once(self):
        data = self.data()
        saved = copy.deepcopy(data)
        self.assertEqual(data['ios_mail_rewards']['settings']['weekly_gift'], [[23, 50, 10], [23, 70, 1]])
        with patch.dict(os.environ, {'EXVIUS_WEEKLY_GIFT': '', 'EXVIUS_REPLAY_MAILS': '0'}):
            self.assertFalse(rewards.initialize(data))
        self.assertEqual(data, saved)
        self.assertEqual([m.key for m in rewards.plan(data, NOW)], ['weekly:44'])

    def test_given_history_when_mail_becomes_due_then_use_exclusive_window_end_and_original_day_brackets(self):
        mail = rewards.catalogue()[0]
        data = self.data()
        data['ios_revival']['replay']['settings']['start'] = '2021-01-07'
        self.assertNotIn('replay:' + str(mail['id']), [m.key for m in rewards.plan(data, NOW)])
        later = rewards.plan(data, NOW + timedelta(weeks=1))
        self.assertIn('replay:' + str(mail['id']), [m.key for m in later])
        appreciation = rewards.catalogue()[1]
        self.assertEqual(rewards.items_for(appreciation, date(2020, 9, 3)), ((20, 1209001468, 3),))
        self.assertEqual(rewards.items_for(appreciation, date(2016, 12, 16)), ((20, 1209001468, 15),))

    def test_given_dst_when_rotation_crosses_boundary_then_offer_current_week_only(self):
        data = self.data()
        for before in (datetime(2027, 3, 15, 1, 59, 59, tzinfo=timezone.utc),
                       datetime(2026, 11, 2, 2, 59, 59, tzinfo=timezone.utc)):
            a = rewards.plan(data, before)[0].key
            b = rewards.plan(data, before + timedelta(seconds=1))[0].key
            self.assertEqual(int(b.split(':')[1]), int(a.split(':')[1]) + 1)

    def test_given_corrupt_record_when_read_then_fail_without_repair(self):
        data = self.data()
        data['ios_mail_rewards']['version'] = 99
        before = copy.deepcopy(data)
        with self.assertRaisesRegex(ValueError, 'Invalid iOS mail'):
            rewards.plan(data, NOW)
        self.assertEqual(data, before)

    def test_given_missed_weeks_or_clock_rollback_when_planning_then_offer_only_current_unissued_week(self):
        data = self.data()
        state = data['ios_mail_rewards']
        state.update(weekly_last=44, next_id=rewards.ID_TOP - 1, issued={'weekly:44': str(rewards.ID_TOP)})
        before = copy.deepcopy(data)
        self.assertEqual([m.key for m in rewards.plan(data, NOW + timedelta(weeks=4))], ['weekly:48'])
        self.assertEqual(rewards.plan(data, NOW - timedelta(weeks=1)), ())
        self.assertEqual(data, before)

    def test_given_disabled_or_malformed_gifts_when_configuring_then_honor_disable_and_refuse_bad_rows(self):
        data = harness.campaign()
        with patch.dict(os.environ, {'EXVIUS_WEEKLY_GIFT': '', 'EXVIUS_REPLAY_MAILS': '0'}):
            rewards.initialize(data)
        self.assertEqual(rewards.plan(data, NOW + timedelta(weeks=200)), ())
        for text in ('23:50', '23:50:0', 'bad', '23:50:1,not-a-gift'):
            data = harness.campaign()
            before = copy.deepcopy(data)
            with patch.dict(os.environ, {'EXVIUS_WEEKLY_GIFT': text}), self.assertRaisesRegex(ValueError, 'weekly gift'):
                rewards.initialize(data)
            self.assertEqual(data, before)

    def test_given_damaged_metadata_when_loaded_then_fail_without_silently_disabling_mail(self):
        from pathlib import Path
        self.addCleanup(rewards.catalogue.cache_clear)
        for text in ('{}', '{"mails":[]}', '{"mails":[{"id":1,"date":"bad","title":"Gift"}]}'):
            rewards.catalogue.cache_clear()
            with patch.object(Path, 'read_text', return_value=text), self.assertRaisesRegex(ValueError, 'pinned replay mail'):
                rewards.catalogue()

    def test_given_invalid_issue_ledger_when_read_then_fail_without_resetting_delivery_facts(self):
        for fields in ({'next_id': 'bad'}, {'weekly_last': 44},
                       {'issued': {'weekly:044': '940000000000'}, 'weekly_last': 44, 'next_id': rewards.ID_TOP - 1},
                       {'issued': {'unknown': '940000000000'}},
                       {'issued': {'replay:1': '0940000000000'}, 'next_id': rewards.ID_TOP - 1}):
            data = self.data()
            data['ios_mail_rewards'].update(fields)
            before = copy.deepcopy(data)
            with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, 'Invalid iOS mail'):
                rewards.plan(data, NOW)
            self.assertEqual(data, before)

    def test_given_issued_mail_without_matching_ledger_when_read_then_do_not_backfill_or_reissue(self):
        data = harness.campaign()
        data['mailbox'] = [{'mail_id': '940000000000', 'ios_reward_key': 'weekly:44'}]
        before = copy.deepcopy(data)
        with self.assertRaisesRegex(ValueError, 'delivery ledger'):
            rewards.initialize(data)
        self.assertEqual(data, before)
        data.pop('mailbox')
        rewards.initialize(data)
        data['mailbox'] = before['mailbox']
        with self.assertRaisesRegex(ValueError, 'delivery ledger'):
            rewards.plan(data, NOW)


class MailRewardIntegration(unittest.TestCase):
    setUp = harness.ReplaySummonIntegration.setUp
    prepared_data = harness.ReplaySummonIntegration.prepared_data
    write_masters = harness.ReplaySummonIntegration.write_masters
    child = harness.ReplaySummonIntegration.child
    run_engine = harness.ReplaySummonIntegration.run_engine
    extra_items = ('1209001319', '1209001468', '1209001572', '1209001629')

    def test_given_native_login_when_gift_arrives_then_inbox_queries_do_not_issue_or_credit(self):
        self.run_engine('''
import revival_mail_rewards as rewards
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
box = request('MailListRequest')
weekly = [row for row in box['qja26wHb'] if row['fbcj5Aq9'] == 'Weekly Summon Gift']
assert len(weekly) == 1
assert weekly[0]['7iJpH5zZ'] == '23:50:10,23:70:1'
assert player.item_count(23, 50) == 0 and player.item_count(23, 70) == 0
assert player.data == before and config.state_file.read_bytes() == saved
with patch.object(rewards, 'clock', return_value=NOW + timedelta(weeks=4)):
    request('MailListRequest')
    assert player.data == before and config.state_file.read_bytes() == saved
    refreshed = request('RoutineHomeUpdateRequest')
    assert len([m for m in player.mailbox if m['title'] == 'Weekly Summon Gift']) == 2
    assert int(refreshed['t8TPs6o2'][0]['2BW7YLwg']) == len(player.mailbox)
    assert int(refreshed['t8TPs6o2'][0]['sC84jvZH']) == len(player.mailbox)
''')

    def test_given_native_receipt_when_retried_reloaded_and_deleted_then_never_reissue_or_credit_twice(self):
        self.run_engine('''
from player_state import PlayerState
import revival_mail_rewards as rewards
mail = next(m for m in player.mailbox if m['title'] == 'Weekly Summon Gift')
mid = mail['mail_id']
payload = {'rStH7od8': [{'gSEN0jb7': '1', 'Qe02W7rX': mid + ':2,' + mid + ':2'}]}
request('MailReceiptRequest', payload)
assert player.item_count(23, 50) == 10 and player.item_count(23, 70) == 1
player.data = PlayerState.load(str(config.state_file)).data
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
request('MailReceiptRequest', payload)
assert player.data == before and config.state_file.read_bytes() == saved
request('MailReceiptRequest', {'rStH7od8': [{'gSEN0jb7': '3'}]})
assert mid not in {m['mail_id'] for m in player.mailbox}
with patch.object(rewards, 'clock', return_value=NOW):
    request('RoutineHomeUpdateRequest')
assert mid not in {m['mail_id'] for m in player.mailbox}
with patch.object(rewards, 'clock', return_value=NOW + timedelta(weeks=1)):
    request('RoutineHomeUpdateRequest')
new = next(m for m in player.mailbox if m['title'] == 'Weekly Summon Gift')
assert int(new['mail_id']) < int(mid)
request('MailReceiptRequest', payload)
assert player.item_count(23, 50) == 10
request('MailReceiptRequest', {'rStH7od8': [{'gSEN0jb7': '1', 'Qe02W7rX': new['mail_id'] + ':2'}]})
assert player.item_count(23, 50) == 20 and player.item_count(23, 70) == 2
''')

    def test_given_historical_mail_when_catching_up_then_deliver_all_due_once_with_original_appreciation_counts(self):
        self.run_engine('''
import revival_mail_rewards as rewards
with patch.object(rewards, 'clock', return_value=NOW + timedelta(weeks=120)):
    request('RoutineHomeUpdateRequest')
    letters = [m for m in player.mailbox if str(m.get('ios_reward_key', '')).startswith('replay:')]
    assert len(letters) == 4
    assert [m['items'][0]['count'] for m in letters] == [1, 15, 15, 15]
    assert [m['items'][0]['item_id'] for m in letters] == [1209001319, 1209001468, 1209001572, 1209001629]
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    request('RoutineHomeUpdateRequest')
    assert player.data == before and config.state_file.read_bytes() == saved
    for mail in letters:
        assert player.item_count(20, mail['items'][0]['item_id']) == 0
    ids = ','.join(m['mail_id'] + ':2' for m in letters)
    request('MailReceiptRequest', {'rStH7od8': [{'gSEN0jb7': '1', 'Qe02W7rX': ids}]})
    assert [player.item_count(20, mid) for mid in (1209001319, 1209001468, 1209001572, 1209001629)] == [1, 15, 15, 15]
''')

    def test_given_fixed_and_automatic_mail_when_new_rewards_arrive_then_keep_numeric_ids_distinct(self):
        self.run_engine('''
import revival_mail_rewards as rewards
weekly = next(m for m in player.mailbox if m['title'] == 'Weekly Summon Gift')
player.deliver_mail('Existing ladder', [], mail_id=str(920000000000 + 44))
player.deliver_mail('Existing special login', [], mail_id='930000000001')
automatic = player.deliver_mail('Existing arena', [])
assert int(automatic['mail_id']) > int(weekly['mail_id'])
player.save(str(config.state_file))
with patch.object(rewards, 'clock', return_value=NOW + timedelta(weeks=120)):
    request('RoutineHomeUpdateRequest')
ids = [m['mail_id'] for m in player.mailbox]
assert len(ids) == len(set(ids))
assert next(m for m in player.mailbox if m['mail_id'] == '930000000001')['title'] == 'Existing special login'
issued = player.data['ios_mail_rewards']['issued']
assert int(issued['replay:930000000001']) < int(weekly['mail_id'])
assert issued['replay:930000000001'] != automatic['mail_id']
''')

    def test_given_save_or_delivery_failure_when_syncing_then_preserve_inbox_and_issue_ledger(self):
        self.run_engine('''
from revival_mail_commands import synchronize
future = NOW + timedelta(weeks=120)
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
with patch.object(type(player), 'save', return_value=False):
    try:
        synchronize(server.State, config.state_file, now=future)
    except OSError:
        pass
    else:
        raise AssertionError('delivery save failure hidden')
assert player.data == before and config.state_file.read_bytes() == saved
original = type(player).deliver_mail
calls = []
def fail_second(candidate, *args, **kwargs):
    calls.append(1)
    if len(calls) == 2:
        raise ValueError('injected delivery failure')
    return original(candidate, *args, **kwargs)
with patch.object(type(player), 'deliver_mail', fail_second):
    try:
        synchronize(server.State, config.state_file, now=future)
    except ValueError:
        pass
    else:
        raise AssertionError('partial delivery was accepted')
assert player.data == before and config.state_file.read_bytes() == saved
assert synchronize(server.State, config.state_file, now=future)
assert len([m for m in player.mailbox if str(m.get('ios_reward_key', '')).startswith('replay:')]) == 4
''')

    def test_given_receipt_or_delete_save_failure_when_claiming_then_keep_inventory_and_inbox_authoritative(self):
        self.run_engine('''
from ffbe_player import serve_mail
mail = next(m for m in player.mailbox if m['title'] == 'Weekly Summon Gift')
other = player.deliver_mail('Currency fixture', [(30, 1, 100)])
player.save(str(config.state_file))
payload = {'rStH7od8': [{'gSEN0jb7': '1', 'Qe02W7rX': mail['mail_id'] + ':2,' + other['mail_id'] + ':2'}]}
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
with patch.object(type(player), 'save', return_value=False):
    try:
        serve_mail({}, 'XK7efER9', json.dumps(payload))
    except OSError:
        pass
    else:
        raise AssertionError('receipt save failure hidden')
assert server.State.player is player and player.data == before and config.state_file.read_bytes() == saved
request('MailReceiptRequest', payload)
assert player.item_count(23, 50) == 10 and player.currencies['gil'] == before['currencies']['gil'] + 100
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
delete = {'rStH7od8': [{'gSEN0jb7': '3'}]}
with patch.object(type(player), 'save', return_value=False):
    try:
        serve_mail({}, 'XK7efER9', json.dumps(delete))
    except OSError:
        pass
    else:
        raise AssertionError('delete save failure hidden')
assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_frozen_or_ephemeral_campaign_when_syncing_or_claiming_then_grant_nothing(self):
        self.run_engine('''
from revival_mail_commands import synchronize
mid = next(m['mail_id'] for m in player.mailbox if m['title'] == 'Weekly Summon Gift')
payload = {'rStH7od8': [{'gSEN0jb7': '1', 'Qe02W7rX': mid + ':2'}]}
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
for mode in ('frozen', 'ephemeral'):
    player.mode = mode
    assert not synchronize(server.State, config.state_file, now=NOW + timedelta(weeks=120))
    request('MailReceiptRequest', payload, allow_empty=True)
    assert player.data == before and config.state_file.read_bytes() == saved
player.mode = 'live'
''')

    def test_given_unsupported_attachment_when_syncing_then_record_no_delivery(self):
        self.run_engine('''
from revival_mail_commands import synchronize
player.data['ios_mail_rewards']['settings']['weekly_gift'] = [[23, 50, 10], [20, 999999999, 1]]
player.dirty = True
player.save(str(config.state_file))
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
try:
    synchronize(server.State, config.state_file, now=NOW + timedelta(weeks=1))
except ValueError:
    pass
else:
    raise AssertionError('unsupported gift issued')
assert player.data == before and config.state_file.read_bytes() == saved
# Friend points can be credited internally, but this native mail class cannot display that kind.
player.data['ios_mail_rewards']['settings']['weekly_gift'] = [[51, 1, 1]]
player.dirty = True
player.save(str(config.state_file))
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
try:
    synchronize(server.State, config.state_file, now=NOW + timedelta(weeks=1))
except ValueError:
    pass
else:
    raise AssertionError('invisible native mail attachment issued')
assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_old_campaign_when_initializing_then_backfill_without_restarting_replay_or_friends(self):
        self.run_engine('''
import revival_mail_rewards as rewards
old = copy.deepcopy((player.data['ios_revival'], player.data['exvius_friends']))
player.data.pop('ios_mail_rewards')
player.data['mailbox'] = [m for m in player.mailbox if 'ios_reward_key' not in m]
player.dirty = True
player.save(str(config.state_file))
with patch.object(rewards, 'clock', return_value=NOW + timedelta(weeks=3)):
    request('RoutineHomeUpdateRequest')
    assert 'ios_mail_rewards' not in player.data
    request('InitializeRequest')
player = server.State.player
assert (player.data['ios_revival'], player.data['exvius_friends']) == old
assert player.data['ios_mail_rewards']['weekly_last'] == 47
assert len([m for m in player.mailbox if m['title'] == 'Weekly Summon Gift']) == 1
''')

    def test_given_corrupt_delivery_record_when_diagnosed_then_report_without_repair(self):
        self.run_engine('''
from ios_server.queries import status, doctor, rotation
player.data['ios_mail_rewards']['version'] = 99
player.dirty = True
player.save(str(config.state_file))
saved = config.state_file.read_bytes()
assert 'error' in status(config)
assert not doctor(config)['ok']
try:
    rotation(config, now=NOW)
except ValueError:
    pass
else:
    raise AssertionError('corrupt ledger accepted')
assert config.state_file.read_bytes() == saved
''')


class LegacyMailCompatibility(unittest.TestCase):
    from test_ios_server import IosServerBehavior as _Harness
    setUp = _Harness.setUp
    prepared_data = _Harness.prepared_data
    write_masters = _Harness.write_masters
    child = _Harness.child

    def test_given_legacy_profile_when_listing_claiming_and_deleting_mail_then_keep_existing_contract(self):
        static, _ = self.prepared_data()
        self.write_masters(static / 'mst_decoded')
        result = self.child('''
import sys, copy, json
sys.path[:0] = sys.argv[1:3]
from engine_profile import select_profile
select_profile('legacy')
import ffbe_state as state
from player_state import PlayerState
from ffbe_player import serve_mail
from revival_mail_commands import synchronize_for_reply
from pathlib import Path
player = PlayerState.load('', slot='legacy-mail')
state.State.player = player
mail = player.deliver_mail('Legacy fixture', [(23, 50, 10), (23, 70, 1)])
before = copy.deepcopy(player.data)
listed = serve_mail({}, 'KQHpi0D7', '{}')
assert listed['qja26wHb'][0]['7iJpH5zZ'] == '23:50:10,23:70:1'
assert player.data == before
assert synchronize_for_reply({}, '75fYdNxq', state.State, sys.argv[3]) == {}
assert 'ios_mail_rewards' not in player.data
payload = json.dumps({'rStH7od8': [{'gSEN0jb7': '1', 'Qe02W7rX': mail['mail_id'] + ':2'}]})
serve_mail({}, 'XK7efER9', payload)
assert player.item_count(23, 50) == 10 and player.item_count(23, 70) == 1
before = copy.deepcopy(player.data)
serve_mail({}, 'XK7efER9', payload)
assert player.data == before
serve_mail({}, 'XK7efER9', json.dumps({'rStH7od8': [{'gSEN0jb7': '3'}]}))
assert player.mailbox == []
assert not Path(sys.argv[3]).exists()
''', str(self.config.state_file), env={'FFBE_DATA': str(static)})
        self.assertEqual(result.returncode, 0, result.stdout[-1500:] + result.stderr)
