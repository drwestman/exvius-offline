"""Corroborated Global-1167 native table definitions; no engine/state dependencies."""
import hashlib
import json
from pathlib import Path
import re
from xml.etree import ElementTree

PATH = Path(__file__).with_name('client_tables.json')
NATIVE_SHA256 = '313b9d3b5c9ea19ac1c4e8b8ec591fe5a49d565b6f849509c7c5d7eed0becdb3'


def definitions():
    try:
        raw = PATH.read_bytes()
        doc = json.loads(raw)
        tables = doc['tables']
        if (type(doc['version']) is not int or doc['version'] != 1 or doc['client']['build'] != 1167
                or doc['client']['native_sha256'] != NATIVE_SHA256 or len(tables) != 364):
            raise ValueError('unsupported native registry')
        tokens = set()
        for name, entry in tables.items():
            if (not re.fullmatch(r'F_[A-Z0-9_]+', name) or set(entry) != {'token', 'key', 'localized', 'cipher'}
                    or not all(re.fullmatch(r'[A-Za-z0-9]{8}', entry[key]) for key in ('token', 'key'))
                    or type(entry['localized']) is not bool or entry['cipher'] not in ('cbc', 'ecb')
                    or entry['localized'] and entry['cipher'] != 'ecb' or entry['token'] in tokens):
                raise ValueError('invalid native table definition: ' + name)
            tokens.add(entry['token'])
        return doc, hashlib.sha256(raw).hexdigest()
    except (OSError, KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ValueError(f'Invalid native client registry: {exc}') from exc


def registered(raw, known):
    """Positive persisted registrations must match the complete supported corpus."""
    try:
        tree = ElementTree.fromstring(raw)
        if tree.tag != 'map':
            raise ValueError('expected the native preference map')
        versions, seen = {}, set()
        for row in tree.findall('string'):
            key = row.get('name', '')
            if not key.startswith('keyF_'):
                continue
            name, value = key[3:], row.text or ''
            if not re.fullmatch(r'-?[0-9]+', value) or name in seen:
                raise ValueError('invalid or duplicate registration: ' + name)
            seen.add(name)
            if int(value) > 0:
                versions[name] = int(value)
        missing, unknown = set(known)-versions.keys(), versions.keys()-set(known)
        if missing or unknown:
            raise ValueError(f'incomplete registrations; missing={sorted(missing)}, unknown={sorted(unknown)}')
        return versions
    except (ElementTree.ParseError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid native version registry: {exc}') from exc
