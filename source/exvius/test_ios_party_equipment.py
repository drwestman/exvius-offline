"""BDD for iOS Manage Party & multi-deck UnitEquip persistence and projections."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SOURCE), str(SOURCE / 'server')]

import test_ios_summons as harness
from engine_profile import LEGACY
import revival_party_commands as party_cmd
import revival_party_domain as party_domain
import revival_party_projections as party_proj


class _FakePlayer:
    """Minimal isolated player double for pure command/projection unit BDD tests."""

    def __init__(self):
        self.mode = 'live'
        self.dirty = False
        self.data = {
            'roster': [
                {
                    'instance_id': '1795309024709',
                    'master_id': '100000102',
                    'equipment': {'1': '301000100'},
                    'materia': ['0', '0', '0', '0'],
                },
                {
                    'instance_id': '1795309024699',
                    'master_id': '100000315',
                    'equipment': {},
                    'shift_equipment': {},
                    'materia': ['0', '0', '0', '0'],
                    'shift_materia': ['0', '0', '0', '0'],
                },
                {
                    'instance_id': '1795309024719',
                    'master_id': '100000202',
                    'equipment': {},
                    'materia': ['0', '0', '0', '0'],
                },
            ],
            'party': {
                'active_deck': 0,
                'decks': [
                    {
                        'id': i,
                        'name': f'Party {i + 1}',
                        'members': (
                            [{'member_type': 0, 'disp_order': 0, 'instance_id': '1795309024709'}]
                            if i == 1 else
                            [{'member_type': 0, 'disp_order': 0, 'instance_id': '1795309024699'}]
                            if i == 2 else []
                        ),
                    }
                    for i in range(10)
                ],
            },
            'inventory': {
                'items': [{'item_type': 22, 'item_id': 504000100, 'count': 2}],
                'carry_items': [],
                'equipment': [
                    {'item_id': 301000100, 'count': 1},
                    {'item_id': 301000200, 'count': 2},
                    {'item_id': 404000200, 'count': 1},
                ],
            },
            'vision_cards': [{'user_vc_id': '9901', 'vc_id': '8000001', 'level': 1}],
        }

    def equip_item_rows(self):
        return party_proj.reconcile_equipped_counts(self)

    def materia_rows(self):
        return party_proj.reconcile_materia_counts(self)

    def set_active_deck(self, deck_id):
        if self._mutate():
            self.data['party']['active_deck'] = int(deck_id)

    def special_party(self, kind):
        special = self.data['party'].setdefault('special', {})
        if kind not in special:
            special[kind] = {
                'decks': copy.deepcopy(self.data['party']['decks']),
                'active_deck': self.data['party']['active_deck'],
                'beast_decks': {},
            }
            self.dirty = True
        return special[kind]

    def link_beast(self, deck_id, slot, esper_id):
        if self._mutate():
            slots = self.data.setdefault('beast_decks', {}).setdefault(str(deck_id), [0] * 5)
            slots[slot] = int(esper_id)

    def _mutate(self):
        if self.mode == 'frozen':
            return False
        self.dirty = True
        return True


class PartyEquipmentUnitBehavior(unittest.TestCase):
    def setUp(self):
        self.player = _FakePlayer()
        self.slots_fn = lambda _u, _s=False: 4
        self.parser = party_cmd.MultiDeckWireLoadoutParser(materia_slots_fn=self.slots_fn)
        self.store = party_cmd.PerDeckLoadoutStore(materia_slots_fn=self.slots_fn)
        self.strategy = party_proj.PerDeckEquipmentStrategy(materia_slots_fn=self.slots_fn)

    def test_given_captured_multi_deck_wire_payload_when_applied_then_update_all_decks_and_shift_forms(self):
        req = {
            'Er92Kdhm': [{
                '93Y6evuT': (
                    '1795309024709:1-301000200@2-0@3-404000200@4-0@5-0@6-0;'
                    '1795309024699:1-0@2-0@3-0@4-0@5-0@6-0|1-301000200@2-0@3-0@4-0@5-0@6-0'
                ),
                '80NUYFMJ': (
                    '1795309024709:1-504000100@2-0@3-0@4-0;'
                    '1795309024699:1-0@2-0@3-0@4-0|1-504000100@2-0@3-0@4-0'
                ),
                'nQ1iAGf3': '1795309024709:0-9901;1795309024699:0-0',
                '2c8nqLrM': '1795309024709:7;1795309024699:0',
                'w1JG7i9j': '1795309024709:0;1795309024699:1',
                'xBi3L6yR': '1',
                'r21y0YzS': '1;2',
            }]
        }
        quest_hits = []
        notes = []
        changed = party_cmd.apply_unit_equip(
            self.player,
            req,
            parser=self.parser,
            store=self.store,
            on_materia_equipped=lambda: quest_hits.append('13'),
            note_fn=notes.append,
        )
        self.assertTrue(changed)
        self.assertTrue(self.player.dirty)
        self.assertEqual(notes, [])
        self.assertEqual(quest_hits, ['13', '13'])
        deck_loadouts = self.player.data['party']['deck_loadouts']
        u_party2 = deck_loadouts['1']['1795309024709']
        u_party3 = deck_loadouts['2']['1795309024699']
        self.assertEqual(u_party2['equipment']['1'], '301000200')
        self.assertEqual(u_party2['equipment']['3'], '404000200')
        self.assertEqual(u_party2['materia'], ['504000100', '0', '0', '0'])
        self.assertEqual(u_party2['vision_card'], '0-9901')
        self.assertEqual(u_party2['skin_id'], 7)
        self.assertEqual(u_party2['brave_shift'], 0)
        self.assertEqual(u_party3['shift_equipment']['1'], '301000200')
        self.assertEqual(u_party3['shift_materia'], ['504000100', '0', '0', '0'])
        self.assertEqual(u_party3['vision_card'], '')
        self.assertEqual(u_party3['brave_shift'], 1)

    def test_given_multi_unit_and_empty_semicolon_segments_when_parsed_then_apply_every_unit(self):
        req = {
            'Er92Kdhm': [{
                'xBi3L6yR': '1',
                'r21y0YzS': '0;1;2',
                '93Y6evuT': (
                    '1795309024709:1-301000100@2-0@3-0@4-0@5-0@6-0;'
                    '1795309024699:1-301000200@2-0@3-0@4-0@5-0@6-0,'
                    '1795309024719:1-0@2-0@3-404000200@4-0@5-0@6-0;'
                ),
                'nQ1iAGf3': ';1795309024699:0-9901;',
            }]
        }
        notes = []
        changed = party_cmd.apply_unit_equip(
            self.player,
            req,
            parser=self.parser,
            store=self.store,
            note_fn=notes.append,
        )
        self.assertTrue(changed)
        self.assertEqual(notes, [])
        deck_loadouts = self.player.data['party']['deck_loadouts']
        self.assertEqual(deck_loadouts['0']['1795309024709']['equipment']['1'], '301000100')
        self.assertEqual(deck_loadouts['1']['1795309024699']['equipment']['1'], '301000200')
        self.assertEqual(deck_loadouts['1']['1795309024699']['vision_card'], '0-9901')
        self.assertEqual(deck_loadouts['1']['1795309024719']['equipment']['3'], '404000200')

    def test_given_mixed_party_types_when_applied_then_log_unsupported_and_commit_normal_party(self):
        req = {
            'Er92Kdhm': [
                {
                    'xBi3L6yR': '2',
                    'r21y0YzS': '0',
                    '93Y6evuT': '1795309024709:1-999999999@2-0@3-0@4-0@5-0@6-0',
                },
                {
                    'xBi3L6yR': '1',
                    'r21y0YzS': '1',
                    '93Y6evuT': '1795309024699:1-301000200@2-0@3-0@4-0@5-0@6-0',
                },
            ]
        }
        notes = []
        changed = party_cmd.apply_unit_equip(
            self.player,
            req,
            parser=self.parser,
            store=self.store,
            note_fn=notes.append,
        )
        self.assertTrue(changed)
        self.assertEqual(
            self.player.data['party']['deck_loadouts']['1']['1795309024699']['equipment']['1'],
            '301000200',
        )
        self.assertTrue(any("xBi3L6yR='2'" in msg and "r21y0YzS='0'" in msg for msg in notes), notes)

    def test_given_unowned_or_malformed_update_when_applied_then_preserve_state_and_emit_context(self):
        cases = [
            {
                'label': 'unowned gear',
                'req': {'Er92Kdhm': [{'xBi3L6yR': '1', 'r21y0YzS': '1',
                                      '93Y6evuT': '1795309024699:1-999000999@2-0@3-0@4-0@5-0@6-0'}]},
                'expect': ('party_type=1', 'deck=1', 'unit=1795309024699', 'equipment'),
            },
            {
                'label': 'unowned vision card',
                'req': {'Er92Kdhm': [{'xBi3L6yR': '1', 'r21y0YzS': '1',
                                      'nQ1iAGf3': '1795309024699:0-7777'}]},
                'expect': ('party_type=1', 'deck=1', 'unit=1795309024699', 'vision_card'),
            },
            {
                'label': 'segment mismatch',
                'req': {'Er92Kdhm': [{'xBi3L6yR': '1', 'r21y0YzS': '1',
                                      '93Y6evuT': '1795309024709:1-0;1795309024699:1-0'}]},
                'expect': ('party_type=1', 'deck=1', '93Y6evuT'),
            },
        ]
        for case in cases:
            with self.subTest(case=case['label']):
                before = copy.deepcopy(self.player.data)
                notes = []
                changed = party_cmd.apply_unit_equip(
                    self.player,
                    case['req'],
                    parser=self.parser,
                    store=self.store,
                    note_fn=notes.append,
                )
                self.assertFalse(changed)
                self.assertFalse(self.player.dirty)
                self.assertEqual(self.player.data, before)
                self.assertEqual(len(notes), 1)
                for fragment in case['expect']:
                    self.assertIn(fragment, notes[0])

    def test_given_action_projection_policies_when_filtered_then_keep_pure_and_symmetric(self):
        groups = {
            'B71MekS8': [{'og2GHy49': '1'}],
            'TJ9eL80N': [{'og2GHy49': '1'}],
            'DW7uH6Mn': [{'og2GHy49': '1'}],
            'VE7KZ8CY': [{'og2GHy49': '1'}],
            'wc8vSHPS': [{'og2GHy49': '1'}],
            'IqkX0gV1': [{'og2GHy49': '1'}],
            '5Eb0Rig6': [{'r21y0YzS': '0'}],
            'fqTUI1z6': [{'r21y0YzS': '0'}],
            'GV7Ej6n0': [{'r21y0YzS': '0'}],
            'zeucwm6H': [{'r21y0YzS': '0'}],
            '49rQB3fP': [{'r21y0YzS': '0'}],
            'REbh19u0': [{'r21y0YzS': '0'}],
            'qVX5Lab8': [{'r21y0YzS': '0'}],
            'g8ZuTVvQ': [{'r21y0YzS': '0'}],
            '8PEB5o7G': [{'r21y0YzS': '0'}],
            'MBPCGT84': [{'J1YX9kmM': '301000200', 'Qy5EvcK1': '2'}],
        }
        before = copy.deepcopy(self.player.data)
        spec = {'LhVz6aD2': [{}]}
        m_out = party_proj.filter_reply_groups('mRPo5n2j', spec, groups)
        self.assertEqual(m_out, spec)

        ts_out = party_proj.filter_reply_groups('TS5Dx9aZ', {**spec, 'TJ9eL80N': [{'stale': True}]}, groups)
        for tag in ('B71MekS8', 'TJ9eL80N', 'DW7uH6Mn', 'VE7KZ8CY', 'wc8vSHPS', 'IqkX0gV1'):
            self.assertNotIn(tag, ts_out)
        for tag in ('5Eb0Rig6', '49rQB3fP', '8PEB5o7G'):
            self.assertIn(tag, ts_out)

        eq_out = party_proj.filter_reply_groups('pB3st6Tg', {**spec, '5Eb0Rig6': [{'stale': True}]}, groups)
        for tag in ('5Eb0Rig6', 'fqTUI1z6', 'GV7Ej6n0', 'zeucwm6H',
                    '49rQB3fP', 'REbh19u0', 'qVX5Lab8', 'g8ZuTVvQ', '8PEB5o7G'):
            self.assertNotIn(tag, eq_out)
        for tag in ('TJ9eL80N', 'B71MekS8', 'MBPCGT84'):
            self.assertIn(tag, eq_out)

        rows = party_proj.project_equip_rows(self.player, strategy=self.strategy)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['r21y0YzS'], '1')
        self.assertEqual(rows[1]['r21y0YzS'], '2')
        self.assertEqual(rows[2]['r21y0YzS'], '0')
        self.assertFalse(self.player.dirty)
        self.assertEqual(self.player.data, before)

    def test_given_same_item_or_unit_across_decks_when_updated_then_keep_per_deck_loadouts_and_counts(self):
        # Put unit 1795309024709 into both Party 1 (deck 0) and Party 2 (deck 1).
        self.player.data['party']['decks'][0]['members'] = [
            {'member_type': 0, 'disp_order': 0, 'instance_id': '1795309024709'},
        ]
        # Give Party 1 (deck 0) and Party 2 (deck 1) distinct gear, and share the single 301000100 across two units/decks.
        self.assertTrue(party_cmd.apply_unit_equip(
            self.player,
            {
                'Er92Kdhm': [
                    {
                        'xBi3L6yR': '1',
                        'r21y0YzS': '0',
                        '93Y6evuT': '1795309024709:1-301000100@2-0@3-0@4-0@5-0@6-0',
                        '80NUYFMJ': '1795309024709:1-504000100@2-0@3-0@4-0',
                    },
                    {
                        'xBi3L6yR': '1',
                        'r21y0YzS': '1',
                        '93Y6evuT': '1795309024709:1-301000200@2-0@3-404000200@4-0@5-0@6-0',
                        '80NUYFMJ': '1795309024709:1-0@2-0@3-0@4-0',
                    },
                ]
            },
            parser=self.parser,
            store=self.store,
        ))
        self.assertTrue(party_cmd.apply_unit_equip(
            self.player,
            {
                'Er92Kdhm': [{
                    'xBi3L6yR': '1',
                    'r21y0YzS': '2',
                    '93Y6evuT': '1795309024699:1-301000100@2-0@3-0@4-0@5-0@6-0',
                }]
            },
            parser=self.parser,
            store=self.store,
        ))
        projected = {
            (r['og2GHy49'], r['r21y0YzS']): r
            for r in party_proj.project_equip_rows(self.player, strategy=self.strategy)
        }
        self.assertTrue(projected[('1795309024709', '0')]['93Y6evuT'].startswith('1-301000100@'))
        self.assertTrue(projected[('1795309024709', '1')]['93Y6evuT'].startswith('1-301000200@2-0@3-404000200@'))
        self.assertTrue(projected[('1795309024699', '2')]['93Y6evuT'].startswith('1-301000100@'))

        # Ownership reconciliation does not mint phantom copies when 1 item is reused in two separate decks.
        owned_gear = {r['J1YX9kmM']: int(r['Qy5EvcK1']) for r in self.player.equip_item_rows()}
        self.assertEqual(owned_gear['301000100'], 1)
        owned_mat = {r['H5jBL0Vf']: int(r['Qy5EvcK1']) for r in self.player.materia_rows()}
        self.assertEqual(owned_mat['504000100'], 2)

    def test_given_pre_track_b_save_when_party2_edits_then_party1_and_party3_preserve_loadouts_and_skip_starter_clones(self):
        # Mirror a real campaign save: active_deck=1, customized decks 0/1/2, starter-clone decks 3..9, no deck_loadouts.
        self.player.data['party']['active_deck'] = 1
        self.player.data['party']['decks'][0]['members'] = [
            {'member_type': 1, 'disp_order': 0, 'instance_id': '1795309024719'},
            {'member_type': 0, 'disp_order': 1, 'instance_id': '1795309024709'},
            {'member_type': 0, 'disp_order': 2, 'instance_id': '1795309024699'},
        ]
        # Shared unit 1795309024699 appears in decks 0 and 2; starter pair appears untouched in decks 3..9.
        for i in range(3, 10):
            self.player.data['party']['decks'][i]['members'] = [
                {'member_type': 1, 'disp_order': 0, 'instance_id': '1795309024719'},
                {'member_type': 0, 'disp_order': 1, 'instance_id': '1795309024709'},
            ]
        self.player.data['roster'][1]['equipment'] = {'1': '301000200'}

        # Read-only boot projection immediately emits deck 0 and deck 2 gear without cloning starter decks 3..9.
        before_rows = {
            (r['og2GHy49'], r['r21y0YzS']): r
            for r in party_proj.project_equip_rows(self.player, strategy=self.strategy)
        }
        self.assertTrue(before_rows[('1795309024709', '0')]['93Y6evuT'].startswith('1-301000100@'))
        self.assertTrue(before_rows[('1795309024699', '2')]['93Y6evuT'].startswith('1-301000200@'))
        self.assertTrue(before_rows[('1795309024709', '3')]['93Y6evuT'].startswith('1-0@'))

        # First Track B write updates Party 2 (deck 1) and must snapshot decks 0 and 2 beforehand.
        self.assertTrue(party_cmd.apply_unit_equip(
            self.player,
            {'Er92Kdhm': [{'xBi3L6yR': '1', 'r21y0YzS': '1',
                           '93Y6evuT': '1795309024709:1-301000200@2-0@3-0@4-0@5-0@6-0'}]},
            parser=self.parser,
            store=self.store,
        ))
        deck_loadouts = self.player.data['party']['deck_loadouts']
        self.assertEqual(deck_loadouts['0']['1795309024709']['equipment']['1'], '301000100')
        self.assertEqual(deck_loadouts['1']['1795309024709']['equipment']['1'], '301000200')
        self.assertEqual(deck_loadouts['2']['1795309024699']['equipment']['1'], '301000200')
        self.assertNotIn('3', deck_loadouts)

    def test_given_partial_loadout_across_decks_when_active_deck_switches_then_clear_stale_roster_fields(self):
        uid = '1795309024699'
        unit = next(u for u in self.player.data['roster'] if u['instance_id'] == uid)
        unit.pop('shift_equipment', None)
        unit.pop('shift_materia', None)
        self.player.data['party']['decks'][0]['members'] = [
            {'member_type': 0, 'disp_order': 0, 'instance_id': uid},
        ]
        self.player.data['party']['decks'][1]['members'] = [
            {'member_type': 0, 'disp_order': 0, 'instance_id': uid},
        ]
        # Party 1 equips gear, materia, VC, skin, brave shift, and shift gear.
        self.assertTrue(party_cmd.apply_unit_equip(
            self.player,
            {'Er92Kdhm': [{
                'xBi3L6yR': '1',
                'r21y0YzS': '0',
                '93Y6evuT': f'{uid}:1-301000100@2-0@3-0@4-0@5-0@6-0|1-301000200@2-0@3-0@4-0@5-0@6-0',
                '80NUYFMJ': f'{uid}:1-504000100@2-0@3-0@4-0|1-504000100@2-0@3-0@4-0',
                'nQ1iAGf3': f'{uid}:0-9901',
                '2c8nqLrM': f'{uid}:5',
                'w1JG7i9j': f'{uid}:1',
            }]},
            parser=self.parser,
            store=self.store,
        ))
        # Party 2 equips ONLY a different weapon on the same unit.
        self.assertTrue(party_cmd.apply_unit_equip(
            self.player,
            {'Er92Kdhm': [{
                'xBi3L6yR': '1',
                'r21y0YzS': '1',
                '93Y6evuT': f'{uid}:1-404000200@2-0@3-0@4-0@5-0@6-0',
            }]},
            parser=self.parser,
            store=self.store,
        ))
        self.assertTrue(party_cmd.apply_party_deck_edit(
            self.player,
            json.dumps({
                'CN92arJK': [{'r21y0YzS': '1', 'xBi3L6yR': '1'}],
                '5Eb0Rig6': [{'r21y0YzS': '1', '2A6fYiEC': f'0:0:{uid}'}],
            }),
            materia_slots_fn=self.slots_fn,
        ))
        unit = next(u for u in self.player.data['roster'] if u['instance_id'] == uid)
        self.assertEqual(unit['equipment'], {'1': '404000200', '2': '0', '3': '0', '4': '0', '5': '0', '6': '0'})
        self.assertEqual(unit['materia'], ['0', '0', '0', '0'])
        self.assertEqual(unit['vision_card'], '')
        self.assertEqual(unit['brave_shift'], 0)
        self.assertNotIn('skin_id', unit)
        self.assertNotIn('shift_equipment', unit)
        self.assertNotIn('shift_materia', unit)
        self.assertNotIn('shift_vision_card', unit)

        # Switching to a deck with no deck_loadouts entry (e.g., Party 3) also clears stale active gear on roster.
        self.player.data['party']['decks'][2]['members'] = [{'member_type': 0, 'disp_order': 0, 'instance_id': uid}]
        del self.player.data['party']['deck_loadouts']['2']
        self.assertTrue(party_cmd.apply_party_deck_edit(
            self.player,
            json.dumps({
                'CN92arJK': [{'r21y0YzS': '2', 'xBi3L6yR': '1'}],
                '5Eb0Rig6': [{'r21y0YzS': '2', '2A6fYiEC': f'0:0:{uid}'}],
            }),
            materia_slots_fn=self.slots_fn,
        ))
        unit = next(u for u in self.player.data['roster'] if u['instance_id'] == uid)
        self.assertEqual(unit['equipment'], {})
        self.assertEqual(unit['materia'], ['0', '0', '0', '0'])

    def test_given_non_active_or_special_deck_brave_shift_when_edited_then_keep_decks_and_roster_isolated(self):
        uid = '1795309024699'
        self.player.data['party']['decks'][0]['members'] = [{'member_type': 0, 'disp_order': 0, 'instance_id': uid}]
        self.player.data['party']['decks'][1]['members'] = [{'member_type': 0, 'disp_order': 0, 'instance_id': uid}]
        # Non-active deck 1 updates brave_shift to 1 while active deck 0 keeps 0; roster must stay 0.
        self.assertTrue(party_cmd.apply_party_deck_edit(
            self.player,
            json.dumps({
                'CN92arJK': [{'r21y0YzS': '0', 'xBi3L6yR': '1'}],
                '5Eb0Rig6': [
                    {'r21y0YzS': '0', '2A6fYiEC': f'0:0:{uid}', 'w1JG7i9j': f'{uid}:0'},
                    {'r21y0YzS': '1', '2A6fYiEC': f'0:0:{uid}', 'w1JG7i9j': f'{uid}:1'},
                ],
            }),
            materia_slots_fn=self.slots_fn,
        ))
        unit = next(u for u in self.player.data['roster'] if u['instance_id'] == uid)
        self.assertEqual(unit.get('brave_shift', 0), 0)
        self.assertEqual(self.player.data['party']['deck_loadouts']['1'][uid]['brave_shift'], 1)

        # Special party w1JG7i9j updates special party loadouts without mutating normal roster brave_shift.
        self.assertTrue(party_cmd.apply_party_deck_edit(
            self.player,
            json.dumps({
                'CN92arJK': [{'b61ICxJk': '0', 'xBi3L6yR': '8'}],
                '5Eb0Rig6': [{'r21y0YzS': '0', '2A6fYiEC': f'0:0:{uid}', 'w1JG7i9j': f'{uid}:1'}],
            }),
            materia_slots_fn=self.slots_fn,
        ))
        self.assertEqual(unit.get('brave_shift', 0), 0)
        self.assertEqual(self.player.data['party']['special']['8']['loadouts'][uid]['brave_shift'], 1)

    def test_given_swapped_party_member_when_reconciling_counts_then_no_phantom_copies_minted(self):
        uid_a, uid_b = '1795309024709', '1795309024699'
        self.player.data['party']['decks'][0]['members'] = [{'member_type': 0, 'disp_order': 0, 'instance_id': uid_a}]
        self.assertTrue(party_cmd.apply_unit_equip(
            self.player,
            {'Er92Kdhm': [{'xBi3L6yR': '1', 'r21y0YzS': '0',
                           '93Y6evuT': f'{uid_a}:1-301000100@2-0@3-0@4-0@5-0@6-0'}]},
            parser=self.parser,
            store=self.store,
        ))
        # Swap uid_a out of Party 1 and put uid_b into Party 1, then equip the single 301000100 onto uid_b.
        self.assertTrue(party_cmd.apply_party_deck_edit(
            self.player,
            json.dumps({
                'CN92arJK': [{'r21y0YzS': '0', 'xBi3L6yR': '1'}],
                '5Eb0Rig6': [{'r21y0YzS': '0', '2A6fYiEC': f'0:0:{uid_b}'}],
            }),
            materia_slots_fn=self.slots_fn,
        ))
        self.assertTrue(party_cmd.apply_unit_equip(
            self.player,
            {'Er92Kdhm': [{'xBi3L6yR': '1', 'r21y0YzS': '0',
                           '93Y6evuT': f'{uid_b}:1-301000100@2-0@3-0@4-0@5-0@6-0'}]},
            parser=self.parser,
            store=self.store,
        ))
        owned_gear = {r['J1YX9kmM']: int(r['Qy5EvcK1']) for r in self.player.equip_item_rows()}
        self.assertEqual(owned_gear['301000100'], 1)
        inv_entry = next(e for e in self.player.data['inventory']['equipment'] if str(e['item_id']) == '301000100')
        self.assertEqual(inv_entry['count'], 1)

    def test_given_track_a_strategy_and_store_when_applied_then_preserve_substitutability(self):
        track_a_store = party_cmd.GlobalRosterLoadoutStore()
        track_a_proj = party_proj.GlobalRosterEquipmentStrategy(materia_slots_fn=self.slots_fn)
        self.assertTrue(party_cmd.apply_unit_equip(
            self.player,
            {'Er92Kdhm': [{'xBi3L6yR': '1', 'r21y0YzS': '1',
                           '93Y6evuT': '1795309024699:1-301000200@2-0@3-0@4-0@5-0@6-0'}]},
            parser=self.parser,
            store=track_a_store,
        ))
        rows = party_proj.project_equip_rows(self.player, strategy=track_a_proj)
        self.assertEqual(len(rows), len(self.player.data['roster']))
        u2_row = next(r for r in rows if r['og2GHy49'] == '1795309024699')
        self.assertTrue(u2_row['93Y6evuT'].startswith('1-301000200@'))
        self.assertNotIn('deck_loadouts', self.player.data['party'])

    def test_given_cqrs_boundaries_when_inspected_then_commands_and_projections_decoupled(self):
        import inspect
        cmd_source = inspect.getsource(party_cmd)
        proj_source = inspect.getsource(party_proj)
        self.assertNotIn('revival_party_projections', cmd_source)
        self.assertNotIn('._format_equip_row', proj_source)
        self.assertNotIn('._build_equip_rows', proj_source)
        self.assertNotIn('._items', proj_source)
        self.assertIs(party_domain.is_untouched_starter_deck.__module__, party_domain.__name__)


class PartyEquipmentIntegration(unittest.TestCase):
    setUp = harness.ReplaySummonIntegration.setUp
    prepared_data = harness.ReplaySummonIntegration.prepared_data
    child = harness.ReplaySummonIntegration.child
    run_engine = harness.ReplaySummonIntegration.run_engine
    extra_units = (('100000315', 5), ('100000337', 5))
    extra_items = ('1209001554',)
    unit_fields = {
        '100000315': {'19ykfMgL': '4', 'JPW8Vs40': '100000315', 'I3SKJ4q0': '0'},
        '100000337': {'19ykfMgL': '4', 'JPW8Vs40': '100000315', 'I3SKJ4q0': '1'},
    }

    def write_masters(self, masters):
        harness.ReplaySummonIntegration.write_masters(self, masters)
        (masters / 'F_EQUIP_ITEM_MST.ndjson').write_text('\n'.join(
            json.dumps({'J1YX9kmM': mid, 'bz6RS3pI': '10'})
            for mid in ('301000100', '301000200', '302000100', '404000200', '406000100', '409000100', '403046900')
        ))
        (masters / 'F_MEDAL_EXCHANGE_MST.ndjson').write_text(json.dumps({
            'S21FT3L8': '990001', 'ak2dhKm3': '1209001554', 'Qy5EvcK1': '1',
            '7iJpH5zZ': '10:100031007:1:100', 'kR4n5DxP': '1', 'x0NDnEC9': '1',
        }))
        (masters / 'F_MATERIA_MST.ndjson').write_text(json.dumps({'H5jBL0Vf': '504000100', 'bz6RS3pI': '10'}))
        (masters / 'F_STORE_ITEM_MST.ndjson').write_text('')
        (masters / 'F_GACHA_STORE_MST.ndjson').write_text('')
        (masters / 'F_BEAST_STATUS_MST.ndjson').write_text(json.dumps({
            'Iwfx42Wo': '1', 'woghJa61': '1', '9fW0TePj': '1',
            'em5hx4FX': '100,200', 'L0MX7edB': '50,100', 'o7Ynu1XP': '10,200',
            '6tyb58Kc': '10,20', 'Y9H6TWnv': '10,20', 'sa8Ewx3H': '10,20',
        }))
        (masters / 'F_RB_SS_MST.ndjson').write_text(json.dumps({
            '6Z9DxQFf': '1', 'VjJQ51uG': '2016-12-15 04:00:00', 'uo0xmn8b': '',
            'dJ1g6p8h': '50:1:20',
        }))
        (masters / 'F_RB_SS_REWARD_MST.ndjson').write_text(json.dumps({
            '6Z9DxQFf': '1', 'vs48LZrt': '0', 'ip94Nqb7': '1', 'XM4Ca3PF': '300000', 'dX6cor8j': '50:1:10',
        }))
        (masters / 'F_RB_AI_PATTERN_MST.ndjson').write_text(json.dumps({'UE3vKA5y': '1', 'ixDq7yJ8': '100'}))
        (masters / 'F_RB_TRADE_BOARD_MST.ndjson').write_text(json.dumps({'6m4Rn5jd': '1', 'dX6cor8j': '50:1:20'}))
        (masters / 'F_RB_TRADE_BOARD_PIECE_MST.ndjson').write_text(json.dumps({
            'AyCR5h7s': '11', '6m4Rn5jd': '1', 'pgS67dFz': '0', '1XRtI2d9': '0:0',
            '3h9XCMqj': '11', 'mRY52Tib': '1', 'i9w6ZCFM': '50:1:20',
        }))

    def test_given_manage_party_exit_chain_when_reloaded_then_party2_equipment_persists(self):
        self.run_engine('''
import ffbe_pipeline
assert ffbe_pipeline.validate_pipeline() == []
edges = {(e.before, e.after) for e in ffbe_pipeline.PIPELINE_EDGES}
assert ('apply_party_edit', 'apply_to_reply') in edges
assert ('serve_actions', 'apply_to_reply') in edges

u_party1 = str(player.data['roster'][0]['instance_id'])
u_party2 = str(player.grant_unit('100000315')['instance_id'])
u_party3 = str(player.grant_unit('100000337')['instance_id'])
starter_item = next(v for v in player.data['roster'][0]['equipment'].values() if v != '0')
player.grant_equipment(302000100, 2)
player.grant_equipment(404000200, 1)
player.grant_item(22, 504000100, 2)
player.data.setdefault('vision_cards', []).append({'user_vc_id': '9901', 'vc_id': '8000001', 'level': 1})
player.save(str(config.state_file))

sw_reply = request('UpdateSwitchInfoRequest', {'0jqUZuT1': [{'dIPkNn61': '10000000'}]})
for tag in ('B71MekS8', 'TJ9eL80N', '5Eb0Rig6', '49rQB3fP'):
    assert tag not in sw_reply, (tag, sw_reply)

party_reply = request('PartyDeckEditRequest', {
    'CN92arJK': [{'r21y0YzS': '2', 'xBi3L6yR': '1'}],
    '5Eb0Rig6': [
        {'r21y0YzS': '0', 'G4L0YIB2': 'Party 1', '2A6fYiEC': f'0:0:{u_party1}'},
        {'r21y0YzS': '1', 'G4L0YIB2': 'Party 2', '2A6fYiEC': f'0:0:{u_party2}', 'w1JG7i9j': f'{u_party2}:1'},
        {'r21y0YzS': '2', 'G4L0YIB2': 'Party 3', '2A6fYiEC': f'0:0:{u_party3}', 'w1JG7i9j': f'{u_party3}:0'},
    ],
})
for tag in ('B71MekS8', 'TJ9eL80N', 'DW7uH6Mn', 'VE7KZ8CY', 'wc8vSHPS', 'IqkX0gV1'):
    assert tag not in party_reply, tag
assert party_reply['8PEB5o7G'][0]['r21y0YzS'] == '2'
assert party_reply['5Eb0Rig6'][1]['2A6fYiEC'] == f'0:0:{u_party2}'

equip_reply = request('UnitEquipRequest', {
    'Er92Kdhm': [{
        '93Y6evuT': (
            f'{u_party2}:1-302000100@2-0@3-404000200@4-0@5-0@6-0;'
            f'{u_party3}:1-0@2-0@3-0@4-0@5-0@6-0|1-302000100@2-0@3-0@4-0@5-0@6-0'
        ),
        '80NUYFMJ': (
            f'{u_party2}:1-504000100@2-0@3-0@4-0;'
            f'{u_party3}:1-0@2-0@3-0@4-0|1-504000100@2-0@3-0@4-0'
        ),
        'nQ1iAGf3': f'{u_party2}:0-9901;{u_party3}:0-0',
        '2c8nqLrM': f'{u_party2}:5;{u_party3}:0',
        'xBi3L6yR': '1',
        'r21y0YzS': '1;2',
    }]
})
for tag in ('5Eb0Rig6', 'fqTUI1z6', 'GV7Ej6n0', 'zeucwm6H',
            '49rQB3fP', 'REbh19u0', 'qVX5Lab8', 'g8ZuTVvQ', '8PEB5o7G'):
    assert tag not in equip_reply, tag
assert 'TJ9eL80N' in equip_reply and 'MBPCGT84' in equip_reply

# Swap/clear starter item on Party 1 unit and verify starter item stays owned.
request('UnitEquipRequest', {
    'Er92Kdhm': [{
        '93Y6evuT': f'{u_party1}:1-0@2-0@3-0@4-0@5-0@6-0',
        'xBi3L6yR': '1',
        'r21y0YzS': '0',
    }]
})
saved_before_read = config.state_file.read_bytes()
login = request('GetUserInfoRequest')
assert config.state_file.read_bytes() == saved_before_read
owned_gear = {row['J1YX9kmM']: int(row['Qy5EvcK1']) for row in login['MBPCGT84']}
assert owned_gear[starter_item] >= 1
assert owned_gear['302000100'] >= 2
(config.root / 'expected_ids.json').write_text(json.dumps({'u2': u_party2, 'u3': u_party3}))
''')
        # Fresh Engine process to verify full server + app restart persistence.
        restart = self.child('''
import json, sys
from pathlib import Path
sys.path[:0] = sys.argv[1:3]
from ios_server.config import Configuration
from ios_server.engine import Engine
from local_game import LocalGame
import ffbe_crypto as crypto

config = Configuration(Path(sys.argv[3]), Path(sys.argv[4]))
ids = json.loads((config.root / 'expected_ids.json').read_text())
endpoints = json.loads((Path(sys.argv[2]) / 'endpoints.json').read_text())['by_class']
engine = Engine(config)
try:
    engine.initialize()
    endpoint = endpoints['GetUserInfoRequest']
    key = crypto.key16(endpoint['encode_key'])
    env = {'TEAYk6R1': {'z5hB3P01': endpoint['request_id'], 'ytHoz4E2': '1', '9K0Pzcpd': '1167'},
           't7n6cVWf': {'qrVcDe48': crypto.cbc_encrypt(key, b'{}', double_pad=True)}}
    resp = LocalGame.request(engine, 'POST', endpoint['url'], json.dumps(env))
    raw = crypto.cbc_decrypt(key, json.loads(resp.body)['t7n6cVWf']['qrVcDe48'])
    if raw and 1 <= raw[-1] <= 16 and raw[-raw[-1]:] == bytes([raw[-1]]) * raw[-1]:
        raw = raw[:-raw[-1]]
    reloaded = json.loads(raw)
    eq_by_unit = {(row['og2GHy49'], row['r21y0YzS']): row for row in reloaded['TJ9eL80N']}
    u_party2, u_party3 = ids['u2'], ids['u3']
    assert eq_by_unit[(u_party2, '1')]['93Y6evuT'].startswith('1-302000100@2-0@3-404000200@'), eq_by_unit[(u_party2, '1')]
    assert eq_by_unit[(u_party2, '1')]['80NUYFMJ'].startswith('1-504000100@'), eq_by_unit[(u_party2, '1')]
    assert eq_by_unit[(u_party2, '1')]['nQ1iAGf3'] == '0-9901', eq_by_unit[(u_party2, '1')]
    assert eq_by_unit[(u_party2, '1')]['2c8nqLrM'] == '5', eq_by_unit[(u_party2, '1')]
    assert '|1-302000100@' in eq_by_unit[(u_party3, '2')]['93Y6evuT'], eq_by_unit[(u_party3, '2')]
    assert '|1-504000100@' in eq_by_unit[(u_party3, '2')]['80NUYFMJ'], eq_by_unit[(u_party3, '2')]
    deck2 = next(d for d in reloaded['5Eb0Rig6'] if d['r21y0YzS'] == '1')
    assert deck2['2A6fYiEC'] == f'0:0:{u_party2}', deck2
    assert deck2['w1JG7i9j'] == f'{u_party2}:1', deck2
finally:
    engine.close()
''', str(self.config.root), str(self.config.data))
        self.assertEqual(restart.returncode, 0, restart.stdout + restart.stderr)

    def test_given_reverse_equip_then_party_edit_with_espers_when_reloaded_then_both_persist(self):
        self.run_engine('''
u_party2 = str(player.grant_unit('100000315')['instance_id'])
player.grant_equipment(302000100, 1)
player.grant_beast('1', rarity=1, level=1)
player.save(str(config.state_file))

eq_reply = request('UnitEquipRequest', {
    'Er92Kdhm': [{
        'xBi3L6yR': '1',
        'r21y0YzS': '1',
        '93Y6evuT': f'{u_party2}:1-302000100@2-0@3-0@4-0@5-0@6-0',
    }]
})
for tag in ('5Eb0Rig6', '49rQB3fP', '8PEB5o7G'):
    assert tag not in eq_reply, tag

party_reply = request('PartyDeckEditRequest', {
    'CN92arJK': [{'r21y0YzS': '1', 'xBi3L6yR': '1'}],
    '5Eb0Rig6': [{'r21y0YzS': '1', 'G4L0YIB2': 'Second', '2A6fYiEC': f'0:0:{u_party2}'}],
    '49rQB3fP': [{'r21y0YzS': '1', 'XZ4Kh7Ic': '0:1,1:0,2:0,3:0,4:0'}],
})
assert '5Eb0Rig6' in party_reply and '49rQB3fP' in party_reply and 'TJ9eL80N' not in party_reply
reloaded = request('GetUserInfoRequest')
eq_row = next(r for r in reloaded['TJ9eL80N'] if r['og2GHy49'] == u_party2 and r['r21y0YzS'] == '1')
assert eq_row['93Y6evuT'].startswith('1-302000100@')
beast_row = next(r for r in reloaded['49rQB3fP'] if r['r21y0YzS'] == '1')
assert beast_row['XZ4Kh7Ic'] == '0:1,1:0,2:0,3:0,4:0'
''')

    def test_given_pre_track_b_party1_and_party2_when_party2_saves_then_both_parties_keep_distinct_gear_and_migrate(self):
        self.run_engine('''
from player_state import PlayerState, state_coherence_issues
u_p1 = str(player.data['roster'][0]['instance_id'])
u_shared = str(player.grant_unit('100000315')['instance_id'])
u_p2 = str(player.grant_unit('100000337')['instance_id'])
player.grant_equipment(301000200, 1)
player.grant_equipment(404000200, 1)
player.grant_item(22, 504000100, 1)

# Simulate existing Track A save before deck_loadouts exists: Party 1 wears 302000100, active_deck becomes 1.
p1_shared_equip = {'1': '302000100', '2': '0', '3': '0', '4': '0', '5': '0', '6': '0'}
player.roster_row(u_shared)['equipment'] = dict(p1_shared_equip)
player.data['party']['decks'][0]['members'] = [
    {'member_type': 0, 'disp_order': 0, 'instance_id': u_p1},
    {'member_type': 1, 'disp_order': 1, 'instance_id': u_shared},
]
player.data['party']['decks'][1]['members'] = [
    {'member_type': 0, 'disp_order': 0, 'instance_id': u_shared},
    {'member_type': 1, 'disp_order': 1, 'instance_id': u_p2},
]
player.set_active_deck('1')
player.save(str(config.state_file))

# Immediately on boot (before any edit), TJ9eL80N exposes BOTH r21y0YzS="0" and r21y0YzS="1".
boot_login = request('GetUserInfoRequest')
boot_rows = {(r['og2GHy49'], r['r21y0YzS']): r for r in boot_login['TJ9eL80N']}
assert boot_rows[(u_p1, '0')]['93Y6evuT'].startswith('1-302000100@'), boot_rows
assert boot_rows[(u_shared, '0')]['93Y6evuT'].startswith('1-302000100@'), boot_rows

# Edit Party 2 (r21y0YzS="1") with DIFFERENT gear on u_shared and u_p2 while active_deck="1".
request('UpdateSwitchInfoRequest', {'0jqUZuT1': [{'dIPkNn61': '10000000'}]})
request('PartyDeckEditRequest', {
    'CN92arJK': [{'r21y0YzS': '1', 'xBi3L6yR': '1'}],
    '5Eb0Rig6': [{'r21y0YzS': '1', 'G4L0YIB2': 'Party 2', '2A6fYiEC': f'0:0:{u_shared},1:1:{u_p2}'}],
})
eq_reply = request('UnitEquipRequest', {
    'Er92Kdhm': [{
        'xBi3L6yR': '1',
        'r21y0YzS': '1',
        '93Y6evuT': (
            f'{u_shared}:1-301000200@2-0@3-0@4-0@5-0@6-0,'
            f'{u_p2}:1-0@2-0@3-404000200@4-0@5-0@6-0'
        ),
        '80NUYFMJ': f'{u_shared}:1-504000100@2-0@3-0@4-0,{u_p2}:1-0@2-0@3-0@4-0',
    }]
})
reply_rows = {(r['og2GHy49'], r['r21y0YzS']): r for r in eq_reply['TJ9eL80N']}
# Party 2 saves its new gear AND Party 1 remains present and intact in the UnitEquipResponse!
assert reply_rows[(u_p1, '0')]['93Y6evuT'].startswith('1-302000100@')
assert reply_rows[(u_shared, '0')]['93Y6evuT'].startswith('1-302000100@')
assert reply_rows[(u_shared, '1')]['93Y6evuT'].startswith('1-301000200@')
assert reply_rows[(u_shared, '1')]['80NUYFMJ'].startswith('1-504000100@')
assert reply_rows[(u_p2, '1')]['93Y6evuT'].startswith('1-0@2-0@3-404000200@')

# Switching back to Party 1 mirrors Party 1 gear onto roster for battle/Arena while preserving Party 2.
request('PartyDeckEditRequest', {
    'CN92arJK': [{'r21y0YzS': '0', 'xBi3L6yR': '1'}],
    '5Eb0Rig6': [{'r21y0YzS': '0', 'G4L0YIB2': 'Party 1', '2A6fYiEC': f'0:0:{u_p1},1:1:{u_shared}'}],
})
assert player.roster_row(u_shared)['equipment']['1'] == '302000100'
assert state_coherence_issues(player.data) == []

# Converting an unrelated/displaced unit drops any dangling deck_loadouts entry cleanly.
u_extra = str(player.grant_unit('100000315')['instance_id'])
player.data['party']['deck_loadouts']['1'][u_extra] = {'equipment': {'1': '301000200'}}
assert player.drop_units([u_extra]) == [u_extra]
assert u_extra not in player.data['party']['deck_loadouts']['1']
player.save(str(config.state_file))
(config.root / 'expected_track_b.json').write_text(json.dumps({
    'u_p1': u_p1, 'u_shared': u_shared, 'u_p2': u_p2,
}))
''')
        restart = self.child('''
import json, sys
from pathlib import Path
sys.path[:0] = sys.argv[1:3]
from ios_server.config import Configuration
from ios_server.engine import Engine
from local_game import LocalGame
import ffbe_crypto as crypto

config = Configuration(Path(sys.argv[3]), Path(sys.argv[4]))
ids = json.loads((config.root / 'expected_track_b.json').read_text())
endpoints = json.loads((Path(sys.argv[2]) / 'endpoints.json').read_text())['by_class']
engine = Engine(config)
try:
    engine.initialize()
    from player_state import PlayerState, state_coherence_issues
    endpoint = endpoints['GetUserInfoRequest']
    key = crypto.key16(endpoint['encode_key'])
    env = {'TEAYk6R1': {'z5hB3P01': endpoint['request_id'], 'ytHoz4E2': '1', '9K0Pzcpd': '1167'},
           't7n6cVWf': {'qrVcDe48': crypto.cbc_encrypt(key, b'{}', double_pad=True)}}
    resp = LocalGame.request(engine, 'POST', endpoint['url'], json.dumps(env))
    raw = crypto.cbc_decrypt(key, json.loads(resp.body)['t7n6cVWf']['qrVcDe48'])
    if raw and 1 <= raw[-1] <= 16 and raw[-raw[-1]:] == bytes([raw[-1]]) * raw[-1]:
        raw = raw[:-raw[-1]]
    reloaded = json.loads(raw)
    rows = {(r['og2GHy49'], r['r21y0YzS']): r for r in reloaded['TJ9eL80N']}
    u_p1, u_shared, u_p2 = ids['u_p1'], ids['u_shared'], ids['u_p2']
    assert rows[(u_p1, '0')]['93Y6evuT'].startswith('1-302000100@')
    assert rows[(u_shared, '0')]['93Y6evuT'].startswith('1-302000100@')
    assert rows[(u_shared, '1')]['93Y6evuT'].startswith('1-301000200@')
    assert rows[(u_shared, '1')]['80NUYFMJ'].startswith('1-504000100@')
    assert rows[(u_p2, '1')]['93Y6evuT'].startswith('1-0@2-0@3-404000200@')
    assert state_coherence_issues(PlayerState.load(str(config.state_file)).data) == []
finally:
    engine.close()
''', str(self.config.root), str(self.config.data))
        self.assertEqual(restart.returncode, 0, restart.stdout + restart.stderr)

    def test_given_save_failure_or_unowned_item_when_encrypted_command_runs_then_rollback_atomically(self):
        self.run_engine('''
from player_state import PlayerState
u_party2 = str(player.grant_unit('100000315')['instance_id'])
player.grant_equipment(301000200, 1)
player.save(str(config.state_file))

before = copy.deepcopy(player.data)
raw = config.state_file.read_bytes()

# Unowned equipment is refused without changing state or file.
request('UnitEquipRequest', {
    'Er92Kdhm': [{'xBi3L6yR': '1', 'r21y0YzS': '1',
                  '93Y6evuT': f'{u_party2}:1-999000999@2-0@3-0@4-0@5-0@6-0'}]
})
assert player.data == before and config.state_file.read_bytes() == raw

# Persistence failure rolls back both UnitEquipRequest and PartyDeckEditRequest.
with patch.object(PlayerState, 'save', return_value=False):
    for cls, body in (
        ('UnitEquipRequest', {'Er92Kdhm': [{'xBi3L6yR': '1', 'r21y0YzS': '1',
                                            '93Y6evuT': f'{u_party2}:1-301000200@2-0@3-0@4-0@5-0@6-0'}]}),
        ('PartyDeckEditRequest', {'CN92arJK': [{'r21y0YzS': '1', 'xBi3L6yR': '1'}],
                                  '5Eb0Rig6': [{'r21y0YzS': '1', 'G4L0YIB2': 'Fail', '2A6fYiEC': f'0:0:{u_party2}'}]}),
    ):
        try:
            request(cls, body)
        except OSError:
            pass
        else:
            raise AssertionError(cls + ' succeeded despite failed save')
assert player.data == before and config.state_file.read_bytes() == raw
''')

    def test_given_legacy_profile_when_party_and_equip_run_then_behavior_stays_unchanged(self):
        static, _ = self.prepared_data()
        self.write_masters(static / 'mst_decoded')
        result = self.child('''
import json, os, sys
from pathlib import Path
from unittest.mock import patch
sys.path[:0] = sys.argv[1:3]
os.environ['FFBE_DATA'] = sys.argv[3]
os.environ['EXVIUS_ENGINE_PROFILE'] = 'legacy'
from engine_profile import current_profile
assert current_profile() == LEGACY if hasattr(sys, 'NEVER') else current_profile().name == 'legacy'
import ffbe_state as st
from player_state import PlayerState
from exvius_actions import unit_equip
from ffbe_player import apply_party_edit

st.STATE_PERSIST = False
p = st.State.player = PlayerState.load('/nonexistent', slot='legacy-check')
iid1 = str(p.data['roster'][0]['instance_id'])
iid2 = str(p.data['roster'][1]['instance_id'])
p.grant_equipment(301000200, 1)

# Legacy apply_to_reply retains legacy TS5Dx9aZ and pB3st6Tg shapes.
ts_reply = p.apply_to_reply({'LhVz6aD2': [{}]}, reply_id='TS5Dx9aZ')
eq_reply = p.apply_to_reply({'LhVz6aD2': [{}]}, reply_id='pB3st6Tg')
assert 'TJ9eL80N' in ts_reply and '5Eb0Rig6' in ts_reply
assert '5Eb0Rig6' not in eq_reply and '49rQB3fP' in eq_reply and '8PEB5o7G' in eq_reply

# Legacy unit_equip rejects semicolon multi-deck string as before.
st.NOTES.clear()
unit_equip({'LhVz6aD2': [{}]}, {'Er92Kdhm': [{
    'xBi3L6yR': '1', 'r21y0YzS': '0;1',
    '93Y6evuT': f'{iid1}:1-301000200@2-0@3-0@4-0@5-0@6-0;{iid2}:1-0@2-0@3-0@4-0@5-0@6-0',
}]})
assert st.NOTES == ['unit-equip: invalid equipment update'], st.NOTES

# Legacy apply_party_edit still works identically.
apply_party_edit(json.dumps({'CN92arJK': [{'r21y0YzS': '1', 'xBi3L6yR': '1'}],
                             '5Eb0Rig6': [{'r21y0YzS': '1', '2A6fYiEC': f'0:0:{iid1}'}]}))
assert p.data['party']['active_deck'] == 1
''', str(static))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_given_corrupt_deck_loadouts_when_checked_then_state_coherence_issues_reports_every_invariant(self):
        self.run_engine('''
from player_state import state_coherence_issues
u1 = str(player.data['roster'][0]['instance_id'])
player.data['party']['deck_loadouts'] = {'0': {u1: {'equipment': {'1': '301000100'}}}}
assert state_coherence_issues(player.data) == []

bad_cases = [
    ('not an object', 'bad', 'party.deck_loadouts is not an object'),
    ('missing deck', {'99': {}}, "references missing deck '99'"),
    ('deck not object', {'0': []}, "party.deck_loadouts['0'] is not an object"),
    ('non-roster unit', {'0': {'9999999999999': {}}}, "references non-roster instance '9999999999999'"),
    ('unit not object', {'0': {u1: []}}, f"party.deck_loadouts['0'][{u1!r}] is not an object"),
    ('equip not object', {'0': {u1: {'equipment': []}}}, f"party.deck_loadouts['0'][{u1!r}].equipment is not an object"),
    ('invalid slot', {'0': {u1: {'shift_equipment': {'7': '301000100'}}}}, "invalid slot '7'"),
    ('unknown item', {'0': {u1: {'equipment': {'1': '999999999'}}}}, 'equips unknown item 999999999'),
]
for label, payload, fragment in bad_cases:
    broken = copy.deepcopy(player.data)
    broken['party']['deck_loadouts'] = payload
    issues = state_coherence_issues(broken)
    assert any(fragment in issue for issue in issues), (label, issues)

# renew_unit_instance migrates instance keys cleanly across party.deck_loadouts.
old_id = str(player.grant_unit('100000315')['instance_id'])
player.data['party']['decks'][1]['members'] = [{'member_type': 0, 'disp_order': 0, 'instance_id': old_id}]
player.data['party']['deck_loadouts']['1'] = {old_id: {'equipment': {'1': '302000100'}}}
renewed = player.renew_unit_instance(old_id)
new_id = str(renewed['instance_id'])
assert new_id != old_id
assert old_id not in player.data['party']['deck_loadouts']['1']
assert player.data['party']['deck_loadouts']['1'][new_id]['equipment']['1'] == '302000100'
assert state_coherence_issues(player.data) == []
''')

    def test_given_party_register_shop_sale_and_arena_under_track_b_when_executed_then_contracts_hold(self):
        self.run_engine('''
import exvius_actions_expedition as exp
import ffbe_state as st
from player_state import state_coherence_issues
from types import SimpleNamespace

u1 = str(player.grant_unit('100000315')['instance_id'])
u2 = str(player.grant_unit('100000337')['instance_id'])
player.grant_equipment(301000100, 1)
player.grant_equipment(301000200, 2)
player.grant_equipment(404000200, 1)
player.grant_item(22, 504000100, 1)
player.save(str(config.state_file))

# Equip Party 1 (deck 0) with 301000100 + 301000200 + materia 504000100, and Party 2 (deck 1) with 404000200.
request('PartyDeckEditRequest', {
    'CN92arJK': [{'r21y0YzS': '1', 'xBi3L6yR': '1'}],
    '5Eb0Rig6': [
        {'r21y0YzS': '0', 'G4L0YIB2': 'Party 1', '2A6fYiEC': f'0:0:{u1}'},
        {'r21y0YzS': '1', 'G4L0YIB2': 'Party 2', '2A6fYiEC': f'0:0:{u2}'},
    ],
})
request('UnitEquipRequest', {
    'Er92Kdhm': [
        {
            'xBi3L6yR': '1', 'r21y0YzS': '0',
            '93Y6evuT': f'{u1}:1-301000100@2-301000200@3-0@4-0@5-0@6-0',
            '80NUYFMJ': f'{u1}:1-504000100@2-0@3-0@4-0',
        },
        {
            'xBi3L6yR': '1', 'r21y0YzS': '1',
            '93Y6evuT': f'{u2}:1-0@2-0@3-404000200@4-0@5-0@6-0',
        },
    ]
})

# Active deck is Party 2 (deck 1), so roster does NOT wear 301000100 or 504000100.
# Selling Party 1's worn equipment or materia must still be refused!
import exvius_actions_shops as shops
before_sell = copy.deepcopy(player.data)
captured_notes = []
with patch.object(shops, '_note', side_effect=captured_notes.append):
    request('ItemSellRequest', {'2tHu3Chy': [{'8X7LwE3r': '21:301000100:1', '97h4mIQo': '10'}]})
    assert player.data == before_sell
    assert any('insufficient unequipped sale inventory' in n for n in captured_notes), captured_notes
    captured_notes.clear()
    request('ItemSellRequest', {'2tHu3Chy': [{'8X7LwE3r': '22:504000100:1', '97h4mIQo': '10'}]})
    assert player.data == before_sell
    assert any('insufficient unequipped sale inventory' in n for n in captured_notes), captured_notes

# Selling the 1 unequipped spare copy of 301000200 succeeds while preserving Party 1's worn copy.
request('ItemSellRequest', {'2tHu3Chy': [{'8X7LwE3r': '21:301000200:1', '97h4mIQo': '10'}]})
owned_after_sell = {r['J1YX9kmM']: int(r['Qy5EvcK1']) for r in player.equip_item_rows()}
assert owned_after_sell['301000200'] == 1

# Save Party 1 into slot 0:0, clear Party 1 gear, then PartyRegisterSlotLoadRequest must restore Party 1 without losing Party 2.
slot_fields = {k: '' for k in exp.SLOT_FIELDS}
slot_fields.update(
    YLi31qam='0', o0T4S52k='0', G4L0YIB2='Saved P1', xBi3L6yR='1', r21y0YzS='0',
    **{'2A6fYiEC': f'0:0:{u1}', 'w1JG7i9j': f'{u1}:0',
       '93Y6evuT': f'{u1}:1-301000100@2-301000200@3-0@4-0@5-0@6-0',
       '80NUYFMJ': f'{u1}:1-504000100@2-0@3-0@4-0'}
)
request('PartyRegisterSlotSaveRequest', {exp.SLOT: [slot_fields]})
request('UnitEquipRequest', {
    'Er92Kdhm': [{'xBi3L6yR': '1', 'r21y0YzS': '0',
                  '93Y6evuT': f'{u1}:1-0@2-0@3-0@4-0@5-0@6-0',
                  '80NUYFMJ': f'{u1}:1-0@2-0@3-0@4-0'}]
})
load_reply = request('PartyRegisterSlotLoadRequest', {exp.SLOT: [{
    'YLi31qam': '0', 'o0T4S52k': '0', 'xBi3L6yR': '1', 'r21y0YzS': '0',
}]})
loaded_rows = {(r['og2GHy49'], r['r21y0YzS']): r for r in load_reply['TJ9eL80N']}
assert loaded_rows[(u1, '0')]['93Y6evuT'].startswith('1-301000100@2-301000200@'), loaded_rows[(u1, '0')]
assert loaded_rows[(u1, '0')]['80NUYFMJ'].startswith('1-504000100@'), loaded_rows[(u1, '0')]
assert loaded_rows[(u2, '1')]['93Y6evuT'].startswith('1-0@2-0@3-404000200@'), loaded_rows[(u2, '1')]
assert player.data['party']['deck_loadouts']['0'][u1]['equipment']['1'] == '301000100'
assert player.data['party']['deck_loadouts']['1'][u2]['equipment']['3'] == '404000200'
assert state_coherence_issues(player.data) == []

# Switch active_deck back to Party 2 (deck 1) and enter Arena: IqkX0gV1 remains single-row-per-unit with active gear.
request('PartyDeckEditRequest', {
    'CN92arJK': [{'r21y0YzS': '1', 'xBi3L6yR': '1'}],
    '5Eb0Rig6': [{'r21y0YzS': '1', 'G4L0YIB2': 'Party 2', '2A6fYiEC': f'0:0:{u2}'}],
})
from revival_campaign import initialize_campaign
from datetime import datetime, timezone
if 'ios_revival' not in player.data:
    initialize_campaign(SimpleNamespace(player=player, state_dirty=False), config.state_file,
                        now=datetime(2026, 11, 9, 3, 0, tzinfo=timezone.utc))
player.save(str(config.state_file))
rb_reply = request('RbEntryRequest')
arena_rows = rb_reply['IqkX0gV1']
assert len(arena_rows) == len(player.data['roster'])
arena_u2 = next(r for r in arena_rows if r['og2GHy49'] == u2)
assert arena_u2['r21y0YzS'] == '1'
assert arena_u2['93Y6evuT'].startswith('1-0@2-0@3-404000200@'), arena_u2

# Special party w1JG7i9j brave_shift projects in special_party_groups without altering normal roster brave_shift.
request('PartyDeckEditRequest', {
    'CN92arJK': [{'b61ICxJk': '0', 'xBi3L6yR': '8'}],
    '5Eb0Rig6': [{'r21y0YzS': '0', '2A6fYiEC': f'0:0:{u2}', 'w1JG7i9j': f'{u2}:1'}],
})
assert int(player.roster_row(u2).get('brave_shift', 0)) == 0
dv_decks = player.special_party_groups('8')['GV7Ej6n0']
assert dv_decks[0]['w1JG7i9j'] == f'{u2}:1', dv_decks[0]
''')


if __name__ == '__main__':
    unittest.main()
