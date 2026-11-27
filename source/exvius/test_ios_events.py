"""BDD for the iOS replay Vortex and exchange shops; no production saves or listeners."""
from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import random
import sys
from types import SimpleNamespace
import unittest
import json
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SOURCE), str(SOURCE / 'server')]

from test_ios_summons import campaign, banner, NOW
import revival_summons as summons
import revival_events as events
import revival_exchanges as exchanges


def event(area, release=None, **fields):
    return dict({'area': str(area), 'name': 'Event ' + str(area), 'release': release,
                 'group': 'season1', 'runs': [release] if release else [],
                 'first_dungeon': str(area) + '01', 'first_mission': str(area) + '0101',
                 'dungeons': [str(area) + '01'], 'missions': [str(area) + '0101']}, **fields)


class ReplayEventBehavior(unittest.TestCase):
    def select(self, rows, now=NOW, data=None, banners=()):
        data = campaign() if data is None else data
        selected = summons.plan(data, now, banners=banners, families=set())
        return events.plan(data, now, rows=rows, summons=selected, art={})

    def test_given_calendar_day_when_selecting_then_include_running_events_and_exclude_future(self):
        rows = [event(100, '2016-10-26'), event(101, '2016-10-01'),
                event(102, '2016-11-01'), event(103, '2017-11-15'),
                event(104, group='permanent')]
        before = copy.deepcopy(rows)
        self.assertEqual({r['area'] for r in self.select(rows).events}, {'100', '102', '104'})
        self.assertEqual(rows, before)
        later = self.select(rows, NOW + timedelta(weeks=1))
        self.assertIn('103', later.areas)
        self.assertNotIn('100', later.areas)

    def test_given_rerun_when_selected_then_date_the_rerun_without_rewriting_the_catalogue(self):
        rows = [event(100, '2016-08-01', runs=['2016-08-01', '2017-11-15'])]
        selected = self.select(rows, NOW + timedelta(weeks=1))
        self.assertEqual(selected.events[0]['release'], '2016-08-01')
        self.assertEqual(selected.events[0]['event_windows'][0]['starts_at'], '2026-11-15T00:00:00-05:00')
        self.assertEqual(rows[0]['release'], '2016-08-01')

    def test_given_holiday_event_when_selecting_then_use_recorded_run_dates(self):
        rows = [event(906, '2016-12-23', name='Christmas event')]
        self.assertFalse(self.select(rows).areas)
        christmas = datetime(2026, 12, 31, 12, tzinfo=timezone.utc)
        selected = self.select(rows, christmas, data=campaign(christmas))
        self.assertEqual(selected.areas, frozenset({'906'}))

    def test_given_ranked_windows_when_overlapping_then_keep_distinct_mission_sets(self):
        rows = [event(100, name='Ranked', windows=[['2016-11-01', '2016-11-20']]),
                event(101, name='Ranked', windows=[['2016-11-05', '2016-11-30']])]
        self.assertEqual(self.select(rows).areas, frozenset({'100', '101'}))

    def test_given_recurring_and_duplicate_tiles_when_selected_then_rotate_deterministically(self):
        rows = [event(i, name='Recurring ' + str(i)) for i in range(100, 108)]
        rows += [event(200, group='permanent', name='Chamber', art_url='same'),
                 event(201, group='permanent', name='Chamber', art_url='same')]
        first, again = self.select(rows), self.select(rows)
        self.assertEqual(first.areas, again.areas)
        self.assertEqual(len(first.events), 3)
        following = self.select(rows, NOW + timedelta(weeks=1))
        self.assertNotEqual(first.areas & {'200', '201'}, following.areas & {'200', '201'})

    def test_given_finished_history_when_selecting_then_use_calendar_dates(self):
        later = datetime(2031, 11, 16, 12, tzinfo=timezone.utc)
        banners = [banner(i, f'2017-01-{i:02d}') for i in range(1, 9)]
        selected = self.select([event(100, '2017-11-15'), event(101, '2024-08-22')], later, banners=banners)
        self.assertIn('100', selected.areas)
        self.assertNotIn('101', selected.areas)

    def test_given_closed_event_when_checking_entry_then_preserve_a_pending_battle_only(self):
        row = event(100, '2016-10-26')
        state = campaign()
        selected = self.select([row], NOW + timedelta(weeks=1), data=state)
        mission = {'qo3PECw6': row['first_mission'], 'uv60hgDW': row['area']}
        self.assertFalse(selected.can_enter(state, mission))
        state['exvius_repeat'] = {'attempt': {'mid': row['first_mission'], 'status': 'pending'}}
        self.assertTrue(selected.can_enter(state, mission, resume=True))
        self.assertFalse(selected.can_enter(state, mission))
        state['exvius_repeat']['attempt']['status'] = 'completed'
        self.assertFalse(selected.can_enter(state, mission, resume=True))
        self.assertTrue(selected.can_enter(state, {'qo3PECw6': '1', 'uv60hgDW': '1'}))

    def test_given_mana_clones_when_projecting_any_campaign_then_keep_one_of_each_difficulty(self):
        from revival_update import initialize
        row = dict(next(row for row in events.catalogue() if row['area'] == '708'),
                   release=None, runs=[], group='permanent', held_back=['later', '7080106'])
        original = copy.deepcopy(row)
        for updated in (False, True):
            with self.subTest(updated=updated):
                data = campaign()
                if updated:
                    initialize(data)
                data['exvius_repeat'] = {'attempt': {'mid': '7080106', 'status': 'completed'}}
                data['progress'] = {'cleared_missions': ['7080106'],
                                    'cleared_challenges': {'7080106': {'challenge'}},
                                    'paid_challenges': {'7080106': {'challenge'}}}
                before = copy.deepcopy(data)
                first, again = self.select([row], data=data), self.select([row], data=data)
                self.assertEqual(first.events, again.events)
                self.assertEqual(first.events[0]['missions'],
                                 ['7080101', '7080102', '7080103', '7080104', '7080105'])
                self.assertEqual(first.events[0]['held_back'],
                                 ['later', '7080106', '7080107', '7080108', '7080109', '7080110'])
                self.assertEqual(first.events[0]['first_mission'], '7080101')
                self.assertEqual(data, before)
                self.assertEqual(row, original)

    def test_given_pinned_clone_map_when_projecting_then_filter_every_mapped_area_only(self):
        from revival_update import document, initialize
        catalogue = {row['area']: row for row in events.catalogue()}
        for area, info in document('clone_quests.json')['areas'].items():
            for updated in (False, True):
                with self.subTest(area=area, updated=updated):
                    data = campaign()
                    if updated:
                        initialize(data)
                    row = dict(catalogue[area], group='permanent', windows=[])
                    original = copy.deepcopy(row)
                    result = self.select([row], data=data).events[0]
                    self.assertEqual(set(row['missions']) - set(result['missions']), set(info['hidden']))
                    self.assertTrue(set(info['hidden'].values()) <= set(result['missions']))
                    self.assertEqual(result['missions'], [mid for mid in row['missions'] if mid not in info['hidden']])
                    self.assertEqual(row, original)
        # Equal labels alone never establish that two missions are clones.
        row = event(99999, missions=['9999901', '9999902'], name='Mana Mystery')
        self.assertEqual(self.select([row]).events[0]['missions'], row['missions'])

    def test_given_optional_update_when_filtering_then_keep_other_rules_opt_in(self):
        from revival_update import document, initialize
        rows = [event(711, group='permanent'),
                event(100, group='permanent', missions=['1000101', '1000102'])]
        def documents(name):
            return {'missions': {'1000102': '2099-01-01'}} if name == 'event_quest_dates.json' else document(name)
        with patch('revival_update.document', side_effect=documents):
            old = self.select(rows)
            self.assertEqual(old.areas, frozenset({'711', '100'}))
            self.assertEqual(next(r for r in old.events if r['area'] == '100')['missions'], rows[1]['missions'])
            data = campaign()
            initialize(data)
            updated = self.select(rows, data=data)
            self.assertEqual(updated.areas, frozenset({'100'}))
            self.assertEqual(updated.events[0]['missions'], ['1000101'])
            self.assertEqual(updated.events[0]['held_back'], ['1000102'])

    def test_given_hidden_clone_when_entering_then_refuse_new_entry_but_allow_pending_resume(self):
        row = event(708, group='permanent', missions=['7080101', '7080106'])
        data = campaign()
        selected = self.select([row], data=data)
        clone = {'uv60hgDW': '708', 'qo3PECw6': '7080106'}
        self.assertTrue(selected.can_enter(data, dict(clone, qo3PECw6='7080101')))
        self.assertFalse(selected.can_enter(data, clone, resume=True))
        data['exvius_repeat'] = {'attempt': {'mid': '7080106', 'status': 'pending'}}
        self.assertTrue(selected.can_enter(data, clone, resume=True))
        self.assertFalse(selected.can_enter(data, clone))
        data['exvius_repeat']['attempt']['status'] = 'completed'
        self.assertFalse(selected.can_enter(data, clone, resume=True))

    def test_given_damaged_history_when_loaded_then_fail_instead_of_opening_all_events(self):
        self.addCleanup(events.history.cache_clear)
        for raw in ('{}', '{"version":2,"runs":{},"windows":{},"added":[]}'):
            events.history.cache_clear()
            with self.subTest(raw=raw), patch.object(Path, 'read_text', return_value=raw):
                with self.assertRaisesRegex(ValueError, 'Invalid pinned event history'):
                    events.history()

    def test_given_gate_planner_when_compared_with_full_planner_then_output_and_windows_match(self):
        from revival_update import initialize
        rows = [
            event(100, '2016-10-26'),
            event(101, '2017-11-15'),
            event(200, group='permanent', name='Chamber', art_url='same'),
            event(201, group='permanent', name='Chamber', art_url='same'),
            event(905, group='permanent', name='Cactuar', art_url='cactuar'),
            event(102, group='permanent', name='Cactuar', art_url='cactuar'),
            event(906, '2016-12-23', name='Christmas event'),
            event(708, group='permanent', missions=[str(mid) for mid in range(7080101, 7080111)]),
        ]
        spec = {'0xkoNP8U': [{'uv60hgDW': str(row['area']), 'qo3PECw6': row['first_mission']} for row in rows]}
        christmas = datetime(2026, 12, 31, 12, tzinfo=timezone.utc)
        finished_now = datetime(2031, 11, 16, 12, tzinfo=timezone.utc)
        updated_data = campaign()
        initialize(updated_data)
        cases = [
            ('active', campaign(), NOW),
            ('updated', updated_data, NOW),
            ('holiday', campaign(christmas), christmas),
            ('finished', campaign(), finished_now),
        ]
        for label, data, moment in cases:
            with self.subTest(case=label):
                oracle = events.plan(data, moment, rows=rows, art={})
                gate = events.plan_for_gate(data, moment, rows=rows, art={})
                self.assertEqual(gate.events, oracle.events)
                self.assertEqual(gate.areas, oracle.areas)
                self.assertEqual(gate.known_areas, oracle.known_areas)
                self.assertEqual(
                    json.dumps(gate.gate_windows(spec), sort_keys=True),
                    json.dumps(oracle.gate_windows(spec), sort_keys=True),
                )
                for row in rows:
                    mission = {'uv60hgDW': str(row['area']), 'qo3PECw6': row['first_mission']}
                    self.assertEqual(gate.can_enter(data, mission), oracle.can_enter(data, mission))

    def test_given_active_holiday_with_event_keys_when_serving_gate_source_then_skip_summon_catalogue(self):
        import event_availability as availability
        christmas = datetime(2026, 12, 24, 12, tzinfo=timezone.utc)
        data = campaign(christmas)
        rows = (
            event(906, '2016-12-23', name='Christmas event'),
            event(905, group='permanent', name='Cactuar', art_url='cactuar'),
            event(102, group='permanent', name='Cactuar', art_url='cactuar'),
        )
        player = SimpleNamespace(data=data, switches={}, mode='frozen', dirty=False)
        oracle = events.plan(data, christmas, rows=rows, art={})
        self.assertEqual(oracle.context['holiday'], 'Christmas')
        with patch.object(events, 'catalogue', return_value=rows), \
             patch.object(events, '_art', return_value={}), \
             patch.object(summons, 'clock', return_value=christmas), \
             patch.object(summons, 'plan', side_effect=AssertionError('summons.plan called')), \
             patch.object(summons, 'catalogue', side_effect=AssertionError('summons.catalogue called')), \
             patch.object(summons, '_catalogue_offer_identities',
                          side_effect=AssertionError('_catalogue_offer_identities called')):
            source = availability.ReplayAvailability().gate_source(player)
        self.assertEqual(
            source.facts,
            [(row['area'], row['first_dungeon'], row['first_mission']) for row in oracle.events],
        )
        self.assertEqual(list(source.archive_events), list(oracle.events))
        # Also verify Dependency Inversion via an explicit custom provider collaborator.
        seen_calls = []
        def custom_provider(d, now, event_keys):
            seen_calls.append((d is data, now, sorted(event_keys)))
            return summons.gate_calendar_facts(d, now, event_keys)
        with patch.object(events, 'catalogue', return_value=rows), \
             patch.object(events, '_art', return_value={}), \
             patch.object(summons, 'clock', return_value=christmas):
            injected = availability.ReplayAvailability(facts_provider=custom_provider).gate_source(player)
        self.assertEqual(len(seen_calls), 1)
        self.assertTrue(seen_calls[0][0])
        self.assertEqual(injected.facts, source.facts)

    def test_given_holiday_week_without_event_keys_when_planning_gate_then_fall_back_to_full_context(self):
        christmas = datetime(2026, 12, 24, 12, tzinfo=timezone.utc)
        data = campaign(christmas)
        rows = [
            event(905, group='permanent', name='Cactuar', art_url='cactuar'),
            event(102, group='permanent', name='Cactuar', art_url='cactuar'),
        ]
        self.assertIsNone(summons.gate_calendar_facts(data, christmas, {}))
        oracle = events.plan(data, christmas, rows=rows, art={})
        self.assertEqual(oracle.context['holiday'], 'Christmas')
        fallback_calls = []
        real_event_context = summons.event_context
        def spy_event_context(*args, **kwargs):
            fallback_calls.append(args)
            return real_event_context(*args, **kwargs)
        with patch.object(summons, 'event_context', side_effect=spy_event_context):
            gate = events.plan_for_gate(data, christmas, rows=rows, art={})
        self.assertEqual(len(fallback_calls), 1)
        self.assertEqual(gate.events, oracle.events)
        self.assertEqual(gate.context['holiday'], oracle.context['holiday'])
        self.assertEqual(gate.areas, oracle.areas)

    def test_given_missing_or_malformed_anchor_when_planning_gate_then_preserve_provisional_and_validation(self):
        rows = [event(100, '2016-10-26'), event(104, group='permanent')]
        unanchored = {}
        oracle = events.plan(unanchored, NOW, rows=rows, art={})
        gate = events.plan_for_gate(unanchored, NOW, rows=rows, art={})
        self.assertEqual(gate.events, oracle.events)
        self.assertFalse(gate.can_enter(unanchored, {'uv60hgDW': '100', 'qo3PECw6': '1000101'}))
        self.assertTrue(gate.can_enter(unanchored, {'uv60hgDW': '1', 'qo3PECw6': '1'}))
        self.assertEqual(unanchored, {})

        broken = campaign()
        broken['ios_revival']['replay']['anchor_week'] = 'broken'
        with self.assertRaisesRegex(ValueError, 'Invalid iOS replay anchor'):
            events.plan_for_gate(broken, NOW, rows=rows, art={})

    def test_given_changed_state_or_time_when_repeating_gate_projection_then_never_cache_facts(self):
        from revival_update import initialize
        rows = [
            event(100, '2016-10-26'),
            event(101, '2017-11-15'),
            event(711, group='permanent'),
        ]
        first_data = campaign(NOW)
        shifted_data = campaign(NOW - timedelta(weeks=20))
        updated_data = campaign(NOW)
        initialize(updated_data)
        sequence = [
            (first_data, NOW),
            (shifted_data, NOW),
            (updated_data, NOW),
            (first_data, NOW + timedelta(weeks=1)),
        ]
        for data, moment in sequence:
            gate = events.plan_for_gate(data, moment, rows=rows, art={})
            oracle = events.plan(data, moment, rows=rows, art={})
            self.assertEqual(gate.events, oracle.events)
            self.assertEqual(gate.areas, oracle.areas)

    def test_given_concurrent_gate_queries_when_running_in_parallel_then_each_matches_its_own_oracle(self):
        from revival_update import initialize
        rows = tuple(events.catalogue())
        updated = campaign(NOW)
        initialize(updated)
        inputs = [
            (campaign(NOW), NOW),
            (campaign(NOW), NOW + timedelta(weeks=1)),
            (campaign(NOW - timedelta(weeks=12)), NOW),
            (updated, NOW),
            ({}, NOW),
        ]
        oracles = [events.plan(data, moment, rows=rows) for data, moment in inputs]
        def run_one(item):
            data, moment = item
            return events.plan_for_gate(data, moment, rows=rows)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(run_one, inputs * 3))
        for index, result in enumerate(results):
            oracle = oracles[index % len(inputs)]
            self.assertEqual(result.events, oracle.events)
            self.assertEqual(result.known_areas, oracle.known_areas)


