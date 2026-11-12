"""Read-only preparation inputs, isolated from engine bindings and state repair."""
import hashlib
import json
from pathlib import Path
import re

from engine_profile import REVIVAL_COMMIT
from exchange_catalogue import build_catalogue
from reward_tuples import parse
import revival_economy
from revival_daily import text_rows
from revival_summons import catalogue, HERE
from ios_server import native_tables as rules
from ios_server.native_text import plan
from ios_server.queries import _saved
from ios_server.native_registry import registered

DOCUMENTS = ('content/revival_bundles.json', 'content/exbonus_text.json', 'battle_names.json', 'colosseum_names.json',
             'content/ios_text_items.json', 'event_archive.json', 'content/permanent_shops.json',
             'content/event_shops.json', 'gacha_deals.json')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def collect(config):
    env = config.engine_environment()
    roots = list(dict.fromkeys(Path(env[key]) for key in ('CDN_OVERLAY', 'CDN_ROOT')))
    sources, records = {}, {}
    version_raw = Path(env['VERSION_TABLE_XML']).read_bytes()
    registrations = registered(version_raw, rules.BY_NAME)
    expected = {'mst': {table.token for table in rules.TABLES if not table.localized},
                'localized_texts/en': {table.token for table in rules.TABLES if table.localized}}
    for root in roots:
        for relative, tokens in expected.items():
            folder = root / relative
            if not folder.resolve().is_relative_to(config.data):
                raise ValueError('Native table folder escapes shared data: ' + str(folder))
            for path in folder.glob('Ver*_*.dat'):
                match = re.fullmatch(r'Ver[0-9]+_([A-Za-z0-9]{8})\.dat', path.name)
                if match is None or match[1] not in tokens:
                    raise ValueError('Unmapped native table source: ' + str(path))

    def read(table, version=None):
        for root in roots:
            folder = root / ('localized_texts/en' if table.localized else 'mst')
            if not folder.resolve().is_relative_to(config.data):
                raise ValueError('Native table folder escapes shared data: ' + str(folder))
            if version is None:
                matches = [(int(m[1]), path) for path in folder.glob('Ver*_' + table.token + '.dat')
                           if (m := re.fullmatch(r'Ver([0-9]+)_' + table.token + r'\.dat', path.name))]
                path = max(matches, default=(0, None), key=lambda p: p[0])[1]
            else:
                path = folder / Path(table.path(version)).name
                if not path.exists():
                    path = None
            if path is not None:
                if not path.resolve().is_relative_to(config.data):
                    raise ValueError('Native table source escapes shared data: ' + str(path))
                base = int(re.match(r'Ver([0-9]+)_', path.name)[1])
                if base < 1:
                    raise ValueError('Native source version must be positive: ' + str(path))
                raw = path.read_bytes()
                sources[table.name] = (base, raw)
                records[table.name] = {'path': str(path.relative_to(config.data)), 'version': base, 'sha256': _sha(raw)}
                return
        raise ValueError('Missing native source table: ' + table.name + (f' Ver{version}' if version else ''))

    for table in rules.INPUT_TABLES:
        if not table.localized:
            read(table)
    localized = rules.english_versions(sources[rules.INDEX.name][1], tables=rules.INPUT_TABLES)
    for table in rules.INPUT_TABLES:
        if table.localized:
            read(table, localized[table.name])
    for _, row, _ in rules.master_rows(sources[rules.INDEX.name][1], rules.INDEX.key):
        name = row.get('a4hXTIm0')
        if name in localized:
            raw = sources[name][1]
            if str(row.get('MLOSu5E0')) != str(len(raw)) or str(row.get('zptmZGqa')).lower() != hashlib.md5(raw).hexdigest():
                raise ValueError('English source checksum disagrees with localized index: ' + name)
    unregistered = []
    for _, row, _ in rules.master_rows(sources[rules.INDEX.name][1], rules.INDEX.key):
        name = row.get('a4hXTIm0')
        if int(row.get('00zAYGYS') or 0) > 0 and name not in rules.BY_NAME:
            if name not in rules.CLIENT_REGISTRY['unregistered_localized']:
                raise ValueError('Unmapped localized index entry: ' + str(name))
            unregistered.append(name)
    documents, document_records = {}, {}
    for name in DOCUMENTS:
        path = HERE / name
        if not path.resolve().is_relative_to(HERE.resolve()):
            raise ValueError('Native metadata escapes the server content tree: ' + name)
        raw = path.read_bytes()
        documents[name] = json.loads(raw)
        document_records[name] = _sha(raw)
    shipped = {}
    for table in rules.INPUT_TABLES:
        if table.localized:
            entries = {}
            for _, lines, _ in rules.text_lines(sources[table.name][1], table.key):
                for line in lines:
                    key, *values = line.split('^')
                    entries[key] = next((value for value in values if value), '')
            shipped[table.name] = entries
    medal = next(table for table in rules.SUPPLEMENTS if not table.localized)
    medal_rows = [row for _, row, _ in rules.master_rows(sources[medal.name][1], medal.key)]
    tickets = sorted({str(ticket) for row in documents['gacha_deals.json']['banners']
                      for ticket in row.get('unit_select_tickets', [])}, key=int)
    _, products, _ = build_catalogue(lambda _: medal_rows,
        {key.rsplit('_', 1)[-1]: value for key, value in shipped['F_TEXT_ITEM_NAME'].items()},
        lambda raw: parse(raw, lambda _: None), permanent_shops=documents['content/permanent_shops.json']['shops'],
        tickets=tickets, event_shops=documents['content/event_shops.json']['shops'])
    labels, coverage = plan(shipped, documents, catalogue(), products, text_rows())
    data = _saved(config) or {}
    saved = revival_economy.settings(data)
    policy = {'source': 'campaign' if saved is not None else 'provisional', 'slot': config.slot,
              'settings': saved if saved is not None else revival_economy.defaults()}
    context = {'economy': policy, 'labels': coverage, 'coverage': {
        'registered': len(registrations), 'masters': sum(not t.localized for t in rules.TABLES),
        'english': len(localized), 'unregistered_localized': sorted(unregistered)}}
    provenance = {'tables': records, 'documents': document_records, 'registry': {
        'versions': registrations, 'sha256': _sha(version_raw), 'definition_sha256': rules.REGISTRY_SHA256}}
    raw = json.dumps({'pipeline': rules.PIPELINE_VERSION, 'reference': REVIVAL_COMMIT,
                     'source_root': str(config.data), 'sources': provenance, 'labels': labels, 'preparation': context},
                    sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    return sources, provenance, _sha(raw), context, labels
