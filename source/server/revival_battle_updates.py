"""Recorded iOS quest rewards. Commands run inside the candidate battle transaction."""
from collections import Counter
import copy
import json
import random

from revival_update import settings, document

JOINS = (
    ("100000302", ("1120704",), 20, "Fina: after Lechios Hills (Bandit's Hideout), Lanzelt; joins at level 20"),
    ("100000503", ("1220505",), 1, "Lid: after Galebreak (Beast in the Storm), Dirnado"),
    ("100000403", ("1320905",), 1, "Nichol: after the Water Shrine (Will of the Ferocious), Olderion"),
    ("100000703", ("1420606",), 1, "Jake: after Invincible Interior (Conclusion), Zoldaad"),
    ("100000603", ("1510506",), 1, "Sakura: after Magic Library - Showdown of Destiny, Mysidia"),
    ("100025705", ("11810702", "11810703"), 1,
     "Blue Mage Fina: the Season 3 opening, Our Tomorrow - Starting on a New Journey, Paladia"),
    ("100037407", ("14010503",), 1, "Runda: Season 4, clear Trail to Yorte - Underground Nest (General Quest)"),
)

COLLECTION = {20:'EWmQy52k',21:'XMgu7qE0',22:'1Z2TD5ai',23:'7rA9WGQe'}


def enabled(player):
    from engine_profile import current_profile
    return player is not None and current_profile().name == 'ios-revival' and settings(player.data) is not None


def prepare(spec, mid, bundle, state, *, rng=random):
    player = state.player
    if not enabled(player) or not bundle or not isinstance(spec, dict) or '09HRWXDf' in spec:
        return spec
    attempt = player.data.get('exvius_repeat', {}).get('attempt', {})
    if attempt.get('mid') != str(mid) or attempt.get('status') != 'pending' or player.mode != 'live':
        return spec
    if 'ios_update' not in attempt:
        from player_state import mission_row
        player.data.setdefault('ios_reward_claims', {'version':1,
            'baseline':list(player.data.get('progress', {}).get('cleared_missions', [])), 'paid':{}})
        row = mission_row(mid) or {}
        first = str(row.get('1x4bG2J8') or '')
        extras = document('story_recipes.json')['missions'].get(str(mid), [])
        first = ','.join(filter(None,[first]+[r['reward'] for r in extras]))
        collection = {}
        doc = document('collection_points.json')
        for point, key in doc['missions'].get(str(mid), []):
            entries = doc['pools'][key]['items']
            kind, iid, _, low, high = rng.choices(entries, weights=[r[2] for r in entries])[0]
            collection[str(point)] = f'{kind}:{iid}:{rng.randint(int(low),int(high))}'
        attempt['ios_update'] = {'version':1, 'first_clear':first, 'gil':max(0,int(row.get('7UR4J2SE') or 0)),
            'collection':collection, 'exploration':str(row.get('Y4VoF8yu')) == '2', 'settled':False}
        player.dirty = True
    out = copy.deepcopy(spec)
    if attempt['ios_update'].get('exploration'):
        out['vM21k0do'] = [{'N3hB0CwE':pid,'9GIvAQC2':'1','1Fa7rL5R':reward}
                          for pid,reward in attempt['ios_update']['collection'].items()]
    return out


def _rows(text):
    from exvius_rewards import parse
    return parse(text)


def shown(rows, data):
    """Native result tuples; Vision Cards require a positive level field."""
    from revival_economy import earned
    result = []
    for row in rows:
        count = earned(data, row['count']) if row['kind'] == 50 else row['count']
        text = f"{row['kind']}:{row['id']}:{count}"
        if row['kind'] == 27:
            text += ':100:' + str(max(1, int(row.get('level') or 1)))
        result.append(text)
    return ','.join(result)


