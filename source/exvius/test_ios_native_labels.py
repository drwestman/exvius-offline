"""BDD for native English labels, saved economy displays and snapshot upgrades."""
import copy
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import test_ios_preparation as harness
from ios_server import native_tables as rules, native_text as labels, preparation as prep
from ios_server.table_codec import master_rows, patch_text, text_lines
from exchange_catalogue import build_catalogue
from reward_tuples import parse
import revival_economy as economy


def documents():
    return {'content/revival_bundles.json':{'bundles':[{'id':'1','name':'Bundle'}]},
        'content/exbonus_text.json':{'1':{'name':'New ability','description':'New description'}},
        'battle_names.json':{'monster':{'1':'Monster'},'skill':{'1':'Skill'}},
        'colosseum_names.json':{}, 'content/ios_text_items.json':{'items':{'20:2':'Recovered item'}},
        'event_archive.json':{'events':[{'area':'7','native_mode':'tfa'}]}}


def render(shipped=None, banners=(), products=()):
    values={name:{} for name in labels.TEXT_SPECS}
    for table,rows in (shipped or {}).items(): values[table].update(rows)
    return labels.plan(values,documents(),banners,products,{})


class NativeLabelPolicy(unittest.TestCase):
    def test_given_revival_only_bundles_when_prepared_then_include_all_canonical_bundle_labels(self):
        from revival_economy import bundles
        doc=documents(); doc['content/revival_bundles.json']['bundles']=list(bundles())
        out,_=labels.plan({name:{} for name in labels.TEXT_SPECS},doc,[],[],{})
        for bundle in bundles():
            self.assertEqual(out['F_TEXT_BUNDLE']['MST_BUNDLE_NAME_'+str(bundle['id'])][0],bundle['name'])
        self.assertIn('MST_BUNDLE_NAME_990000126',out['F_TEXT_BUNDLE'])

    def test_given_usable_english_when_filling_hook_text_then_preserve_it_and_replace_only_missing_or_bad_text(self):
        shipped={'F_TEXT_ABILITY_NAME':{'MST_ABILITY_NAME_1':'Original ability'},
            'F_TEXT_MONSTER_NAME':{'MST_MONSTER_NAME_1':'Original monster'},
            'F_TEXT_MONSTER_SKILL_NAME':{'MST_MONSTER_SKILL_NAME_1':'TFA_PLACEHOLDER'},
            'F_TEXT_ITEM_NAME':{'MST_ITEM_NAME_2':'アイテム'}}
        before=copy.deepcopy(shipped); out,_=render(shipped)
        self.assertNotIn('MST_ABILITY_NAME_1',out['F_TEXT_ABILITY_NAME'])
        self.assertNotIn('MST_MONSTER_NAME_1',out['F_TEXT_MONSTER_NAME'])
        self.assertEqual(out['F_TEXT_MONSTER_SKILL_NAME']['MST_MONSTER_SKILL_NAME_1'],('Skill',True))
        self.assertEqual(out['F_TEXT_ITEM_NAME']['MST_ITEM_NAME_2'],('Recovered item',True))
        self.assertEqual(shipped,before)

    def test_given_existing_bundle_and_ticket_text_when_patched_then_append_missing_keys_without_overwriting(self):
        out,_=render()
        table='F_TEXT_BUNDLE'; key='MST_BUNDLE_NAME_1'
        raw=harness.text(rules.BY_NAME[table].key,[key+'^Shipped^Shipped'])
        new,_=patch_text(raw,rules.BY_NAME[table].key,out[table])
        rows=[line for _,lines,_ in text_lines(new,rules.BY_NAME[table].key) for line in lines]
        self.assertIn(key+'^Shipped^Shipped',rows)
        self.assertIn('MST_BUNDLE_DESC_1^Bundle^Bundle',rows)
        self.assertEqual(out['F_TEXT_ITEM_NAME']['MST_ITEM_NAME_106213050'][1],False)

    def test_given_banner_overrides_when_projected_then_preserve_names_except_explicit_overrides_and_add_details(self):
        banners=[{'id':'1','name':'Keep','draws':1},{'id':'2','name':'Override','name_override':True,'steps':[{}]},
                 {'id':'3','name':'Select','selection':True}]
        out,report=render({'F_TEXT_GACHA':{'MST_GACHA_NAME_1':'Retail','MST_GACHA_NAME_2':'Old'}},banners)
        self.assertNotIn('MST_GACHA_NAME_1',out['F_TEXT_GACHA'])
        self.assertEqual(out['F_TEXT_GACHA']['MST_GACHA_NAME_2'],('Override',True))
        self.assertIn('1-step summon',out['F_TEXT_GACHA']['MST_GACHA_EXPLAIN_LONG_2'][0])
        self.assertIn('Choose a unit',out['F_TEXT_GACHA']['MST_GACHA_EXPLAIN_SHORT_3'][0])
        self.assertFalse(out['F_TEXT_GACHA']['MST_GACHA_EXPLAIN_LONG_1'][1])
        self.assertEqual(report['banners'],3)

    def test_given_product_rewards_when_named_then_use_native_names_and_report_unresolved_references(self):
        products=[{'jPV7Xc4N':'1','P4puB2ch':'20:2:1000,50:1:20'},
                  {'jPV7Xc4N':'2','P4puB2ch':'27:999:1'}]
        out,report=render(products=products)
        self.assertEqual(out['F_TEXT_NV_SHOP_PRODUCT_NAME']['MST_NVSHOP_PRODUCT_NAME_1'][0],
                         'Recovered item x1,000, Lapis x20')
        self.assertEqual(report['unresolved_products'],['2'])
        self.assertEqual(report['named_products'],1)
        self.assertNotIn('MST_NVSHOP_PRODUCT_NAME_2',out['F_TEXT_NV_SHOP_PRODUCT_NAME'])

    def test_given_all_item_kinds_when_filling_then_cover_native_name_short_and_long_families(self):
        doc=documents(); doc['content/ios_text_items.json']['items']={kind+':1':'Name ^ '+kind for kind in labels.ITEM_TEXT}
        shipped={name:{} for name in labels.TEXT_SPECS}
        out,_=labels.plan(shipped,doc,[],[],{})
        for kind,entries in labels.ITEM_TEXT.items():
            for table,prefix in entries: self.assertEqual(out[table][prefix+'1'],('Name '+kind,True))

    def test_given_unit_metadata_when_decoded_with_injected_master_then_preserve_specific_and_generic_trust(self):
        lookup=Mock(return_value={'9mu4boy7':'20:2:1:100'})
        row=parse('10:904000105:1:100:1:0:100001234',lookup)[0]
        self.assertEqual(row['affinity_points'],['100',''])
        self.assertEqual(row['affinity_info'],['20:2:1:100',''])
        lookup.assert_called_once_with(100001234)
        generic=parse('10:904000105:1:100:1:0:100000050',lambda _:None)[0]
        self.assertEqual(generic['affinity_points'],['500',''])

    def test_given_pure_exchange_inputs_when_compiled_then_keep_prices_ids_limits_and_input_rows(self):
        rows=[{'ak2dhKm3':'1','7iJpH5zZ':'20:250000001:2','S21FT3L8':'7','kR4n5DxP':'1','x0NDnEC9':'3','Qy5EvcK1':'9'},
              {'ak2dhKm3':'2','7iJpH5zZ':'10:100000102:1','S21FT3L8':'8','kR4n5DxP':'0','Qy5EvcK1':'1'}]
        before=copy.deepcopy(rows)
        details,products,offers=build_catalogue(lambda _:rows,{},lambda raw:parse(raw,lambda _:None),
            permanent_shops=[],tickets=['2'],event_shops=[{'name':'Event','currency':[20,3],'event_areas':['7'],
                'products':[{'reward':'20:2:1','price':4,'limit':5}]}])
        by={row['jPV7Xc4N']:row for row in products}
        self.assertEqual((by['900000007']['e4mG8jTc'],by['900000007']['uYcL8IQ1']),('9','3'))
        self.assertEqual(by['900000008']['3X1gLufw'],'850003000')
        self.assertTrue(offers['900000008']['requires_currency'])
        self.assertEqual(offers['950000000']['event_areas'],['7'])
        self.assertEqual((by['950000000']['e4mG8jTc'],by['950000000']['uYcL8IQ1']),('4','5'))
        self.assertEqual(rows,before)


