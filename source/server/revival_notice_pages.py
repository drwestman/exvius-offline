"""Local WebView presentation of replay news; no remote artwork or disk caches."""
from html import escape
from urllib.parse import quote

import revival_notices as policy


def _image(kind, filename):
    if not filename or filename in ('.', '..') or any(c in str(filename) for c in ('/', '\\', '\x00')):
        return ''
    prefix = {'summon': '/banner/en/sd/static_banner/gacha/main/',
              'event': '/en/sd/area/', 'bundle': '/banner/common_lang/sd/static_banner/bundle/'}[kind]
    return '<img src="' + prefix + quote(str(filename), safe='') + '" alt="" onerror="this.style.display=\'none\'">'


def _guarantee(rule, unit_name):
    if rule.get('unit_id'):
        return (unit_name(rule['unit_id']) or 'A featured unit') + ' guaranteed'
    rarity, count = int(rule.get('rarity') or 0), int(rule.get('count') or 1)
    if not rarity:
        return ''
    label = 'NV' if rarity >= 7 else f'{rarity}★ or higher'
    return (label if count == 1 else f'{count} units {label}') + ' guaranteed'


def deal_terms(banner, reward_name, unit_name):
    """Pinned offer facts, including steps, limits, guarantees and bonus choices."""
    out = []
    steps = banner.get('steps') or []
    if steps:
        prices = sorted({int((s.get('cost') or {}).get('amount') or 0) for s in steps})
        price = f'{prices[0]:,}' if len(prices) == 1 else f'{prices[0]:,}–{prices[-1]:,}'
        out.append(f'Step-up: {len(steps)} steps, {price} Lapis a step')
        if banner.get('lap_limit'):
            out.append(f"up to {banner['lap_limit']} laps")
        for i, step in enumerate(steps, 1):
            guarantee = _guarantee(step.get('guarantee') or {}, unit_name)
            if guarantee:
                out.append(f'Step {i}: {guarantee}')
        bonus = sum(bool(s.get('bonus_rewards')) for s in steps)
        if bonus:
            out.append(f'Bonus items on {bonus} of the steps')
    else:
        draws, cost = int(banner.get('draws') or 1), banner.get('cost') or {}
        pulls = f'{draws - 1}+1' if draws in (6, 11) else str(draws)
        if cost.get('kind') == 'free':
            out.append(f'{pulls} free summons')
        elif cost.get('kind') == 'lapis':
            out.append(f"{pulls} summons for {int(cost.get('amount') or 0):,} Lapis")
        elif cost.get('item_id'):
            kind = 23 if cost['kind'] == 'important' else 20
            name = reward_name({'kind': kind, 'id': cost['item_id']})
            out.append(f"{pulls} summons for {int(cost.get('amount') or 1)} {name}")
        for key, label in (('daily_limit', 'per day'), ('weekly_limit', 'per week'), ('purchase_limit', 'per player')):
            if banner.get(key):
                out.append(f"Up to {banner[key]} {label}")
        guarantee = _guarantee(banner.get('guarantee') or {}, unit_name)
        if guarantee:
            out.append(guarantee)
        out.extend(str(slot['label']) + ' guaranteed' for slot in banner.get('guarantee_slots') or [] if slot.get('label'))
        if banner.get('resummon'):
            out.append(f"Up to {banner['resummon']} free re-summons")
        if banner.get('bonus_choice'):
            out.append('Bonus Lapis with every pull')
        if banner.get('bonus_rewards'):
            out.append('Bonus items included')
        if banner.get('unit_select_tickets'):
            out.append('Includes an NV Unit Select Ticket')
    return '. '.join(out) + ('.' if out else '')


def _bundle_price(row):
    if 'usd' in row:
        # Match the canonical Shop's Global bundle conversion, without its stock
        # or schedule projection (which depends on the current campaign).
        from decimal import Decimal, ROUND_CEILING
        from player_state import _load_ndjson
        pack = _load_ndjson('F_DIAMOND_MST.ndjson', 'D7FX3MYh').get('100', {})
        rate = Decimal(str(pack.get('FBjo93gK') or '120')) / Decimal(str(pack.get('AOHRcCC2') or '0.99'))
        price = int((Decimal(str(row['usd'])) * rate).to_integral_value(rounding=ROUND_CEILING))
        return f'{price:,} Lapis'
    if 'gil' in row:
        return f"{int(row['gil']):,} Gil"
    return f"{int(row.get('lapis') or 0):,} Lapis"


