"""BDD for native bootstrap receipts and update-specific master transformations."""
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SOURCE), str(SOURCE / 'server')]
from engine_profile import IOS_REVIVAL
from revival_boot import step
from ios_server.update_tables import transform
from revival_carry import settle


class NativeUpdateBehavior(unittest.TestCase):
    def test_given_vision_card_first_clear_when_projected_then_include_positive_native_level(self):
        from revival_battle_updates import shown
        self.assertEqual(shown([{'kind':27,'id':123,'count':1}], {}), '27:123:1:100:1')

    def setUp(self):
        self.profile = patch('engine_profile.current_profile', return_value=IOS_REVIVAL)
        self.profile.start(); self.addCleanup(self.profile.stop)
        self.player = SimpleNamespace(data={'identity': {'user_id': '123'}}, mode='live', dirty=False)
        self.state = SimpleNamespace(player=self.player, state_dirty=False,
            native_tables=SimpleNamespace(manifest={'tables': {'F_FUNCTION_MST': {'version': 200}}}))
        self.req = json.dumps({'LhVz6aD2': [{'9Tbns0eI': '123', '6e4ik6kA': 'device'}]})

    def test_given_first_client_when_early_then_do_not_advertise_until_completed_login(self):
        self.assertEqual(step({}, 'lEHBdOEf', self.req, self.state), {})
        step({}, '75fYdNxq', self.req, self.state)
        self.assertEqual(step({}, 'lEHBdOEf', self.req, self.state), {})
        step({}, 'Daud71Hn', self.req, self.state)
        before = copy.deepcopy(self.player.data)
        self.assertEqual(step({}, 'lEHBdOEf', self.req, self.state)['c1qYg84Q'][0]['wM9AfX6I'], '200')
        self.assertEqual(self.player.data, before)
        self.state.native_tables.manifest['tables']['F_FUNCTION_MST']['version'] = 201
        self.assertEqual(step({}, 'lEHBdOEf', self.req, self.state), {})

    def test_given_other_campaign_identity_or_frozen_player_when_synchronizing_then_write_nothing(self):
        before = copy.deepcopy(self.player.data)
        step({}, '75fYdNxq', self.req.replace('123', '456'), self.state)
        self.assertEqual(self.player.data, before)
        self.player.mode = 'frozen'
        step({}, '75fYdNxq', self.req, self.state)
        self.assertEqual(self.player.data, before)

    def test_given_farplane_placeholder_when_preparing_then_exclude_only_recorded_packs(self):
        row = {'Y4PER0gB': '390001201,123'}
        self.assertEqual(transform('F_MAP_EXT_RESOURCE_MST', dict(row)), {'Y4PER0gB': '123'})
        self.assertEqual(transform('F_MAP_EXT_RESOURCE_MST', {'Y4PER0gB':'390001213'}),
                         {'Y4PER0gB':'', 'a3u6d1re':''})
        self.assertEqual(row['Y4PER0gB'], '390001201,123')

    def test_given_used_items_when_settling_then_debit_once_even_after_refilling(self):
        class Player:
            mode = 'live'
            dirty = False
            stock = 10
            data = {'exvius_repeat': {'attempt': {'mid':'1', 'sequence':1,
                'carry_at_load':[{'disp_order':0,'item_id':90,'count':5}]}},
                'inventory': {'carry_items':[{'disp_order':0,'item_id':90,'count':5}]}}
            def item_count(self, *args): return self.stock
            def spend_item(self, kind, iid, amount): self.stock -= amount
        player = Player()
        req = {'nE7pV2wr':[{'jsvoa0I2':'0:90:2'}]}
        settle(player, req, '1')
        self.assertEqual(player.stock, 7)
        player.data['inventory']['carry_items'][0]['count'] = 5
        settle(player, req, '1')
        self.assertEqual(player.stock, 7)

    def test_given_empty_or_wrong_attempt_report_when_settling_then_preserve_items(self):
        player = SimpleNamespace(mode='live', data={'exvius_repeat': {'attempt': {'mid':'1', 'carry_at_load':[]}}})
        before = copy.deepcopy(player.data)
        settle(player, {'nE7pV2wr':[{'jsvoa0I2':''}]}, '1')
        settle(player, {'nE7pV2wr':[{'jsvoa0I2':'0:90:0'}]}, '2')
        self.assertEqual(player.data, before)

    def test_given_native_cbc_and_ecb_tables_when_appending_then_preserve_cipher_padding_and_original_lines(self):
        from test_ios_preparation import master
        from ios_server.table_codec import append_master, master_rows
        for mode in ('cbc','ecb'):
            raw = master('fixture1',[{'id':'1'},{'id':'2'}],mode=mode)
            out = append_master(raw,'fixture1',[{'id':'3'}],mode=mode)
            rows = master_rows(out,'fixture1',mode=mode)
            self.assertEqual([r[1]['id'] for r in rows],['1','2','3'])
            self.assertEqual(out.splitlines()[:2],raw.splitlines())
            self.assertEqual([r[2] for r in rows],[False,True,False])


if __name__ == '__main__':
    unittest.main()
