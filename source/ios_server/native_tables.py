"""Native iOS table preparation rules; no filesystem or engine state access."""
from dataclasses import dataclass
import hashlib
import re

from ios_server import version_policy
from ios_server.table_codec import master_rows, patch_master, patch_text, text_lines, normalize_master, validate_master
from ios_server.native_registry import definitions
from revival_daily import text_rows
from ios_server.native_text import TEXT_SPECS
import revival_economy

PIPELINE_VERSION = 6
VERSION_OFFSET = version_policy.VERSION_OFFSET
VERSION_STEP = version_policy.VERSION_STEP
EARLY_PACKS = frozenset(('resources_common.cpk', 'resources.cpk'))
# Gacha detail opens synchronously: its UI and default Ochu preview cannot wait
# behind the background movie queue (confirmed by native reports on 2026-11-11).
MENU_PACKS = frozenset(('gacha1_common.cpk', 'gacha1.cpk', 'monster3_common.cpk'))
UPFRONT_PACKS = EARLY_PACKS | MENU_PACKS
# Unit list, party, equip, and unit detail scenes load unit icons/illustrations
# synchronously from the `unit` CPK group without triggering on-demand downloads.
# Leaving unit*_common.cpk / unit*_sg_common.cpk / unit22.cpk in background traps
# Global-original packs (unit1_sg_common.cpk..unit3_sg_common.cpk) behind ~4.5 GB
# of LBMovie/beastMovie packs and leaves JP-restored unit packs unreconciled.
UNIT_ART_PACK = re.compile(r'^unit[0-9]+(?:_sg)?(?:_common)?\.cpk$')
RATE_URL = 'https://v910-lapis.gumi.sg/lapisProd/app/php/web/statics/probability/sg_summons_list.php'


def is_promoted_menu_pack(row):
    name = row.get('pJ56sAEo', '')
    if not isinstance(name, str):
        return False
    if name in MENU_PACKS:
        return True
    return row.get('3LHdc6Qa') == 'unit' and bool(UNIT_ART_PACK.fullmatch(name))


def is_upfront_pack(row):
    name = row.get('pJ56sAEo', '')
    return name in EARLY_PACKS or is_promoted_menu_pack(row)


@dataclass(frozen=True)
class Table:
    name: str
    token: str
    key: str
    localized: bool = False
    cipher: str = 'cbc'

    def path(self, version):
        folder = 'localized_texts/en' if self.localized else 'mst'
        return f'{folder}/Ver{version}_{self.token}.dat'


RESOURCE = Table('F_RESOURCE_MST', 'ZQqB38Ns', 'u6q3F02d')
VERSIONS = Table('F_RESOURCE_VERSION_MST_LOCALIZE', 'A1L1GlaQ', 'JchlFPWK')
QUEST = Table('F_QUEST_MST', '2Px75LpY', '20mEeKo3')
URL = Table('F_URL_MST', '9wmd4iua', 'UREmi85S')
INDEX = Table('F_LOCALIZED_TEXT_MST', 'i5QEJpua', 'R8PYPnJ9')
DAILY_NAME = Table('F_TEXT_DAILY_QUEST_NAME', 'FBBD8vv6', 'BhDl8FWG', True)
DAILY_DETAIL = Table('F_TEXT_DAILY_QUEST_DETAIL', 'gCfFcx75', 'xpLyjA9A', True)
CORE_TABLES = (RESOURCE, VERSIONS, QUEST, URL, INDEX, DAILY_NAME, DAILY_DETAIL)
TEXT_TABLES = tuple(Table(name, token, key, True) for name, (token, key) in TEXT_SPECS.items())
# Recovered from the original client's literal-returning ARM64 getters in the
# local v0.1.25 artifact (libgame SHA-256 313b9d3b5c9ea19ac1c4e8b8ec591fe5a49d565b6f849509c7c5d7eed0becdb3).
# Every mapping was corroborated by decrypting the corresponding prepared table.
ECONOMY_TABLES = (
    Table('F_CHALLENGE_MST', 'GL9t6cMF', '8Dx2QUZS'),
    Table('F_PANEL_QUEST_MST', 'jG2GqtV7', '41x7kgDu'),
    Table('F_SP_CHALLENGE_MST', '4b6NcpLo', 'wd1t3MPf'),
    Table('F_RB_SS_MST', 'gd74jWQn', 'gY7NiJL8'),
    Table('F_RB_SS_REWARD_MST', 'cg5k2Mxn', 'KNWf37Bm'),
)
SUPPLEMENTS = (
    Table('F_MEDAL_EXCHANGE_MST', '2qDEnLF9', '7FmTj0hp'),
    Table('F_TEXT_UNITS_NAME', 'sZE3Lhgj', '3IfWAnJ3', True),
    Table('F_TEXT_VISION_CARD_NAME', 'jDYeUTZA', 'PJu2EYP8', True),
    Table('F_TEXT_RECIPE_BOOK_NAME', 'tFnHkR8G', 'lEWsm9iI', True),
)
LABEL_TABLES = CORE_TABLES[:5] + TEXT_TABLES + ECONOMY_TABLES
LABEL_INPUT_TABLES = LABEL_TABLES + SUPPLEMENTS
CLIENT_REGISTRY, REGISTRY_SHA256 = definitions()
TABLES = tuple(Table(name, **entry) for name, entry in CLIENT_REGISTRY['tables'].items())
BY_NAME = {table.name: table for table in TABLES}
INPUT_TABLES = TABLES


