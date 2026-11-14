"""BDD for explicit iOS friendships and the native encrypted social endpoints."""
import copy
from datetime import timedelta
import os
import unittest
from unittest.mock import patch

import test_ios_summons as harness
import revival_friends as friends

NOW, campaign = harness.NOW, harness.campaign


class SimulatedFriendBehavior(unittest.TestCase):
    def test_given_new_campaign_when_initialized_then_seed_once_without_using_global_random(self):
        import random
        data = campaign()
        rng = random.getstate()
        self.assertTrue(friends.initialize(data, yaml_friends=[]))
        state = copy.deepcopy(data)
        self.assertEqual(len(friends.accepted_ids(data)), 15)
        self.assertEqual(len(friends.names(200)), len(set(friends.names(200))))
        self.assertTrue(all(len(name) <= 12 for name in friends.names(200)))
        self.assertEqual(random.getstate(), rng)
        with patch.dict(os.environ, {'EXVIUS_PLAYERS': '2', 'EXVIUS_START_FRIENDS': '1'}):
            self.assertFalse(friends.initialize(data, yaml_friends=[]))
        self.assertEqual(data, state)

    def test_given_no_friend_initialization_when_read_then_leave_state_empty(self):
        data = campaign()
        before = copy.deepcopy(data)
        self.assertEqual(friends.accepted_ids(data), ())
        self.assertEqual(friends.suggestion_ids(data, NOW), ())
        self.assertEqual(data, before)

    def test_given_previous_relationships_when_backfilled_then_keep_removals_and_favorites(self):
        data = campaign()
        data['exvius_friends'] = {'relations': {'910000001': {'type': 0, 'favorite': 0},
                                             '900000001': {'type': 1, 'favorite': 1}}}
        anchor = copy.deepcopy(data['ios_revival'])
        friends.initialize(data, yaml_friends=[])
        self.assertEqual(data['ios_revival'], anchor)
        self.assertEqual(data['exvius_friends']['relations']['910000001']['type'], 0)
        self.assertEqual(data['exvius_friends']['relations']['900000001']['favorite'], 1)

    def test_given_saved_timezone_when_suggesting_then_change_at_local_midnight_and_skip_friends(self):
        data = campaign()
        friends.initialize(data, yaml_friends=[])
        # 03:00 UTC and 04:59 UTC are the same Eastern date; 05:00 is the next.
        first = friends.suggestion_ids(data, NOW)
        self.assertEqual(first, friends.suggestion_ids(data, NOW + timedelta(hours=1, minutes=59)))
        self.assertNotEqual(first, friends.suggestion_ids(data, NOW + timedelta(hours=2)))
        self.assertEqual(len(first), 10)
        self.assertFalse(set(first).intersection(friends.accepted_ids(data)))

    def test_given_corrupt_record_when_read_then_fail_without_reseeding(self):
        data = campaign()
        friends.initialize(data, yaml_friends=[])
        data['exvius_friends']['simulation']['version'] = 99
        before = copy.deepcopy(data)
        with self.assertRaisesRegex(ValueError, 'Invalid iOS friend'):
            friends.accepted_ids(data)
        self.assertEqual(data, before)


    def test_given_disabled_crowd_when_initialized_then_keep_curated_friends_and_tombstones(self):
        data = campaign()
        data['exvius_friends'] = {'relations': {'900000001': {'type': 0, 'favorite': 0}}}
        with patch.dict(os.environ, {'EXVIUS_PLAYERS': '0'}):
            friends.initialize(data, yaml_friends=[{'friend_id': 900000001}, {'friend_id': 900000002}])
        self.assertEqual(friends.accepted_ids(data), ('900000002',))
        self.assertEqual(friends.suggestion_ids(data, NOW), ())
        self.assertEqual(data['counts']['friend'], 1)

    def test_given_dst_when_suggestions_change_then_use_the_saved_local_date(self):
        from datetime import datetime, timezone
        data = campaign()
        friends.initialize(data, yaml_friends=[])
        for boundary in (datetime(2027, 3, 14, 5, tzinfo=timezone.utc),
                         datetime(2027, 3, 15, 4, tzinfo=timezone.utc)):
            before = friends.suggestion_ids(data, boundary - timedelta(seconds=1))
            after = friends.suggestion_ids(data, boundary)
            self.assertNotEqual(before, after)
            self.assertEqual(after, friends.suggestion_ids(data, boundary + timedelta(hours=1)))


