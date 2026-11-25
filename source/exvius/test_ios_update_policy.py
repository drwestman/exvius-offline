"""BDD for the pinned update catalogue, full runs and offline pack composition."""
import copy
from datetime import timedelta
import json
import unittest
from pathlib import Path
import sys
sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[1] / 'server')]

from test_ios_summons import campaign, banner, NOW
from revival_update import initialize, document, REVISION
import revival_summons as summons
from ios_server import pack_manifest


class UpdatePolicy(unittest.TestCase):
    def test_given_updated_policy_when_banner_run_overlaps_then_offer_on_both_weeks(self):
        data = campaign()
        initialize(data)
        before = copy.deepcopy(data)
        banners = [banner(1, '2016-12-16', until='2017-01-08')]
        first = summons.plan(data, NOW, banners=banners, families=set())
        second = summons.plan(data, NOW + timedelta(weeks=1), banners=banners, families=set())
        self.assertEqual(first.ids, ('1',))
        self.assertEqual(second.ids, ('1',))
        self.assertEqual(data, before)

    def test_given_pinned_documents_when_read_then_all_checksums_match(self):
        provenance = json.loads((Path(__file__).resolve().parents[1] / 'server/content/upstream/provenance.json').read_bytes())
        self.assertEqual(provenance['revision'], REVISION)
        for name in provenance['documents']:
            self.assertIsInstance(document(name), dict)

    def test_given_late_catalogue_then_exclude_unconfirmed_banners_and_preserve_aliases(self):
        rows = summons.catalogue(True)
        self.assertEqual(len({str(b['id']) for b in rows}), len(rows))
        self.assertFalse(any(b.get('unconfirmed') for b in rows))
        self.assertTrue(any(str(b['id']).startswith('970') for b in rows))

    def test_given_default_manifest_then_compose_supplement_without_replacing_destination(self):
        original = pack_manifest.DEFAULT.read_bytes()
        base = pack_manifest.parse(original)
        composed = pack_manifest.read()
        self.assertEqual(len(composed.packs), len(base.packs) + 1)
        self.assertEqual(composed.document['app'], base.document['app'])
        self.assertEqual(pack_manifest.DEFAULT.read_bytes(), original)
        for pack in base.packs:
            self.assertIn(pack, composed.packs)
        for name in ('static/summon_art/base/test.png','static/summon_art/main/test.png',
                     'static/summon_art/sub/test.png','static/summon_art/list.json'):
            self.assertEqual(pack_manifest.destination(name),name)
        with self.assertRaises(ValueError):
            pack_manifest.destination('static/summon_art/../state.json')


if __name__ == '__main__':
    unittest.main()
