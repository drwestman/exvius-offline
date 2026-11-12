"""Supply the original native exchange screens with recovered shop stock."""
from functools import lru_cache
import json
from pathlib import Path
import time

from data_paths import TEXT_DIR
from exvius_actions_shops import (_action, _feature, _grant, _int, _node, _pay,
                                  _reply, _require, _rewards, _rows, _store)
from exvius_rewards import parse
from ffbe_state import State
from engine_profile import current_profile
from exchange_catalogue import START, END, build_catalogue


def catalogue():
    raw = _catalogue()
    if current_profile().name == 'ios-revival':
        from revival_exchanges import policy
        return policy(State.player.data if State.player else {}).filter_catalogue(raw)
    return raw


@lru_cache(maxsize=1)
def _catalogue():
    names = {}
    for line in (Path(TEXT_DIR) / 'F_TEXT_ITEM_NAME.ndjson').read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        names[row['key'].rsplit('_', 1)[-1]] = row['v'][0]
    recovered = json.loads(Path(__file__).with_name('content').joinpath('permanent_shops.json').read_text())
    tickets, events = (), ()
    if current_profile().name == 'ios-revival':
        from revival_deals import ticket_ids
        from revival_exchanges import event_shops
        tickets, events = ticket_ids(), event_shops()
    return build_catalogue(_rows, names, parse, permanent_shops=recovered['shops'],
                           tickets=tickets, event_shops=events)


def receipt_key(pid, offer):
    if not offer['monthly']:
        return pid
    months = int(offer['monthly'])
    if current_profile().name == 'ios-revival':
        from replay_calendar import read_anchor
        from engine_profile import IOS_REVIVAL
        from revival_summons import clock
        from zoneinfo import ZoneInfo
        saved = read_anchor(State.player.data)
        now = clock().astimezone(ZoneInfo((saved[1] if saved else IOS_REVIVAL.replay).timezone))
        return pid + '/' + str((now.year * 12 + now.month - 1) // months)
    now = time.localtime()
    period = (now.tm_year * 12 + now.tm_mon - 1) // months
    return pid + '/' + str(period)


def labels():
    rows = _labels()
    if current_profile().name == 'ios-revival':
        offered = catalogue()[2]
        return {pid: row for pid, row in rows.items() if pid in offered}
    return rows


@lru_cache(maxsize=1)
def _labels():
    names = {}
    for kind, table in [(20, 'ITEM'), (23, 'IMPORTANT_ITEM'), (10, 'UNITS'), (27, 'VISION_CARD'),
                        (21, 'ITEM_EQUIP'), (22, 'MATERIA'), (60, 'RECIPE_BOOK')]:
        path = Path(TEXT_DIR) / ('F_TEXT_' + table + '_NAME.ndjson')
        for line in path.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            names[kind, row['key'].rsplit('_', 1)[-1]] = row['v'][0].strip()
    result = {}
    for pid, offer in _catalogue()[2].items():
        texts = []
        for row in offer['rewards']:
            name = names[row['kind'], str(row['id'])]
            if row.get('affinity_points', [''])[0]:
                name += ' (ALL ' + str(int(row['affinity_points'][0]) // 10) + '%)'
            if row['count'] > 1:
                name += ' x' + str(row['count'])
            texts.append(name)
        title = ', '.join(texts)
        result[pid] = {'name': title, 'description': 'Exchange for ' + title + '.'}
    return result


def entry(spec, req):
    details, products, offers = catalogue()
    out = _reply(spec)
    out['F2rNo6qf'] = [dict(row) for row in details]
    out['TPrh6Ay3'] = [dict(row) for row in products]
    counts = _feature('shop_catalogue').get('counts', {})
    out['qS62ewjH'] = [{'jPV7Xc4N': pid, '3X1gLufw': offer['detail'],
                        'Q8GLK1pz': str(counts.get(receipt_key(pid, offer), 0))}
                       for pid, offer in offers.items()]
    return out


def purchase(spec, req):
    if current_profile().name == 'ios-revival':
        spec = dict(spec or {})
        spec.pop('4owH1uT2', None)  # A recorded success row must never survive a refused purchase.
    return _purchase(spec, req)


@_action
def _purchase(spec, req):
    if current_profile().name == 'ios-revival':
        from replay_calendar import read_anchor
        _require(read_anchor(State.player.data) is not None, 'iOS campaign is not initialized')
    node = _node(req, '4mrD6JuA') or {}
    pid = str(node.get('jPV7Xc4N', ''))
    offer = catalogue()[2].get(pid)
    _require(offer is not None, 'unknown exchange product')
    quantity = _int(node.get('Qy5EvcK1'), 1)
    counts = dict(_feature('shop_catalogue').get('counts', {}))
    key = receipt_key(pid, offer)
    bought = int(counts.get(key, 0))
    _require(bought + quantity <= offer['limit'], 'exchange stock exhausted')
    rewards = [dict(row, count=row['count'] * quantity) for row in offer['rewards']]
    _rewards(rewards)
    kind, currency = offer['cost']
    amount = offer['price'] * quantity
    if kind == 50:
        _require(State.player.spend_lapis(amount), 'not enough Lapis')
    else:
        _pay([{'kind': kind, 'id': currency, 'count': amount}])
    _grant(rewards)
    counts[key] = bought + quantity
    _store('shop_catalogue', {'counts': counts})
    out = _reply(spec)
    out['4owH1uT2'] = [{'jPV7Xc4N': pid, '3X1gLufw': offer['detail'], 'Q8GLK1pz': str(counts[key])}]
    return out