class NativeLabelPreparation(unittest.TestCase):
    setUp=harness.NativePreparation.setUp
    fixture=harness.NativePreparation.fixture
    source=harness.NativePreparation.source
    pointer=harness.NativePreparation.pointer
    assert_shared=harness.NativePreparation.assert_shared

    def saved(self,multiplier):
        data={}; economy.initialize(data); data['ios_economy']['settings']['multiplier']=multiplier
        self.config.state_file.parent.mkdir(parents=True,exist_ok=True)
        self.config.state_file.write_text(json.dumps(data))
        return data

    def reward(self,pack,table,column='dX6cor8j'):
        return master_rows(pack.lookup(pack.manifest['tables'][table.name]['path']),table.key)[0][1][column]

    def test_given_saved_policy_when_preparing_then_convert_five_masters_once_and_ignore_environment_edits(self):
        self.fixture(); self.saved(2)
        before=self.config.state_file.read_bytes()
        with patch.dict(os.environ,{'EXVIUS_LAPIS_MULTIPLIER':'999'}):
            report=prep.prepare_data(self.config)
        pack=prep.load_prepared(self.config)
        self.assertEqual(report['preparation']['economy']['source'],'campaign')
        for table in rules.ECONOMY_TABLES:
            if table.name=='F_RB_SS_MST':
                self.assertEqual(self.reward(pack,table,'dJ1g6p8h'),'50:1:40')
                self.assertEqual(self.reward(pack,table,'6Emk0agT'),'50:1:4')
            else: self.assertEqual(self.reward(pack,table),'50:1:40:100:1,20:1:3:100:1')
        with patch.dict(os.environ,{'EXVIUS_LAPIS_MULTIPLIER':'bad'}):
            self.assertTrue(prep.verify_data(self.config)['ok'])
            self.assertFalse(prep.prepare_data(self.config)['prepared_now'])
        self.assertEqual(self.config.state_file.read_bytes(),before); self.assert_shared()

    def test_given_unrelated_campaign_progress_when_verified_then_keep_prepared_settings_current_without_writes(self):
        self.fixture(); data=self.saved(5); prep.prepare_data(self.config)
        data['progress']={'unrelated':123}; self.config.state_file.write_text(json.dumps(data))
        before=self.config.state_file.read_bytes()
        with patch('pathlib.Path.mkdir',side_effect=AssertionError('query wrote')):
            self.assertTrue(prep.verify_data(self.config)['ok'])
        self.assertEqual(self.config.state_file.read_bytes(),before)

    def test_given_changed_saved_multiplier_when_prepared_again_then_rebuild_from_raw_rewards(self):
        self.fixture(); self.saved(5); prep.prepare_data(self.config); old=prep.load_prepared(self.config)
        self.saved(3); self.assertFalse(prep.verify_data(self.config)['ok'])
        self.assertEqual(prep.prepare_data(self.config)['generation'],2)
        new=prep.load_prepared(self.config); table=rules.ECONOMY_TABLES[0]
        self.assertTrue(self.reward(old,table).startswith('50:1:100:'))
        self.assertTrue(self.reward(new,table).startswith('50:1:60:'))
        self.assert_shared()

    def test_given_provisional_defaults_when_environment_changes_then_reprepare_without_initializing_campaign(self):
        self.fixture()
        with patch.dict(os.environ,{'EXVIUS_LAPIS_MULTIPLIER':'5'}): prep.prepare_data(self.config)
        with patch.dict(os.environ,{'EXVIUS_LAPIS_MULTIPLIER':'2'}):
            self.assertFalse(prep.verify_data(self.config)['ok'])
            report=prep.prepare_data(self.config)
        self.assertEqual(report['preparation']['economy']['source'],'provisional')
        self.assertEqual(report['generation'],2)
        self.assertFalse(self.config.state_file.exists())

    def test_given_corrupt_saved_settings_when_preparing_then_keep_save_and_snapshot_without_repair(self):
        self.fixture(); data=self.saved(5); prep.prepare_data(self.config); before=self.pointer().read_bytes()
        data['ios_economy']['settings']['multiplier']='bad'; self.config.state_file.write_text(json.dumps(data))
        saved=self.config.state_file.read_bytes()
        self.assertIn('economy',prep.verify_data(self.config)['error'])
        with self.assertRaisesRegex(ValueError,'economy'): prep.prepare_data(self.config)
        self.assertEqual(self.pointer().read_bytes(),before); self.assertEqual(self.config.state_file.read_bytes(),saved)

    def test_given_malformed_label_metadata_when_preparing_then_keep_current_snapshot_and_report_error(self):
        from ios_server import native_inputs
        self.fixture(); prep.prepare_data(self.config); before=self.pointer().read_bytes()
        metadata=self.root/'metadata'
        for name in native_inputs.DOCUMENTS:
            target=metadata/name; target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((native_inputs.HERE/name).read_bytes())
        (metadata/'content/revival_bundles.json').write_text('[]')
        with patch.object(native_inputs,'HERE',metadata):
            with self.assertRaisesRegex(ValueError,'metadata'): prep.prepare_data(self.config)
            self.assertIn('metadata',prep.verify_data(self.config)['error'])
        self.assertEqual(self.pointer().read_bytes(),before)

    def core_snapshot(self):
        sources={table.name:(10,self.source(table).read_bytes()) for table in rules.CORE_TABLES}
        outputs,versions,changes=rules.build(sources,1,tables=rules.CORE_TABLES)
        records={name:{'path':str(self.source(next(t for t in rules.CORE_TABLES if t.name==name)).relative_to(self.config.data)),
            'version':10,'sha256':hashlib.sha256(raw).hexdigest()} for name,(_,raw) in sources.items()}
        manifest={'version':1,'scope':'core-native-tables','reference_commit':prep.REVIVAL_COMMIT,
            'source_root':str(self.config.data),'pipeline_version':1,'generation':1,'fingerprint':'a'*64,'sources':records,'tables':{}}
        for table in rules.CORE_TABLES:
            raw=outputs[table.name]
            manifest['tables'][table.name]={'path':table.path(versions[table.name]),'version':versions[table.name],
                'source_version':10,'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                'md5':hashlib.md5(raw).hexdigest(),'changed_rows':changes[table.name]}
        prep._publish(self.config,manifest,outputs)

    def test_given_valid_core_snapshot_when_expanding_then_preserve_old_generation_and_advance_all_versions(self):
        self.fixture(); self.core_snapshot(); old=prep.load_prepared(self.config)
        self.assertEqual(len(old.files),7); self.assertFalse(prep.verify_data(self.config)['ok'])
        report=prep.prepare_data(self.config); new=prep.load_prepared(self.config)
        self.assertEqual((report['generation'],report['tables']),(2,35))
        for name,row in old.manifest['tables'].items():
            self.assertGreater(new.manifest['tables'][name]['version'],row['version'])
            self.assertEqual((old.directory/row['path']).read_bytes(),old.files[row['path']])

    def test_given_core_snapshot_and_missing_new_source_when_expanding_then_leave_old_pointer_available(self):
        self.fixture(); self.core_snapshot(); before=self.pointer().read_bytes()
        self.source(rules.ECONOMY_TABLES[0]).unlink()
        with self.assertRaisesRegex(ValueError,'Missing native'): prep.prepare_data(self.config)
        self.assertEqual(self.pointer().read_bytes(),before)
        self.assertEqual(len(prep.load_prepared(self.config).files),7)


if __name__=='__main__': unittest.main()
