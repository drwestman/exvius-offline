"""BDD for read-only replay news and durable native notice receipts."""
import copy
from datetime import datetime, timedelta, timezone
import json
import os
import random
import unittest
from unittest.mock import patch

import test_ios_summons as harness
from replay_calendar import rotation_week
import revival_notices as notices

NOW = harness.NOW


class NoticePolicyBehavior(unittest.TestCase):
    def data(self, start=None):
        data = harness.campaign()
        if start:
            data['ios_revival']['replay']['settings']['start'] = start
        notices.initialize(data)
        return data

    def test_given_defaults_when_initialized_then_record_eight_weeks_once(self):
        data = self.data()
        self.assertEqual(notices.settings(data), {'enabled': True, 'weeks': 8})
        before = copy.deepcopy(data)
        with patch.dict(os.environ, {'EXVIUS_REPLAY_NOTICES': '0', 'EXVIUS_REPLAY_NOTICE_WEEKS': '1'}):
            self.assertFalse(notices.initialize(data))
        self.assertEqual(data, before)

    def test_given_invalid_defaults_or_saved_settings_when_read_then_fail_without_repair(self):
        for value in ('bad', '0', '53'):
            data = harness.campaign()
            before = copy.deepcopy(data)
            with patch.dict(os.environ, {'EXVIUS_REPLAY_NOTICE_WEEKS': value}), self.assertRaises(ValueError):
                notices.initialize(data)
            self.assertEqual(data, before)
        for value in ({}, None, {'version': 2, 'settings': {'enabled': True, 'weeks': 8}}):
            data = self.data()
            data[notices.STATE_KEY] = value
            before = copy.deepcopy(data)
            with self.assertRaisesRegex(ValueError, 'notice'):
                notices.initialize(data)
            self.assertEqual(data, before)

    def test_given_retention_when_listing_then_keep_current_and_seven_previous_identities(self):
        data = self.data()
        later = NOW + timedelta(weeks=10)
        self.assertEqual(notices.indices(data, later), tuple(range(3, 11)))
        self.assertEqual(notices.identity(data, 0, later)[0], str(notices.NOTICE_ID_BASE))
        self.assertIsNone(notices.identity(data, -1, later))
        self.assertIsNone(notices.identity(data, 11, later))
        self.assertEqual(notices.indices({}, later), ())
        self.assertEqual(notices.indices(data, NOW - timedelta(weeks=1)), ())
        data[notices.STATE_KEY]['settings']['enabled'] = False
        self.assertEqual(notices.indices(data, later), ())

    def test_given_dst_and_new_year_when_identifying_then_keep_local_rollover_and_utc_wire_dates(self):
        data = self.data()
        for start, seconds in ((datetime(2027, 3, 8, 3, tzinfo=timezone.utc), 167 * 3600),
                               (datetime(2027, 11, 1, 2, tzinfo=timezone.utc), 169 * 3600)):
            index = rotation_week(start).number - data['ios_revival']['replay']['anchor_week']
            row = notices.native_row(data, index, {'caption': 'Week'}, now=start)
            begin = datetime.strptime(row['o6n5aQ8C'], '%Y-%m-%d %H:%M:%S')
            end = datetime.strptime(row['9miE75sp'], '%Y-%m-%d %H:%M:%S')
            self.assertEqual(int((end - begin).total_seconds()), seconds)
        jan = datetime(2027, 1, 4, 3, tzinfo=timezone.utc)
        index = rotation_week(jan).number - data['ios_revival']['replay']['anchor_week']
        row = notices.native_row(data, index, {'caption': 'Week'}, now=jan)
        self.assertEqual(row['1d8R5ajV'], '2027-01-04 03:00:00')

    def test_given_selected_catalogues_when_summarizing_then_share_deals_events_and_exclusive_dates(self):
        data = self.data()
        banners = [harness.banner(1, '2016-12-16', name='Opening'),
                   harness.banner(2, '2016-12-23', name='Step Deal', deal=True, steps=[{'cost': {'kind': 'lapis', 'amount': 1000}}]),
                   harness.banner(3, permanent={'from': '2016-12-20'}, name='Dated permanent'),
                   harness.banner(4, '2017-01-06', name='Future')]
        with patch.object(harness.summons, 'catalogue', return_value=banners):
            summary = notices.summary(data, 0, NOW)
        self.assertEqual([b['name'] for group in summary['summons'] for b in group['banners']], ['Opening'])
        self.assertEqual({b['name'] for b in summary['deals']}, {'Step Deal', 'Dated permanent'})
        self.assertEqual((summary['from'], summary['to']), ('2016-12-16', '2017-01-05'))

    def test_given_dated_bundles_and_mail_when_history_reaches_them_then_announce_without_delivering(self):
        import revival_mail_rewards as mail
        data = self.data('2022-06-23')
        mail.initialize(data)
        before, rng = copy.deepcopy(data), random.getstate()
        summary = notices.summary(data, 0, NOW)
        self.assertIn('990000117', {b['id'] for b in summary['bundles']})
        self.assertIn('6th Anniversary Player Appreciation Tickets', {m['title'] for m in summary['mails']})
        self.assertEqual(data, before)
        self.assertEqual(random.getstate(), rng)

    def test_given_corrupt_read_ledger_when_projected_then_report_without_reset(self):
        for ledger in ({'read': ['880000'], 'index': {'880000': ['2026', 65536]}},
                       {'read': '880000', 'index': {}}, {'read': [], 'index': {'x': ['bad', 2]}}):
            data = self.data()
            data['notices'] = ledger
            before = copy.deepcopy(data)
            with self.assertRaisesRegex(ValueError, 'notice'):
                notices.project({}, data)
            self.assertEqual(data, before)

    def test_given_finished_history_when_projected_then_share_rotating_summon_selection(self):
        data = self.data()
        moment = NOW + timedelta(weeks=220)
        summary = notices.summary(data, 220, moment)
        selected = harness.summons.plan(data, moment)
        self.assertTrue(summary['finished'])
        self.assertEqual({b['id'] for group in summary['summons'] for b in group['banners']}
                         | {b['id'] for b in summary['deals']},
                         {bid for _key, ids in selected.sets for bid in ids})

    def test_given_html_and_unsafe_art_when_rendered_then_escape_text_and_keep_images_local(self):
        from revival_notice_pages import render, _image, deal_terms
        data = self.data()
        content = notices.summary(data, 0, NOW)
        content['summons'] = [{'banners': [harness.banner(1, name='<script>bad()</script>',
            released='2016-12-16', art={'banner': 'https://outside.example/art.png'})]}]
        content.update(deals=[], bundles=[], mails=[], events=[])
        html = render(content, reward_name=lambda row: str(row['id']), unit_name=str)
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('outside.example', html)
        self.assertEqual(_image('summon', '../private.png'), '')
        self.assertIn('/banner/en/sd/static_banner/gacha/main/Gacha%20One.png', _image('summon', 'Gacha One.png'))
        terms = deal_terms({'draws': 11, 'cost': {'kind': 'lapis', 'amount': 5000},
            'guarantee': {'rarity': 7}, 'resummon': 3, 'bonus_choice': [{}]}, str, str)
        self.assertIn('10+1 summons for 5,000 Lapis', terms)
        self.assertIn('NV guaranteed', terms)
        self.assertIn('3 free re-summons', terms)

    def test_given_saved_receipt_when_static_index_changes_then_preserve_recorded_mask(self):
        data = self.data()
        data['notices'] = {'index': {'102': ['2026', 5]}, 'read': ['102']}
        spec = {'3BI1xSGW': [{'td06MKEX': '102', '1d8R5ajV': '2027-01-01', 'QLfe23bu': '99'}]}
        self.assertEqual(notices.project(spec, data)['Z53gL0RU'], [{'Gs6BT8n5': '2026', 'goAiX84L': '04'}])

    def test_given_captured_read_flags_when_campaign_has_none_then_clear_the_wire_copy_only(self):
        data = self.data()
        spec = {'Z53gL0RU': [{'Gs6BT8n5': '2024', 'goAiX84L': 'f'}]}
        before = copy.deepcopy(spec)
        self.assertEqual(notices.project(spec, data)['Z53gL0RU'], [])
        self.assertEqual(spec, before)


