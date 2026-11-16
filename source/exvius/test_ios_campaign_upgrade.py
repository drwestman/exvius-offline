"""BDD for explicit upgrades, identity preservation and historical ambiguity."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SOURCE), str(SOURCE / 'server')]
from ios_server import campaign_upgrade as upgrade
from revival_update import settings, initialize
from revival_carry import fit, settle
from revival_quests import report


class UpgradeBehavior(unittest.TestCase):
    def setUp(self):
        self.data = {'identity': {'user_id': '123'}, 'ios_revival': {'replay': {'anchor_week': 999}},
            'progress': {'switches': {}, 'cleared_missions': ['20']},
            'exvius_map': {'quests': {'10': {'Z34jU7ue': '1', '4kcAD9fW': '2'}}},
            'inventory': {'items': [{'item_type': 20, 'item_id': 90, 'count': 3}],
                          'carry_items': [{'disp_order': 0, 'item_id': 90, 'count': 5}]}, 'roster': []}
        self.tables = dict(units={}, experience=[], steps={'10': {'Z34jU7ue': '1', 'dIPkNn61': '100'}},
            switches={'100': {'5opcUT9t': '200', 'QLfe23bu': '4'}},
            missions={'20': {'1x4bG2J8': '50:1:100'}})

    def test_given_old_campaign_when_planned_then_repair_purely_and_keep_unknown_backpay_unpaid(self):
        before = copy.deepcopy(self.data)
        candidate, result = upgrade.build(self.data, **self.tables)
        self.assertEqual(self.data, before)
        self.assertEqual(candidate['identity'], before['identity'])
        self.assertEqual(candidate['ios_revival'], before['ios_revival'])
        self.assertEqual(candidate['progress']['switches'], {'200': [4]})
        self.assertEqual(candidate['inventory']['carry_items'][0]['count'], 3)
        self.assertEqual(result['compensation'], [])
        self.assertEqual(len(result['unresolved']), 1)
        self.assertTrue(settings(candidate)['full_runs'])
        second, result = upgrade.build(candidate, **self.tables)
        self.assertEqual(second, candidate)
        self.assertTrue(result['already_upgraded'])

    def test_given_changed_save_when_applying_then_refuse_before_backup_or_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            save = root / 'state' / 'campaign.json'; save.parent.mkdir(); save.write_text('{}')
            config = SimpleNamespace(root=root, state_file=save, slot='campaign')
            with patch.object(upgrade, 'plan', return_value=({}, {'save_sha256': 'a'*64, 'changed': True})):
                with self.assertRaisesRegex(ValueError, 'changed since'):
                    upgrade.apply(config, 'b'*64)
            self.assertEqual(save.read_text(), '{}')
            self.assertFalse((save.parent / 'backups').exists())

    def test_given_valid_plan_when_save_replace_fails_then_preserve_campaign_and_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); save = root / 'state' / 'campaign.json'; save.parent.mkdir(); save.write_text('{}')
            digest = hashlib.sha256(save.read_bytes()).hexdigest()
            config = SimpleNamespace(root=root, state_file=save, slot='campaign')
            original = upgrade._atomic
            def write(path, raw):
                if path == save:
                    raise OSError('disk full')
                return original(path, raw)
            with patch.object(upgrade, 'plan', return_value=({'new': True}, {'save_sha256': digest, 'changed': True})), \
                    patch.object(upgrade, '_atomic', side_effect=write):
                with self.assertRaises(OSError):
                    upgrade.apply(config, digest)
            self.assertEqual(save.read_text(), '{}')
            self.assertEqual(next((save.parent / 'backups').iterdir()).read_text(), '{}')

    def test_given_completed_and_active_steps_when_projected_then_report_whole_quest_without_mutation(self):
        saved = {'10': {'Z34jU7ue': '1', '4kcAD9fW': '2'}}
        steps = {'10': {'Z34jU7ue': '1'}, '11': {'Z34jU7ue': '1'}}
        self.assertEqual(report(saved, steps), [{'Z34jU7ue': '1', '4kcAD9fW': '1'}])
        saved['11'] = {'Z34jU7ue': '1', '4kcAD9fW': '2'}
        self.assertEqual(report(saved, steps)[0]['4kcAD9fW'], '2')

    def test_given_duplicate_slots_when_fitting_then_never_allocate_more_than_owned(self):
        rows = [{'disp_order': n, 'item_id': 90, 'count': 2} for n in (0, 0, 1)]
        self.assertEqual(sum(r['count'] for r in fit(rows, {'90': 3})), 3)


if __name__ == '__main__':
    unittest.main()
