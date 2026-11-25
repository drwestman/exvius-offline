"""BDD for mode-specific conversion, without engine binding or state writes."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from revival_unit_rules import ConversionRules, awakened_flag, summon_unit


class UnitRulesBehavior(unittest.TestCase):
    def setUp(self):
        self.units = {
            '1': {'3HriTp6B': '1', 'woghJa61': '1', '9fW0TePj': '5'},
            '2': {'3HriTp6B': '2', 'woghJa61': '1', '9fW0TePj': '7', '5Mgpv8hJ': '1', 'k9GFaWm1': '1'},
            '3': {'3HriTp6B': '3', 'woghJa61': '3', '9fW0TePj': '7', '5Mgpv8hJ': '1'},
            '4': {'3HriTp6B': '4', 'woghJa61': '4', 'I3SKJ4q0': '1', 'JPW8Vs40': '2'},
        }
        self.rows = {'1': {'jBVop84T': '5', 'tL6G9egd': '90', 'q1PJQ3eE': '20:91:25'},
                     '2': {'jBVop84T': '7', 'q1PJQ3eE': '20:92:25'},
                     '3': {'jBVop84T': '7', '1swM3H4T': '20:93:50'}}
        self.rules = ConversionRules(self.units, self.rows)

    def test_given_prism_mode_then_grant_only_prism(self):
        self.assertEqual(self.rules.rewards('1', 'prism'), '20:90:1')
        self.assertEqual(self.rules.rewards('1', 'fragments'), '20:91:25')

    def test_given_awakened_nv_then_use_own_fragment_row_and_native_flag(self):
        self.assertEqual(self.rules.rewards('2', 'fragments'), '20:92:25')
        self.assertEqual(awakened_flag(self.units['2']), '1')
        self.assertEqual(self.rules.rewards('2', 'prism'), '')

    def test_given_summoned_nv_then_use_family_reward(self):
        self.assertEqual(self.rules.rewards('3', 'fragments'), '20:93:50')
        self.assertIsNone(awakened_flag(self.units['3']))

    def test_given_invalid_mode_or_master_then_never_guess_reward(self):
        with self.assertRaises(ValueError):
            self.rules.rewards('1', 'both')
        self.assertEqual(self.rules.rewards('999', 'fragments'), '')

    def test_given_shift_form_then_resolve_root_without_mutation(self):
        before = copy.deepcopy(self.units)
        self.assertEqual(summon_unit('4', self.units), '1')
        self.assertEqual(self.units, before)


if __name__ == '__main__':
    unittest.main()