def settle(spec, mid, plaintext, state):
    player = state.player
    if not enabled(player) or not isinstance(spec, dict) or '09HRWXDf' not in spec:
        return spec
    attempt = player.data.get('exvius_repeat', {}).get('attempt', {})
    facts = attempt.get('ios_update')
    if (player.mode != 'live' or attempt.get('mid') != str(mid) or not facts
            or attempt.get('status') != 'completed' or attempt.get('cleared') is not True
            or not attempt.get('normal_rewards_recorded')):
        return spec
    if facts['settled']:
        return spec  # the canonical result echo carries the original paid result
    out = copy.deepcopy(spec)
    try:
        req = json.JSONDecoder().raw_decode(plaintext or '{}')[0]
    except ValueError:
        return spec
    result = (req.get('09HRWXDf') or [{}])[0]
    earned = Counter()
    for reward in facts['collection'].values():
        row = _rows(reward)[0]
        earned[(row['kind'],row['id'])] += row['count']
    collected = []
    for kind, channel in COLLECTION.items():
        reported = Counter()
        for row in _rows(result.get(channel) or ''):
            if row['kind'] == kind:
                reported[(kind,row['id'])] += row['count']
        grants = [{'kind':k,'id':iid,'count':min(n,earned.get((k,iid),0))} for (k,iid),n in reported.items()
                  if earned.get((k,iid),0) > 0]
        for row in grants:
            if not player._can_credit(row) or player._grant_items([row]) != [row]:
                raise ValueError('Recorded collection reward could not be credited')
        collected.extend(grants)
        if grants:
            text = ','.join(f"{r['kind']}:{r['id']}:{r['count']}" for r in grants)
            for row in out['09HRWXDf']:
                row[channel] = text
    claims = player.data['ios_reward_claims']
    first = []
    blocked = []
    if str(mid) not in claims['baseline']:
        paid = claims['paid'].setdefault(str(mid), [])
        for index, entry in enumerate(facts['first_clear'].split(',')):
            if not entry or entry == '0':
                continue
            key = str(index) + ':' + entry
            if key in paid:
                continue
            try:
                rows = _rows(entry)
            except ValueError as exc:
                blocked.append({'entry':entry,'reason':str(exc)})
                continue
            for row in rows:
                # The canonical pre-existing mission bonus has its own receipt.
                if any(row == bonus for bonus in attempt.get('mission_bonus_awards', [])):
                    paid.append(key)
                    continue
                if not player._can_credit(row):
                    blocked.append({'entry':entry,'reason':'unsupported reward'})
                    continue
                if player._grant_items([row]) != [row]:
                    raise ValueError('First-clear reward could not be credited')
                first.append(row)
                paid.append(key)
    if first:
        text = shown(first, player.data)
        for row in out['09HRWXDf']:
            row['p1K5NecV'] = text
    # Riches already pays its mission Gil through the canonical special-stage rule.
    from ffbe_battle import CHAMBER_OF_RICHES
    gil = 0 if str(mid) in CHAMBER_OF_RICHES else facts['gil']
    if gil:
        player.add_currency('gil',gil)
        for row in out['09HRWXDf']:
            row['16LQuC5r'] = str(int(row.get('16LQuC5r') or 0)+gil)
    if settings(player.data)['lb_exp']:
        from revival_lb import plan, apply
        changes = plan(player,mid)
        apply(player,changes)
        for row in out['09HRWXDf']:
            pieces = []
            for text in str(row.get('Qic38SuC') or '').split(','):
                uid, sep, halves = text.partition('@')
                if sep and uid in changes:
                    before, after = [half.split(':') for half in halves.split('_')]
                    if len(before)==15 and len(after)==15:
                        a,b,c,d = changes[uid]
                        before[10:12], after[10:12] = [str(a),str(b)], [str(c),str(d)]
                        text = uid+'@'+':'.join(before)+'_'+':'.join(after)
                pieces.append(text)
            if pieces:
                row['Qic38SuC'] = ','.join(pieces)
    from revival_guide import record_battle, register_holdings
    record_battle(out, plaintext)
    joined = player.data.setdefault('ios_story_joins', [])
    for uid, triggers, level, _ in JOINS:
        if str(mid) in triggers and uid not in joined and str(mid) not in claims['baseline']:
            from player_state import unit_mst
            if unit_mst(uid) is not None:
                unit = player.grant_unit(uid)
                if unit is None:
                    raise ValueError('Story unit could not join')
                if level > 1:
                    player.set_unit_level(unit['instance_id'], level)
                joined.append(uid)
    register_holdings(player)
    facts.update(settled=True, first_clear_granted=first, blocked=blocked, collected=collected)
    player.dirty = True
    return out