def additions():
    return {name: {row['key']: ' '.join(str(row['v'][0]).replace('^', ' ').split()) for row in rows}
            for name, rows in text_rows().items()}


def english_versions(raw, *, tables=TEXT_TABLES):
    wanted = {table.name for table in tables if table.localized}
    result = {}
    for _, row, _ in master_rows(raw, INDEX.key):
        name = row.get('a4hXTIm0')
        if name in wanted:
            value = row.get('00zAYGYS')
            if name in result or not isinstance(value, str) or not value.isascii() or not value.isdigit() or int(value) < 1:
                raise ValueError('Invalid English localized version: ' + name)
            result[name] = int(value)
    if set(result) != wanted:
        raise ValueError('Localized text tables are missing from the index: ' + ', '.join(sorted(wanted-result.keys())))
    return result


def _floor(sources, name, floors):
    return max(sources[name][0], (floors or {}).get(name, 0))


def build_localized(sources, generation, *, labels=None, tables=TABLES, floors=None, prior=None):
    """Build localized text tables and resolve their content-preserving versions."""
    if type(generation) is not int or generation < 1:
        raise ValueError('Native table version generation is out of range.')
    for table in tables:
        version_policy.check_bounds(_floor(sources, table.name, floors), generation, label='Native table')
    outputs, changes, resolved = {}, {}, {}
    labels = additions() if labels is None else labels
    prior = prior or {}
    for table in tables:
        if table.localized:
            raw, count = patch_text(sources[table.name][1], table.key, labels.get(table.name, {}))
            outputs[table.name] = raw
            changes[table.name] = count
            resolved[table.name] = version_policy.resolve_managed(
                _floor(sources, table.name, floors), hashlib.sha256(raw).hexdigest(),
                prior.get(table.name), generation, label='Native table')
    return outputs, changes, resolved


