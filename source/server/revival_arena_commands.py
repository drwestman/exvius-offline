"""iOS arena commands: stage changes, settle one played week, save, then publish.

RbEntryRequest is the explicit arena initialization/rollover command. Ranking and
restart project the recorded week and never settle rewards or reset scores.
"""
import copy
from datetime import datetime, timedelta, timezone

from replay_calendar import read_anchor
import revival_arena as policy


def execute(spec, run, *, initialize=False, readonly=False):
    from ffbe_state import State, STATE_FILE, _note
    from exvius_arena import _model
    player = State.player
    if player is None or (not readonly and player.mode != 'live'):
        return spec
    candidate = player if readonly else copy.deepcopy(player)
    State.player = candidate
    try:
        model = _model()
        if not readonly:
            if read_anchor(candidate.data) is None:
                raise ValueError('Initialize the iOS campaign before entering Arena.')
            if not initialize and 'ladder' not in model:
                if not model.get('active'):
                    raise ValueError('Enter Arena before selecting an opponent.')
                prepare(candidate, model)  # An already-started pre-ladder battle may finish directly.
        result = run(model)
    except (ValueError, KeyError, StopIteration, OSError) as error:
        _note('Arena refused: ' + str(error))
        return spec
    finally:
        State.player = player
    if not readonly and candidate.data != player.data:
        if not candidate.save(STATE_FILE):
            raise OSError('The iOS Arena transaction could not be saved; the previous campaign is preserved.')
        player.data, player.dirty = candidate.data, candidate.dirty
    return result


def settle(player, model):
    points = int(model['user']['UbQ26oH4'])
    if points <= 0 or model.get('ladder_last_paid') == model['week']:
        return
    end = datetime.fromisoformat(model['week_ends']).astimezone(timezone.utc)
    ladder = policy.for_model(player.data, model, end - timedelta(seconds=1))
    if ladder.week.number != model['week']:
        raise ValueError('Saved Arena week does not match its recorded boundary.')
    standings = ladder.standings(points)
    rank = ladder.rank_of(points)
    reward = policy.reward_row(model['season_id'], policy.placement(rank, len(standings)))
    if reward is None:
        raise ValueError('The played Arena season has no placement reward table.')
    from exvius_rewards import parse
    entries = [entry.split(':') for entry in reward['dX6cor8j'].split(',')]
    for entry in entries:
        if len(entry) > 3 and entry[3] == '0':
            entry[3] = '100'
    items = parse(','.join(':'.join(entry) for entry in entries))
    if not items or any(not player._can_credit(item) for item in items) or player._grant_items(items) != items:
        raise ValueError('Arena placement reward could not be granted completely.')
    player.deliver_mail('Arena Weekly Ranking', [], message=
        f'You finished the week at rank {rank} of {len(standings)} with {points} points '
        f'(Global ranks {reward["ip94Nqb7"]}-{reward["XM4Ca3PF"]}). '
        'Your ranking rewards have been added to your inventory.')
    model['ladder_last_paid'] = model['week']
    model['last_week_result'] = {'week': model['week'], 'rank': rank, 'players': len(standings),
                                'points': points, 'bracket': [reward['ip94Nqb7'], reward['XM4Ca3PF']]}


def prepare(player, model):
    model.setdefault('ladder', copy.deepcopy(policy.configuration(player.data)))
    ladder = policy.Ladder(player.data)
    if model.get('week') is not None:
        policy.for_model(player.data, model)  # Validate even an empty or pending played week.
    if not ladder.enabled or model.get('active'):
        return
    previous = model.get('week')
    if previous == ladder.week.number:
        return
    if previous is not None:
        if type(previous) is not int or previous > ladder.week.number:
            raise ValueError('Arena clock cannot move behind its recorded week.')
        settle(player, model)
    model['lifetime_points'] = int(model.get('lifetime_points', 0)) + int(model['user']['UbQ26oH4'])
    model['user']['UbQ26oH4'] = '0'
    model.update(week=ladder.week.number, week_starts=ladder.week.starts.isoformat(),
                 week_ends=ladder.week.ends.isoformat(), season_id=ladder.season_id(), matched=None)


def require_current_week(model):
    from ffbe_state import State
    ladder = policy.Ladder(State.player.data)
    if ladder.enabled and not model.get('active') and model.get('week') != ladder.week.number:
        raise ValueError('Refresh Arena before selecting an opponent in a new week.')


def entry(spec, request):
    def run(model):
        from ffbe_state import State
        from exvius_arena import _save, _party, settle_weekly_reward
        from exvius_actions_arena import _arena_rows, _entry_reply
        prepare(State.player, model)
        ladder = policy.for_model(State.player.data, model)
        if not ladder.enabled:
            settle_weekly_reward(model)
        rows = _arena_rows(model)
        if rows is None:
            raise ValueError('No shipped Arena season.')
        if ladder.enabled:
            packed = ladder.candidate_entries(ladder.candidates(_party()))
        else:
            from ffbe_friends import all_friends
            packed = ','.join(':'.join(map(str, (f['friend_id'], policy.clean(f['display_name']),
                f['unit']['master_id'], f['unit']['level'], 0, 0, f['rank'], 100, f['emblem_id'], 0, 0)))
                for f in all_friends())
        _save(model)
        return _entry_reply(spec, model, rows, packed)
    return execute(spec, run, initialize=True)


def ranking(spec, request):
    def run(model):
        from ffbe_state import State
        from exvius_actions import _node
        from exvius_actions_arena import _arena_rows, _valid_season
        from exvius_arena import _party
        term = str((_node(request, 'e7n2P5IJ') or {}).get('3HbFrqo5', ''))
        if not _valid_season(request, model) or term not in ('1', '3'):
            raise ValueError('Unknown ranking season or term.')
        rows = _arena_rows(model)
        if rows is None:
            raise ValueError('No shipped Arena season.')
        ladder = policy.for_model(State.player.data, model)
        party = _party()
        leader = party[0] if party else {'master_id': 0, 'level': 1}
        identity = State.player.data['identity']
        user = {'id': identity['user_id'], 'name': identity.get('handle_name', ''),
                'unit': leader['master_id'], 'unit_level': leader['level'], 'rank': State.player.data['rank']['level']}
        out = dict(spec) if isinstance(spec, dict) else {}
        out.update(rows)
        out['YQN6zx3R'] = [{'3HbFrqo5': term, '8s9wNSpd': '0',
                           'CLg9j1sh': ladder.ranking_entries(int(model['user']['UbQ26oH4']), user)
                           if ladder.enabled else ''}]
        return out
    return execute(spec, run, readonly=True)
