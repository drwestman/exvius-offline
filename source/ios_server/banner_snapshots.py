"""Explicit immutable summon artwork generations, independent of table versions."""
import copy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from ios_server import banner_fit, banner_inputs
from ios_server.preparation import _publish
from ios_server.runtime import InstanceLock, private_path

POINTER = 'assets/banners/current.json'
SCOPE = 'summon-banners'
PREFIX = banner_inputs.DETAIL_URL + '/'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def owned_name(relative):
    match = re.fullmatch(r'(?:banner/)?(?:en|common_lang)/sd/static_banner/gacha/sub/(ios-fit-[a-f0-9]{64}\.png)', relative)
    return match[1] if match else None


@dataclass(frozen=True)
class Banners:
    directory: Path
    manifest: dict
    files: dict

    def lookup(self, relative):
        name = owned_name(relative)
        return self.files.get(PREFIX + name) if name else None

    def describe(self):
        source = self.manifest['sources']
        return {'ok': True, 'scope': SCOPE, 'generation': self.manifest['generation'],
                'images': len(self.manifest['images']), 'files': len(self.files),
                'sources': len(source['images']), 'missing': list(source['missing']),
                'directory': str(self.directory), 'gameplay_ready': False}

    def project(self, spec):
        """Fit detail/carousel names using actual wire layout; preserve bare list names."""
        if not isinstance(spec, dict):
            return spec
        out = copy.deepcopy(spec)
        layouts = {str(row.get('X1IuZnj2')): 'paid' if str(row.get('7xBNR2MH', '0')) in ('1', '2') else 'base'
                   for row in out.get('PcUrGH13', []) if isinstance(row, dict)}
        for tag in ('IC0ueV5s', '4D5k8dpI'):
            for row in out.get(tag, []):
                if not isinstance(row, dict) or not isinstance(row.get('4yT7FUqj'), str):
                    continue
                mode = layouts.get(str(row.get('X1IuZnj2')))
                if mode is None:
                    continue
                parts = row['4yT7FUqj'].split(',')
                for index, part in enumerate(parts):
                    fields = part.split(':')
                    if len(fields) == 2 and fields[0].isdigit():
                        image = self.manifest['images'].get(mode + ':' + fields[1])
                        if image is not None:
                            parts[index] = fields[0] + ':' + Path(image['path']).name
                row['4yT7FUqj'] = ','.join(parts)
        return out


def collect(config):
    try:
        return banner_inputs.collect(config)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f'Invalid summon artwork metadata: {exc}') from exc


