"""BDD for pinned iOS summon deals, printed guarantees and select-ticket exchanges."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SOURCE), str(SOURCE / 'server')]

from test_ios_summons import NOW, banner, campaign
import revival_deals as deals
import revival_summons as summons


class DealPolicyBehavior(unittest.TestCase):
    def test_given_pinned_catalogue_when_loaded_then_include_deals_without_mutating_source_banners(self):
        rows = deals.banners()
        self.assertEqual(len(rows), 311)
        self.assertEqual(sum(bool(b.get('resummon')) for b in rows), 6)
        self.assertEqual(len(deals.ticket_ids()), 7)
        by_id = {str(b['id']): b for b in summons.catalogue()}
        self.assertTrue({str(b['id']) for b in rows} <= set(by_id))
        self.assertEqual(by_id['9503462']['unit_select_tickets'], [1209001554])

    def test_given_printed_bonus_when_secondary_offer_is_used_then_add_only_missing_terms(self):
        source = banner('800720', secondary_offer={'draws': 11, 'cost': {'kind': 'lapis', 'amount': 5000}})
        before = copy.deepcopy(source)
        configured = deals.apply_printed(source)
        self.assertTrue(configured['secondary_offer']['bonus_rewards'])
        self.assertEqual(source, before)
        authored = dict(source, secondary_offer=dict(source['secondary_offer'],
                        bonus_rewards=[{'kind': 30, 'id': 0, 'count': 7}], guarantee={'rarity': 7, 'count': 2}))
        self.assertEqual(deals.apply_printed(authored)['secondary_offer'], authored['secondary_offer'])

    def test_given_printed_pool_rule_when_checking_units_then_enforce_dates_and_exclusions(self):
        root = {'3HriTp6B': '100000315', 'woghJa61': '100000315', '9fW0TePj': '5'}
        b = banner(1, pool_rule={'released_by': '2016-12-31'})
        self.assertFalse(deals.pool_rule_allows(b, '100000315', root))
        b['pool_rule'] = {'released_from': '2017-01-01', 'released_by': '2017-01-31'}
        self.assertTrue(deals.pool_rule_allows(b, '100000315', root))
        self.assertFalse(deals.pool_rule_allows(b, '100000102', {}))
        b['pool_rule'] = {'exclude': ['limited', 'collab']}
        with patch.object(deals, 'limited_units', return_value=frozenset({'100000315'})):
            self.assertFalse(deals.pool_rule_allows(b, '100000315', root))
            b['pool'] = {'tiers': [{'featured': ['100000315']}]}
            self.assertTrue(deals.pool_rule_allows(b, '100000315', root))

    def test_given_damaged_deal_metadata_when_loaded_then_fail_without_opening_pools(self):
        self.addCleanup(deals.banners.cache_clear)
        for raw in ('{}', '{"banners":{}}'):
            deals.banners.cache_clear()
            with self.subTest(raw=raw), patch.object(Path, 'read_text', return_value=raw):
                with self.assertRaisesRegex(ValueError, 'Invalid pinned summon deals'):
                    deals.banners()


class DealCommandBehavior(unittest.TestCase):
    from test_ios_summons import ReplaySummonIntegration as _Harness
    setUp = _Harness.setUp
    child = _Harness.child
    run_engine = _Harness.run_engine
    extra_units = (('100031007', 7), ('904000104', 4), ('904000105', 5))
    extra_items = ('1209001554',)

    def prepared_data(self, managed=False):
        static, native = self._Harness.prepared_data(self, managed)
        for name in ('F_TEXT_ITEM_NAME', 'F_TEXT_IMPORTANT_ITEM_NAME'):
            (static / 'text_decoded' / (name + '.ndjson')).write_text('')
        return static, native

    def write_masters(self, masters):
        self._Harness.write_masters(self, masters)
        (masters / 'F_MEDAL_EXCHANGE_MST.ndjson').write_text(json.dumps({
            'S21FT3L8': '990001', 'ak2dhKm3': '1209001554', 'Qy5EvcK1': '1',
            '7iJpH5zZ': '10:100031007:1:100', 'kR4n5DxP': '1', 'x0NDnEC9': '1'}))

    def test_given_printed_pool_rule_when_expanding_and_drawing_then_rates_and_guarantees_use_same_units(self):
        self.run_engine('''
import revival_deals as deals
from player_state import summon_pool, summon_subpool
from gacha_rates import page
player.data['ios_revival']['replay']['settings']['start'] = '2023-01-01'
old = {'unit_id': '100000102', 'rarity': 2, 'rate': 1}
later = {'unit_id': '100000315', 'rarity': 5, 'rate': 1}
base = banner(9800001, permanent=True, pool=[old,later],
              pool_rule={'released_by': '2016-12-31'})
with patch.object(summons, 'catalogue', return_value=(base,)), patch.object(summons, 'clock', return_value=NOW):
    prepared = summons.plan(player.data).banners()[0]
    assert summon_pool(prepared) == [old]
    assert summon_subpool(prepared, [old,later]) == [old]
    html = page(base['id'])
    assert 'Unit 100000102' in html and 'Unit 100000315' not in html
    bad = dict(base, guarantee={'rarity': 5, 'count': 1})
    before, dirty = copy.deepcopy(player.data), player.dirty
    assert player.roll_gacha(bad) is None
    assert player.data == before and player.dirty == dirty
    result = player.roll_gacha(base)
    assert result and result['awards'][0]['unit_id'] == '100000102'
    named = dict(base, guarantee={'rarity':5,'count':1,'pool':[later]})
    result = player.roll_gacha(named)
    assert result and result['awards'][0]['unit_id'] == '100000315'
''')

    def test_given_secondary_weighted_bonus_when_pulling_then_charge_once_and_grant_metadata(self):
        self.run_engine('''
base = banner(9800001, '2016-12-16', secondary_offer={
    'cost': {'kind': 'lapis', 'amount': 1000}, 'draws': 2,
    'bonus_choice': [{'rate': 1, 'rewards': [{'kind': 10, 'id': 904000104, 'count': 1,
                                           'affinity_points': ['50', '']}]}]})
with patch.object(summons, 'catalogue', return_value=(base,)), patch.object(summons, 'clock', return_value=NOW):
    before, held = player.currencies['lapis_free'], len(player.data['roster'])
    result = player.roll_gacha(base, repeats=11, offer=base['secondary_offer'])
    assert result and result['count'] == 2 and len(result['awards']) == 3, result
    assert player.currencies['lapis_free'] == before - 1000
    assert len(player.data['roster']) == held + 3
    bonus = player.data['roster'][-1]
    assert bonus['master_id'] == '904000104' and bonus['affinity_points'] == ['50',''], bonus
''')

    def test_given_failed_bonus_grant_when_staged_then_preserve_balance_roster_counters_and_original_save(self):
        self.run_engine('''
from player_state import PlayerState
base = banner(9800001, '2016-12-16', bonus_rewards=[{'kind': 30, 'id': 0, 'count': 7}])
with patch.object(summons, 'catalogue', return_value=(base,)), patch.object(summons, 'clock', return_value=NOW):
    before, dirty, saved = copy.deepcopy(player.data), player.dirty, config.state_file.read_bytes()
    original = PlayerState._grant_items
    def partial(candidate, rows):
        original(candidate, rows)
        return []
    with patch.object(PlayerState, '_grant_items', partial):
        assert player.roll_gacha(base) is None
    assert player.data == before and player.dirty == dirty and config.state_file.read_bytes() == saved
    original_grant = PlayerState.grant_unit
    def broken(candidate, *args, **kwargs):
        original_grant(candidate, *args, **kwargs)
        raise ValueError('injected failure after a unit grant')
    with patch.object(PlayerState, 'grant_unit', broken):
        try:
            player.roll_gacha(base)
        except ValueError:
            pass
        else:
            raise AssertionError('injected grant failure was hidden')
    assert player.data == before and player.dirty == dirty and config.state_file.read_bytes() == saved
''')

    def test_given_counted_guarantees_and_nv_slot_when_pulling_then_deliver_every_printed_slot(self):
        self.run_engine('''
player.data['ios_revival']['replay']['settings']['start'] = '2023-01-01'
base = banner(9800001, permanent=True, draws=11,
    pool=[{'unit_id':'100000315','rarity':5,'rate':1}],
    guarantee={'rarity':5,'count':10},
    guarantee_slots=[{'count':1,'label':'NV','pool':[{'unit_id':'100031007','rarity':7,'rate':1}]}])
with patch.object(summons, 'catalogue', return_value=(base,)), patch.object(summons, 'clock', return_value=NOW):
    result = player.roll_gacha(base)
    assert result and result['count'] == 11, result
    assert sum(a['unit_id'] == '100031007' for a in result['awards']) == 1, result
    assert sum(a['unit_id'] == '100000315' for a in result['awards']) == 10, result
''')

    def test_given_step_pool_on_mixed_reward_banner_when_pulling_then_replace_the_mixed_pool(self):
        self.run_engine('''
base = banner(9800001, '2016-12-16', reward_pool=[{'kind':30,'id':0,'count':999,'rate':1}],
    steps=[{'cost':{'kind':'lapis','amount':100},'draws':1,
            'pool':[{'unit_id':'100000102','rarity':2,'rate':1}]}])
with patch.object(summons, 'catalogue', return_value=(base,)), patch.object(summons, 'clock', return_value=NOW):
    gil, lapis = player.currencies['gil'], player.currencies['lapis_free']
    result = player.roll_gacha(base)
    assert result and result['awards'][0]['unit_id'] == '100000102', result
    assert not result['reward_awards'] and player.currencies['gil'] == gil
    assert player.currencies['lapis_free'] == lapis - 100
''')

    def test_given_encrypted_paid_deal_when_ticket_is_earned_then_exchange_and_stock_survive_reload(self):
        self.run_engine('''
import exvius_shop_catalogue as shops
from player_state import PlayerState
player.data['ios_revival']['replay']['settings']['start'] = '2023-01-01'
base = banner(9800001, permanent=True, purchase_limit=1,
    bonus_rewards=[{'kind':20,'id':1209001554,'count':1}])
with patch.object(summons, 'catalogue', return_value=(base,)), patch.object(summons, 'clock', return_value=NOW):
    assert '900990001' not in shops.catalogue()[2]
    payload={'5yLD4dYI':[{'X1IuZnj2':base['id'],'nqzG3b2v':base['detail_id'],'2RtVPS3b':'1'}]}
    result=request('GachaExeRequest', payload)
    assert result[GACHA_TAG][0]['UJz5QED2'].startswith('10:'), result
    assert player.item_count(20,1209001554) == 1
    assert '900990001' in shops.catalogue()[2]
    held=len(player.data['roster'])
    bought=request('GachaSelectExchangeExeRequest', {'4mrD6JuA':[{'jPV7Xc4N':'900990001','Qy5EvcK1':'1'}]})
    assert bought.get('4owH1uT2') and len(player.data['roster']) == held+1
    assert player.item_count(20,1209001554) == 0
    assert '900990001' not in shops.catalogue()[2]
    player.save(str(config.state_file))
    player=server.State.player=PlayerState.load(str(config.state_file),slot=config.slot)
    before,saved=copy.deepcopy(player.data),config.state_file.read_bytes()
    assert request('GachaExeRequest', payload)[GACHA_TAG][0]['UJz5QED2'] == ''
    assert player.data == before and config.state_file.read_bytes() == saved
    player.grant_item(20,1209001554,1)
    before=copy.deepcopy(player.data)
    result=request('GachaSelectExchangeExeRequest', {'4mrD6JuA':[{'jPV7Xc4N':'900990001','Qy5EvcK1':'1'}]})
    assert '4owH1uT2' not in result and player.data == before
''')

    def test_given_resummon_when_redone_then_replace_main_units_keep_bonus_and_never_charge_again(self):
        self.run_engine('''
from player_state import PlayerState
base=banner(9800001,'2016-12-16',resummon=2,purchase_limit=1,draws=2,
    bonus_rewards=[{'kind':30,'id':0,'count':7}],
    secondary_offer={'cost':{'kind':'free','amount':0},'draws':2,'resummon':True,'bonus_rewards':[]})
with patch.object(summons,'catalogue',return_value=(base,)),patch.object(summons,'clock',return_value=NOW):
    before,dirty=copy.deepcopy(player.data),player.dirty
    assert player.roll_gacha(base,offer=base['secondary_offer']) is None
    assert player.data == before and player.dirty == dirty
    result=player.roll_gacha(base)
    assert result and player.currencies['gil'] == before['currencies']['gil']+7
    paid=player.currencies['lapis_free']
    first={a['instance_id'] for a in result['awards']}
    player.save(str(config.state_file))
    player=server.State.player=PlayerState.load(str(config.state_file),slot=config.slot)
    for remaining in (1,0):
        result=player.roll_gacha(base,offer=base['secondary_offer'])
        assert result and player.currencies['lapis_free'] == paid, result
        assert player.currencies['gil'] == before['currencies']['gil']+7
        assert len(player.data['roster']) == len(before['roster'])+2
        assert not first.intersection({u['instance_id'] for u in player.data['roster']})
        assert player.data['gacha']['resummon'][base['id']]['left'] == remaining
        assert player.data['gacha']['user_banners'][base['id']]['total_exe_count'] == 1
    before,dirty=copy.deepcopy(player.data),player.dirty
    assert player.roll_gacha(base,offer=base['secondary_offer']) is None
    assert player.roll_gacha(base) is None
    assert player.data == before and player.dirty == dirty
''')

    def test_given_used_or_changed_resummon_unit_when_redo_is_requested_then_keep_original_result(self):
        self.run_engine('''
base=banner(9800001,'2016-12-16',resummon=2,purchase_limit=1,
    secondary_offer={'cost':{'kind':'free','amount':0},'draws':1,'resummon':True,'bonus_rewards':[]})
with patch.object(summons,'catalogue',return_value=(base,)),patch.object(summons,'clock',return_value=NOW):
    result=player.roll_gacha(base)
    state=copy.deepcopy(player.data)
    uid=result['awards'][0]['instance_id']
    for change in ('level','party','missing'):
        player.data=copy.deepcopy(state)
        if change=='level':
            next(u for u in player.data['roster'] if str(u['instance_id'])==uid)['level']=2
        elif change=='party':
            player.data['party']['decks'][0]['members'].append({'instance_id':uid})
        else:
            player.drop_units([uid])
        before,dirty=copy.deepcopy(player.data),player.dirty
        assert player.roll_gacha(base,offer=base['secondary_offer']) is None, change
        assert player.data == before and player.dirty == dirty
''')

    def test_given_resummon_result_when_projected_then_publish_free_limit_and_used_count_without_writes(self):
        self.run_engine('''
from ffbe_gacha import all_banners,gacha_groups,gacha_secondary_detail_id
from ffbe_config import GACHA_DETAIL_TAG
base=banner(9800001,'2016-12-16',resummon=2,purchase_limit=1,
    secondary_offer={'cost':{'kind':'free','amount':0},'draws':1,'resummon':True,'bonus_rewards':[]})
with patch.object(summons,'catalogue',return_value=(base,)),patch.object(summons,'clock',return_value=NOW):
    active=all_banners()
    groups=gacha_groups(active)
    secondary=gacha_secondary_detail_id(base)
    assert next(r for r in groups[GACHA_DETAIL_TAG] if r['nqzG3b2v']==secondary)['1ovyP04j']=='2:0'
    assert next(r for r in player.gacha_user_rows(active) if r['nqzG3b2v']==secondary)['08MuyfqD']=='2'
    assert player.roll_gacha(base)
    before,dirty=copy.deepcopy(player.data),player.dirty
    assert next(r for r in player.gacha_user_rows(all_banners()) if r['nqzG3b2v']==secondary)['08MuyfqD']=='0'
    assert player.data==before and player.dirty==dirty
    assert player.roll_gacha(base,offer=base['secondary_offer'])
    assert next(r for r in player.gacha_user_rows(all_banners()) if r['nqzG3b2v']==secondary)['08MuyfqD']=='1'
''')

    def test_given_free_daily_when_utc_date_changes_then_reset_only_at_recorded_local_midnight(self):
        self.run_engine('''
from ffbe_gacha import all_banners
base=banner(9800001,permanent=True,daily_limit=1,cost={'kind':'free','amount':0})
with patch.object(summons,'catalogue',return_value=(base,)):
    with patch.object(summons,'clock',return_value=datetime(2026,11,9,12,tzinfo=timezone.utc)):
        assert player.roll_gacha(base)
    with patch.object(summons,'clock',return_value=datetime(2026,11,10,4,59,tzinfo=timezone.utc)):
        before,dirty=copy.deepcopy(player.data),player.dirty
        assert player.roll_gacha(base) is None
        row=player.gacha_user_rows(all_banners())[0]
        assert row['Lqenh7d2']=='2026-11-09 05:00:00' and row['u7dM3XwK']=='2026-11-10 04:59:59',row
        assert row['08MuyfqD']=='1' and player.data==before and player.dirty==dirty
    with patch.object(summons,'clock',return_value=datetime(2026,11,10,5,tzinfo=timezone.utc)):
        assert player.roll_gacha(base)
    for moment,first,last in [(datetime(2026,3,8,12,tzinfo=timezone.utc),'2026-03-08 05:00:00','2026-03-09 03:59:59'),
                              (datetime(2026,11,1,12,tzinfo=timezone.utc),'2026-11-01 04:00:00','2026-11-02 04:59:59')]:
        with patch.object(summons,'clock',return_value=moment):
            before=copy.deepcopy(player.data)
            row=player.gacha_user_rows(all_banners())[0]
            assert (row['Lqenh7d2'],row['u7dM3XwK'])==(first,last),row
            assert player.data==before
''')

    def test_given_encrypted_resummon_when_paid_then_refresh_the_secondary_limit_and_replace_result(self):
        self.run_engine('''
from ffbe_gacha import gacha_secondary_detail_id
from ffbe_config import GACHA_USER_INFO_TAG
base=banner(9800001,'2016-12-16',resummon=1,purchase_limit=1,
    secondary_offer={'cost':{'kind':'free','amount':0},'draws':1,'resummon':True,'bonus_rewards':[]})
with patch.object(summons,'catalogue',return_value=(base,)),patch.object(summons,'clock',return_value=NOW):
    request_body={'X1IuZnj2':base['id'],'nqzG3b2v':base['detail_id'],'2RtVPS3b':'1'}
    first=request('GachaExeRequest',{'5yLD4dYI':[request_body]})
    secondary=gacha_secondary_detail_id(base)
    assert next(r for r in first[GACHA_USER_INFO_TAG] if r['nqzG3b2v']==secondary)['08MuyfqD']=='0',first
    uid=first[GACHA_TAG][0]['UJz5QED2'].split(':')[2]
    paid=player.currencies['lapis_free']
    request_body['nqzG3b2v']=secondary
    second=request('GachaExeRequest',{'5yLD4dYI':[request_body]})
    assert second[GACHA_TAG][0]['UJz5QED2'].split(':')[2]!=uid
    assert not any(str(u['instance_id'])==uid for u in player.data['roster'])
    assert player.currencies['lapis_free']==paid
    assert next(r for r in second[GACHA_USER_INFO_TAG] if r['nqzG3b2v']==secondary)['08MuyfqD']=='1'
    before=copy.deepcopy(player.data)
    assert request('GachaExeRequest',{'5yLD4dYI':[request_body]})[GACHA_TAG][0]['UJz5QED2']==''
    assert player.data==before
''')

    def test_given_zero_weight_pool_when_pulled_then_preserve_the_original_transaction(self):
        self.run_engine('''
base=banner(9800001,'2016-12-16')
with patch.object(summons,'catalogue',return_value=(base,)),patch.object(summons,'clock',return_value=NOW):
    bad=[dict(base,pool=[{'unit_id':'100000102','rarity':2,'rate':rate}]) for rate in (0,-1,float('inf'))]
    bad += [dict(base,guarantee={'rarity':2,'count':1,'pool':[{'unit_id':'100000102','rarity':2,'rate':0}]}),
            dict(base,bonus_choice=[{'rate':float('inf'),'rewards':[{'kind':30,'id':0,'count':1}]}])]
    for candidate in bad:
        before,dirty=copy.deepcopy(player.data),player.dirty
        assert player.roll_gacha(candidate) is None
        assert player.data==before and player.dirty==dirty
''')


if __name__ == '__main__':
    unittest.main()
