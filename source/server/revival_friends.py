"""iOS crowd policy, derived from friend_players.py at revival 47a13c084f42.

Only initialize() changes the supplied candidate campaign. Directory, accepted
ids and suggestions are projections: never seed, migrate or dirty player state.
Names, ranks and weekly choices retain the pinned deterministic random seeds.
"""
import copy
from datetime import datetime, timezone
from functools import lru_cache
import os
import random
from zoneinfo import ZoneInfo

from replay_calendar import preview, read_anchor, rotation_week
from revival_summons import unit_dates

ID_BASE = 910000000

_PARTS_A = [
    "Moogle", "Chocobo", "Cactuar", "Tonberry", "Kupo", "Mako", "Lapis", "Limit", "Esper", "Mithril",
    "Phoenix", "Crystal", "Ultima", "Omega", "Zodiac", "Behemoth", "Malboro", "Bomb", "Ahriman", "Coeurl",
    "Senpai", "Kaiju", "Shonen", "Sakura", "Kitsune", "Ronin", "Shinobi", "Mecha", "Neko", "Oni",
    "Tsundere", "Isekai", "Ramen", "Bento", "Mochi", "Tanuki", "Kawaii", "Sensei", "Chibi", "Yokai",
    "Pixel", "Turbo", "Combo", "Critical", "Rare", "Rainbow", "Gacha", "Speedrun", "Respawn", "Loot",
]
_PARTS_B = [
    "Main", "Slayer", "Knight", "Sage", "Blade", "Hunter", "Dreamer", "Kun", "Chan", "Sama",
    "Prime", "Zero", "Rising", "Breaker", "Lord", "Rider", "Mage", "Ninja", "Bard", "Tamer",
    "Whale", "Fan", "Pilot", "Smith", "Fist", "Storm", "Fang", "Heart", "Soul", "Star",
]
_HANDLES = [
    "LimitBreakLu", "ChainItAll", "PullForNoctis", "XxDarkFinaxX", "RainbowRain", "TrustMeBro",
    "NoLapisNoLife", "SummonAddict", "KupoKupoKupo", "MogKingFan", "OnlyChains", "DualcastDan",
    "GilSnapper", "BraveShifter", "TMRhunter", "VortexVet", "ArenaAce", "ExpeditionEd",
    "OneMorePull", "SaltyRNG", "PityTimer", "GuaranteedGG", "WhaleWatcher", "F2Pforever",
    "MasterTrust", "SevenStarSam", "SoulCrystal", "MegacrystalM", "AwakenedAmy", "PrismPrince",
    "CrystalChaser", "ElementalEli", "KillerChains", "MultiCaster", "TankNTaunt", "CoverGod",
    "StopKillers", "BreakerBob", "AilmentAndy", "EvokerEve", "BlueMageBo", "BardicBella",
    "SamuraiSoul", "DragoonDash", "JumpingJin", "NinjaNoodle", "MonkMode", "PaladinPam",
    "DarkKnightDK", "SpellbladeSi", "ChemistKai", "ThiefTaro", "TimeMageTia", "GeomancerGo",
    "OtakuOracle", "ShonenJump", "MechaPilot", "IsekaiIvy", "KawaiiKaiju", "SenpaiNotice",
    "RamenRonin", "NekoNinja", "ChibiChamp", "AnimeAlex", "MangaMax", "CosplayCam",
    "PixelPaladin", "RetroRyu", "SpeedrunSol", "ComboCarl", "FrameDataFi", "HitboxHana",
]


@lru_cache(maxsize=8)
def names(count: int = 200) -> tuple[str, ...]:
    """`count` unique handles of at most 12 characters, the same every time."""
    out, seen = [], set()
    for name in _HANDLES:
        if len(name) <= 12 and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    rng = random.Random("exvius-players")
    combos = [a + b for a in _PARTS_A for b in _PARTS_B if len(a + b) <= 12]
    rng.shuffle(combos)
    for name in combos:
        if len(out) >= count:
            break
        if rng.random() < 0.25:
            name += str(rng.randint(1, 99))
            if len(name) > 12:
                continue
        if name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    order = list(range(len(out)))
    random.Random("exvius-players-order").shuffle(order)
    return tuple(out[i] for i in order[:count])


def clock():
    return datetime.now(timezone.utc)


def _setting(name, default, maximum):
    try:
        return max(0, min(maximum, int(os.environ.get(name, str(default)))))
    except ValueError:
        return default


def settings(data):
    """Absent means uninitialized; an invalid recorded configuration is not a new campaign."""
    state = data.get('exvius_friends', {})
    if not isinstance(state, dict) or not isinstance(state.get('relations', {}), dict):
        raise ValueError('Invalid iOS friend relationships.')
    for fid, relation in state.get('relations', {}).items():
        if (not isinstance(fid, str) or not isinstance(relation, dict) or
                type(relation.get('type')) is not int or relation['type'] not in (0, 1, 2, 3) or
                type(relation.get('favorite', 0)) is not int or relation.get('favorite', 0) not in (0, 1)):
            raise ValueError('Invalid iOS friend relationship.')
    if 'simulation' not in state:
        return None
    raw = state['simulation']
    if (not isinstance(raw, dict) or set(raw) != {'version', 'count', 'suggestions'} or
            type(raw['version']) is not int or raw['version'] != 1 or
            type(raw['count']) is not int or not 0 <= raw['count'] <= 999 or
            type(raw['suggestions']) is not int or not 0 <= raw['suggestions'] <= 999):
        raise ValueError('Invalid iOS friend simulation settings.')
    return raw