class SimulatedFriendIntegration(unittest.TestCase):
    setUp = harness.ReplaySummonIntegration.setUp
    prepared_data = harness.ReplaySummonIntegration.prepared_data
    write_masters = harness.ReplaySummonIntegration.write_masters
    child = harness.ReplaySummonIntegration.child
    run_engine = harness.ReplaySummonIntegration.run_engine

    def family_masters(self):
        self.extra_units = [('100000103', 3), ('100000106', 6), ('100000107', 7),
                            ('100000108', 8), ('100000109', 5), ('900000001', 5)]
        self.unit_fields = {uid: {'woghJa61': '100000102'} for uid, _ in self.extra_units}
        self.unit_fields['100000102'] = {'JPW8Vs40': '100000108'}
        self.unit_fields['100000103']['aU3o2D4t'] = 20
        self.unit_fields['100000109'].update({stat: '0' for stat in
            ('em5hx4FX', 'L0MX7edB', 'o7Ynu1XP', '6tyb58Kc', 'Y9H6TWnv', 'sa8Ewx3H')})

    def test_given_owned_family_when_projected_then_rotate_valid_forms_and_cap_levels_without_writes(self):
        self.family_masters()
        self.run_engine('''
import random
import revival_friends as friends
from ffbe_friends import serve_friends, BOOT_REPLIES
player.data['roster'] = [dict(player.data['roster'][0], level=12),
                        dict(player.data['roster'][0], instance_id='999', level=30, storage_state=1)]
player.dirty = True
player.save(str(config.state_file))
before, saved, rng = copy.deepcopy(player.data), config.state_file.read_bytes(), random.getstate()
dates = {'100000102': '2016-01-01', '100000107': '2099-01-01'}
with patch.object(friends, 'unit_dates', return_value=dates), patch.object(friends, 'clock', return_value=NOW):
    listing = request('FriendListRequest')['56gJBnVh']
    suggestions = request('FriendSuggestRequest')['f6yGgCj2']
    supports = request('GetReinforcementInfoRequest')['pzf5se6V']
    target = listing[0]['m3Wghr1j']
    payload = {'I53AVzSo': [{'m3Wghr1j': target, 'K3BV17gk': '1'}]}
    searched = request('FriendSearchRequest', payload)['2K05IxtX']
    detail = request('FriendDetailRequest', payload)['2vuhy0Ex']
    boot = serve_friends({}, next(iter(BOOT_REPLIES)))['56gJBnVh']
    for row in listing + suggestions + supports + searched + detail + boot:
        assert row['3HriTp6B'] in ('100000102', '100000103', '100000106'), row
        assert int(row['10fNKueF']) == (20 if row['3HriTp6B'] == '100000103' else 30), row
        assert all(row.get(k) for k in ('m3Wghr1j', 'og2GHy49', 'em5hx4FX'))
    first = friends.catalogue(player.data, NOW)
    without_duplicate = dict(player.data, roster=[player.data['roster'][1]])
    assert friends.catalogue(without_duplicate, NOW) == first
    later = friends.catalogue(player.data, NOW + timedelta(weeks=1))
    assert first == friends.catalogue(player.data, NOW)
    assert any(first[fid]['unit'] != later[fid]['unit'] for fid in first)
    for fid in first:
        assert all(first[fid][k] == later[fid][k] for k in ('friend_id', 'display_name', 'rank', 'instance_id'))
assert player.data == before and config.state_file.read_bytes() == saved
assert random.getstate() == rng
''')

    def test_given_roster_changes_when_projected_then_refresh_families_and_caps_after_reload(self):
        self.run_engine('''
import revival_friends as friends
from player_state import PlayerState
data = copy.deepcopy(player.data)
data['roster'] = [dict(data['roster'][0], level=7)]
def helpers():
    return list(friends.catalogue(data, NOW).values())
assert {f['unit']['master_id'] for f in helpers()} == {100000102}
assert {f['unit']['level'] for f in helpers()} == {7}
data['roster'][0]['level'] = 18
assert {f['unit']['level'] for f in helpers()} == {18}
data['roster'].append(dict(player.data['roster'][1], level=9, storage_state=1))
assert {f['unit']['master_id'] for f in helpers()} == {100000102, 100000202}
player.data = data
player.drop_units([data['roster'][0]['instance_id']])
data = player.data
assert {f['unit']['master_id'] for f in helpers()} == {100000202}
for deck in data['party']['decks']:
    deck['members'] = []  # The remaining copy is in storage, outside active parties.
player.dirty = True
player.save(str(config.state_file))
reloaded = PlayerState.load(str(config.state_file), slot='campaign')
assert friends.catalogue(reloaded.data, NOW) == friends.catalogue(data, NOW)
''')

    def test_given_curated_friends_when_unowned_then_replace_builds_and_keep_owned_forms_capped(self):
        self.family_masters()
        self.run_engine('''
import ffbe_friends
import revival_friends as friends
player.data['roster'] = [dict(player.data['roster'][0], level=30)]
yaml = config.root / 'owned-test-friends.yaml'
yaml.write_text('friends:\\n  - display_name: Replaced\\n    friend_id: 900000003\\n    rank: 150\\n    unit:\\n      master_id: 100000337\\n      level: 80\\n      equipment: [123]\\n      abilities: [456]\\n      vision_card: 789\\n      esper: 1\\n  - display_name: Kept\\n    friend_id: 900000004\\n    unit:\\n      master_id: 100000103\\n      level: 90\\n      equipment: [123]\\n')
with patch.object(ffbe_friends, 'FRIENDS_FILE', str(yaml)), patch.object(ffbe_friends, '_cache', {'mtime': None, 'friends': []}):
    original = copy.deepcopy(ffbe_friends.configured_friends())
    before = copy.deepcopy(player.data)
    catalog = friends.catalogue(player.data, NOW)
    replaced, kept = catalog['900000003'], catalog['900000004']
    assert replaced['unit']['master_id'] in (100000102, 100000103, 100000106, 100000107)
    assert replaced['unit']['level'] <= 30
    assert replaced['unit']['equipment'] == replaced['unit']['abilities'] == []
    assert replaced['unit']['vision_card'] == '' and replaced['unit']['esper'] == 0
    assert all(replaced[k] == original[0][k] for k in ('friend_id', 'display_name', 'rank', 'instance_id'))
    assert kept['unit']['master_id'] == 100000103 and kept['unit']['level'] == 20
    assert kept['unit']['equipment'] == ['123']
    assert friends.catalogue(player.data, NOW) == catalog
    assert ffbe_friends.configured_friends() == original and player.data == before
    assert friends.catalogue(dict(player.data, roster=[]), NOW) == {}
''')

    def test_given_no_eligible_units_when_read_then_clear_rows_without_changing_relationships(self):
        self.run_engine('''
import revival_friends as friends
player.data['roster'] = []
player.dirty = True
player.save(str(config.state_file))
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
with patch.object(friends, 'clock', return_value=NOW):
    assert request('FriendListRequest')['56gJBnVh'] == []
    assert request('FriendSuggestRequest')['f6yGgCj2'] == []
    supports = request('GetReinforcementInfoRequest')
    assert supports['pzf5se6V'] == [] and '9Tp2fiyB' not in supports
    target = friends.accepted_ids(player.data)[0]
    assert request('FriendSearchRequest', {'I53AVzSo': [{'m3Wghr1j': target}]})['2K05IxtX'] == []
    assert friends.catalogue(player.data, NOW) == {}
assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_undated_form_when_family_is_future_then_do_not_bypass_replay_cutoff(self):
        self.family_masters()
        self.run_engine('''
import revival_friends as friends
data = copy.deepcopy(player.data)
data['roster'] = data['roster'][:1]
with patch.object(friends, 'unit_dates', return_value={'100000102': '2099-01-01'}):
    assert friends.catalogue(data, NOW) == {}
''')

    def test_given_missing_family_metadata_when_initialized_then_omit_helpers_without_query_writes(self):
        self.unit_fields = {uid: {'woghJa61': None} for uid in ('100000102', '100000202')}
        self.run_engine('''
import revival_friends as friends
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
assert friends.catalogue(player.data, NOW) == {}
assert request('FriendListRequest')['56gJBnVh'] == []
assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_native_friend_pages_when_read_then_show_seeded_friends_without_writes(self):
        self.run_engine('''
import revival_friends as friends
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
with patch.object(friends, 'clock', return_value=NOW):
    listing = request('FriendListRequest')
    suggestions = request('FriendSuggestRequest')['f6yGgCj2']
    supports = request('GetReinforcementInfoRequest')
assert len(listing['56gJBnVh']) == 15, listing.get('56gJBnVh')
assert len(suggestions) == 10
assert len(supports['pzf5se6V']) == 15
assert not set(r['m3Wghr1j'] for r in suggestions).intersection(r['m3Wghr1j'] for r in listing['56gJBnVh'])
for row in suggestions + listing['56gJBnVh']:
    assert all(row.get(k) for k in ('m3Wghr1j', '9qh17ZUf', '3HriTp6B', 'og2GHy49', '10fNKueF', 'em5hx4FX')), row
assert player.data == before
assert config.state_file.read_bytes() == saved
''')

    def test_given_suggested_player_when_added_favorited_removed_and_reloaded_then_persist_once(self):
        self.run_engine('''
import revival_friends as friends
from ffbe_player import score_quest_action
from player_state import PlayerState
with patch.object(friends, 'clock', return_value=NOW):
    target = request('FriendSuggestRequest')['f6yGgCj2'][0]['m3Wghr1j']
    payload = {'I53AVzSo': [{'m3Wghr1j': target}]}
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    row = request('FriendSearchRequest', payload)['2K05IxtX'][0]
    assert row['K3BV17gk'] == '4'
    assert player.data == before and config.state_file.read_bytes() == saved
    with patch('ffbe_player.score_quest_action', wraps=score_quest_action) as score:
        added = request('FriendRequest', payload)
        assert added['2vuhy0Ex'][0]['K3BV17gk'] == '1'
        assert player.data['counts']['friend'] == 16
        saved = config.state_file.read_bytes()
        request('FriendRequest', payload)
        assert score.call_count == 1, score.call_count
        assert config.state_file.read_bytes() == saved
    request('FriendFavoriteRequest', {'I53AVzSo': [{'m3Wghr1j': target, '8zE6w9RP': '1'}]})
    player.data = PlayerState.load(str(config.state_file), slot='campaign').data
    row = next(r for r in request('FriendListRequest')['56gJBnVh'] if r['m3Wghr1j'] == target)
    assert row['8zE6w9RP'] == '1'
    removed = request('FriendDeleteRequest', payload)
    assert removed['I53AVzSo'][0]['0NVFk2fD'] == target
    assert player.data['counts']['friend'] == 15
    saved = config.state_file.read_bytes()
    request('FriendDeleteRequest', payload)
    assert config.state_file.read_bytes() == saved
    player.data = PlayerState.load(str(config.state_file), slot='campaign').data
    assert target not in {r['m3Wghr1j'] for r in request('FriendListRequest')['56gJBnVh']}
    assert target not in {r['m3Wghr1j'] for r in request('GetReinforcementInfoRequest')['pzf5se6V']}
    assert not engine.initialize_campaign()
    assert player.data['exvius_friends']['relations'][target]['type'] == 0
    request('FriendAgreeRequest', payload)
    assert player.data['counts']['friend'] == 16
    request('FriendRefuseRequest', payload)
    assert player.data['counts']['friend'] == 15
''')

    def test_given_refused_or_unsaved_friend_command_when_retried_then_keep_previous_campaign(self):
        self.run_engine('''
import revival_friends as friends
from exvius_actions_arena import friend_request
with patch.object(friends, 'clock', return_value=NOW):
    target = request('FriendSuggestRequest')['f6yGgCj2'][0]['m3Wghr1j']
    payload = {'I53AVzSo': [{'m3Wghr1j': target}]}
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    for invalid in ('unknown', player.friend_id()):
        request('FriendRequest', {'I53AVzSo': [{'m3Wghr1j': invalid}]})
        assert player.data == before and config.state_file.read_bytes() == saved
    with patch.object(type(player), 'save', return_value=False):
        try:
            friend_request({}, payload)
        except OSError:
            pass
        else:
            raise AssertionError('save failure was hidden')
    assert server.State.player is player
    assert player.data == before and config.state_file.read_bytes() == saved
    player.mode = 'frozen'
    request('FriendRequest', payload)
    assert player.data == before and config.state_file.read_bytes() == saved
    player.mode = 'live'
    # A full roster refuses the request without changing anything.
    player.data['exvius_friends']['relations'].update({str(friends.ID_BASE+i): {'type': 1, 'favorite': 0}
                                                    for i in range(1, 201) if str(friends.ID_BASE+i) != target})
    player.dirty = True
    player.save(str(config.state_file))
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    request('FriendRequest', payload)
    assert player.data == before and config.state_file.read_bytes() == saved
''')

    def test_given_historical_replay_when_helpers_rotate_then_keep_identity_and_filter_future_units(self):
        # A named, dated master can still be a statless placeholder in real data.
        self.extra_units = [('100014905', 5)]
        self.unit_fields = {'100014905': {stat: '0' for stat in
                            ('em5hx4FX', 'L0MX7edB', 'o7Ynu1XP', '6tyb58Kc', 'Y9H6TWnv', 'sa8Ewx3H')}}
        self.run_engine('''
import revival_friends as friends
from revival_summons import unit_dates
data = copy.deepcopy(player.data)
first = friends.Directory(data, NOW)
later = friends.Directory(data, NOW + timedelta(weeks=20))
ids = first.ids()
assert len(ids) == 200
changed = 0
for fid in ids:
    a, b = first.by_id(fid), later.by_id(fid)
    assert (a['friend_id'], a['display_name'], a['rank']) == (b['friend_id'], b['display_name'], b['rank'])
    assert a == first.by_id(fid)
    for row, directory in ((a, first), (b, later)):
        uid = str(row['unit']['master_id'])
        assert uid != '100014905'
        assert unit_dates().get(uid, '') < directory.cutoff, (uid, directory.cutoff)
        assert row['unit']['level'] <= 100
    changed += a['unit'] != b['unit']
assert changed > 0
assert player.data == data
''')

    def test_given_old_campaign_when_backfilled_then_save_friends_atomically_without_resetting_anchor(self):
        self.run_engine('''
from revival_campaign import initialize_campaign
old = copy.deepcopy(player.data['ios_revival'])
del player.data['exvius_friends']['simulation']
removed = next(iter(player.data['exvius_friends']['relations']))
player.data['exvius_friends']['relations'][removed] = {'type': 0, 'favorite': 0}
player.dirty = True
player.save(str(config.state_file))
before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
with patch.object(type(player), 'save', return_value=False):
    try:
        initialize_campaign(server.State, config.state_file, now=NOW + timedelta(weeks=4))
    except OSError:
        pass
    else:
        raise AssertionError('backfill save failure was hidden')
assert server.State.player is player and player.data == before
assert config.state_file.read_bytes() == saved
assert initialize_campaign(server.State, config.state_file, now=NOW + timedelta(weeks=4))
player = server.State.player
assert player.data['ios_revival'] == old
assert player.data['exvius_friends']['relations'][removed]['type'] == 0
assert not initialize_campaign(server.State, config.state_file, now=NOW + timedelta(weeks=8))
''')

    def test_given_curated_friend_when_removed_then_list_boot_and_helpers_keep_the_tombstone(self):
        self.run_engine('''
import ffbe_friends
yaml = config.root / 'test-friends.yaml'
yaml.write_text('friends:\\n  - display_name: Kupo\\n    friend_id: 900000003\\n    unit:\\n      master_id: 100000102\\n      level: 10\\n')
with patch.object(ffbe_friends, 'FRIENDS_FILE', str(yaml)), patch.object(ffbe_friends, '_cache', {'mtime': None, 'friends': []}):
    payload = {'I53AVzSo': [{'m3Wghr1j': '900000003'}]}
    assert '900000003' in {r['m3Wghr1j'] for r in request('FriendListRequest')['56gJBnVh']}
    request('FriendDeleteRequest', payload)
    assert '900000003' not in {r['m3Wghr1j'] for r in request('InitializeRequest')['56gJBnVh']}
    assert '900000003' not in {r['m3Wghr1j'] for r in request('GetReinforcementInfoRequest')['pzf5se6V']}
    row = request('FriendSearchRequest', payload)['2K05IxtX'][0]
    assert row['K3BV17gk'] == '4'
    request('FriendRequest', payload)
    assert player.data['exvius_friends']['relations']['900000003']['type'] == 1
''')

    def test_given_generated_friend_when_gifting_then_retry_and_collection_do_not_duplicate_rewards(self):
        self.run_engine('''
import revival_friends as friends
from player_state import PlayerState
from unittest.mock import patch
with patch.object(friends, 'clock', return_value=NOW):
    target = request('FriendListRequest')['56gJBnVh'][0]['m3Wghr1j']
    payload = {'WSH38iMI': [{'Utx8P1Qo': '20', '2L0dxwuN': target + ':10'}]}
    first = request('GiftUpdateRequest', payload)['h5XGny0N']
    assert len(first) == 2, first
    assert request('GiftUpdateRequest', payload)['h5XGny0N'] == first
    incoming = next(r['2HqjK1F7'] for r in first if r['bUfq8BJ3'] == player.friend_id())
    claim = {'WSH38iMI': [{'9wXIbKq2': incoming}]}
    before = player.currencies['friend_point']
    request('GiftUpdateRequest', claim)
    assert player.currencies['friend_point'] == before + 10
    player.data = PlayerState.load(str(config.state_file), slot='campaign').data
    request('GiftUpdateRequest', claim)
    assert player.currencies['friend_point'] == before + 10
    request('FriendDeleteRequest', {'I53AVzSo': [{'m3Wghr1j': target}]})
    before, saved = copy.deepcopy(player.data), config.state_file.read_bytes()
    request('GiftUpdateRequest', payload)
    assert player.data == before and config.state_file.read_bytes() == saved
''')