SETUP = '''
import revival_notices as notices
from player_state import PlayerState
from local_game import LocalGame
def news(moment=NOW):
    with patch.object(notices, 'clock', return_value=moment):
        return request('NoticeUpdateRequest')
def mark(ids, moment=NOW):
    with patch.object(notices, 'clock', return_value=moment):
        return request('NoticeReadUpdateRequest', {'p4U2NosZ': [{'goAiX84L': ids}]})
'''


class NoticeIntegration(unittest.TestCase):
    setUp = harness.ReplaySummonIntegration.setUp
    prepared_data = harness.ReplaySummonIntegration.prepared_data
    write_masters = harness.ReplaySummonIntegration.write_masters
    child = harness.ReplaySummonIntegration.child
    run_engine = harness.ReplaySummonIntegration.run_engine

    def test_given_encrypted_news_and_pages_when_opened_then_do_not_change_campaign_or_save(self):
        self.run_engine(SETUP + '''
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
result = news()
row = next(r for r in result[notices.TAG] if r['td06MKEX'] == '880000')
assert row['QLfe23bu'] == '500'
assert row['1X65WPLU'] == 'https://v900-lapis.gumi.sg/exvius/notices/0.html'
with patch.object(notices, 'clock', return_value=NOW):
    page = LocalGame.request(engine, 'GET', '/exvius/notices/0.html')
    head = LocalGame.request(engine, 'HEAD', '/exvius/notices/0.html')
assert page.status == head.status == 200
assert not head.body and head.headers['Content-Length'] == str(len(page.body))
assert b'Global history' in page.body and b'New Summons' in page.body
assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_read_receipt_when_retried_after_reload_then_keep_native_mask_without_extra_writes(self):
        self.run_engine(SETUP + '''
news()
result = mark('880000,880000,9999999999')
mask = result['Z53gL0RU']
assert mask[0]['Gs6BT8n5'] == '2026' and mask[0]['goAiX84L'].endswith('8')
assert player.data['notices']['read'] == ['880000']
player.data = PlayerState.load(str(config.state_file)).data
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
assert mark('880000')['Z53gL0RU'] == mask
assert news()['Z53gL0RU'] == mask
from exvius_actions import notice_state
assert notice_state({'LhVz6aD2': []}, {}, 'X07iYtp5')['Z53gL0RU'] == mask
assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_receipt_save_failure_when_marking_then_preserve_previous_read_state(self):
        self.run_engine(SETUP + '''
from exvius_actions import notice_state
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
with patch.object(notices, 'clock', return_value=NOW), patch.object(type(player), 'save', return_value=False):
    try:
        notice_state({}, {'p4U2NosZ': [{'goAiX84L': '880000'}]}, 'pC3a2JWU')
    except OSError:
        pass
    else:
        raise AssertionError('receipt save failure hidden')
assert player.data == before and config.state_file.read_bytes() == saved
mark('880000')
assert player.data['notices']['read'] == ['880000']
''')

    def test_given_receipt_projection_failure_when_marking_then_do_not_commit_partial_receipts(self):
        self.run_engine(SETUP + '''
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
with patch.object(notices, 'project', side_effect=ValueError('projection failed')):
    try:
        mark('880000')
    except ValueError as exc:
        assert str(exc) == 'projection failed'
    else:
        raise AssertionError('receipt projection failure hidden')
assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_rollover_when_list_changes_then_old_page_and_read_mask_remain_available(self):
        self.run_engine(SETUP + '''
marked = mark('880000')['Z53gL0RU']
later = NOW + timedelta(weeks=10)
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
rows = news(later)[notices.TAG]
assert {r['td06MKEX'] for r in rows} == {str(880000 + i) for i in range(3, 11)}
with patch.object(notices, 'clock', return_value=later):
    assert LocalGame.request(engine, 'GET', '/exvius/notices/0.html').status == 200
    assert LocalGame.request(engine, 'GET', '/exvius/notices/11.html').status == 404
assert news(later)['Z53gL0RU'] == marked
assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_static_notices_when_read_then_keep_their_native_identity_beside_replay_rows(self):
        self.run_engine(SETUP + '''
from exvius_actions import notice_state
static = {'3BI1xSGW': [{'td06MKEX': '102', '1d8R5ajV': '2026-11-04', 'QLfe23bu': '5'}]}
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
notice_state(copy.deepcopy(static), {}, 'CQ4jTm2F')
assert player.data == before and config.state_file.read_bytes() == saved
with patch.object(notices, 'clock', return_value=NOW):
    out = notice_state(static, {'p4U2NosZ': [{'goAiX84L': '102,880000'}]}, 'pC3a2JWU')
assert out['Z53gL0RU'][0]['goAiX84L'].startswith('04')
assert out['Z53gL0RU'][0]['goAiX84L'].endswith('8')
assert static['3BI1xSGW'][0]['td06MKEX'] == '102'
''')

    def test_given_unavailable_or_nonpersistent_notices_when_marked_then_do_not_record_unknown_ids(self):
        self.run_engine(SETUP + '''
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
mark('880001,9999999999999999999999999999,bad,-1')
assert player.data == before and config.state_file.read_bytes() == saved
for mode in ('frozen', 'ephemeral'):
    player.mode = mode
    mark('880000')
    assert player.data == before and config.state_file.read_bytes() == saved
player.mode = 'live'
import ffbe_state as runtime
with patch.object(runtime, 'STATE_PERSIST', False):
    try:
        mark('880000')
    except ValueError:
        pass
    else:
        raise AssertionError('nonpersistent receipt accepted')
assert player.data == before and config.state_file.read_bytes() == saved
player.data[notices.STATE_KEY]['settings']['enabled'] = False
player.save(str(config.state_file))
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
assert not any(r['td06MKEX'] == '880000' for r in news().get(notices.TAG, []))
mark('880000')
with patch.object(notices, 'clock', return_value=NOW):
    assert LocalGame.request(engine, 'GET', '/exvius/notices/0.html').status == 404
assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_legacy_profile_when_notices_are_read_then_retain_original_masks_and_indexing(self):
        static, _ = self.prepared_data()
        self.write_masters(static / 'mst_decoded')
        result = self.child('''
import sys
sys.path[:0] = sys.argv[1:3]
from pathlib import Path
from ffbe_state import State
from player_state import PlayerState
from exvius_actions import notice_state
from engine_profile import current_profile
assert current_profile().name == 'legacy'
State.player = PlayerState.load('')
notice_state({'3BI1xSGW': [{'td06MKEX': '102', '1d8R5ajV': '2026-11-04', 'QLfe23bu': '5'}]}, {}, 'CQ4jTm2F')
assert '102' in State.player.data['notices']['index']
out = notice_state({}, {'p4U2NosZ': [{'goAiX84L': '102'}]}, 'pC3a2JWU')
assert out['Z53gL0RU'] == [{'Gs6BT8n5': '2026', 'goAiX84L': '04'}]
assert State.player.save(sys.argv[3])
State.player = PlayerState.load(sys.argv[3])
assert notice_state({'LhVz6aD2': []}, {}, 'X07iYtp5')['Z53gL0RU'] == out['Z53gL0RU']
''', str(self.root / 'legacy.json'), env={'FFBE_DATA': str(static)})
        self.assertEqual(result.returncode, 0, result.stdout[-1000:] + result.stderr)

    def test_given_old_campaign_when_initialization_backfills_notices_then_keep_anchor_and_receipts(self):
        self.run_engine(SETUP + '''
from revival_campaign import initialize_campaign
mark('880000')
del player.data[notices.STATE_KEY]
player.save(str(config.state_file))
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
with patch.object(type(player), 'save', return_value=False):
    try:
        initialize_campaign(server.State, config.state_file)
    except OSError:
        pass
    else:
        raise AssertionError('notice backfill failure hidden')
assert player.data == before and config.state_file.read_bytes() == saved
assert initialize_campaign(server.State, config.state_file)
player = server.State.player
assert player.data['ios_revival'] == before['ios_revival']
assert player.data['notices'] == before['notices']
''')

    def test_given_corrupt_notice_state_when_diagnosed_then_preserve_bytes_and_report_error(self):
        self.run_engine(SETUP + '''
from ios_server.queries import status, doctor
player.data['notices'] = {'read': [], 'index': {'102': ['2026', 999999999]}}
player.save(str(config.state_file))
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
assert 'notice' in status(config)['error']
assert not doctor(config)['ok']
assert player.data == before and config.state_file.read_bytes() == saved
''')


if __name__ == '__main__':
    unittest.main()
