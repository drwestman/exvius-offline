"""Explicit immutable home-carousel PNG snapshots and narrow artwork bindings."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from ios_server.banner_fit import inspect
from ios_server.preparation import _publish
from ios_server.runtime import InstanceLock, private_path
from revival_marquee import ID_BASE

HERE = Path(__file__).resolve().parents[1] / 'server'
DOCUMENTS = ('event_art.json', 'event_history.json')
POINTER = 'assets/home-banners/current.json'
SCOPE = 'replay-home-banners'
PIPELINE = 1
PREFIX = 'banner/en/sd/static_banner/marquee/'
SHA = r'[a-f0-9]{64}'


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')) + '\n').encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_name(name):
    return isinstance(name, str) and bool(re.fullmatch(r'[A-Za-z0-9_.-]+\.png', name))


def owns(relative):
    return bool(re.match(r'(?:banner/)?(?:en|common_lang)/sd/static_banner/marquee/ios-home-', relative))


def image_url(area, sha):
    return f'{PREFIX}ios-home-{sha}/HomeBanner_{ID_BASE + int(area)}.png'


def _areas(documents):
    areas = {str(area): row['filename'] for area, row in documents['event_art.json']['events'].items()
             if row.get('filename')}
    for row in documents['event_history.json']['added']:
        if row.get('filename'):
            areas.setdefault(str(row['area']), row['filename'])
    if (not areas or any(not area.isascii() or not area.isdigit() or not 1 <= int(area) <= 2147483647 - ID_BASE
                         or str(int(area)) != area or not safe_name(name) for area, name in areas.items())):
        raise ValueError('Invalid replay home artwork identity')
    return areas


@dataclass(frozen=True)
class Inputs:
    sources: dict
    images: dict
    fingerprint: str


def collect(config):
    try:
        return _collect(config)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f'Invalid home artwork metadata: {exc}') from exc


def _collect(config):
    documents, hashes = {}, {}
    for name in DOCUMENTS:
        path = HERE / name
        if not path.resolve().is_relative_to(HERE.resolve()):
            raise ValueError('Home artwork metadata escapes its source tree')
        raw = path.read_bytes(); documents[name] = json.loads(raw); hashes[name] = digest(raw)
    areas = _areas(documents)
    env = config.engine_environment()
    roots = list(dict.fromkeys(Path(env[key]) for key in ('CDN_OVERLAY', 'CDN_ROOT')))
    records, images, missing = {}, {}, []
    for name in sorted(set(areas.values())):
        selected = None
        for root in roots:
            path = root / 'en/sd/area' / name
            if not path.resolve().is_relative_to(config.data):
                raise ValueError('Home artwork escapes shared data: ' + str(path))
            if path.is_file():
                selected = path; break
            if path.is_symlink():
                raise ValueError('Invalid home artwork link: ' + str(path))
        if selected is None:
            missing.append(name); continue
        raw = selected.read_bytes(); width, height = inspect(raw)
        images[name] = raw
        records[name] = {'path': str(selected.relative_to(config.data)), 'sha256': digest(raw),
                         'width': width, 'height': height}
    sources = {'pipeline': PIPELINE, 'documents': hashes, 'areas': areas, 'images': records, 'missing': missing}
    return Inputs(sources, images, digest(encoded(sources)))


@dataclass(frozen=True)
class Banners:
    directory: Path
    manifest: dict
    files: dict

    def image(self, area):
        name = self.manifest['sources']['areas'].get(area)
        entry = self.manifest['images'].get(name)
        return {**entry, 'source': name, 'url': image_url(area, entry['sha256'])} if entry is not None else None

    def lookup(self, relative):
        match = re.fullmatch(r'(?:banner/)?(?:en|common_lang)/sd/static_banner/marquee/ios-home-(' + SHA + r')/HomeBanner_([1-9][0-9]{0,9})\.png', relative)
        if match is None:
            return None
        image = self.image(str(int(match[2]) - ID_BASE))
        return self.files.get(image['path']) if image is not None and image['sha256'] == match[1] else None

    def describe(self):
        return {'ok': True, 'scope': SCOPE, 'generation': self.manifest['generation'],
                'directory': str(self.directory), 'areas': len(self.manifest['sources']['areas']),
                'images': len(self.manifest['images']), 'files': len(self.files),
                'missing': list(self.manifest['sources']['missing']), 'gameplay_ready': False}


def _validate_sources(source):
    if (set(source) != {'pipeline', 'documents', 'areas', 'images', 'missing'}
            or type(source['pipeline']) is not int or source['pipeline'] < 1
            or set(source['documents']) != set(DOCUMENTS)
            or any(not re.fullmatch(SHA, value) for value in source['documents'].values())
            or not source['areas']
            or any(not isinstance(area, str) or not area.isascii() or not area.isdigit()
                   or not 1 <= int(area) <= 2147483647 - ID_BASE or str(int(area)) != area or not safe_name(name)
                   for area, name in source['areas'].items())
            or not set(source['images']) <= set(source['areas'].values())
            or source['missing'] != sorted(set(source['areas'].values()) - set(source['images']))):
        raise ValueError('Invalid home artwork inventory')


def load(config):
    pointer = private_path(config.root, POINTER)
    if not pointer.exists():
        if pointer.is_symlink():
            raise ValueError('Invalid home artwork pointer')
        return None
    try:
        ref = json.loads(pointer.read_bytes())
        if (set(ref) != {'version', 'directory', 'manifest_sha256'} or type(ref['version']) is not int or ref['version'] != 1
                or not re.fullmatch(r'[0-9]{8}-' + SHA, ref['directory'])):
            raise ValueError('Invalid home artwork pointer')
        directory = private_path(config.root, Path(POINTER).parent / ref['directory'])
        raw = private_path(config.root, directory.relative_to(config.root) / 'manifest.json').read_bytes()
        if digest(raw) != ref['manifest_sha256']:
            raise ValueError('Home artwork manifest checksum mismatch')
        doc = json.loads(raw)
        if (set(doc) != {'version', 'scope', 'source_root', 'generation', 'fingerprint', 'sources', 'images'}
                or type(doc['version']) is not int or doc['version'] != 1 or doc['scope'] != SCOPE
                or type(doc['generation']) is not int or not 1 <= doc['generation'] <= 99999999
                or not isinstance(doc['source_root'], str) or not Path(doc['source_root']).is_absolute()
                or doc['fingerprint'] != digest(encoded(doc['sources']))
                or ref['directory'] != f"{doc['generation']:08d}-{doc['fingerprint']}"
                or set(doc['images']) != set(doc['sources']['images'])):
            raise ValueError('Invalid home artwork manifest')
        _validate_sources(doc['sources'])
        files = {}
        for name, entry in doc['images'].items():
            source = doc['sources']['images'][name]
            relative = Path(source['path'])
            if (set(source) != {'path', 'sha256', 'width', 'height'} or relative.is_absolute() or '..' in relative.parts
                    or '\\' in source['path'] or not re.fullmatch(SHA, source['sha256'])
                    or type(source['width']) is not int or type(source['height']) is not int
                    or min(source['width'], source['height']) < 1
                    or set(entry) != {'path', 'sha256', 'size', 'width', 'height'}
                    or entry['path'] != 'images/' + source['sha256'] + '.png' or entry['sha256'] != source['sha256']
                    or type(entry['size']) is not int or entry['size'] < 1
                    or type(entry['width']) is not int or type(entry['height']) is not int
                    or (entry['width'], entry['height']) != (source['width'], source['height'])):
                raise ValueError('Invalid home artwork identity')
            path = private_path(config.root, directory.relative_to(config.root) / entry['path'])
            if not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError('Home artwork escapes generation')
            image = path.read_bytes()
            if len(image) != entry['size'] or digest(image) != entry['sha256'] or inspect(image) != (entry['width'], entry['height']):
                raise ValueError('Home artwork checksum or dimensions mismatch')
            files[entry['path']] = image
        return Banners(directory, doc, files)
    except (OSError, KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ValueError(f'Invalid home artwork snapshot: {exc}') from exc


def current(config):
    snapshot = load(config)
    if snapshot is not None:
        inputs = collect(config)
        if (snapshot.manifest['source_root'] != str(config.data) or snapshot.manifest['sources'] != inputs.sources
                or snapshot.manifest['fingerprint'] != inputs.fingerprint):
            raise ValueError('Home artwork is stale. Run prepare-home-banners.')
    return snapshot


def verify(config):
    try:
        snapshot = current(config)
        if snapshot is None:
            return {'ok': False, 'scope': SCOPE, 'prepared': False, 'gameplay_ready': False,
                    'error': 'No home artwork snapshot. Run prepare-home-banners.'}
        return {**snapshot.describe(), 'prepared': True}
    except (OSError, ValueError) as exc:
        return {'ok': False, 'scope': SCOPE, 'error': str(exc), 'gameplay_ready': False}


def prepare(config):
    with InstanceLock(config.root):
        old = load(config); inputs = collect(config)
        if old is not None and old.manifest['fingerprint'] == inputs.fingerprint:
            if old.manifest['sources'] != inputs.sources or old.manifest['source_root'] != str(config.data):
                raise ValueError('Invalid home artwork provenance')
            return {**old.describe(), 'prepared_now': False}
        generation = old.manifest['generation'] + 1 if old is not None else 1
        if generation > 99999999:
            raise ValueError('Home artwork generation is out of range')
        entries = {name: {'path': 'images/' + digest(raw) + '.png', 'sha256': digest(raw), 'size': len(raw),
                          'width': inputs.sources['images'][name]['width'], 'height': inputs.sources['images'][name]['height']}
                   for name, raw in inputs.images.items()}
        doc = {'version': 1, 'scope': SCOPE, 'source_root': str(config.data), 'generation': generation,
               'fingerprint': inputs.fingerprint, 'sources': inputs.sources, 'images': entries}
        directory = _publish(config, doc, inputs.images, pointer_name=POINTER, entries=entries)
        return {**Banners(directory, doc, {entries[name]['path']: raw for name, raw in inputs.images.items()}).describe(),
                'prepared_now': True}


@dataclass(frozen=True)
class Artwork:
    summons: object
    home: Banners

    def project(self, spec):
        return self.summons.project(spec) if self.summons is not None else spec

    def lookup(self, relative):
        if owns(relative):
            return self.home.lookup(relative)
        return self.summons.lookup(relative) if self.summons is not None else None


def bind(summons, home):
    return Artwork(summons, home) if home is not None else summons
