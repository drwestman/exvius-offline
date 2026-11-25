"""Collect summon artwork without importing the engine or populating its indexes."""
from dataclasses import dataclass
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path

from ios_server import banner_fit

HERE = Path(__file__).resolve().parents[1] / 'server'
DOCUMENTS = tuple('gacha_' + name + '.json' for name in ('catalogue', 'community', 'named', 'authored', 'deals', 'standard'))
DEFAULT = 'generalpu_bn_gacha1_blackfriday.png'
DETAIL_URL = 'banner/en/sd/static_banner/gacha/sub'


def safe_name(name):
    return (isinstance(name, str) and name.lower().endswith('.png') and name not in ('.', '..')
            and not any(char in name for char in '/\\\0,:'))


def names(documents, default):
    """Mirror catalogue identity precedence; collect both locale overrides and step extras."""
    by_id = {}
    for name in DOCUMENTS[:-1]:
        for row in documents[name]['banners']:
            by_id[str(row['id'])] = row
    for row in documents[DOCUMENTS[-1]]['banners']:
        if row.get('serve', True):
            by_id.setdefault(str(row['id']), row)
    result = set()
    for row in by_id.values():
        art = row.get('art') or {}
        for suffix in ('', '_en'):
            # English falls back to the non-localized field, just like _gacha_art.
            detail = art.get('detail_banner' + suffix) or art.get('detail_banner')
            main = art.get('banner' + suffix) or art.get('banner') or default
            result.add(detail or main)
        result.update(art.get('detail_extra') or [])
    if not all(safe_name(name) for name in result):
        raise ValueError('Invalid summon artwork filename')
    return sorted(result), len(by_id)


@dataclass(frozen=True)
class Inputs:
    images: dict
    sources: dict
    fingerprint: str


def collect(config):
    env = config.engine_environment()
    docs, hashes = {}, {}
    for name in DOCUMENTS:
        path = HERE / name
        if not path.resolve().is_relative_to(HERE.resolve()):
            raise ValueError('Summon metadata escapes the server content tree')
        raw = path.read_bytes()
        docs[name] = json.loads(raw)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    wanted, count = names(docs, os.environ.get('GACHA_DEFAULT_BANNER_ART') or DEFAULT)
    native = Path(env['CDN_ROOT']); extracted = Path(env['ART_ROOT'])
    # Exact native URLs win before the canonical extracted/community basename fallback.
    exact = [Path(env[key]) for key in ('CDN_OVERLAY', 'CDN_ROOT')]
    roots = [extracted / relative for relative in ('en/banner', 'en/gacha', 'common_lang/banner', 'common_lang/gacha')]
    roots += [Path(env['COMMUNITY_ART_ROOT']), native/'en/sd/static_banner', native/'common_lang/sd/static_banner']
    index = {}
    for root in dict.fromkeys(roots):
        if not root.resolve().is_relative_to(config.data):
            raise ValueError('Summon artwork root escapes shared data: ' + str(root))
        for path in sorted(root.rglob('*')):
            if path.name in wanted:
                if not path.resolve().is_relative_to(config.data):
                    raise ValueError('Summon artwork escapes shared data: ' + str(path))
                if path.is_file():
                    index.setdefault(path.name, path)
    images, records, missing = {}, {}, []
    for name in wanted:
        selected = None
        for root in exact:
            path = root / DETAIL_URL / name
            if not path.resolve().is_relative_to(config.data):
                raise ValueError('Summon artwork escapes shared data: ' + str(path))
            if path.is_file():
                selected = path; break
        selected = selected or index.get(name)
        if selected is None:
            missing.append(name)
            continue
        raw = selected.read_bytes()
        size = banner_fit.inspect(raw)
        images[name] = raw
        records[name] = {'path': str(selected.relative_to(config.data)), 'sha256': hashlib.sha256(raw).hexdigest(),
                         'width': size[0], 'height': size[1]}
    sources = {'documents': hashes, 'images': records, 'missing': missing, 'requested': wanted,
               'banners': count, 'pipeline': banner_fit.PIPELINE, 'pillow': version('Pillow')}
    fingerprint = hashlib.sha256(json.dumps(sources, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    return Inputs(images, sources, fingerprint)