class ReplayExchangeBehavior(unittest.TestCase):
    def test_given_leftover_currency_when_event_closes_then_exchange_remains_redeemable(self):
        data = campaign()
        selected = ReplayEventBehavior().select([event(100, '2016-10-26')], NOW + timedelta(weeks=1), data=data)
        offer = {'event_areas': ['100'], 'cost': [20, '123']}
        self.assertFalse(exchanges.policy(data, events=selected).detail_open(offer))
        data['inventory'] = {'items': [{'item_type': 20, 'item_id': 123, 'count': 1}]}
        self.assertTrue(exchanges.policy(data, events=selected).detail_open(offer))

    def test_given_unreleased_unit_when_filtering_shop_then_preserve_ids_and_hide_it_until_release(self):
        data = campaign()
        raw = shop_fixture()
        before = copy.deepcopy(raw)
        first = exchanges.policy(data, NOW).filter_catalogue(raw)
        self.assertIn('940000000', first[2])
        self.assertNotIn('940000001', first[2])
        later = exchanges.policy(data, NOW + timedelta(weeks=1)).filter_catalogue(raw)
        self.assertIn('940000001', later[2])
        self.assertEqual(raw, before)


def shop_fixture():
    details = [{'3X1gLufw': did} for did in ('850001000', '850002000')]
    offers = {
        '940000000': {'detail': '850001000', 'rewards': [{'kind': 10, 'id': 100000102, 'count': 1}],
                      'cost': (50, '1'), 'price': 500, 'limit': 1, 'monthly': False},
        '940000001': {'detail': '850001000', 'rewards': [{'kind': 10, 'id': 100000315, 'count': 1}],
                      'cost': (50, '1'), 'price': 500, 'limit': 1, 'monthly': False},
        '950000000': {'detail': '850002000', 'rewards': [{'kind': 30, 'id': 0, 'count': 50}],
                      'event_areas': ['100'], 'cost': (20, '106213050'), 'price': 1, 'limit': 1, 'monthly': False},
    }
    products = [{'jPV7Xc4N': pid, '3X1gLufw': offer['detail']} for pid, offer in offers.items()]
    return details, products, offers


