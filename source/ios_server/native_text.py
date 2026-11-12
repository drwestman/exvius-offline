"""Pure English label projections, ported from the pinned revival ios_texts.py.

Callers supply native English text and canonical catalogue definitions. No engine,
campaign, filesystem, process configuration or clock dependencies live here.
"""
import re

JAPANESE = re.compile('[\u3040-\u30ff\u3400-\u9fff]')


def bad(value, key):
    return not value or value == key or value.startswith('TFA') or bool(JAPANESE.search(value))


def clean(value):
    return ' '.join(str(value).replace('^', ' ').split())


def plan(shipped, documents, banners, products, daily):
    """Return explicit (text, replace-existing) rules and declared label gaps."""
    out = {name: {} for name in TEXT_SPECS}

    def put(table, key, text, replace=False):
        if text:
            out[table][key] = (clean(text), replace)

    def fill(table, key, text):
        if bad(shipped.get(table, {}).get(key), key):
            put(table, key, text, True)

    bundles = {'990000001': '2,000 Friend Points'}
    bundles.update({str(row['id']): row['name'] for row in documents['content/revival_bundles.json']['bundles']})
    for bid, name in bundles.items():
        for prefix in ('MST_BUNDLE_NAME_', 'MST_BUNDLE_DESC_'):
            put('F_TEXT_BUNDLE', prefix + bid, name)
    for iid, name in TICKET_NAMES.items():
        put('F_TEXT_ITEM_NAME', 'MST_ITEM_NAME_' + iid, name)
        put('F_TEXT_ITEM_EXPLAIN_SHORT', 'MST_ITEM_SHORTDESCRIPTION_' + iid, TICKET_DESCRIPTIONS[iid])
        put('F_TEXT_ITEM_EXPLAIN_LONG', 'MST_ITEM_LONGDESCRIPTION_' + iid, TICKET_DESCRIPTIONS[iid] + TICKET_LONG)
    for aid, row in documents['content/exbonus_text.json'].items():
        fill('F_TEXT_ABILITY_NAME', 'MST_ABILITY_NAME_' + aid, row.get('name'))
        for prefix in ('MST_ABILITY_SHORTDESCRIPTION_', 'MST_ABILITY_EXPLAIN_SHORT_', 'MST_ABILITY_LONGDESCRIPTION_'):
            fill('F_TEXT_ABILITY_EXPLAIN_SHORT', prefix + aid, row.get('description'))
    battle = documents['battle_names.json']
    for mid, name in {**documents['colosseum_names.json'], **battle['monster']}.items():
        fill('F_TEXT_MONSTER_NAME', 'MST_MONSTER_NAME_' + str(mid), name)
    for sid, name in battle['skill'].items():
        fill('F_TEXT_MONSTER_SKILL_NAME', 'MST_MONSTER_SKILL_NAME_' + str(sid), name)
    fill('F_TEXT_DUNGEON_NAME', 'MST_DUNGEONS_NAME_99999', 'Story')
    for event in documents['event_archive.json']['events']:
        label = {'tfa': 'Clash of Wills', 'parade': 'Dark Visions'}.get(event.get('native_mode'))
        if label:
            put('F_TEXT_AREA_NAME', 'MST_AREA_NAME_' + str(event['area']), label, True)
    item_names = documents['content/ios_text_items.json']['items']
    for ref, name in item_names.items():
        kind, iid = ref.split(':')
        if kind not in ITEM_TEXT:
            continue
        (table, prefix), short, long = ITEM_TEXT[kind]
        fill(table, prefix + iid, name)
        name = name or shipped.get(table, {}).get(prefix + iid)
        for table, prefix in (short, long):
            fill(table, prefix + iid, name)

    def reward_text(raw):
        parts = []
        for entry in filter(None, str(raw or '').split(',')):
            fields = entry.split(':')
            if len(fields) < 2:
                raise ValueError('Invalid product reward label reference.')
            kind, iid = fields[:2]
            count = fields[2] if len(fields) > 2 and fields[2].isdigit() else '1'
            if kind in CURRENCY_NAMES:
                name = CURRENCY_NAMES[kind]
            else:
                table, prefix = REWARD_NAMES.get(kind, (None, None))
                name = shipped.get(table, {}).get(prefix + iid) if table else None
                if bad(name, (prefix or '') + iid):
                    name = item_names.get(kind + ':' + iid)
                if not name:
                    return ''
                if kind == '60':
                    name += ' Recipe'
            parts.append(name + (f' x{int(count):,}' if count != '1' else ''))
        return ', '.join(parts)

    unresolved = []
    for product in products:
        pid = str(product['jPV7Xc4N'])
        title = reward_text(product.get('P4puB2ch'))
        if not title:
            unresolved.append(pid)
            continue
        put('F_TEXT_NV_SHOP_PRODUCT_NAME', 'MST_NVSHOP_PRODUCT_NAME_' + pid, title, True)
        put('F_TEXT_NV_SHOP_PRODUCT_SHORT_DES', 'MST_NVSHOP_PRODUCT_SHORT_DES_' + pid, title, True)
        put('F_TEXT_NV_SHOP_PRODUCT_LONG_DES', 'MST_NVSHOP_PRODUCT_LONG_DES_' + pid, 'Exchange for ' + title + '.', True)
    for banner in banners:
        bid = str(banner['id'])
        key = 'MST_GACHA_NAME_' + bid
        if key not in shipped['F_TEXT_GACHA'] or banner.get('name_override'):
            put('F_TEXT_GACHA', key, banner.get('name') or 'Summon', True)
        text = ('Choose a unit or prism from the selection list.' if banner.get('selection') else
                f"{len(banner['steps'])}-step summon. Review each step's contents above." if banner.get('steps') else
                f"Summon {banner.get('draws', 1)} reward(s). The button shows the cost. See Drop Rates for the reward list.")
        for prefix in ('MST_GACHA_EXPLAIN_LONG_', 'MST_GACHA_EXPLAIN_SHORT_'):
            put('F_TEXT_GACHA', prefix + bid, text)
    for table, rows in daily.items():
        for row in rows:
            put(table, row['key'], row['v'][0], True)
    return out, {'banners': len(banners), 'products': len(products), 'named_products': len(products)-len(unresolved),
                 'unresolved_products': sorted(unresolved, key=int), 'entries': {name: len(rows) for name, rows in out.items()}}

