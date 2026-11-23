"""BDD for annual Vortex availability, independent of the summon replay clock."""
import copy
from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parents[1] / 'server')]
import test_ios_events as event_harness
from test_ios_summons import campaign

event = event_harness.event

NY = ZoneInfo('America/New_York')


class AnnualEventBehavior(unittest.TestCase):
    def select(self, first, last, now, data=None):
        row = event(99990, first, windows=[[first, last]])
        return event_harness.ReplayEventBehavior().select([row], now, data=campaign(now) if data is None else data)

    def test_given_january_run_when_calendar_dates_match_then_open_only_inclusive_days(self):
        for day, expected in ((5, False), (6, True), (19, True), (20, False)):
            with self.subTest(day=day):
                selected = self.select('2017-01-06', '2017-01-19', datetime(2027, 1, day, 12, tzinfo=NY))
                self.assertEqual(bool(selected.events), expected)
        self.assertFalse(self.select('2017-01-06', '2017-01-19', datetime(2026, 11, 16, 12, tzinfo=NY)).events)

    def test_given_active_run_when_projected_then_use_new_york_midnight_as_utc(self):
        selected = self.select('2017-01-06', '2017-01-19', datetime(2027, 1, 10, tzinfo=NY))
        gate = selected.gate_windows({'0xkoNP8U': [{'uv60hgDW': '99990'}]})['0xkoNP8U'][0]
        self.assertEqual(gate['VjJQ51uG'], '2027-01-06 05:00:00')
        self.assertEqual(gate['m8ivD4NX'], '2027-01-20 04:59:59')

    def test_given_different_campaign_ages_when_selecting_then_return_same_events_without_writes(self):
        now = datetime(2027, 1, 10, tzinfo=NY)
        for anchor in (now, now - timedelta(weeks=80)):
            data = campaign(anchor)
            before = copy.deepcopy(data)
            self.assertTrue(self.select('2017-01-06', '2017-01-19', now, data).events)
            self.assertEqual(data, before)

    def test_given_year_crossing_run_when_january_arrives_then_use_previous_december(self):
        chosen = self.select('2017-12-29', '2018-01-11', datetime(2027, 1, 5, tzinfo=NY))
        self.assertEqual(chosen.events[0]['event_windows'], [{
            'starts_at': '2026-12-29T00:00:00-05:00', 'ends_at': '2027-01-12T00:00:00-05:00'}])
        self.assertFalse(self.select('2017-12-29', '2018-01-11', datetime(2027, 1, 12, tzinfo=NY)).events)

    def test_given_leap_day_when_nonleap_year_then_use_february_28(self):
        self.assertTrue(self.select('2024-02-29', '2024-03-13', datetime(2027, 2, 28, tzinfo=NY)).events)
        self.assertFalse(self.select('2024-02-29', '2024-03-13', datetime(2028, 2, 28, tzinfo=NY)).events)
        self.assertTrue(self.select('2024-02-29', '2024-03-13', datetime(2028, 2, 29, tzinfo=NY)).events)

    def test_given_dst_change_when_projecting_then_preserve_local_midnights(self):
        chosen = self.select('2017-03-06', '2017-03-15', datetime(2027, 3, 10, tzinfo=NY))
        from event_calendar import window
        self.assertEqual(window(chosen.events[0]).wire(), ('2027-03-06 05:00:00', '2027-03-16 03:59:59'))

    def test_given_exact_boundaries_when_selecting_then_change_at_midnight(self):
        for moment, expected in ((datetime(2027, 1, 6, tzinfo=NY), True),
                                 (datetime(2027, 1, 6, tzinfo=NY) - timedelta(microseconds=1), False),
                                 (datetime(2027, 1, 20, tzinfo=NY) - timedelta(microseconds=1), True),
                                 (datetime(2027, 1, 20, tzinfo=NY), False)):
            self.assertEqual(bool(self.select('2017-01-06', '2017-01-19', moment).events), expected)

    def test_given_reruns_when_overlapping_then_merge_same_area_without_bridging_gaps(self):
        from event_calendar import select
        row = event(99990, windows=[['2017-01-06', '2017-01-19'], ['2019-01-15', '2019-01-25'],
                                   ['2020-03-01', '2020-03-02']])
        original = copy.deepcopy(row)
        chosen = select([row], datetime(2027, 1, 20, tzinfo=NY))[0]
        self.assertEqual(chosen['event_windows'][0]['ends_at'], '2027-01-26T00:00:00-05:00')
        self.assertFalse(select([row], datetime(2027, 2, 1, tzinfo=NY)))
        self.assertEqual(row, original)

    def test_given_legacy_override_when_projecting_then_apply_annual_dates_and_remove_closed_rows(self):
        from event_calendar import Availability
        from exvius_events import apply_availability
        row = event(99990, windows=[['2017-01-06', '2017-01-19']])
        source = {'0xkoNP8U': [{'uv60hgDW': '99990'}, {'uv60hgDW': '1', 'other': 'keep'}]}
        original = copy.deepcopy(source)
        for permanent in (True, False):
            policy = {'version': 1, 'areas': ['99990'], 'permanent': permanent}
            now = datetime(2027, 1, 10, tzinfo=NY)
            opened = apply_availability(source, policy, now.timestamp(),
                                        availability=Availability.at([row], now))
            self.assertEqual(opened['0xkoNP8U'][0]['m8ivD4NX'], '2027-01-20 04:59:59')
            now = datetime(2027, 11, 16, tzinfo=NY)
            closed = apply_availability(source, policy, now.timestamp(),
                                        availability=Availability.at([row], now))
            self.assertEqual(closed['0xkoNP8U'], [source['0xkoNP8U'][1]])
        self.assertEqual(source, original)

    def test_given_no_snapshot_when_projecting_then_never_read_the_catalogue(self):
        from exvius_events import apply_availability
        source = {'0xkoNP8U': [{'uv60hgDW': '99990'}]}
        with patch('event_archive.document', side_effect=AssertionError('projection fetched')):
            out = apply_availability(source, {'version': 1, 'areas': [], 'permanent': True}, 1000)
        self.assertEqual(out, source)

    def test_given_legacy_guard_when_called_then_require_an_explicit_instant(self):
        from exvius_events import can_enter
        from engine_profile import LEGACY
        with patch('engine_profile.current_profile', return_value=LEGACY):
            with self.assertRaises(TypeError):
                can_enter({}, {'uv60hgDW': '1'})

    def test_given_request_when_guarding_then_clock_is_read_once_per_handler(self):
        import exvius_events
        from engine_profile import LEGACY
        row = event(99990, windows=[['2017-01-06', '2017-01-19']])
        missions = [{'uv60hgDW': '99990', 'qo3PECw6': '1'}, {'uv60hgDW': '99990', 'qo3PECw6': '2'}]
        reads = []
        def tick():
            reads.append(1)
            return datetime(2027, 1, 19, 23, 59, 59, tzinfo=NY)
        with patch('engine_profile.current_profile', return_value=LEGACY), \
             patch('event_calendar.clock', side_effect=tick), \
             patch('event_archive.document', return_value={'events': [row]}):
            moment = exvius_events.request_moment()
            self.assertTrue(all(exvius_events.can_enter({}, m, now=moment) for m in missions))
        self.assertEqual(len(reads), 1)

    def test_given_each_profile_when_resolving_availability_then_pick_its_strategy(self):
        import event_availability as availability
        from engine_profile import IOS_REVIVAL, LEGACY
        with patch('engine_profile.current_profile', return_value=LEGACY):
            self.assertIsInstance(availability.current(), availability.AnnualAvailability)
        with patch('engine_profile.current_profile', return_value=IOS_REVIVAL):
            self.assertIsInstance(availability.current(), availability.ReplayAvailability)

    def test_given_unreadable_legacy_policy_when_serving_gate_then_serve_no_extra_gates(self):
        import ffbe_player
        from engine_profile import LEGACY
        spec = {'0xkoNP8U': [{'uv60hgDW': '1'}]}
        with patch('engine_profile.current_profile', return_value=LEGACY), \
             patch.object(ffbe_player.State, 'player', object()), \
             patch('exvius_events.load_policy', side_effect=ValueError('bad policy')):
            self.assertEqual(ffbe_player.serve_event_gate(spec, ffbe_player.EVENT_GATE_CARRIERS[0]), spec)

    def test_given_closed_event_when_legacy_client_retries_then_allow_only_pending_resume(self):
        from exvius_events import can_enter
        from engine_profile import LEGACY
        row = event(99990, windows=[['2017-01-06', '2017-01-19']])
        mission = {'uv60hgDW': '99990', 'qo3PECw6': row['first_mission']}
        data = {'exvius_repeat': {'attempt': {'mid': row['first_mission'], 'status': 'pending'}}}
        original = copy.deepcopy(data)
        with patch('engine_profile.current_profile', return_value=LEGACY), \
             patch('event_archive.document', return_value={'events': [row]}):
            now = datetime(2027, 1, 20, tzinfo=NY)
            self.assertFalse(can_enter(data, mission, now=now))
            self.assertTrue(can_enter(data, mission, now=now, resume=True))
            self.assertFalse(can_enter({}, mission, now=now, resume=True))
        self.assertEqual(data, original)

    def test_given_closed_legacy_rm_dungeon_when_starting_then_refuse_before_mutation(self):
        import exvius_actions_modes as modes
        from engine_profile import LEGACY
        row = event(99990, windows=[['2017-01-06', '2017-01-19']])
        mission = {'uv60hgDW': '99990', 'qo3PECw6': row['first_mission']}
        player = type('P', (), {'data': {}})()
        closed = datetime(2027, 1, 20, tzinfo=NY)
        with patch('engine_profile.current_profile', return_value=LEGACY), \
             patch('event_archive.document', return_value={'events': [row]}), \
             patch('event_calendar.clock', return_value=closed), \
             patch.object(modes.State, 'player', player), \
             patch.object(modes, '_feature', return_value={}), \
             patch.object(modes, '_node', return_value={'U9iHsau3': '1'}), \
             patch.object(modes, '_missions', return_value=[mission]), \
             patch.object(modes, '_rm_snapshot', side_effect=AssertionError('mutated')), \
             patch.object(modes, '_save', side_effect=AssertionError('saved')):
            with self.assertRaisesRegex(modes._Refused, 'annual dates'):
                modes.rm_dungeon_start.__wrapped__({}, {})

    def test_given_unreadable_event_dates_when_serving_legacy_gate_then_serve_no_extra_gates(self):
        import ffbe_player
        from engine_profile import LEGACY
        spec = {'0xkoNP8U': [{'uv60hgDW': '1'}]}
        with patch('engine_profile.current_profile', return_value=LEGACY), \
             patch.object(ffbe_player.State, 'player', object()), \
             patch('exvius_events.load_policy', return_value={'version': 1, 'areas': [99990], 'permanent': True}), \
             patch('exvius_events.native_gate_dates', side_effect=lambda value: value), \
             patch('ffbe_player._event_area_facts', return_value=[('99990', 'd', 'm')]), \
             patch('event_archive.document', side_effect=ValueError('Damaged revival update document')):
            self.assertEqual(ffbe_player.serve_event_gate(spec, ffbe_player.EVENT_GATE_CARRIERS[0]), spec)

    def test_given_selected_rows_when_mutated_then_catalogue_rows_are_untouched(self):
        from event_calendar import select
        dated = event(99990, windows=[['2017-01-06', '2017-01-19']])
        undated = event(99991, group='permanent')
        before = copy.deepcopy([dated, undated])
        for row in select([dated, undated], datetime(2027, 1, 10, tzinfo=NY)):
            row['name'] = 'changed'
        self.assertEqual([dated, undated], before)

    def test_given_dst_and_permanent_rows_when_selected_then_preserve_windows_and_independent_copies(self):
        from event_calendar import select
        rows = [event(100, '2016-11-01', missions=['1000101']),
                event(104, group='permanent', missions=['1040101'])]
        original = copy.deepcopy(rows)

        selected = select(rows, event_harness.NOW)

        self.assertEqual(selected[0]['event_windows'], [{
            'starts_at': '2026-11-01T00:00:00-04:00',
            'ends_at': '2026-11-15T00:00:00-05:00',
        }])
        self.assertEqual([row['area'] for row in selected], ['100', '104'])
        selected[0]['missions'].append('changed')
        selected[1]['missions'].append('changed')
        self.assertEqual(rows, original)
        repeated = select(rows, event_harness.NOW)
        self.assertEqual(repeated[0]['missions'], original[0]['missions'])
        self.assertEqual(repeated[1]['missions'], original[1]['missions'])

    def test_given_occurrences_when_queried_then_merge_overlapping_windows_and_distinguish_closed_or_permanent(self):
        from event_calendar import EventWindow, occurrences, periods
        dated = event(99990, windows=[['2017-01-06', '2017-01-19'], ['2019-01-15', '2019-01-25']])
        permanent = event(99991, group='permanent')
        start = datetime(2027, 1, 10, tzinfo=NY)
        end = datetime(2027, 1, 21, tzinfo=NY)
        self.assertEqual(occurrences(dated, start, end), (
            EventWindow(datetime(2027, 1, 6, tzinfo=NY), datetime(2027, 1, 26, tzinfo=NY)),
        ))
        self.assertEqual(occurrences(dated, datetime(2027, 2, 1, tzinfo=NY), datetime(2027, 2, 2, tzinfo=NY)), ())
        self.assertTrue(periods(dated))
        self.assertEqual(occurrences(permanent, start, end), ())
        self.assertEqual(periods(permanent), ())

    def test_given_invalid_selection_interval_when_selecting_or_querying_occurrences_then_raise_value_error(self):
        from event_calendar import occurrences, select
        row = event(99990, windows=[['2017-01-06', '2017-01-19']])
        aware = datetime(2027, 1, 10, tzinfo=NY)
        naive = datetime(2027, 1, 10)
        for bad_start, bad_end in ((naive, aware), (aware, naive), (aware, aware), (aware, aware - timedelta(seconds=1))):
            with self.subTest(bad_start=bad_start, bad_end=bad_end):
                with self.assertRaisesRegex(ValueError, 'increasing timezone-aware interval'):
                    occurrences(row, bad_start, bad_end)
                with self.assertRaisesRegex(ValueError, 'increasing timezone-aware interval'):
                    select([], bad_start, until=bad_end)
                with self.assertRaisesRegex(ValueError, 'increasing timezone-aware interval'):
                    select([row], bad_start, until=bad_end)

    def test_given_midweek_event_when_news_is_rendered_then_show_real_window_and_original_release(self):
        import revival_events
        import revival_notices
        from revival_notice_pages import render
        now = datetime(2027, 1, 10, 12, tzinfo=NY)
        data = campaign(now)
        revival_notices.initialize(data)
        row = event(99990, '2017-01-06', windows=[['2017-01-06', '2017-01-19']])
        original = copy.deepcopy(data)
        with patch.object(revival_events, 'catalogue', return_value=(row,)):
            content = revival_notices.summary(data, 0, now)
        self.assertEqual(len(content['events']), 1)
        html = render(content, reward_name=str, unit_name=str)
        self.assertIn('Available 2027-01-06 – 2027-01-19 (New York)', html)
        self.assertIn('Originally 2017-01-06', html)
        self.assertEqual(data, original)

    def test_given_dated_updated_event_when_replay_is_early_then_keep_all_supported_missions(self):
        from revival_update import initialize
        now = datetime(2027, 1, 10, tzinfo=NY)
        data = campaign(now)
        initialize(data)
        self.assertEqual(self.select('2024-01-06', '2024-01-19', now, data).areas, {'99990'})