def build_masters(sources, outputs, changes, localized_versions, *, economy=None, tables=TABLES, update=None):
    """Build non-localized master tables using resolved localized versions in F_LOCALIZED_TEXT_MST."""
    unversioned = {str(r.get('9ZCEWn0z')) for _, r, _ in master_rows(sources[VERSIONS.name][1], VERSIONS.key)
                   if str(r.get('OzT5lSz3') or '0') == '0' and str(r.get('86SWOBTb') or '0') == '0'}
    found = set()

    def resource(row):
        if str(row.get('9ZCEWn0z')) in unversioned:
            return None
        if row.get('pJ56sAEo') in EARLY_PACKS:
            found.add(row['pJ56sAEo'])
        if is_upfront_pack(row):
            if not row.get('81fTkEDP') or (is_promoted_menu_pack(row)
                    and str(row.get('81fTkEDP', '')).upper() not in ('TUTO', 'PRE_TUTO')):
                row['81fTkEDP'] = 'TUTO'
        return row

    def quest(row):
        entries = []
        for reward in str(row.get('dX6cor8j') or '').split(','):
            fields = reward.split(':')
            if len(fields) >= 5:
                fields[4] = '1'
            entries.append(':'.join(fields))
        if 'dX6cor8j' in row:
            row['dX6cor8j'] = ','.join(entries)
        return row

    def url(row):
        if row.get('gu8McTA6') == 'GACHA_RATE_URL':
            found.add('GACHA_RATE_URL')
            row = {key: RATE_URL if key not in ('gu8McTA6', 'G4L0YIB2') and value else value
                   for key, value in row.items()}
        return row

    localized_names = {table.name for table in tables if table.localized}

    def index(row):
        name = row.get('a4hXTIm0')
        if name in outputs and name in localized_names:
            raw = outputs[name]
            row.update({'00zAYGYS': str(localized_versions[name]), 'zptmZGqa': hashlib.md5(raw).hexdigest(),
                        'MLOSu5E0': str(len(raw))})
        return row

    for table, transform in ((RESOURCE, resource), (VERSIONS, lambda r: r), (QUEST, quest), (URL, url), (INDEX, index)):
        outputs[table.name], changes[table.name] = patch_master(sources[table.name][1], table.key, transform)
    for table in tables:
        if table.name in {entry.name for entry in ECONOMY_TABLES}:
            if economy is None:
                raise ValueError('Native economy preparation requires explicit settings.')
            data = {'ios_economy': {'version': 1, 'settings': economy}}
            outputs[table.name], changes[table.name] = patch_master(sources[table.name][1], table.key,
                lambda row: revival_economy.transform_master(data, table.name, [row])[0], mode=table.cipher)
        elif not table.localized and table.name not in outputs:
            outputs[table.name] = normalize_master(sources[table.name][1], table.key, mode=table.cipher)
            changes[table.name] = 0
    if not EARLY_PACKS | {'GACHA_RATE_URL'} <= found:
        raise ValueError('Required tutorial resources or Drop Rates URL are missing.')
    if update:
        from ios_server.update_tables import prepare
        prepare(outputs, changes, tables, select_limited=update['settings']['select_limited'])
    return outputs, changes


def resolve_masters(outputs, sources, generation, localized_resolved, *, tables=TABLES, floors=None, prior=None):
    """Resolve versions for non-localized master tables after all projections complete."""
    prior = prior or {}
    resolved = dict(localized_resolved)
    for table in tables:
        if not table.localized:
            resolved[table.name] = version_policy.resolve_managed(
                _floor(sources, table.name, floors),
                hashlib.sha256(outputs[table.name]).hexdigest(),
                prior.get(table.name),
                generation,
                label='Native table',
            )
    versions = {name: item.version for name, item in resolved.items()}
    return versions, resolved


def build(sources, generation, *, labels=None, economy=None, tables=TABLES, floors=None, update=None, prior=None):
    """Sources are {table name: (native source version, raw bytes)}."""
    outputs, changes, localized_resolved = build_localized(
        sources, generation, labels=labels, tables=tables, floors=floors, prior=prior)
    localized_versions = {name: item.version for name, item in localized_resolved.items()}
    build_masters(sources, outputs, changes, localized_versions, economy=economy, tables=tables, update=update)
    versions, _ = resolve_masters(
        outputs, sources, generation, localized_resolved, tables=tables, floors=floors, prior=prior)
    validate(outputs, versions, tables=tables)
    return outputs, versions, changes


def validate(outputs, versions, *, tables=TABLES):
    """Decode every output and check English index versions, MD5s and sizes."""
    for table in tables:
        raw = outputs[table.name]
        if b'\r' in raw or not raw.endswith(b'\n'):
            raise ValueError('Native table must use LF endings: ' + table.name)
        if table.localized:
            text_lines(raw, table.key)
        else:
            validate_master(raw, table.key, mode=table.cipher)
    actual = english_versions(outputs[INDEX.name], tables=tables)
    for _, row, _ in master_rows(outputs[INDEX.name], INDEX.key):
        name = row.get('a4hXTIm0')
        if name in actual:
            raw = outputs[name]
            if (actual[name] != versions[name] or row.get('zptmZGqa') != hashlib.md5(raw).hexdigest()
                    or row.get('MLOSu5E0') != str(len(raw))):
                raise ValueError('Localized index disagrees with prepared bytes: ' + name)