TEXT_SPECS = {
    "F_TEXT_BUNDLE": ("4OBhnBKu", "3VkESseA"),
    "F_TEXT_ITEM_NAME": ("VhkhtvDn", "xDkegMbe"),
    "F_TEXT_ITEM_EXPLAIN_SHORT": ("IAPS1jOu", "TZh30bbo"),
    "F_TEXT_ITEM_EXPLAIN_LONG": ("9NCIDltW", "s3fVSywt"),
    "F_TEXT_GACHA": ("ZJz5QwAy", "Ab2Kb6yJ"),
    "F_TEXT_ABILITY_NAME": ("eSB5Ry3E", "At4ghcWo"),
    "F_TEXT_ABILITY_EXPLAIN_SHORT": ("8GJBzdQV", "D9UVupRQ"),
    "F_TEXT_MONSTER_NAME": ("0xkPiwVI", "UOz3hI2k"),
    "F_TEXT_MONSTER_SKILL_NAME": ("F1z92dkt", "B41kLp2C"),
    "F_TEXT_AREA_NAME": ("4qiOcmtJ", "FhWJxFlW"),
    "F_TEXT_DUNGEON_NAME": ("AyVqkz2B", "0cqVvd61"),
    "F_TEXT_ITEM_EQUIP_NAME": ("E0NdslwL", "SGMI0nIq"),
    "F_TEXT_ITEM_EQUIP_SHORT": ("Nao9HYWk", "I0l1uc2s"),
    "F_TEXT_ITEM_EQUIP_LONG": ("CD4giPVu", "jqe9yQm0"),
    "F_TEXT_MATERIA_NAME": ("2Eg5s20D", "E5jbLGyb"),
    "F_TEXT_MATERIA_EXPLAIN_SHORT": ("8g18k8jD", "DvdwoXYQ"),
    "F_TEXT_MATERIA_EXPLAIN_LONG": ("QEbXmDTD", "3ZaDmbq1"),
    "F_TEXT_IMPORTANT_ITEM_NAME": ("TIKwbf3D", "lx4HCdrQ"),
    "F_TEXT_IMPORTANT_ITEM_EXPLAIN_SHORT": ("YBqAUJt1", "Fc6H1Udw"),
    "F_TEXT_IMPORTANT_ITEM_EXPLAIN_LONG": ("aJ4tvgSq", "iElLxksB"),
    "F_TEXT_NV_SHOP_PRODUCT_NAME": ("s5K4EzVy", "spxNTzFX"),
    "F_TEXT_NV_SHOP_PRODUCT_SHORT_DES": ("39tuQBKk", "bLUjnqGk"),
    "F_TEXT_NV_SHOP_PRODUCT_LONG_DES": ("jhDV9jT6", "uaCuMXaq"),
    "F_TEXT_DAILY_QUEST_NAME": ("FBBD8vv6", "BhDl8FWG"),
    "F_TEXT_DAILY_QUEST_DETAIL": ("gCfFcx75", "xpLyjA9A"),
}

