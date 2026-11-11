"""Pinned local release-manifest policy and exact managed ZIP destinations."""
from dataclasses import dataclass
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit

DEFAULT = Path(__file__).resolve().parents[2] / 'data/latest.json'
POLICY = 1
SHA = r'[a-f0-9]{64}'


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')) + '\n').encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def file_digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def web_url(value):
    if not isinstance(value, str) or any(c in value for c in '\r\n\0'):
        return False
    parsed = urlsplit(value)
    if not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.fragment:
        return False
    if parsed.scheme == 'https':
        return True
    try:
        loopback = parsed.hostname == 'localhost' or ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        loopback = False
    return parsed.scheme == 'http' and loopback


@dataclass(frozen=True)
class Pack:
    id: str
    url: str
    size: int
    unpacked_size: int
    sha256: str


@dataclass(frozen=True)
class Manifest:
    raw: bytes
    document: dict
    packs: tuple

    @property
    def sha256(self):
        return digest(self.raw)

    @property
    def generation(self):
        return digest(encoded({'policy': POLICY, 'manifest': self.sha256}))


def parse(raw):
    try:
        doc = json.loads(raw)
        if (type(doc['schema']) is not int or doc['schema'] != 1 or type(doc['revision']) is not int
                or doc['revision'] < 1 or not isinstance(doc['version'], str) or not doc['version']
                or not isinstance(doc['packs'], list)):
            raise ValueError('unsupported release manifest')
        packs, ids = [], set()
        for row in doc['packs']:
            identity = row['id']
            if (not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', identity)
                    or identity in ids or not web_url(row['url'])
                    or type(row['size']) is not int or row['size'] < 1
                    or type(row['unpackedSize']) is not int or row['unpackedSize'] < 0
                    or not re.fullmatch(SHA, row['sha256'])):
                raise ValueError('invalid or duplicate data pack')
            ids.add(identity)
            if identity != 'client-assets':
                packs.append(Pack(identity, row['url'], row['size'], row['unpackedSize'], row['sha256']))
        if not packs:
            raise ValueError('no iOS data packs')
        return Manifest(raw, doc, tuple(packs))
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ValueError(f'Invalid managed data manifest: {exc}') from exc


def read(path=DEFAULT):
    return parse(Path(path).read_bytes())


def destination(name):
    """Map release pack paths; exclude app resources, saves and private runtime data."""
    if (not isinstance(name, str) or not name or any(c in name for c in '\\\0:')
            or any(part in ('', '.', '..') for part in name.split('/'))):
        raise ValueError('Unsafe data pack path: ' + str(name))
    if name == 'metadata/registry.json':
        return 'registry.json'
    if re.fullmatch(r'native/(?:mst|localized_texts|common_lang|en|homeMarquee)/.+', name):
        return name
    if re.fullmatch(r'static/(?:mst_decoded|text_decoded|cpk_extract)/.+', name):
        return name
    if name.startswith('static/gacha_community/art/') or name == 'static/client/shared_prefs/gamedata.xml':
        return name
    raise ValueError('Unsupported iOS data pack entry: ' + name)


def collision_key(path):
    return unicodedata.normalize('NFC', path).casefold()
