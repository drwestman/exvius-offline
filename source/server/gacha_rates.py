"""Read-only content for the original client's summon drop-rate WebView."""
from functools import lru_cache
from html import escape
import json
from pathlib import Path

from data_paths import TEXT_DIR
from revival_summons import reward_allowed, unit_allowed
from engine_profile import current_profile


@lru_cache(maxsize=1)
def _item_names():
    names = {}
    for filename in ('F_TEXT_ITEM_NAME.ndjson', 'F_TEXT_IMPORTANT_ITEM_NAME.ndjson'):
        with (Path(TEXT_DIR) / filename).open(encoding='utf-8') as source:
            for line in source:
                row = json.loads(line)
                values = row.get('v', [])
                if values:
                    names[row['key'].rsplit('_', 1)[-1]] = values[0]
    return names


def reward_name(reward):
    from ffbe_gacha import unit_name
    if reward.get('display_name'):
        return str(reward['display_name'])
    if int(reward['kind']) in (30, 31, 50):
        return {30: 'Gil', 31: 'Friend Points', 50: 'Lapis'}[int(reward['kind'])]
    if int(reward['kind']) == 10:
        name = unit_name(reward['id']) or 'Unit ' + str(reward['id'])
        points = reward.get('affinity_points', [])
        if len(points) == 2 and any(str(point).isdigit() and int(point) for point in points):
            name += ' (ALL ' + str(max(int(p) if str(p).isdigit() else 0 for p in points) / 10).rstrip('0').rstrip('.') + '%)'
        return name
    return _item_names().get(str(reward['id']), 'Item ' + str(reward['id']))


def _table(pool, mixed=False):
    from ffbe_gacha import unit_name
    total = sum(max(0, float(row.get('rate', 0))) for row in pool)
    if not total:
        return '<p>No eligible rewards.</p>'
    rows = []
    for row in sorted(pool, key=lambda r: -float(r.get('rate', 0))):
        name = reward_name(row) if mixed else unit_name(row['unit_id'])
        count = int(row.get('count', 1))
        chance = max(0, float(row.get('rate', 0))) * 100 / total
        rows.append('<tr><td>%s%s</td><td>%.6f%%</td></tr>' % (
            escape(name), (' x' + str(count)) if count != 1 else '', chance))
    return '<table><thead><tr><th>Reward</th><th>Chance per draw</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'


