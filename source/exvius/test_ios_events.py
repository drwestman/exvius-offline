"""BDD for the iOS replay Vortex and exchange shops; no production saves or listeners."""
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
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

    def test_given_first_week_when_selecting_then_include_running_events_and_exclude_future(self):
        rows = [event(100, '2016-12-02'), event(101, '2016-12-01'),
                event(102, '2016-12-16'), event(103, '2017-01-06'),
                event(104, group='permanent')]
        before = copy.deepcopy(rows)
        self.assertEqual({r['area'] for r in self.select(rows).events}, {'100', '102', '104'})
        self.assertEqual(rows, before)
        later = self.select(rows, NOW + timedelta(weeks=1))
        self.assertIn('103', later.areas)
        self.assertNotIn('100', later.areas)

    def test_given_rerun_when_selected_then_date_the_rerun_without_rewriting_the_catalogue(self):
        rows = [event(100, '2016-08-01', runs=['2016-08-01', '2017-01-10'])]
        selected = self.select(rows, NOW + timedelta(weeks=1))
        self.assertEqual(selected.events[0]['release'], '2017-01-10')
        self.assertEqual(selected.events[0]['first_release'], '2016-08-01')
        self.assertEqual(rows[0]['release'], '2016-08-01')

    def test_given_holiday_event_when_its_history_date_arrives_then_wait_for_the_real_holiday(self):
        rows = [event(906, '2016-12-23', name='Christmas event')]
        self.assertFalse(self.select(rows).areas)
        christmas = datetime(2026, 12, 21, 4, tzinfo=timezone.utc)
        selected = self.select(rows, christmas, data=campaign(christmas))
        self.assertEqual(selected.areas, frozenset({'906'}))

    def test_given_ranked_windows_when_overlapping_then_show_only_the_newest_run(self):
        rows = [event(100, name='Ranked', windows=[['2016-12-02', '2016-12-20']]),
                event(101, name='Ranked', windows=[['2016-12-16', '2017-01-08']])]
        self.assertEqual(self.select(rows).areas, frozenset({'101'}))

    def test_given_recurring_and_duplicate_tiles_when_selected_then_rotate_deterministically(self):
        rows = [event(i, name='Recurring ' + str(i)) for i in range(100, 108)]
        rows += [event(200, group='permanent', name='Chamber', art_url='same'),
                 event(201, group='permanent', name='Chamber', art_url='same')]
        first, again = self.select(rows), self.select(rows)
        self.assertEqual(first.areas, again.areas)
        self.assertEqual(len(first.events), 3)
        following = self.select(rows, NOW + timedelta(weeks=1))
        self.assertNotEqual(first.areas & {'200', '201'}, following.areas & {'200', '201'})

    def test_given_finished_history_when_selecting_then_follow_the_weekly_summon_sets(self):
        later = NOW + timedelta(weeks=220)
        banners = [banner(i, f'2017-01-{i:02d}') for i in range(1, 9)]
        selected = self.select([event(100, '2017-01-10'), event(101, '2024-08-22')], later, banners=banners)
        self.assertIn('100', selected.areas)
        self.assertNotIn('101', selected.areas)

    def test_given_closed_event_when_checking_entry_then_preserve_a_pending_battle_only(self):
        row = event(100, '2016-12-16')
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

    def test_given_damaged_history_when_loaded_then_fail_instead_of_opening_all_events(self):
        self.addCleanup(events.history.cache_clear)
        for raw in ('{}', '{"version":2,"runs":{},"windows":{},"added":[]}'):
            events.history.cache_clear()
            with self.subTest(raw=raw), patch.object(Path, 'read_text', return_value=raw):
                with self.assertRaisesRegex(ValueError, 'Invalid pinned event history'):
                    events.history()


class ReplayExchangeBehavior(unittest.TestCase):
    def test_given_leftover_currency_when_event_closes_then_exchange_remains_redeemable(self):
        data = campaign()
        selected = ReplayEventBehavior().select([event(100, '2016-12-16')], NOW + timedelta(weeks=1), data=data)
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
        }) for area, mid in [('100', '1000101'), ('101', '1010101')]))
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
rows = (event(100, '2016-12-16'), event(101, '2017-01-06'))
captured = {'0xkoNP8U': [{'uv60hgDW': '101', 'qo3PECw6': '1010101'},
                         {'uv60hgDW': '1', 'qo3PECw6': '1'}]}
with patch.object(events, 'catalogue', return_value=rows), patch.object(summons, 'clock', return_value=NOW):
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    result = serve_event_gate(captured, EVENT_GATE_CARRIERS[0])
    gates = result['0xkoNP8U']
    assert {r['uv60hgDW'] for r in gates} == {'100', '1'}, gates
    active = next(r for r in gates if r['uv60hgDW'] == '100')
    assert active['VjJQ51uG'] == '2026-11-09 03:00:00', active
    assert active['m8ivD4NX'] == '2026-11-16 02:59:59', active
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
rows = (event(100, '2016-12-16'), event(101, '2017-01-06'))
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

    def test_given_expired_mode_when_starting_then_reject_before_stamina_or_orb_spending(self):
        self.run_engine('''
import revival_events as events
from test_ios_events import event
from exvius_actions_modes import _begin, _Refused
from player_state import mission_row
with patch.object(events, 'catalogue', return_value=(event(100, '2016-12-16'),)), \\
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
with patch.object(events, 'catalogue', return_value=(event(100, '2016-12-16'),)), \\
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
with patch.object(events, 'catalogue', return_value=(event(100, '2016-12-16'),)), \\
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
with patch.object(events, 'catalogue', return_value=(event(100, '2016-12-16'),)), \\
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


if __name__ == '__main__':
    unittest.main()