class ReplayEventIntegration(unittest.TestCase):
    from test_ios_summons import ReplaySummonIntegration as _Harness
    setUp = _Harness.setUp
    prepared_data = _Harness.prepared_data
    child = _Harness.child
    run_engine = _Harness.run_engine

    def write_masters(self, masters):
        self._Harness.write_masters(self, masters)
        (masters / 'F_FUNCTION_MST.ndjson').write_text(json.dumps({
            'G1nfeht7': 'FUNCTION_REEL_DIMENSION', 'juA0Z4m7': '10005001'}))
        (masters / 'F_SWITCH_MST.ndjson').write_text(json.dumps({
            '8vAYn3IX': '10005001', '5opcUT9t': '100', 'QLfe23bu': '8'}))
        (masters / 'F_MISSION_MST.ndjson').write_text('\n'.join(json.dumps({
            'qo3PECw6': mid, 'uv60hgDW': area, 'U9iHsau3': area + '01', 'Z0EN6jSh': '1',
            '8xi6Xvyk': '0', 'gQR24kST': '1', 'Y4VoF8yu': '1', 'B6kyCQ9M': '5', 'CQN15Hgr': '0',
            '69fVGgcI': '1',
        }) for area, mid in [('100', '1000101'), ('101', '1010101')] +
            [('708', str(mid)) for mid in range(7080101, 7080111)]))
        (masters / 'F_TOWN_STORE_MST.ndjson').write_text(json.dumps({'Z20mNDvL': '980001', 'kaG4xf3I': '5'}))
        (masters / 'F_GACHA_STORE_MST.ndjson').write_text(json.dumps({'Z20mNDvL': '980001', 'X1IuZnj2': '9800001'}))
        (masters / 'F_STORE_ITEM_MST.ndjson').write_text('\n'.join(json.dumps({
            'Z20mNDvL': '980001', 'YWF08vZS': '50', '6uIYE15X': pid,
        }) for pid in ('90001', '90002')))
        (masters / 'F_MEDAL_EXCHANGE_MST.ndjson').write_text('\n'.join(json.dumps({
            'S21FT3L8': pid, 'ak2dhKm3': '106213050', 'Qy5EvcK1': '1',
            '7iJpH5zZ': '10:' + uid + ':1:100', 'kR4n5DxP': '1', 'x0NDnEC9': '2',
        }) for pid, uid in [('90001', '100000102'), ('90002', '100000315')]))

    def test_given_captured_future_gate_when_projecting_then_remove_it_and_keep_views_read_only(self):
        self.run_engine('''
import revival_events as events
from test_ios_events import event
from ffbe_player import serve_event_gate
from ffbe_config import EVENT_GATE_CARRIERS
rows = (event(100, '2016-10-26'), event(101, '2017-11-15'))
captured = {'0xkoNP8U': [{'uv60hgDW': '101', 'qo3PECw6': '1010101'},
                         {'uv60hgDW': '1', 'qo3PECw6': '1'}]}
with patch.object(events, 'catalogue', return_value=rows), patch.object(summons, 'clock', return_value=NOW):
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    result = serve_event_gate(captured, EVENT_GATE_CARRIERS[0])
    gates = result['0xkoNP8U']
    assert {r['uv60hgDW'] for r in gates} == {'100', '1'}, gates
    active = next(r for r in gates if r['uv60hgDW'] == '100')
    assert active['VjJQ51uG'] == '2026-10-26 04:00:00', active
    assert active['m8ivD4NX'] == '2026-11-09 04:59:59', active
    assert player.data == before and config.state_file.read_bytes() == saved
    assert captured['0xkoNP8U'][0]['uv60hgDW'] == '101'
    from event_archive import menu
    assert menu(player)['selected']['ids'] == ['100']
    assert player.data == before
''')

    def test_given_event_rollover_when_encrypted_load_retries_then_resume_pending_and_reject_new_entry(self):
        self.run_engine('''
import revival_events as events
from test_ios_events import event
from exvius_repeat import complete_attempt
rows = (event(100, '2016-10-26'), event(101, '2017-11-15'))
mid = '1000101'
server.State.replies['jnw49dUq@' + mid] = {'an6TB4WS': [{'qo3PECw6': mid, 'gou39JeI': '0'}]}
payload = {'1zTjkp5B': [{'6uIYE15X': mid}]}
with patch.object(events, 'catalogue', return_value=rows), patch.object(summons, 'clock', return_value=NOW):
    assert request('DungeonResourceLoadMstListRequest', payload)
    attempt = copy.deepcopy(player.data['exvius_repeat']['attempt'])
    assert attempt['mid'] == mid and attempt['status'] == 'pending'
with patch.object(events, 'catalogue', return_value=rows), \\
     patch.object(summons, 'clock', return_value=NOW + timedelta(weeks=1)):
    assert request('DungeonResourceLoadMstListRequest', payload)
    assert player.data['exvius_repeat']['attempt'] == attempt
    result = complete_attempt(player, mid, False, [], {}, {})
    assert result['reason'] == 'completed'
    player.save(str(config.state_file))
    before, dirty, saved = copy.deepcopy(player.data), player.dirty, config.state_file.read_bytes()
    assert request('DungeonResourceLoadMstListRequest', payload, allow_empty=True) is None
    assert player.data == before and player.dirty == dirty
    assert config.state_file.read_bytes() == saved
''')

    def test_given_existing_campaign_when_mana_gates_project_then_remove_clones_without_writes(self):
        self.run_engine('''
import revival_events as events
from test_ios_events import event
from ffbe_player import serve_event_gate
from ffbe_config import EVENT_GATE_CARRIERS
player.data.pop('ios_revival_update', None)
player.save(str(config.state_file))
missions = [str(mid) for mid in range(7080101, 7080111)]
rows = (event(708, group='permanent', missions=missions),)
captured = {'0xkoNP8U': [{'uv60hgDW': '708', 'U9iHsau3': '70801', 'qo3PECw6': mid}
                         for mid in missions] + [{'uv60hgDW': '1', 'qo3PECw6': '1'}]}
original = copy.deepcopy(captured)
with patch.object(events, 'catalogue', return_value=rows), patch.object(summons, 'clock', return_value=NOW):
    before, dirty, saved = copy.deepcopy(player.data), player.dirty, config.state_file.read_bytes()
    for carrier in EVENT_GATE_CARRIERS:
        result = serve_event_gate(captured, carrier)
        assert [r['qo3PECw6'] for r in result['0xkoNP8U'] if r['uv60hgDW'] == '708'] == missions[:5]
        assert {'uv60hgDW': '1', 'qo3PECw6': '1'} in result['0xkoNP8U']
    assert captured == original
    assert player.data == before and player.dirty == dirty
    assert config.state_file.read_bytes() == saved
''')

    def test_given_hidden_mana_clone_when_encrypted_load_arrives_then_only_resume_existing_attempt(self):
        self.run_engine('''
import revival_events as events
from test_ios_events import event
from exvius_repeat import begin_attempt, complete_attempt
player.data.pop('ios_revival_update', None)
player.save(str(config.state_file))
mid = '7080106'
rows = (event(708, group='permanent', missions=['7080101', mid]),)
bundle = {'an6TB4WS': [{'qo3PECw6': mid, 'gou39JeI': '0'}]}
server.State.replies['jnw49dUq@' + mid] = bundle
payload = {'1zTjkp5B': [{'6uIYE15X': mid}]}
with patch.object(events, 'catalogue', return_value=rows), patch.object(summons, 'clock', return_value=NOW):
    before, dirty, saved = copy.deepcopy(player.data), player.dirty, config.state_file.read_bytes()
    assert request('DungeonResourceLoadMstListRequest', payload, allow_empty=True) is None
    assert player.data == before and player.dirty == dirty
    assert config.state_file.read_bytes() == saved
    # Model an attempt durably opened before the duplicate filter was deployed.
    begin_attempt(player, mid)
    player.save(str(config.state_file))
    attempt = copy.deepcopy(player.data['exvius_repeat']['attempt'])
    assert request('DungeonResourceLoadMstListRequest', payload)
    assert player.data['exvius_repeat']['attempt'] == attempt
    assert complete_attempt(player, mid, False, [], {}, {})['reason'] == 'completed'
    player.save(str(config.state_file))
    before, dirty, saved = copy.deepcopy(player.data), player.dirty, config.state_file.read_bytes()
    assert request('DungeonResourceLoadMstListRequest', payload, allow_empty=True) is None
    assert player.data == before and player.dirty == dirty
    assert config.state_file.read_bytes() == saved
''')

    def test_given_expired_mode_when_starting_then_reject_before_stamina_or_orb_spending(self):
        self.run_engine('''
import revival_events as events
from test_ios_events import event
from exvius_actions_modes import _begin, _Refused
from player_state import mission_row
with patch.object(events, 'catalogue', return_value=(event(100, '2016-10-26'),)), \\
     patch.object(summons, 'clock', return_value=NOW + timedelta(weeks=1)), \\
     patch.object(player, 'settle_nrg', side_effect=AssertionError('entry debited before eligibility')):
    before, dirty = copy.deepcopy(player.data), player.dirty
    try:
        _begin('survival', {}, mission_row('1000101'), {})
    except _Refused:
        pass
    else:
        raise AssertionError('expired mode accepted')
    assert player.data == before and player.dirty == dirty
''')

    def test_given_encrypted_shop_when_history_advances_then_unreleased_purchase_declines_and_stock_persists(self):
        self.run_engine('''
import revival_events as events
import exvius_shop_catalogue as shops
from test_ios_events import event, shop_fixture
raw = shop_fixture()
def buy(pid):
    return request('GachaSelectExchangeExeRequest', {'4mrD6JuA': [{'jPV7Xc4N': pid, 'Qy5EvcK1': '1'}]})
with patch.object(events, 'catalogue', return_value=(event(100, '2016-10-26'),)), \\
     patch.object(shops, '_catalogue', return_value=raw), patch.object(summons, 'clock', return_value=NOW):
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    listed = request('GachaSelectEntryRequest')
    assert {r['jPV7Xc4N'] for r in listed['TPrh6Ay3']} == {'940000000', '950000000'}, listed
    assert player.data == before and config.state_file.read_bytes() == saved
    with patch.object(player, 'spend_lapis', side_effect=AssertionError('future reward charged')):
        refused = buy('940000001')
    assert '4owH1uT2' not in refused
    assert player.data == before and config.state_file.read_bytes() == saved
    assert '4owH1uT2' in buy('940000000')
    first = copy.deepcopy(player.data)
    assert '4owH1uT2' not in buy('940000000')
    assert player.data == first
    player.grant_item(20, 106213050, 1)
    assert '4owH1uT2' in buy('950000000')
    assert player.item_count(20, 106213050) == 0
with patch.object(events, 'catalogue', return_value=(event(100, '2016-10-26'),)), \\
     patch.object(shops, '_catalogue', return_value=raw), \\
     patch.object(summons, 'clock', return_value=NOW + timedelta(weeks=1)):
    assert '940000001' in shops.catalogue()[2]
    assert '950000000' not in shops.catalogue()[2]
    assert '4owH1uT2' in buy('940000001')
    player.save(str(config.state_file))
    from player_state import PlayerState
    player = server.State.player = PlayerState.load(str(config.state_file), slot=config.slot)
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    assert '4owH1uT2' not in buy('940000000')
    assert player.data == before and config.state_file.read_bytes() == saved
    with patch.object(player, 'spend_item', side_effect=AssertionError('expired shop reached payment')):
        refused = shops.purchase({'4owH1uT2': [{'jPV7Xc4N': 'stale-success'}]},
            {'4mrD6JuA': [{'jPV7Xc4N': '950000000', 'Qy5EvcK1': '1'}]})
    assert '4owH1uT2' not in refused and player.data == before
''')

    def test_given_native_medal_batch_with_future_unit_when_purchasing_then_entire_batch_is_atomic(self):
        self.run_engine('''
import revival_events as events
from test_ios_events import event
from exvius_actions_shops import medal_exchange, archived_store_schedules
player.grant_item(20, 106213050, 3)
with patch.object(events, 'catalogue', return_value=(event(100, '2016-10-26'),)), \\
     patch.object(summons, 'clock', return_value=NOW):
    assert any(row['Z20mNDvL'] == '980001' for row in archived_store_schedules())
    before, dirty = copy.deepcopy(player.data), player.dirty
    medal_exchange({}, {'2d6RAkvh': [{'Z20mNDvL': '980001', 'L2gHC5ta': '90001:1,90002:1'}]})
    assert player.data == before and player.dirty == dirty
    medal_exchange({}, {'2d6RAkvh': [{'Z20mNDvL': '980001', 'L2gHC5ta': '90001:1'}]})
    assert player.item_count(20, 106213050) == 2
''')

    def test_given_older_anchor_without_vortex_flag_when_initializing_then_upgrade_atomically_without_reset(self):
        self.run_engine('''
from revival_campaign import initialize_campaign
anchor = copy.deepcopy(player.data['ios_revival'])
assert 8 in player.switches['100']
player.switches['100'].discard(8)
player.dirty = True
player.save(str(config.state_file))
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
with patch.object(type(player), 'save', return_value=False):
    try:
        initialize_campaign(server.State, config.state_file, now=NOW + timedelta(weeks=3))
    except OSError:
        pass
    else:
        raise AssertionError('failed upgrade was published')
assert server.State.player is player and player.data == before
assert config.state_file.read_bytes() == saved
assert initialize_campaign(server.State, config.state_file, now=NOW + timedelta(weeks=3))
player = server.State.player
assert player.data['ios_revival'] == anchor and 8 in player.switches['100']
saved = config.state_file.read_bytes()
assert not initialize_campaign(server.State, config.state_file)
assert config.state_file.read_bytes() == saved
''')

    def test_given_uninitialized_campaign_when_switches_are_projected_then_clear_captured_flags_without_writes(self):
        self.run_engine('''
from ffbe_player import serve_switches
player.data.pop('ios_revival')
player.switches.clear()
before, dirty = copy.deepcopy(player.data), player.dirty
captured = {'8J1R5PXG': [{'5opcUT9t': '101', 'juA0Z4m7': '111111111111111111111111111111'}]}
result = serve_switches(captured)
assert set(result['8J1R5PXG'][0]['juA0Z4m7']) == {'0'}
assert player.data == before and player.dirty == dirty
assert captured['8J1R5PXG'][0]['juA0Z4m7'].startswith('111')
''')

    def test_given_month_boundary_in_utc_when_eastern_month_has_not_changed_then_keep_stock_receipt(self):
        self.run_engine('''
from exvius_shop_catalogue import receipt_key
offer = {'monthly': True}
with patch.object(summons, 'clock', return_value=datetime(2026, 11, 30, 12, tzinfo=timezone.utc)):
    november = receipt_key('940000000', offer)
with patch.object(summons, 'clock', return_value=datetime(2026, 12, 1, 4, 59, tzinfo=timezone.utc)):
    assert receipt_key('940000000', offer) == november
with patch.object(summons, 'clock', return_value=datetime(2026, 12, 1, 5, tzinfo=timezone.utc)):
    assert receipt_key('940000000', offer) != november
''')

    def test_given_saved_campaign_when_serving_event_gate_read_only_and_restarting_then_parity_and_retry_hold(self):
        self.run_engine('''
import os
import random
import subprocess
import textwrap
import event_availability as availability
import revival_events as events
from test_ios_events import event
from ffbe_player import serve_event_gate
from ffbe_config import EVENT_GATE_CARRIERS, EVENT_GATE_TAG

rows = (event(100, '2016-10-26'), event(101, '2017-11-15'))
mid = '1000101'
server.State.replies['jnw49dUq@' + mid] = {'an6TB4WS': [{'qo3PECw6': mid, 'gou39JeI': '0'}]}
payload = {'1zTjkp5B': [{'6uIYE15X': mid}]}
carrier = {EVENT_GATE_TAG: [{'uv60hgDW': '101', 'qo3PECw6': '1010101'},
                            {'uv60hgDW': '1', 'qo3PECw6': '1'}]}
original_carrier = copy.deepcopy(carrier)

def full_oracle_gate(spec, reply_id):
    def full_gate_source(_self, player_obj):
        revival = events.plan(player_obj.data)
        selected = revival.events
        missions = {m for ev in selected for m in ev['missions']}
        order = {str(r['area']): i for i, r in enumerate(selected)}
        return availability.GateSource(
            [(r['area'], r['first_dungeon'], r['first_mission']) for r in selected], selected,
            serve_when_empty=True, rewrites=True,
            prune=lambda rs: [r for r in rs if str(r.get('uv60hgDW')) not in revival.known_areas or
                              (str(r.get('uv60hgDW')) in revival.areas and str(r.get('qo3PECw6')) in missions)],
            order=lambda rs: sorted(rs, key=lambda r: order.get(str(r.get('uv60hgDW')), len(order))),
            window=lambda sp, chosen: revival.gate_windows(sp))
    with patch.object(availability.ReplayAvailability, 'gate_source', full_gate_source):
        return serve_event_gate(copy.deepcopy(spec), reply_id)

with patch.object(events, 'catalogue', return_value=rows), \
     patch.object(summons, 'clock', return_value=NOW):
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    rng_before = random.getstate()
    with patch.object(type(player), 'save', side_effect=AssertionError('gate query saved')), \
         patch.object(summons, 'plan', side_effect=AssertionError('gate query built summon plan')):
        fast_result = serve_event_gate(copy.deepcopy(carrier), EVENT_GATE_CARRIERS[0])
    assert player.data == before and config.state_file.read_bytes() == saved
    assert random.getstate() == rng_before
    assert carrier == original_carrier
    oracle_result = full_oracle_gate(carrier, EVENT_GATE_CARRIERS[0])
    assert json.dumps(fast_result).encode('utf-8') == json.dumps(oracle_result).encode('utf-8')
    assert request('DungeonResourceLoadMstListRequest', payload)
    attempt = copy.deepcopy(player.data['exvius_repeat']['attempt'])
    assert attempt['mid'] == mid and attempt['status'] == 'pending'
    player.save(str(config.state_file))

engine.close()

restart_script = """
import copy, json, sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
sys.path[:0] = sys.argv[1:4]
from ios_server.config import Configuration
from ios_server.engine import Engine

config = Configuration(Path(sys.argv[4]), Path(sys.argv[5]))
engine = Engine(config)
server = engine.initialize()
from local_game import LocalGame
import ffbe_crypto as crypto
import revival_events as events
import revival_summons as summons
from test_ios_events import event
from test_ios_summons import NOW
from ffbe_player import serve_event_gate
from ffbe_config import EVENT_GATE_CARRIERS, EVENT_GATE_TAG
from exvius_repeat import complete_attempt
try:
    player = server.State.player
    rows = (event(100, '2016-10-26'), event(101, '2017-11-15'))
    mid = '1000101'
    attempt = copy.deepcopy(player.data['exvius_repeat']['attempt'])
    assert attempt['mid'] == mid and attempt['status'] == 'pending'
    server.State.replies['jnw49dUq@' + mid] = {'an6TB4WS': [{'qo3PECw6': mid, 'gou39JeI': '0'}]}
    endpoints = json.loads((Path(sys.argv[2]) / 'endpoints.json').read_text())['by_class']
    endpoint = endpoints['DungeonResourceLoadMstListRequest']
    key = crypto.key16(endpoint['encode_key'])
    envelope = {'TEAYk6R1': {'z5hB3P01': endpoint['request_id'], 'ytHoz4E2': '1', '9K0Pzcpd': '1167'},
                't7n6cVWf': {'qrVcDe48': crypto.cbc_encrypt(key, json.dumps({'1zTjkp5B': [{'6uIYE15X': mid}]}).encode(), double_pad=True)}}
    rollover = NOW + timedelta(weeks=1)
    with patch.object(events, 'catalogue', return_value=rows), \\
         patch.object(summons, 'clock', return_value=rollover), \\
         patch.object(summons, 'plan', side_effect=AssertionError('gate query built summon plan')):
        before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
        gate = serve_event_gate({EVENT_GATE_TAG: []}, EVENT_GATE_CARRIERS[0])
        assert {r['uv60hgDW'] for r in gate[EVENT_GATE_TAG]} == {'101'}
        assert player.data == before and config.state_file.read_bytes() == saved
    with patch.object(events, 'catalogue', return_value=rows), \\
         patch.object(summons, 'clock', return_value=rollover), \\
         patch('revival_daily.clock', return_value=rollover):
        resp = LocalGame.request(engine, 'POST', endpoint['url'], json.dumps(envelope))
        assert resp.status == 200 and json.loads(resp.body)['t7n6cVWf']['qrVcDe48']
        assert player.data['exvius_repeat']['attempt'] == attempt
        assert complete_attempt(player, mid, False, [], {}, {})['reason'] == 'completed'
finally:
    engine.close()
"""
env = {k: v for k, v in os.environ.items() if not k.startswith(('FFBE_', 'EXVIUS_', 'STATE_', 'CDN_', 'OUT_'))}
run = subprocess.run(
    [sys.executable, '-B', '-c', textwrap.dedent(restart_script), sys.argv[1], sys.argv[2], str(Path(sys.argv[1]) / 'exvius'),
     str(config.root), str(config.data)],
    env=env, capture_output=True, text=True, timeout=60)
assert run.returncode == 0, run.stdout[-2000:] + run.stderr
''')


if __name__ == '__main__':
    unittest.main()
