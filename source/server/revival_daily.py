"""Pinned daily selection/rewards with immutable per-day snapshots and pure views."""
import copy
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import random
from zoneinfo import ZoneInfo

from replay_calendar import read_anchor
import revival_economy as economy

HERE = Path(__file__).resolve().parent
DEFAULT_POOLS = ('vortex_gil_summon', 'gifter', 'explorer')


def clock():
    return datetime.now(timezone.utc)


def day(data, now=None):
    now = now if now is not None else clock()
    if now.utcoffset() is None:
        raise ValueError('Daily time must include a timezone.')
    saved = read_anchor(data)
    local = now.astimezone(ZoneInfo(saved[1].timezone if saved else 'America/New_York'))
    midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return local.date().isoformat(), max(0, int(midnight.timestamp() - now.timestamp()))


@lru_cache(maxsize=1)
def documents():
    try:
        base = json.loads((HERE / 'daily_quests.json').read_text())
        custom = json.loads((HERE / 'daily_quests_custom.json').read_text())
        seen = set()
        for q in base['quests'] + custom['quests']:
            if (not str(q['id']).isdigit() or q['id'] in seen or type(q['target']) is not int or q['target'] <= 0 or
                    not q['action'] or not q['detail'] or not 1 <= int(q['type']) <= 5):
                raise ValueError('invalid quest definition')
            seen.add(q['id'])
        if not custom['quests'] or not custom['pools'] or not custom['tiers']:
            raise ValueError('missing custom daily content')
        return base, custom
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid pinned daily quest content: {exc}') from exc


def catalogue(data):
    base, custom = documents()
    s = economy.settings(data)
    rows = copy.deepcopy(base)
    if s and s['custom']:
        rows['pools'].update(custom['pools'])
        rows['quests'] += [dict(q, custom=True) for q in custom['quests']]
    return rows


def seed(*parts):
    return int(hashlib.sha256('|'.join(map(str, parts)).encode()).hexdigest()[:8], 16)


def choose(data, today):
    s = economy.settings(data)
    cat = catalogue(data)
    custom = documents()[1]
    pools = list(custom['pools']) + list(DEFAULT_POOLS) if s['custom'] else list(DEFAULT_POOLS)
    by_pool = {p: sorted((q for q in cat['quests'] if q.get('pool') == p), key=lambda q: str(q['id'])) for p in pools}
    order = list(pools)
    if s['custom']:
        random.Random(seed(today, '/'.join(pools))).shuffle(order)
        chosen, kinds = [], set()
        for p in order:
            rows = by_pool[p]
            offset = seed(today, p)
            for k in range(len(rows)):
                row = rows[(offset + k) % len(rows)]
                if row['action'] not in kinds:
                    chosen.append(str(row['id']))
                    kinds.add(row['action'])
                    break
            if len(chosen) >= s['count']:
                break
    else:
        offset = seed(today, '/'.join(pools))
        chosen = [str(by_pool[p][offset % len(by_pool[p])]['id']) for p in pools if by_pool[p]]
    return chosen, pools


def snapshot(data, ids, today):
    from exvius_rewards import parse
    from ffbe_player import _parse_reward
    defs = {str(q['id']): q for q in catalogue(data)['quests']}
    s = economy.settings(data)
    out = {}
    for qid in ids:
        q = copy.deepcopy(defs[qid])
        if q.get('custom'):
            options = documents()[1]['tiers'][str(q.get('tier') or 1)]
            raw = options[seed(today, qid) % len(options)]
            reward = parse(raw)
        else:
            raw = f"50:1:{s['daily_lapis']}" if s['daily_lapis'] else q['reward_info']
            reward = [dict(zip(('kind', 'id', 'count'), row)) for row in _parse_reward(raw)]
        q['reward'] = economy.rewards(data, reward)
        out[qid] = q
    return {'version': 1, 'day': today, 'quests': out,
            'bonus': economy.earned(data, s['all_bonus'])}