def load(config):
    """Load recorded facts only; a missing snapshot is distinct from a corrupt one."""
    pointer = private_path(config.root, POINTER)
    if not pointer.exists():
        if pointer.is_symlink():
            raise ValueError('Invalid summon artwork pointer')
        return None
    try:
        ref = json.loads(pointer.read_bytes())
        if (set(ref) != {'version', 'directory', 'manifest_sha256'} or type(ref['version']) is not int or ref['version'] != 1
                or not re.fullmatch(r'[0-9]{8}-[a-f0-9]{64}', ref['directory'])):
            raise ValueError('invalid pointer')
        directory = private_path(config.root, Path(POINTER).parent / ref['directory'])
        raw = private_path(config.root, directory.relative_to(config.root) / 'manifest.json').read_bytes()
        if digest(raw) != ref['manifest_sha256']:
            raise ValueError('manifest checksum mismatch')
        doc = json.loads(raw)
        if (set(doc) != {'version', 'scope', 'source_root', 'generation', 'fingerprint', 'sources', 'images'}
                or type(doc['version']) is not int or doc['version'] != 1 or doc['scope'] != SCOPE
                or type(doc['generation']) is not int or not 1 <= doc['generation'] <= 99999999
                or not isinstance(doc['source_root'], str) or not Path(doc['source_root']).is_absolute()
                or not re.fullmatch(r'[a-f0-9]{64}', doc['fingerprint'])
                or ref['directory'] != f"{doc['generation']:08d}-{doc['fingerprint']}"):
            raise ValueError('invalid manifest')
        source = doc['sources']
        if (set(source) != {'documents', 'images', 'missing', 'requested', 'banners', 'pipeline', 'pillow'}
                or set(source['documents']) != set(banner_inputs.DOCUMENTS)
                or any(not re.fullmatch(r'[a-f0-9]{64}', value) for value in source['documents'].values())
                or type(source['pipeline']) is not int or source['pipeline'] < 1 or not isinstance(source['pillow'], str)
                or type(source['banners']) is not int or source['banners'] < 1
                or source['requested'] != sorted(set(source['requested']))
                or source['missing'] != sorted(set(source['requested']) - set(source['images']))
                or not set(source['images']) <= set(source['requested'])
                or not all(banner_inputs.safe_name(name) for name in source['requested'])
                or set(doc['images']) != {mode + ':' + name for name in source['images'] for mode in banner_fit.FRAMES}):
            raise ValueError('invalid source inventory')
        files = {}
        for key, entry in doc['images'].items():
            name, mode = entry['source'], entry['mode']
            original = source['images'][name]
            if (set(original) != {'path', 'sha256', 'width', 'height'}
                    or not re.fullmatch(r'[a-f0-9]{64}', original['sha256'])
                    or type(original['width']) is not int or original['width'] < 1
                    or type(original['height']) is not int or original['height'] < 1
                    or set(entry) != {'source', 'mode', 'path', 'sha256', 'size', 'width', 'height'}
                    or key != mode + ':' + name or mode not in banner_fit.FRAMES
                    or not re.fullmatch(r'[a-f0-9]{64}', entry['sha256'])
                    or entry['path'] != PREFIX + 'ios-fit-' + entry['sha256'] + '.png'
                    or type(entry['size']) is not int or entry['size'] < 1
                    or type(entry['width']) is not int or type(entry['height']) is not int):
                raise ValueError('invalid image identity')
            path = private_path(config.root, directory.relative_to(config.root) / entry['path'])
            if not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError('image escapes generation')
            image = path.read_bytes()
            size = banner_fit.inspect(image)
            expected = banner_fit.dimensions((original['width'], original['height']), mode)
            if (digest(image) != entry['sha256'] or len(image) != entry['size'] or size != expected
                    or size != (entry['width'], entry['height'])
                    or size == (original['width'], original['height']) and entry['sha256'] != original['sha256']):
                raise ValueError('image checksum or dimensions disagree')
            files[entry['path']] = image
        return Banners(directory, doc, files)
    except (OSError, KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ValueError(f'Invalid summon artwork snapshot: {exc}') from exc


def current(config):
    snapshot = load(config)
    if snapshot is not None:
        inputs = collect(config)
        if (snapshot.manifest['fingerprint'] != inputs.fingerprint or snapshot.manifest['sources'] != inputs.sources
                or snapshot.manifest['source_root'] != str(config.data)):
            raise ValueError('Summon artwork is stale. Run prepare-banners.')
    return snapshot


def verify(config):
    try:
        snapshot = current(config)
        if snapshot is None:
            return {'ok': False, 'scope': SCOPE, 'prepared': False, 'gameplay_ready': False,
                    'error': 'No summon artwork snapshot. Run prepare-banners.'}
        return {**snapshot.describe(), 'prepared': True}
    except (OSError, ValueError) as exc:
        return {'ok': False, 'scope': SCOPE, 'error': str(exc), 'gameplay_ready': False}


def prepare(config):
    with InstanceLock(config.root):
        old = load(config)
        inputs = collect(config)
        if old is not None and old.manifest['fingerprint'] == inputs.fingerprint:
            if old.manifest['sources'] != inputs.sources or old.manifest['source_root'] != str(config.data):
                raise ValueError('Invalid summon snapshot provenance')
            return {**old.describe(), 'prepared_now': False}
        generation = old.manifest['generation'] + 1 if old else 1
        if generation > 99999999:
            raise ValueError('Summon artwork generation is out of range')
        entries, outputs = {}, {}
        for name, raw in inputs.images.items():
            for mode in banner_fit.FRAMES:
                image = banner_fit.render(raw, mode)
                sha = digest(image); width, height = banner_fit.inspect(image)
                original = inputs.sources['images'][name]
                size = (original['width'], original['height'])
                if ((width, height) != banner_fit.dimensions(size, mode)
                        or (width, height) == size and sha != original['sha256']):
                    raise ValueError('Fitted summon image disagrees with its source dimensions')
                key = mode + ':' + name
                entries[key] = {'source': name, 'mode': mode, 'path': PREFIX + 'ios-fit-' + sha + '.png',
                                'sha256': sha, 'size': len(image), 'width': width, 'height': height}
                outputs[key] = image
        doc = {'version': 1, 'scope': SCOPE, 'source_root': str(config.data), 'generation': generation,
               'fingerprint': inputs.fingerprint, 'sources': inputs.sources, 'images': entries}
        directory = _publish(config, doc, outputs, pointer_name=POINTER, entries=entries)
        snapshot = Banners(directory, doc, {entries[key]['path']: raw for key, raw in outputs.items()})
        return {**snapshot.describe(), 'prepared_now': True}