def render(summary, *, reward_name, unit_name):
    parts = ['<header><p>Brave Exvius News</p>', f'<h1>Week of {summary["start"]:%B %d, %Y}</h1>']
    era = ("Global's history is complete. Summons rotate weekly now." if summary['finished'] else
           f"Global history: {summary['from']} – {summary['to']}")
    parts.append('<p>' + escape(era) + '</p></header>')
    if summary['holiday']:
        parts.append('<p class="ribbon">' + escape(summary['holiday']) + ' summons are here this week</p>')

    def banner(row):
        image = _image('summon', (row.get('art') or {}).get('banner'))
        parts.append('<article>' + image + '<h3>' + escape(row['name']) + '</h3>')
        if row.get('deal'):
            parts.append('<p>' + escape(deal_terms(row, reward_name, unit_name)) + '</p>')
        ids = [str(uid) for uid in (row.get('community') or {}).get('unit_ids', [])]
        pool = row.get('pool')
        if isinstance(pool, dict):
            ids += [str(uid) for tier in pool.get('tiers', []) for uid in tier.get('featured', [])]
        names = [unit_name(uid) for uid in dict.fromkeys(ids)]
        if any(names):
            parts.append('<p>' + escape(', '.join(filter(None, names))) + '</p>')
        until = (row.get('permanent') or {}).get('until') if isinstance(row.get('permanent'), dict) else (row.get('community') or {}).get('until')
        period = 'Originally ' + row['released'] + (' – ' + until if until else '')
        if row.get('stays'):
            period = 'Available from this week' + (' until history reaches ' + until if until else ' onward')
        parts.append('<p class="date">' + escape(period) + '</p></article>')

    parts.append('<section><h2>New Summons</h2>')
    for group in summary['summons']:
        for row in group['banners']:
            banner(row)
    if not summary['summons']:
        parts.append('<p>No new summons this week.</p>')
    parts.append('</section>')
    if summary['deals']:
        parts.append('<section><h2>Deals</h2>')
        for row in summary['deals']:
            banner(row)
        parts.append('</section>')
    if summary['bundles']:
        parts.append('<section><h2>In the Shop</h2>')
        for row in summary['bundles']:
            parts.append('<article>' + _image('bundle', row.get('icon')) + '<h3>' + escape(row['name']) + '</h3>')
            limit = ' · Once per player' if row.get('limit') == 'once' else ''
            parts.append('<p>' + escape(_bundle_price(row) + limit) + '</p>')
            contents = []
            for raw in row.get('contents') or []:
                kind, iid, count = map(int, str(raw).split(':')[:3])
                contents.append(f"{reward_name({'kind': kind, 'id': iid})} ×{count:,}")
            period = row['from'] + (' – ' + row['until'] if row.get('until') else '')
            parts.append('<p>' + escape(', '.join(contents)) + '</p><p class="date">Originally ' + escape(period) + '</p></article>')
        parts.append('</section>')
    if summary['mails']:
        parts.append('<section><h2>In Your Gifts</h2>')
        for row in summary['mails']:
            items = [f"{reward_name({'kind': k, 'id': i})} ×{n:,}" for k, i, n in row['items']]
            parts.append('<article><h3>' + escape(row['title']) + '</h3><p>' + escape(row.get('message', ''))
                         + '</p><p>Attached: ' + escape(', '.join(items)) + '</p></article>')
        parts.append('</section>')
    parts.append('<section><h2>In the Vortex</h2>')
    art = policy.events._art()
    for row in summary['events']:
        filename = art.get(str(row['area']), {}).get('filename')
        parts.append('<article>' + _image('event', filename) + '<h3>' + escape(row['name']) + '</h3><p>'
                     + escape(str(row.get('kind', '')).split('<br>')[0]) + '</p><p class="date">Originally '
                     + escape(row['release']) + '</p></article>')
    if not summary['events']:
        parts.append('<p>No new events this week. Permanent Vortex areas remain available.</p>')
    parts.append('</section>')
    return PAGE.replace('{{BODY}}', '\n'.join(parts))


def page(data, index, *, now=None):
    from engine_profile import current_profile
    if current_profile().replay is None or not isinstance(index, str) or not index.isascii() or not index.isdigit() or len(index) > 5:
        return None
    content = policy.summary(data, int(index), now)
    if content is None:
        return None
    from ffbe_gacha import unit_name
    from gacha_rates import reward_name
    return render(content, reward_name=reward_name, unit_name=unit_name)


PAGE = '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>This Week in Exvius</title><style>
*{box-sizing:border-box}body{margin:0;background:#0d1230;color:#f3ecd9;font:16px/1.5 system-ui,sans-serif;padding:18px}
header{text-align:center;border-bottom:1px solid #8e794c;padding-bottom:12px}h1,h2{color:#e8c46a;font-family:Georgia,serif}
h1{font-size:25px}h2{font-size:20px}h3{margin:10px 0;font-size:17px}section{max-width:720px;margin:24px auto}
article{background:#151b42;border:1px solid #8e794c;border-radius:5px;overflow:hidden;margin:14px 0;padding:12px}
article img{display:block;max-width:100%;height:auto;margin:auto}p{overflow-wrap:anywhere}.date{color:#b4abc9;font-size:13px}
.ribbon{text-align:center;color:#ffd7a3}header p{margin:8px}article p:last-child{margin-bottom:0}
</style></head><body>{{BODY}}</body></html>'''
