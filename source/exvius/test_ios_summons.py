"""BDD for the iOS replay catalogue, pool rules and encrypted summon boundary."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SOURCE), str(SOURCE / 'server')]

from engine_profile import IOS_REVIVAL
from replay_calendar import new_anchor
import revival_summons as summons

NOW = datetime(2026, 11, 9, 3, tzinfo=timezone.utc)


def campaign(now=NOW):
    return {'ios_revival': {'version': 1, 'replay': new_anchor(now, IOS_REVIVAL.replay)}}


def banner(bid, release=None, **fields):
    return dict({'id': str(bid), 'detail_id': str(bid) + '1', 'name': 'Banner ' + str(bid),
                 'release': release, 'art': {'banner': 'art_' + str(bid)},
                 'cost': {'kind': 'lapis', 'amount': 500}, 'draws': 1,
                 'pool': [{'unit_id': '100000102', 'rarity': 2, 'rate': 1}]}, **fields)


class ReplaySummonBehavior(unittest.TestCase):
    def test_given_historical_window_when_listing_then_include_sets_and_hide_future_and_jp_only(self):
        banners = [banner(1, '2016-12-16'), banner(2, '2017-01-06'),
                   banner(3, '2016-12-30', source='translated-jp-calendar'),
                   banner(4, '2016-12-23'), banner(5, name='Rare Summon'),
                   banner(6, name='NV EXVIUS Summon', permanent=True)]
        plan = summons.plan(campaign(), NOW, banners=banners, families={'6'})
        self.assertEqual(set(plan.ids), {'1', '4', '5'})
        self.assertEqual(plan.window['to'], '2017-01-06')
        after = summons.plan(campaign(), NOW + timedelta(weeks=1), banners=banners, families={'6'})
        self.assertIn('2', after.ids)
        self.assertNotIn('1', after.ids)

    def test_given_missing_anchor_when_previewed_then_use_provisional_week_without_mutation(self):
        data = {}
        plan = summons.plan(data, NOW)
        self.assertFalse(plan.anchored)
        self.assertTrue(plan.ids)
        self.assertEqual(data, {})
        future = summons.rotation(data, NOW, 3)
        self.assertFalse(future['anchored'])
        self.assertEqual([w['index'] for w in future['windows']], [0, 1, 2])
        self.assertEqual(future['windows'][1]['from'], '2017-01-06')

    def test_given_corrupt_anchor_when_selecting_then_fail_instead_of_resetting_history(self):
        data = campaign()
        data['ios_revival']['replay']['anchor_week'] = 'broken'
        with self.assertRaisesRegex(ValueError, 'Invalid iOS replay anchor'):
            summons.plan(data, NOW)

    def test_given_calendar_alias_when_selecting_then_publish_replacement_once(self):
        banners = [banner(1, '2016-12-16'), banner(2, '2016-12-16', alias_ids=['1'])]
        plan = summons.plan(campaign(), NOW, banners=banners, families=set())
        self.assertEqual(plan.ids, ('2',))

    def test_given_dated_permanent_when_replay_overlaps_then_open_only_its_historical_period(self):
        banners = [banner(1, permanent={'from': '2016-12-20', 'until': '2017-01-02'}),
                   banner(2, permanent={'from': '2020-01-01'})]
        self.assertEqual(summons.plan(campaign(), NOW, banners=banners, families=set()).ids, ('1',))
        self.assertNotIn('1', summons.plan(campaign(), NOW + timedelta(weeks=1),
                                        banners=banners, families=set()).ids)

    def test_given_christmas_ahead_of_history_when_holiday_week_then_keep_featured_units_only(self):
        christmas = datetime(2026, 12, 21, 4, tzinfo=timezone.utc)
        banners = [banner(1, '2016-12-23', name='Christmas summon',
                          community={'unit_ids': ['100000315']})]
        earlier = summons.plan(campaign(christmas), christmas - timedelta(weeks=3),
                               banners=banners, families=set())
        self.assertFalse(earlier.ids)
        selected = summons.plan(campaign(christmas), christmas, banners=banners, families=set())
        self.assertEqual(selected.holiday, 'Christmas')
        self.assertEqual(selected.ids, ('1',))
        configured = selected.configure(banners[0])
        self.assertTrue(summons.unit_allowed(configured, '100000315'))
        self.assertFalse(summons.unit_allowed(configured, '100000337'))

    def test_given_holiday_years_ahead_when_horizon_too_far_then_do_not_skip_to_powerful_units(self):
        christmas = datetime(2026, 12, 21, 4, tzinfo=timezone.utc)
        banners = [banner(1, '2021-12-23', name='Christmas summon')]
        plan = summons.plan(campaign(christmas), christmas, banners=banners, families=set())
        self.assertFalse(plan.ids)

    def test_given_one_off_and_unlimited_tickets_when_filtering_then_apply_ticket_exceptions(self):
        plan = summons.plan(campaign(), NOW)
        one_off = plan.configure(banner('9200107'))
        plain_sp = plan.configure(banner('9200106'))
        unlimited = next(b for b in summons.catalogue() if str(b['id']) == '9200109')
        self.assertTrue(summons.unit_allowed(one_off, '100000337'))
        self.assertFalse(summons.unit_allowed(plain_sp, '100000337'))
        self.assertFalse(summons.unit_allowed(plan.configure(unlimited), '100000337'))

    def test_given_finished_history_when_previewing_then_use_repeatable_normal_rotation(self):
        later = NOW + timedelta(weeks=220)
        banners = [banner(i, f'2017-01-{i:02d}') for i in range(1, 9)]
        banners += [banner(9, '2017-02-01', steps=[{}]), banner(10, name='Rare Summon')]
        first = summons.plan(campaign(), later, banners=banners, families=set())
        second = summons.plan(campaign(), later, banners=banners, families=set())
        self.assertTrue(first.finished)
        self.assertEqual(first.ids, second.ids)
        self.assertEqual(len(first.sets), 3)  # One special and two featured release sets.
        self.assertIn('10', first.ids)
        self.assertTrue(summons.unit_allowed(first.configure(banners[0]), '100000337'))

    def test_given_saved_settings_when_process_defaults_change_then_use_recorded_pace(self):
        data = campaign()
        data['ios_revival']['replay']['settings']['initial_pace'] = 1
        plan = summons.plan(data, NOW)
        self.assertEqual(plan.window['to'], '2016-12-23')

    def test_given_damaged_release_metadata_when_policy_loads_then_fail_without_opening_future_pools(self):
        self.addCleanup(summons.unit_dates.cache_clear)
        for raw in ('{}', '{"units":{}}', '{"units":{"123":"bad-date"}}'):
            summons.unit_dates.cache_clear()
            with self.subTest(raw=raw), patch.object(Path, 'read_text', return_value=raw):
                with self.assertRaisesRegex(ValueError, 'Invalid pinned unit-release metadata'):
                    summons.unit_dates()


class ReplaySummonIntegration(unittest.TestCase):
    # Reuse the foundation's synthetic-data and isolated-process harness, without
    # inheriting/re-running its unrelated scenarios.
    from test_ios_server import IosServerBehavior as _Harness
    setUp = _Harness.setUp
    prepared_data = _Harness.prepared_data
    write_masters = _Harness.write_masters
    child = _Harness.child

    def run_engine(self, body):
        static, _ = self.prepared_data()
        self.write_masters(static / 'mst_decoded')
        masters = static / 'mst_decoded'
        units = [('100000102', 2), ('100000202', 2), ('100000302', 3),
                 ('100000315', 5), ('100000337', 5), ('100001005', 5)]
        units += list(getattr(self, 'extra_units', ()))
        (masters / 'F_UNIT_MST.ndjson').write_text('\n'.join(json.dumps({
            '3HriTp6B': uid, 'woghJa61': uid, 'aU3o2D4t': 100, '9fW0TePj': rarity,
        }) for uid, rarity in units))
        (masters / 'F_ITEM_MST.ndjson').write_text('\n'.join(json.dumps({'tL6G9egd': iid})
            for iid in ('106213050', '106213030', *getattr(self, 'extra_items', ()))))
        (masters / 'F_GACHA_SELECT_UNIT_MST.ndjson').write_text('\n'.join(json.dumps({
            '3HriTp6B': uid, 'VjJQ51uG': '2016-01-01 00:00:00',
            'm8ivD4NX': '2099-12-31 23:59:59', 'e4mG8jTc': '1',
        }) for uid in ('100000102', '100000315')))
        text = static / 'text_decoded'
        (text / 'F_TEXT_UNITS_NAME.ndjson').write_text('\n'.join(json.dumps({
            'key': 'MST_UNIT_NAME_' + uid, 'v': ['Unit ' + uid],
        }) for uid, _rarity in units))
        script = '''
import sys, copy, json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
sys.path[:0] = sys.argv[1:3]
sys.path.insert(0, str(Path(sys.argv[1]) / 'exvius'))
from ios_server.config import Configuration
from ios_server.engine import Engine
from local_game import LocalGame
import revival_summons as summons
from test_ios_summons import banner, NOW, campaign
config = Configuration(Path(sys.argv[3]), Path(sys.argv[4]))
engine = Engine(config)
server = engine.initialize()
import ffbe_crypto as crypto
from ffbe_config import GACHA_TAG, GACHA_MST_TAG, GACHA_SCHEDULE_TAG
from player_state import expand_pool
endpoints = json.loads((Path(sys.argv[2]) / 'endpoints.json').read_text())['by_class']
def request(name, payload=None, *, allow_empty=False):
    endpoint = endpoints[name]
    key = crypto.key16(endpoint['encode_key'])
    envelope = {'TEAYk6R1': {'z5hB3P01': endpoint['request_id'], 'ytHoz4E2': '1', '9K0Pzcpd': '1167'},
                't7n6cVWf': {'qrVcDe48': crypto.cbc_encrypt(key, json.dumps(payload or {}).encode(), double_pad=True)}}
    response = LocalGame.request(engine, 'POST', endpoint['url'], json.dumps(envelope))
    assert response.status == 200, (response.status, response.body)
    encoded = json.loads(response.body)['t7n6cVWf']['qrVcDe48']
    if not encoded:
        assert allow_empty, response.body
        return None
    raw = crypto.cbc_decrypt(key, encoded)
    if raw and 1 <= raw[-1] <= 16 and raw[-raw[-1]:] == bytes([raw[-1]]) * raw[-1]:
        raw = raw[:-raw[-1]]
    return json.loads(raw)
with patch('revival_campaign.datetime') as dt:
    dt.now.return_value = NOW
    request('InitializeRequest')
player = server.State.player
player.add_currency('lapis_free', 20000)
player.save(str(config.state_file))
try:
''' + '\n'.join('    ' + line for line in body.splitlines()) + '''
finally:
    engine.close()
'''
        result = self.child(script, str(self.config.root), str(self.config.data))
        self.assertEqual(result.returncode, 0, result.stdout[-7000:] + result.stderr)

    def test_given_encrypted_catalogue_when_rollover_then_new_list_and_stale_purchase_preserves_save(self):
        self.run_engine('''
first, future = banner(9800001, '2016-12-16'), banner(9800002, '2017-01-06')
with patch.object(summons, 'catalogue', return_value=(first, future)), patch.object(summons, 'clock', return_value=NOW):
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    catalog = request('GachaEntryRequest')
    assert player.data == before
    assert config.state_file.read_bytes() == saved
    assert {b['X1IuZnj2'] for b in catalog[GACHA_MST_TAG]} == {'9800001'}, catalog
    schedule = catalog[GACHA_SCHEDULE_TAG][0]
    assert schedule['VjJQ51uG'] == '2026-11-09 03:00:00', schedule
    assert schedule['m8ivD4NX'] == '2026-11-16 02:59:59', schedule
    before = copy.deepcopy(player.data)
    from ios_server.queries import rotation
    projection = rotation(config, now=NOW)
    assert projection['anchored']
    assert projection['windows'][0]['sets'][0]['banners'][0]['id'] == '9800001'
    payload = {'5yLD4dYI': [{'X1IuZnj2': first['id'], 'nqzG3b2v': first['detail_id'], '2RtVPS3b': '1'}]}
    result = request('GachaExeRequest', payload)
    assert result[GACHA_TAG][0]['UJz5QED2'].startswith('10:100000102:'), result
    assert len(player.data['roster']) == len(before['roster']) + 1
    assert player.currencies['lapis_free'] == before['currencies']['lapis_free'] - 500
    cached = summons.plan(player.data, NOW).banners()[0]
with patch.object(summons, 'catalogue', return_value=(first, future)), \\
     patch.object(summons, 'clock', return_value=NOW + timedelta(weeks=1)):
    assert {b['X1IuZnj2'] for b in request('GachaInfoRequest')[GACHA_MST_TAG]} == {'9800002'}
    before, dirty = copy.deepcopy(player.data), player.dirty
    saved = config.state_file.read_bytes()
    result = request('GachaExeRequest', payload)
    assert result[GACHA_TAG][0]['UJz5QED2'] == '', result
    assert player.data == before
    assert config.state_file.read_bytes() == saved
    assert player.roll_gacha(cached) is None
    assert player.data == before and player.dirty == dirty
    from gacha_rates import page
    assert page(first['id']) is None
''')

    def test_given_future_units_when_drawing_then_filter_every_pool_and_decline_unfulfillable_guarantees(self):
        self.run_engine('''
old = {'unit_id': '100000102', 'rarity': 2, 'rate': 1}
future = {'unit_id': '100000315', 'rarity': 5, 'rate': 1}
base = banner(9800001, '2016-12-16', pool=[old, future])
with patch.object(summons, 'catalogue', return_value=(base,)), patch.object(summons, 'clock', return_value=NOW):
    configured = summons.plan(player.data, NOW).banners()[0]
    assert expand_pool(configured) == [old]
    tiers = dict(configured, pool={'tiers': [{'rarity': 5, 'rate': 30,
          'units': ['100000315', '100001005']}, {'rarity': 2, 'rate': 70}]})
    pool = expand_pool(tiers)
    assert '100000315' not in {r['unit_id'] for r in pool}
    assert abs(sum(r['rate'] for r in pool if r['rarity'] == 5) - 30) < 0.0001, pool
    assert abs(sum(r['rate'] for r in pool if r['rarity'] == 2) - 70) < 0.0001, pool
    cases = [dict(base, guarantee={'unit_id': '100000315'}),
             dict(base, guarantee={'any_of': ['100000315']}),
             dict(base, guarantee={'rarity': 5, 'count': 1, 'pool': [future]}),
             dict(base, guarantee_slots=[{'count': 1, 'pool': [future]}]),
             dict(base, bonus_rewards=[{'kind': 10, 'id': '100000315', 'count': 1}]),
             dict(base, reward_pool=[{'kind': 10, 'id': '100000315', 'count': 1, 'rate': 1}]),
             dict(base, steps=[{'cost': base['cost'], 'draws': 1, 'pool': [future]}])]
    for candidate in cases:
        before, dirty = copy.deepcopy(player.data), player.dirty
        assert player.roll_gacha(candidate) is None, candidate
        assert player.data == before and player.dirty == dirty, candidate
    for candidate, offer in [(base, None), (base, {'cost': base['cost'], 'draws': 1, 'pool': [old, future]}),
                             (dict(base, guarantee={'any_of': ['100000102', '100000315']}), None)]:
        result = player.roll_gacha(candidate, offer=offer)
        assert result and all(a['unit_id'] == '100000102' for a in result['awards']), result
    from gacha_rates import page
    html = page(base['id'])
    assert 'Unit 100000102' in html and 'Unit 100000315' not in html, html
    from ffbe_player import _global_bundles
    bundles = {row['id']: row for row in _global_bundles()}
    assert '990000107' not in bundles
    assert bundles['990000108']['limit'] == bundles['990000109']['limit'] == 'once'
''')

    def test_given_one_off_ticket_bundle_when_purchase_retries_after_reload_then_no_second_charge(self):
        self.run_engine('''
from ffbe_player import serve_lapis_shop
from player_state import PlayerState
for bid, iid in [('990000108', 106213050), ('990000109', 106213030)]:
    held = player.item_count(20, iid)
    plaintext = json.dumps({'blmGz1EI': [{'EzXXHtTY': bid}]})
    serve_lapis_shop({}, 'w6Z9a6tD', plaintext)
    assert player.item_count(20, iid) == held + 1
    player.save(str(config.state_file))
    player = server.State.player = PlayerState.load(str(config.state_file), slot=config.slot)
    before, dirty = copy.deepcopy(player.data), player.dirty
    saved = config.state_file.read_bytes()
    try:
        serve_lapis_shop({}, 'w6Z9a6tD', plaintext)
    except ValueError:
        pass
    else:
        raise AssertionError('one-off bundle was sold twice')
    assert player.data == before and player.dirty == dirty
    assert config.state_file.read_bytes() == saved
''')

    def test_given_weekly_limit_when_monday_passes_then_wait_until_eastern_sunday_to_reset(self):
        self.run_engine('''
base = banner(9800001, name='Weekly fixture', permanent=True, weekly_limit=1)
with patch.object(summons, 'catalogue', return_value=(base,)):
    with patch.object(summons, 'clock', return_value=NOW):
        assert player.roll_gacha(base)
    for moment in (NOW + timedelta(hours=15), NOW + timedelta(days=6, hours=23)):
        with patch.object(summons, 'clock', return_value=moment):
            before, dirty = copy.deepcopy(player.data), player.dirty
            assert player.roll_gacha(base) is None
            assert player.data == before and player.dirty == dirty
    with patch.object(summons, 'clock', return_value=NOW + timedelta(weeks=1)):
        assert player.roll_gacha(base)
        configured = summons.plan(player.data).banners()
        before = copy.deepcopy(player.data)
        row = player.gacha_user_rows(configured)[0]
        assert row['Lqenh7d2'] == '2026-11-16 03:00:00', row
        assert row['08MuyfqD'] == '1', row
        assert player.data == before
''')

    def test_given_uninitialized_campaign_when_summon_is_attempted_then_do_not_create_anchor_or_spend(self):
        self.run_engine('''
base = banner(9800001, '2016-12-16')
del player.data['ios_revival']
with patch.object(summons, 'catalogue', return_value=(base,)), patch.object(summons, 'clock', return_value=NOW):
    before, dirty = copy.deepcopy(player.data), player.dirty
    assert player.roll_gacha(base) is None
    assert player.data == before and player.dirty == dirty
    try:
        expand_pool(base)
    except ValueError:
        pass
    else:
        raise AssertionError('unscoped iOS pool silently bypassed the cutoff')
''')

    def test_given_future_box_reward_when_drawing_then_preserve_currency_and_box_inventory(self):
        self.run_engine('''
import gacha_box
base = banner(9800001, '2016-12-16', box_base_id=9800100,
              boxes=[[{'reward': {'kind': 10, 'id': '100000315', 'count': 1}, 'copies': 1}]])
with patch.object(summons, 'catalogue', return_value=(base,)), patch.object(summons, 'clock', return_value=NOW):
    before, dirty = copy.deepcopy(player.data), player.dirty
    assert gacha_box.roll(player, base, gacha_box.detail_id(player, base)) is None
    assert player.data == before and player.dirty == dirty
''')

    def test_given_select_summon_when_reward_is_in_future_then_decline_before_spending_select_tickets(self):
        self.run_engine('''
from exvius_gacha_select import select_unit
base = banner(9800001, '2016-12-16', selection=True)
player.grant_item(23, 260, 2)
with patch.object(summons, 'catalogue', return_value=(base,)), patch.object(summons, 'clock', return_value=NOW):
    before, dirty = copy.deepcopy(player.data), player.dirty
    node = {'X1IuZnj2': base['id'], 'nqzG3b2v': base['detail_id'], '3HriTp6B': '100000315'}
    out = select_unit({}, {'u9jY6hQJ': [node]})
    assert out['u9jY6hQJ'][0]['UJz5QED2'] == ''
    assert player.data == before and player.dirty == dirty
    node['3HriTp6B'] = '100000102'
    out = select_unit({}, {'u9jY6hQJ': [node]})
    assert out['u9jY6hQJ'][0]['UJz5QED2'].startswith('10:100000102:')
    assert player.item_count(23, 260) == 1
''')


if __name__ == '__main__':
    unittest.main()