class AnnualLegacyIntegration(unittest.TestCase):
    from test_ios_summons import ReplaySummonIntegration as _Harness
    setUp = _Harness.setUp
    prepared_data = _Harness.prepared_data
    child = _Harness.child

    def test_given_encrypted_legacy_load_when_event_closes_then_resume_once_and_reject_new_entry(self):
        import json
        static, _ = self.prepared_data()
        self._Harness.write_masters(self, static / 'mst_decoded')
        (static / 'mst_decoded/F_MISSION_MST.ndjson').write_text(json.dumps({
            'qo3PECw6': '999900101', 'uv60hgDW': '99990', 'U9iHsau3': '9999001',
            '8xi6Xvyk': '0', 'gQR24kST': '1', 'Y4VoF8yu': '1', 'B6kyCQ9M': '0', 'CQN15Hgr': '0'}))
        result = self.child('''
import sys, json, copy
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
sys.path[:0] = sys.argv[1:3]
sys.path.insert(0, str(Path(sys.argv[1]) / 'exvius'))
from local_game import LocalGame
game = LocalGame(sys.argv[3], slot='annual-fixture')
server = game.server
player = server.State.player
state_file = Path(sys.argv[3]) / 'state/annual-fixture.json'
from test_ios_events import event
import event_archive, event_calendar, ffbe_crypto as crypto
from exvius_repeat import complete_attempt
from ffbe_player import serve_event_gate
from ffbe_config import EVENT_GATE_CARRIERS
row = event(99990, '2017-01-06', windows=[['2017-01-06','2017-01-19']])
mid = row['first_mission']
server.State.replies['jnw49dUq@' + mid] = {'an6TB4WS': [{'qo3PECw6': mid, 'gou39JeI': '0'}]}
endpoint = json.loads((Path(sys.argv[2]) / 'endpoints.json').read_text())['by_class']['DungeonResourceLoadMstListRequest']
key = crypto.key16(endpoint['encode_key'])
payload = {'sHGC5c4G': [{'6uIYE15X': mid}]}
envelope = {'TEAYk6R1': {'z5hB3P01': endpoint['request_id'], 'ytHoz4E2': '1', '9K0Pzcpd': '1167'},
            't7n6cVWf': {'qrVcDe48': crypto.cbc_encrypt(key, json.dumps(payload).encode(), double_pad=True)}}
def load():
    reply = game.request('POST', endpoint['url'], json.dumps(envelope))
    assert reply.status == 200, (reply.status, reply.body)
    return json.loads(reply.body)['t7n6cVWf']['qrVcDe48']
with patch.object(event_archive, 'document', return_value={'events': [row]}):
    with patch.object(event_calendar, 'clock', return_value=datetime(2027, 1, 6, tzinfo=ZoneInfo('America/New_York'))):
        assert serve_event_gate({}, EVENT_GATE_CARRIERS[0])['0xkoNP8U'][0]['VjJQ51uG'] == '2027-01-06 05:00:00'
        assert load()
        attempt = copy.deepcopy(player.data['exvius_repeat']['attempt'])
    with patch.object(event_calendar, 'clock', return_value=datetime(2027, 1, 20, tzinfo=ZoneInfo('America/New_York'))):
        assert serve_event_gate({'0xkoNP8U': [{'uv60hgDW': '99990'}]}, EVENT_GATE_CARRIERS[0])['0xkoNP8U'] == []
        assert load()
        assert player.data['exvius_repeat']['attempt'] == attempt
        complete_attempt(player, mid, False, [], {}, {})
        player.save(str(state_file))
        before, saved, dirty = copy.deepcopy(player.data), state_file.read_bytes(), player.dirty
        assert not load()
        from exvius_actions_modes import _begin, _Refused
        from player_state import mission_row
        with patch.object(player, 'settle_nrg', side_effect=AssertionError('closed entry reached spending')):
            try:
                _begin('survival', {}, mission_row(mid), {})
            except _Refused:
                pass
            else:
                raise AssertionError('closed event accepted')
        assert player.data == before and player.dirty == dirty
        assert state_file.read_bytes() == saved
''', str(static))
        self.assertEqual(result.returncode, 0, result.stdout[-2000:] + result.stderr)


if __name__ == '__main__':
    unittest.main()