def initialize(data, *, yaml_friends=None):
    """Seed the candidate once; the campaign command owns the single atomic save."""
    if settings(data) is not None:
        return False
    if yaml_friends is None:
        from ffbe_friends import configured_friends
        yaml_friends = configured_friends()
    state = copy.deepcopy(data.get('exvius_friends', {}))
    relations = state.setdefault('relations', {})
    for friend in yaml_friends:
        fid = str(friend['friend_id'])
        relations.setdefault(fid, {'type': 1, 'favorite': int(bool(state.get('favorites', {}).get(fid)))})
    count = _setting('EXVIUS_PLAYERS', 200, 999)
    start = _setting('EXVIUS_START_FRIENDS', 15, 100)
    picks = random.Random('exvius-start-friends').sample(range(ID_BASE + 1, ID_BASE + count + 1), min(start, count))
    accepted = sum(r['type'] == 1 for r in relations.values())
    for fid in sorted(picks):
        if str(fid) not in relations and accepted < 100:
            relations[str(fid)] = {'type': 1, 'favorite': 0}
            accepted += 1
    state['simulation'] = {'version': 1, 'count': count,
                           'suggestions': _setting('EXVIUS_PLAYER_SUGGESTIONS', 10, 999)}
    data['exvius_friends'] = state
    data.setdefault('counts', {})['friend'] = sum(r['type'] == 1 for r in relations.values())
    return True


def accepted_ids(data):
    settings(data)  # Validate even when the caller only needs stored relations.
    return tuple(fid for fid, relation in data.get('exvius_friends', {}).get('relations', {}).items()
                 if relation['type'] == 1)


def suggestion_ids(data, now=None):
    config = settings(data)
    if config is None:
        return ()
    saved = read_anchor(data)
    if saved is None:
        return ()
    now = now if now is not None else clock()
    local = now.astimezone(ZoneInfo(saved[1].timezone))
    relations = data.get('exvius_friends', {}).get('relations', {})
    others = [str(ID_BASE + i) for i in range(1, config['count'] + 1)
              if relations.get(str(ID_BASE + i), {}).get('type', 0) == 0]
    # The fork samples integer ids; preserve that ordering and random seed.
    picks = random.Random('exvius-suggest-' + local.strftime('%Y-%m-%d')).sample(
        others, min(config['suggestions'], len(others)))
    return tuple(picks)


class Directory:
    """A request-local view. Pool caches cannot outlive its campaign/week/cutoff."""
    def __init__(self, data, now=None):
        self.data = data
        self.config = settings(data)
        self.now = now if now is not None else clock()
        calendar = preview(data, self.now)
        self.window = calendar['windows'][0]
        self.week = rotation_week(self.now, read_anchor(data)[1]).number if calendar['anchored'] else 0
        last = max(max(unit_dates().values()), '2024-08-22')
        self.cutoff = None if self.window['from'] > last else self.window['to']
        self._pools = {}

    def ids(self):
        return tuple(str(ID_BASE + i) for i in range(1, self.config['count'] + 1)) if self.config else ()

    def unit_pool(self, rank):
        from player_state import named_unit_ids, unit_roots_by_rarity, unit_mst, unit_stats
        rarities = ('5', '7') if rank >= 100 else ('4', '5') if rank < 40 else ('4', '5', '7')
        if rarities not in self._pools:
            named = named_unit_ids()
            roots = unit_roots_by_rarity()
            levels = {'4': 60, '5': 80, '7': 99}
            dates = unit_dates()
            pool = []
            for rarity in rarities:
                for uid in roots.get(rarity, []):
                    if uid.startswith('9') or (named and uid not in named):
                        continue
                    if self.cutoff is not None and dates.get(uid, '') >= self.cutoff:
                        continue
                    cap = int(unit_mst(uid)['aU3o2D4t'])
                    level = min(levels[rarity], cap)
                    # Some named base rows are empty placeholders. They cannot
                    # render a valid native helper, even though their name ships.
                    if level > 0 and any(unit_stats(uid, level)):
                        pool.append((uid, level))
            if not pool:
                # The pinned early-game fallback, still resolved through real masters.
                pool = [('100000102', 1)]
            self._pools[rarities] = tuple(pool)
        return self._pools[rarities]

    def by_id(self, friend_id):
        from ffbe_friends import _entry
        try:
            index = int(friend_id) - ID_BASE
        except (TypeError, ValueError):
            return None
        if self.config is None or not 1 <= index <= self.config['count']:
            return None
        rng = random.Random(f'exvius-player-{index}')
        rank = rng.choice([rng.randint(8, 40), rng.randint(40, 120), rng.randint(120, 250), rng.randint(60, 180)])
        uid, level = random.Random(f'exvius-player-{index}-week-{self.week}').choice(self.unit_pool(rank))
        return _entry(index, {'display_name': names(self.config['count'])[index - 1],
                              'friend_id': ID_BASE + index, 'rank': rank, 'emblem_id': 0,
                              'unit': {'master_id': uid, 'level': level}})


def catalogue(data, now=None):
    from ffbe_friends import configured_friends
    yaml = {str(f['friend_id']): f for f in configured_friends()}
    directory = Directory(data, now)
    generated = {fid: directory.by_id(fid) for fid in directory.ids() if fid not in yaml}
    return {**yaml, **generated}


def state_view(data, catalog):
    """New curated helpers default to accepted; explicit tombstones always win."""
    state = copy.deepcopy(data.get('exvius_friends', {}))
    relations = state.setdefault('relations', {})
    for fid in catalog:
        if not ID_BASE < int(fid) <= ID_BASE + 999:
            relations.setdefault(fid, {'type': 1, 'favorite': int(bool(state.get('favorites', {}).get(fid)))})
    return state

