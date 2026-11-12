"""Pure native exchange definitions shared by gameplay and offline text preparation."""
from collections import defaultdict

START = '2020-01-01 00:00:00'
END = '2099-12-31 23:59:59'


def build_catalogue(rows, names, parse, *, permanent_shops, tickets=(), event_shops=()):
    """Preserve canonical identities/prices; callers supply content and reward decoding."""
    currencies = defaultdict(list)
    for row in rows('F_MEDAL_EXCHANGE_MST'):
        if not str(row.get('7iJpH5zZ', '')).startswith('20:250'):
            continue
        rewards = parse(row.get('7iJpH5zZ'))
        if len(rewards) == 1 and rewards[0]['kind'] == 20 and str(rewards[0]['id']).startswith('250'):
            currencies[str(row['ak2dhKm3'])].append((row, rewards[0]))
    details, products, offers = [], [], {}

    def detail(did, title, kind, currency, category, banner=0):
        details.append({'3X1gLufw': str(did), 'X1IuZnj2': '0', 'JV8AIH3n': str(category),
                        'Z0EN6jSh': str(len(details) + 1), 'fSxqkF10': str(banner), 'uYcL8IQ1': '-1',
                        '6uvHX2JG': title, 'VjJQ51uG': START, 'm8ivD4NX': END,
                        '0GgK6ytT': str(kind) + ':' + str(currency)})

    def product(pid, did, reward, price, limit, currency, monthly=False):
        row = {'jPV7Xc4N': str(pid), '3X1gLufw': str(did), 'P4puB2ch': reward,
               'e4mG8jTc': str(price), 'uYcL8IQ1': str(-1 if int(limit) == 2147483647 else limit),
               'Z0EN6jSh': str(len(products) + 1),
               '6uvHX2JG': '', 'VjJQ51uG': START, 'm8ivD4NX': END, 'fbcj5Aq9': '', 'JasF1S3u': ''}
        products.append(row)
        offers[str(pid)] = {'detail': str(did), 'rewards': parse(reward), 'cost': currency,
                            'price': int(price), 'limit': int(limit), 'monthly': monthly}

    for index, (currency, stock) in enumerate(sorted(currencies.items(), key=lambda pair: int(pair[0]))):
        did = 850000000 + index
        detail(did, names.get(currency, 'Fragment Exchange'), 20, currency, 5)
        for row, _reward in stock:
            limit = int(row['x0NDnEC9']) if row['kR4n5DxP'] == '1' else 2147483647
            product(900000000 + int(row['S21FT3L8']), did, row['7iJpH5zZ'], row['Qy5EvcK1'],
                    limit, (20, currency))

    # Original monthly VIP stock and prices, recorded on the preservation wiki.
    # https://exvius.fandom.com/wiki/VIP_Coin#Exchange_Shop
    did = 850001000
    detail(did, 'VIP Shop', 50, 1, 6, 10)
    vip = [
        ('23:110260:10', 10000, 1), ('23:110260:1', 1000, 1),
        ('23:80:1', 1750, 1), ('23:50:2', 200, 2),
        ('23:110180:1', 1400, 2), ('23:110160:3', 200, 5),
        ('20:900000001:1', 2500, 1),
        ('10:904000105:1:100:1:500:0:0:100000050', 200, 8),
        ('20:293000200:1', 200, 3), ('20:293000100:1', 1000, 2),
        ('10:900010501:10', 60, 20), ('10:900020401:10:100:60', 70, 20),
        ('27:900020101:1', 700, 10), ('20:1209001274:30', 200, 10),
    ]
    for index, (reward, price, limit) in enumerate(vip):
        product(940000000 + index, did, reward, price, limit, (50, '1'), True)
    for index, shop in enumerate(permanent_shops):
        did = 850001001 + index
        kind, currency = shop['currency']
        category = shop.get('category', 6)
        if category == 6:
            kind, currency = 50, '1'
        banner = 60 if shop['name'] == 'EX Coin Shop' else 0
        detail(did, shop['name'], kind, currency, category, banner)
        for position, row in enumerate(shop['products']):
            product(940001000 + index * 1000 + position, did, row['reward'], row['price'],
                    row['limit'], (kind, currency), shop['reset_months'])
    if tickets or event_shops:
        ticket_order = tuple(tickets)
        tickets = set(ticket_order)
        stock = defaultdict(list)
        for row in rows('F_MEDAL_EXCHANGE_MST'):
            if str(row.get('ak2dhKm3')) in tickets and str(row.get('7iJpH5zZ', '')).startswith('10:'):
                stock[str(row['ak2dhKm3'])].append(row)
        # IDs use the entire pinned ticket list, so unavailable masters or
        # historical filtering never shift another exchange's identity.
        for index, currency in enumerate(ticket_order):
            did = 850003000 + index
            if not stock[currency]:
                continue
            detail(did, names.get(currency, 'NV Unit Select').strip(), 20, currency, 5)
            for row in stock[currency]:
                pid = 900000000 + int(row['S21FT3L8'])
                limit = int(row['x0NDnEC9']) if row['kR4n5DxP'] == '1' else 2147483647
                product(pid, did, row['7iJpH5zZ'], row['Qy5EvcK1'], limit, (20, currency))
                offers[str(pid)]['requires_currency'] = True
        for index, shop in enumerate(event_shops):
            did = 850002000 + index
            kind, currency = shop['currency']
            detail(did, shop['name'], kind, currency, shop.get('category', 4))
            for position, row in enumerate(shop['products']):
                pid = 950000000 + index * 1000 + position
                product(pid, did, row['reward'], row['price'], row['limit'], (kind, str(currency)))
                offers[str(pid)]['event_areas'] = list(shop['event_areas'])
    return details, products, offers