def read(data):
    block = data.get('daily_quest', {})
    if not isinstance(block, dict):
        raise ValueError('Invalid iOS daily quests: daily state must be a mapping.')
    if 'ios' not in block:
        return None
    try:
        if economy.settings(data) is None:
            raise ValueError('missing recorded economy settings')
        snap = block['ios']
        if (not isinstance(snap, dict) or not isinstance(snap.get('quests'), dict) or
                not isinstance(block.get('set'), list) or not block['set']):
            raise ValueError('invalid daily snapshot structure')
        if (type(snap['version']) is not int or snap['version'] != 1 or snap['day'] != block['day'] or
                len(block['set']) != len(set(block['set'])) or set(snap['quests']) != set(block['set']) or
                type(snap['bonus']) is not int or snap['bonus'] < 0):
            raise ValueError('inconsistent daily snapshot')
        if date.fromisoformat(snap['day']).isoformat() != snap['day']:
            raise ValueError('invalid recorded date')
        for qid, q in snap['quests'].items():
            if (str(q['id']) != qid or type(q['target']) is not int or q['target'] <= 0 or
                    any(not isinstance(q[k], str) or not q[k] for k in ('action', 'name', 'detail')) or
                    type(q['type']) is not int or not 1 <= q['type'] <= 5 or
                    not isinstance(q['reward'], list) or not q['reward']):
                raise ValueError('invalid recorded daily quest')
            for r in q['reward']:
                if any(type(r[k]) is not int for k in ('kind', 'id', 'count')) or r['count'] < 0:
                    raise ValueError('invalid recorded daily reward')
        return snap
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid iOS daily quests: {exc}') from exc


def action_rows(player, action):
    snap = read(player.data)
    if not snap or snap['day'] != day(player.data)[0]:
        return []
    return [(player.daily_progress_key(qid, snap['day']), qid, q['target'])
            for qid, q in snap['quests'].items() if q['action'] == action]


def score(player, action, amount=1):
    if player is None or player.mode == 'frozen' or amount <= 0:
        return
    for key, qid, target in action_rows(player, action):
        player.bump_progress(key, amount, cap=target, what=f'{action} -> daily quest {qid}')


def rows(player):
    from ffbe_config import (DQ_ID, DQ_TYPE, DQ_STATUS, DQ_CURRENT, DQ_TARGET, DQ_LOCATION, DQ_NAME, DQ_DETAILS, DQ_REWARD)
    snap = read(player.data)
    if not snap or snap['day'] != day(player.data)[0]:
        return []
    out = []
    for qid in player.daily_quest_ids():
        q = snap['quests'][qid]
        current = player.progress_value(player.daily_progress_key(qid, snap['day']))
        status = 2 if player.progress_value(player.daily_claim_key(qid, snap['day'])) else int(current >= q['target'])
        reward = ','.join(f"{r['kind']}:{r['count'] if r['kind'] == 30 else r['id']}:{r['count']}" for r in q['reward'])
        out.append({DQ_ID: qid, DQ_TYPE: str(q['type']), DQ_STATUS: str(status), DQ_CURRENT: str(min(current, q['target'])),
                    DQ_TARGET: str(q['target']), DQ_LOCATION: '0', DQ_NAME: q['name'], DQ_DETAILS: q['detail'], DQ_REWARD: reward})
    return out


def serve(spec, reply_id, player):
    from ffbe_config import (DAILY_QUEST_INFO_CARRIERS, DAILY_QUEST_CARRIERS, DAILY_QUEST_TAG, DAILY_QUEST_INFO_TAG,
                            DQ_ID, DQ_STATUS, DQI_REMAINING, DQI_SHOW_COMPLETE, DQI_LEVEL_UP_DIA)
    if reply_id not in DAILY_QUEST_INFO_CARRIERS or player is None:
        return spec
    out = dict(spec) if isinstance(spec, dict) else {}
    shown = rows(player)
    if reply_id in DAILY_QUEST_CARRIERS:
        out[DAILY_QUEST_TAG] = shown
    info = {DQI_REMAINING: str(day(player.data)[1] if shown else 0),
            DQI_SHOW_COMPLETE: '1' if shown and all(r[DQ_STATUS] == '1' for r in shown) else '0', DQI_LEVEL_UP_DIA: '0'}
    if shown:
        info[DQ_ID] = next((r[DQ_ID] for r in shown if r[DQ_STATUS] == '0'), shown[0][DQ_ID])
    if player.data.get('rank', {}).get('last_up'):
        from ffbe_player import _daily_team_lv_string
        from ffbe_config import DQI_TEAM_LV, DQI_RANKUP_LAPIS
        info[DQI_TEAM_LV] = _daily_team_lv_string(player)
        fact = player.data['rank']['last_up']
        if info[DQI_SHOW_COMPLETE] == '1':
            info[DQI_LEVEL_UP_DIA] = str(economy.earned(player.data, DQI_RANKUP_LAPIS *
                max(0, int(fact['to_level']) - int(fact['before_level']))))
    out[DAILY_QUEST_INFO_TAG] = [info]
    return out


def text_rows():
    return {table: [{'key': prefix + q['id'], 'v': [q[field]]} for q in documents()[1]['quests']]
            for table, prefix, field in (('F_TEXT_DAILY_QUEST_NAME', 'MST_DAILY_QUEST_NAME_', 'name'),
                                        ('F_TEXT_DAILY_QUEST_DETAIL', 'MST_DAILY_QUEST_DETAIL_', 'detail'))}
