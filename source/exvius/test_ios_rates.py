"""BDD for the stock iPhone's read-only Drop Rates WebView request."""
import unittest

import test_ios_summons as harness


class NativeRatesRequests(unittest.TestCase):
    setUp = harness.ReplaySummonIntegration.setUp
    prepared_data = harness.ReplaySummonIntegration.prepared_data
    write_masters = harness.ReplaySummonIntegration.write_masters
    child = harness.ReplaySummonIntegration.child
    run_engine = harness.ReplaySummonIntegration.run_engine

    def test_given_native_banner_form_when_opened_then_match_existing_rates_without_gameplay(self):
        self.run_engine('''
import random
first = banner(9800001, '2016-12-16', name='First <Banner>', pool=[
    {'unit_id': '100000102', 'rarity': 2, 'rate': 1},
    {'unit_id': '100000202', 'rarity': 2, 'rate': 3}])
second = banner(9800002, '2016-12-16', name='Second Banner')
native = '/lapisProd/app/php/web/statics/probability/sg_summons_list.php'
with patch.object(summons, 'catalogue', return_value=(first, second)), patch.object(summons, 'clock', return_value=NOW):
    before, saved, rng = copy.deepcopy(player.data), config.state_file.read_bytes(), random.getstate()
    records = set(config.root.rglob('requests/*.json'))
    with patch.object(server.Handler, '_handle', side_effect=AssertionError('page entered game pipeline')), \\
         patch.object(type(player), 'save', side_effect=AssertionError('page saved campaign')):
        expected = LocalGame.request(engine, 'GET', '/exvius/gacha-rates/9800001.html')
        assert expected.status == 200
        reply = LocalGame.request(engine, 'POST', native, 'gacha_id=9800001&localization=en',
                                  {'Content-Type': 'application/x-www-form-urlencoded'})
        assert reply.status == 200, (reply.status, reply.body)
        assert reply.body == expected.body
        assert reply.headers['Content-Type'] == 'text/html; charset=utf-8'
        assert b'First &lt;Banner&gt;' in reply.body and b'Unit 100000102' in reply.body
        assert b'25.000000%' in reply.body and b'75.000000%' in reply.body
        # The native/reference parser reads URL-encoded fields regardless of MIME label.
        for media in ('application/octet-stream', 'text/plain'):
            alternate = LocalGame.request(engine, 'POST', native, 'gacha_id=9800001',
                                          {'Content-Type': media})
            assert alternate.status == 200 and alternate.body == expected.body
        following = LocalGame.request(engine, 'POST', native, 'gacha_id=9800002&localization=en',
                                      {'Content-Type': 'application/x-www-form-urlencoded'})
        assert b'Second Banner' in following.body and b'First &lt;Banner&gt;' not in following.body
        query = LocalGame.request(engine, 'GET', native + '?gacha_id=9800001')
        head = LocalGame.request(engine, 'HEAD', native + '?gacha_id=9800001')
        assert query.body == expected.body
        assert head.status == 200 and not head.body
        assert int(head.headers['Content-Length']) == len(expected.body)
    assert player.data == before and config.state_file.read_bytes() == saved
    assert random.getstate() == rng and set(config.root.rglob('requests/*.json')) == records
''')

    def test_given_missing_banner_when_opened_then_list_only_replay_eligible_summons(self):
        self.run_engine('''
first = banner(9800001, '2016-12-16', name='First <Banner>')
future = banner(9800002, '2017-01-06', name='Future Banner')
native = '/lapisProd/app/php/web/statics/probability/sg_summons_list.php'
with patch.object(summons, 'catalogue', return_value=(first, future)), patch.object(summons, 'clock', return_value=NOW):
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    for method in ('GET', 'POST', 'HEAD'):
        reply = LocalGame.request(engine, method, native, '', {'Content-Type': 'application/x-www-form-urlencoded'})
        assert reply.status == 200, (reply.status, reply.body)
        if method != 'HEAD':
            assert b'First &lt;Banner&gt;' in reply.body
            assert b'/exvius/gacha-rates/9800001.html' in reply.body
            assert b'Future Banner' not in reply.body
        else:
            assert not reply.body and int(reply.headers['Content-Length']) > 0
    assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_invalid_native_form_when_opened_then_return_error_without_gameplay(self):
        self.run_engine('''
native = '/lapisProd/app/php/web/statics/probability/sg_summons_list.php'
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
with patch.object(server.Handler, '_handle', side_effect=AssertionError('invalid form entered game pipeline')):
    for payload, code in [('gacha_id=invalid', 400), ('gacha_id=1&gacha_id=2', 400),
                          ('gacha_id=1&padding=' + 'x' * 65536, 413)]:
        reply = LocalGame.request(engine, 'POST', native, payload,
                                  {'Content-Type': 'application/x-www-form-urlencoded'})
        assert reply.status == code, (reply.status, reply.body)
        assert reply.body
    unknown = LocalGame.request(engine, 'GET', native + '?gacha_id=999999999999')
    assert unknown.status == 404 and unknown.body
assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_legacy_profile_when_native_url_requested_then_keep_existing_resource_routing(self):
        self.run_engine('''
from engine_profile import LEGACY
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
with patch.object(server.data_paths, 'PROFILE', LEGACY):
    reply = LocalGame.request(engine, 'GET', '/lapisProd/app/php/web/statics/probability/sg_summons_list.php')
    assert reply.status == 404
assert player.data == before and config.state_file.read_bytes() == saved
''')


if __name__ == '__main__':
    unittest.main()