ITEM_TEXT = {
    "20": (("F_TEXT_ITEM_NAME", "MST_ITEM_NAME_"), ("F_TEXT_ITEM_EXPLAIN_SHORT", "MST_ITEM_SHORTDESCRIPTION_"),
           ("F_TEXT_ITEM_EXPLAIN_LONG", "MST_ITEM_LONGDESCRIPTION_")),
    "21": (("F_TEXT_ITEM_EQUIP_NAME", "MST_EQUIP_ITEM_NAME_"), ("F_TEXT_ITEM_EQUIP_SHORT", "MST_EQUIP_ITEM_SHORTDESCRIPTION_"),
           ("F_TEXT_ITEM_EQUIP_LONG", "MST_EQUIP_ITEM_LONGDESCRIPTION_")),
    "22": (("F_TEXT_MATERIA_NAME", "MST_MATERIA_NAME_"), ("F_TEXT_MATERIA_EXPLAIN_SHORT", "MST_MATERIA_SHORTDESCRIPTION_"),
           ("F_TEXT_MATERIA_EXPLAIN_LONG", "MST_MATERIA_LONGDESCRIPTION_")),
    "23": (("F_TEXT_IMPORTANT_ITEM_NAME", "MST_IMPORTANT_ITEM_NAME_"),
           ("F_TEXT_IMPORTANT_ITEM_EXPLAIN_SHORT", "MST_IMPORTANT_ITEM_SHORTDESCRIPTION_"),
           ("F_TEXT_IMPORTANT_ITEM_EXPLAIN_LONG", "MST_IMPORTANT_ITEM_LONGDESCRIPTION_")),
}

TICKET_NAMES = {
    "106213040": "SP Summon Ticket",
    "106213050": "4★/5★/NV SP Summon Ticket",
    "106213030": "5★/NV SP Summon Ticket",
    "106213060": "Bonus Summon Ticket",
    "106213070": "Boss Rush Summon Ticket",
    "106213080": "Brave Ability Box Ticket",
}

TICKET_DESCRIPTIONS = {
    "106213040": "Use for one SP Special Summon.",
    "106213050": "Use for one 4★/5★/NV SP Special Summon.",
    "106213030": "Use for one 5★/NV SP Special Summon.",
    "106213060": "Use for one Bonus Summon.",
    "106213070": "Use for one Boss Rush Event Summon.",
    "106213080": "Use for one Brave Ability Enhancement Box Summon.",
}

TICKET_LONG = " The summon appears on the Summon screen while you hold this ticket."

REWARD_NAMES = {
    "10": ("F_TEXT_UNITS_NAME", "MST_UNIT_NAME_"),
    "20": ("F_TEXT_ITEM_NAME", "MST_ITEM_NAME_"),
    "21": ("F_TEXT_ITEM_EQUIP_NAME", "MST_EQUIP_ITEM_NAME_"),
    "22": ("F_TEXT_MATERIA_NAME", "MST_MATERIA_NAME_"),
    "23": ("F_TEXT_IMPORTANT_ITEM_NAME", "MST_IMPORTANT_ITEM_NAME_"),
    "27": ("F_TEXT_VISION_CARD_NAME", "MST_VISION_CARD_NAME_"),
    "60": ("F_TEXT_RECIPE_BOOK_NAME", "MST_RECIPEBOOK_NAME_"),
}

CURRENCY_NAMES = {"30": "Gil", "31": "Friend Points", "50": "Lapis"}