def page(banner_id):
    from ffbe_gacha import all_banners
    from player_state import expand_pool, summon_subpool, summon_pool, summon_guarantee_pool
    banner = next((b for b in all_banners() if str(b['id']) == str(banner_id)), None)
    if banner is None:
        return None
    notice = ('Choose a unit or prism from the selection list.' if banner.get('selection') else
              'The rates below apply to this summon. Guaranteed slots and additional rewards are listed separately.')
    body = '<h1>' + escape(banner['name']) + '</h1><p class="notice">' + escape(notice).replace('\n', '<br>') + '</p>'
    if current_profile().name == 'ios-revival' and banner.get('resummon'):
        from revival_deal_commands import remaining
        from ffbe_state import State
        left = remaining(State.player, banner) if State.player else 0
        body += '<p>Free re-summons remaining: ' + str(left) + '. Each replaces the previous main result. '
        body += 'The paid-pull bonus is kept. Using or changing a result prevents replacement.</p>'
    if banner.get('boxes'):
        body += '<p>The first five boxes draw without replacement. Remaining quantities and featured rewards appear in the original Box Details screen.</p>'
        body += '<h2>Standard pool after the five boxes</h2><p>Materials 80%, enhancers 19%, ultra-rare rewards 1%, divided equally within each group.</p>'
    if banner.get('selection'):
        from exvius_actions import _mst
        from ffbe_gacha import unit_name
        choices = _mst('F_GACHA_SELECT_UNIT_MST.ndjson', '3HriTp6B')
        body += '<table><thead><tr><th>Selectable unit</th><th>Select tickets</th></tr></thead><tbody>' + ''.join(
            '<tr><td>' + escape(unit_name(iid)) + '</td><td>' + row['e4mG8jTc'] + '</td></tr>'
            for iid, row in choices.items() if unit_allowed(banner, iid)) + '</tbody></table>'
    offers = banner.get('steps') or [banner]
    if not banner.get('steps') and banner.get('secondary_offer'):
        offers = [banner, banner['secondary_offer']]
    for index, offer in enumerate([] if banner.get('selection') else offers):
        if banner.get('steps'):
            body += '<h2>Step ' + str(index + 1) + '</h2>'
        elif len(offers) > 1:
            body += '<h2>' + ('Single summon' if index == 0 else 'Multi-summon') + '</h2>'
        cost = offer.get('cost', banner.get('cost', {}))
        if isinstance(cost, dict):
            amount = int(cost.get('amount', 0))
            currency = cost.get('kind', 'free')
            if cost.get('item_id'):
                currency = _item_names().get(str(cost['item_id']), 'Item ' + str(cost['item_id']))
            if amount:
                cost_text = str(amount) + ' ' + escape(str(currency))
            elif offer.get('ticket_group_id') or banner.get('ticket_group_id'):
                from player_state import ticket_group_items
                group = offer.get('ticket_group_id') or banner.get('ticket_group_id')
                tickets = []
                for item_type, item_id, _rarity in sorted(ticket_group_items(group), key=lambda row: row[1],
                                                          reverse=True):
                    name = _item_names().get(str(item_id), f'Item {item_id}')
                    tickets.append(escape(name))
                cost_text = '1 ticket from ' + (', '.join(tickets) if tickets else 'the ticket group')
            else:
                cost_text = 'Free'
            body += '<p>' + str(offer.get('draws', banner.get('draws', 1))) + ' draws. Cost: ' + cost_text + '.</p>'
        ios = current_profile().name == 'ios-revival'
        if ios:
            from revival_deals import effective_banner
            definition = effective_banner(banner, offer)
            pool = summon_pool(definition)
        else:
            definition = dict(banner)
            if 'pool' in offer:
                definition['pool'] = offer['pool']
            pool = banner.get('reward_pool') or expand_pool(definition)
            if banner.get('reward_pool'):
                pool = [row for row in pool if reward_allowed(banner, row)]
        body += _table(pool, bool(definition.get('reward_pool')))
        guarantee = offer.get('guarantee', banner.get('guarantee', {}))
        if ios:
            guarantee = definition.get('guarantee') or {}
        if guarantee:
            count = int(guarantee.get('count', 1))
            if guarantee.get('rarity'):
                body += '<p>' + str(count) + ' guaranteed reward(s) of rarity ' + str(guarantee['rarity']) + ' or higher.</p>'
                if ios:
                    restricted = summon_guarantee_pool(definition, pool, guarantee)
                else:
                    restricted = summon_subpool(definition, guarantee['pool']) if guarantee.get('pool') else pool
                    restricted = [r for r in restricted if int(r.get('rarity', 0)) >= int(guarantee['rarity'])]
                body += '<h3>Guaranteed slot rates</h3>' + _table(restricted)
            if guarantee.get('unit_id') and unit_allowed(definition, guarantee['unit_id']):
                from ffbe_gacha import unit_name
                body += '<p>Guaranteed unit: ' + escape(unit_name(guarantee['unit_id'])) + '.</p>'
        bonuses = offer.get('bonus_rewards', banner.get('bonus_rewards', []))
        for slot in offer.get('guarantee_slots', banner.get('guarantee_slots', [])):
            body += '<h3>' + str(slot.get('count', 1)) + ' guaranteed ' + escape(slot.get('label', 'reward')) + '</h3>'
            body += _table(summon_subpool(definition, slot['pool']))
        bonuses = [reward for reward in bonuses if reward_allowed(definition, reward)]
        if bonuses:
            body += '<h3>Additional rewards</h3><ul>' + ''.join(
                '<li>' + escape(reward_name(r)) + ' x' + str(r['count']) + '</li>' for r in bonuses) + '</ul>'
        choices = offer.get('bonus_choice', banner.get('bonus_choice', []))
        if choices:
            total = sum(float(choice['rate']) for choice in choices)
            body += '<h3>Bonus alternatives</h3><ul>' + ''.join('<li>' +
                ', '.join(escape(reward_name(r)) + ' x' + str(r['count']) for r in choice['rewards']
                          if reward_allowed(definition, r)) +
                ': %.2f%%</li>' % (float(choice['rate']) * 100 / total) for choice in choices) + '</ul>'
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Summon Rates</title><style>body{margin:0;padding:14px;background:#081d43;color:white;font:16px Arial}'
            'h1{font-size:21px}h1,h2,h3{color:#ffe398}.notice{padding:12px;background:#15385b;line-height:1.5}'
            'table{width:100%;border-collapse:collapse}th,td{padding:9px;border:1px solid #4b6990;text-align:left}'
            'td:last-child{white-space:nowrap}th{background:#194875}</style></head><body>' + body + '</body></html>')
