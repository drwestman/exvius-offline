"""Pure pinned deal catalogue, printed bonuses and pool restrictions for iOS.

Data and rules are selectively ported from revival
47a13c084f42cf1b83b53173d0c21065c78fc2de. No engine imports or view-time writes.
"""
import copy
from functools import lru_cache
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEASONAL_WORDS = ('halloween', 'christmas', 'holiday', 'festive', 'summer', 'swimsuit', 'valentine',
                  'bride', 'wedding', 'lunar new year', 'new year', 'spring', 'winter', 'easter')
LIMITED_SERIES = ('ffxv', 'final fantasy xv', 'ffvii remake', 'ff7r', 'final fantasy vii remake',
                  'ffx-2', 'ffxiv', 'ff14', 'dissidia', 'ff brave exvius heroes')


@lru_cache(maxsize=1)
def banners():
    try:
        rows = json.loads((HERE / 'gacha_deals.json').read_text(encoding='utf-8'))['banners']
        if not isinstance(rows, list) or not rows or any(not isinstance(row, dict) or not row.get('id') for row in rows):
            raise ValueError('expected a nonempty banner list')
        if len({str(row['id']) for row in rows}) != len(rows):
            raise ValueError('duplicate deal IDs')
        return tuple(rows)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid pinned summon deals: {exc}') from exc


@lru_cache(maxsize=1)
def printed():
    try:
        rows = json.loads((HERE / 'banner_deals.json').read_text(encoding='utf-8'))['banners']
        if not isinstance(rows, dict) or not rows:
            raise ValueError('expected printed bonus definitions')
        return rows
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid pinned printed summon bonuses: {exc}') from exc


def apply_printed(banner):
    deal = printed().get(str(banner['id']))
    if not deal:
        return banner
    out = copy.deepcopy(banner)
    ten, offer = deal.get('ten_plus_one') or {}, out.get('secondary_offer')
    if ten and isinstance(offer, dict) and offer:
        for key in ('bonus_rewards', 'bonus_choice'):
            if ten.get(key) and not offer.get(key):
                offer[key] = copy.deepcopy(ten[key])
        want = ten.get('guarantee')
        if want and int(want.get('rarity') or 0) > int((offer.get('guarantee') or {}).get('rarity') or 0):
            offer['guarantee'] = copy.deepcopy(want)
    every = deal.get('every_pull') or {}
    if every.get('bonus_rewards') and not out.get('bonus_rewards'):
        out['bonus_rewards'] = copy.deepcopy(every['bonus_rewards'])
    return out


@lru_cache(maxsize=1)
def ticket_ids():
    return tuple(sorted({str(ticket) for row in banners() for ticket in row.get('unit_select_tickets', [])}, key=int))


def effective_banner(banner, *parts):
    """One definition for a step/secondary offer, shared by draws and rate projections."""
    out = dict(banner)
    for part in parts:
        if not part:
            continue
        if part.get('pool') is not None:
            out['pool'] = part['pool']
            out.pop('reward_pool', None)
        if part.get('reward_pool') is not None:
            out['reward_pool'] = part['reward_pool']
        for key in ('cost', 'draws', 'guarantee', 'guarantee_slots', 'bonus_rewards', 'bonus_choice'):
            if key in part:
                out[key] = part[key]
    return out


def valid_weights(rows):
    weights = [float(row.get('rate', 0)) for row in rows]
    return bool(weights) and all(math.isfinite(w) and w >= 0 for w in weights) and any(w > 0 for w in weights)


@lru_cache(maxsize=1)
def _permanent_units():
    from revival_summons import catalogue
    by_id = {str(row['id']): row for row in catalogue()}
    return frozenset(str(uid) for bid in ('150', '9100203', '49')
                     for pool in [(by_id.get(bid) or {}).get('pool') or {}] if isinstance(pool, dict)
                     for tier in pool.get('tiers', []) for uid in tier.get('units', []))


@lru_cache(maxsize=1)
def limited_units():
    from gacha_archive import COLLABORATIONS
    from revival_summons import catalogue
    limited, ordinary = set(), set()
    for banner in catalogue():
        community = banner.get('community') or {}
        ids = {str(uid) for uid in community.get('unit_ids', [])}
        pool = banner.get('pool')
        if isinstance(pool, dict):
            ids.update(str(uid) for tier in pool.get('tiers', []) for uid in tier.get('featured', []))
        search = (banner.get('name', '') + ' ' + str((banner.get('art') or {}).get('banner', ''))).lower()
        if community.get('limited') or any(word.lower() in search for word in COLLABORATIONS + SEASONAL_WORDS + LIMITED_SERIES):
            limited.update(ids)
        else:
            ordinary.update(ids)
    return frozenset(limited - ordinary)


def pool_rule_allows(banner, unit_id, master=None):
    rule = banner.get('pool_rule') or {}
    if not rule:
        return True
    uid, pool = str(unit_id), banner.get('pool')
    if isinstance(pool, dict) and any(uid in map(str, tier.get('featured', [])) for tier in pool.get('tiers', [])):
        return True
    from revival_summons import unit_dates
    day = unit_dates().get(uid)
    if rule.get('released_by') and day is not None and day > rule['released_by']:
        return False
    if rule.get('released_from') and (day is None or day < rule['released_from']):
        return False
    if {'limited', 'collab'} & set(rule.get('exclude') or []):
        if uid in limited_units():
            return False
        master = master or {}
        base = uid == str(master.get('woghJa61')) and str(master.get('9fW0TePj')) in ('3', '4', '5')
        if base and day and day <= '2019-08-31' and not uid.startswith('9'):
            permanent = _permanent_units()
            if permanent and uid not in permanent:
                return False
    return True
