"""Explicit native-table preparation and read-only verification.

Publish immutable generations through one atomic pointer under the private root.
Neither command imports the engine, reads a campaign, downloads, or starts a service.
"""
import copy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from engine_profile import REVIVAL_COMMIT
from ios_server import native_tables as rules
from ios_server.runtime import InstanceLock, private_path

SCOPE = 'core-native-tables'
POINTER = 'assets/tables/current.json'


def _json(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')) + '\n').encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _content(config, path):
    if not path.resolve().is_relative_to(config.data):
        raise ValueError('Native table source escapes shared data: ' + str(path))
    return path.read_bytes()


def _inputs(config):
    env = config.engine_environment()
    roots = list(dict.fromkeys(Path(env[key]) for key in ('CDN_OVERLAY', 'CDN_ROOT')))
    sources, records = {}, {}

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
                base = int(re.match(r'Ver([0-9]+)_', path.name)[1])
                if base < 1:
                    raise ValueError('Native source version must be positive: ' + str(path))
                raw = _content(config, path)
                sources[table.name] = (base, raw)
                records[table.name] = {'path': str(path.relative_to(config.data)), 'version': base, 'sha256': _sha(raw)}
                return
        raise ValueError('Missing native source table: ' + table.name + (f' Ver{version}' if version else ''))

    for table in rules.TABLES:
        if not table.localized:
            read(table)
    localized = rules.english_versions(sources[rules.INDEX.name][1])
    for table in rules.TABLES:
        if table.localized:
            read(table, localized[table.name])
    for _, row, _ in rules.master_rows(sources[rules.INDEX.name][1], rules.INDEX.key):
        name = row.get('a4hXTIm0')
        if name in localized:
            raw = sources[name][1]
            if str(row.get('MLOSu5E0')) != str(len(raw)) or str(row.get('zptmZGqa')).lower() != hashlib.md5(raw).hexdigest():
                raise ValueError('English source checksum disagrees with localized index: ' + name)
    fingerprint = _sha(_json({'pipeline': rules.PIPELINE_VERSION, 'reference': REVIVAL_COMMIT,
                             'source_root': str(config.data), 'sources': records, 'daily_text': rules.additions()}))
    return sources, records, fingerprint


@dataclass(frozen=True)
class PreparedTables:
    directory: Path
    manifest: dict
    files: dict

    def lookup(self, relative):
        """Only exact published version paths resolve; no path rewriting or writes."""
        return self.files.get(relative)

    def project_versions(self, spec):
        """Use after canonical version projection when native gameplay hosting is added."""
        if not isinstance(spec, dict) or not isinstance(spec.get('c1qYg84Q'), list):
            return spec
        out = copy.deepcopy(spec)
        versions = {name: str(row['version']) for name, row in self.manifest['tables'].items()}
        seen = set()
        for row in out['c1qYg84Q']:
            if isinstance(row, dict) and row.get('a4hXTIm0') in versions:
                row['wM9AfX6I'] = versions[row['a4hXTIm0']]
                seen.add(row['a4hXTIm0'])
        out['c1qYg84Q'].extend({'a4hXTIm0': name, 'wM9AfX6I': versions[name]} for name in sorted(versions.keys() - seen))
        return out

    def describe(self):
        return {'ok': True, 'scope': SCOPE, 'generation': self.manifest['generation'],
                'directory': str(self.directory), 'tables': len(self.manifest['tables']),
                'changed_rows': {name: row['changed_rows'] for name, row in self.manifest['tables'].items()},
                'gameplay_ready': False}


def load_prepared(config):
    """Verify every published byte before returning a snapshot; missing is distinct from corrupt."""
    pointer = private_path(config.root, POINTER)
    if not pointer.exists():
        if pointer.is_symlink():
            raise ValueError('Invalid native table snapshot pointer.')
        return None
    try:
        ref = json.loads(pointer.read_bytes())
        if (set(ref) != {'version', 'directory', 'manifest_sha256'} or type(ref['version']) is not int
                or ref['version'] != 1 or not re.fullmatch(r'[0-9]{8}-[a-f0-9]{64}', ref['directory'])):
            raise ValueError('invalid pointer')
        directory = private_path(config.root, 'assets/tables/' + ref['directory'])
        manifest_raw = private_path(config.root, directory.relative_to(config.root) / 'manifest.json').read_bytes()
        if _sha(manifest_raw) != ref['manifest_sha256']:
            raise ValueError('manifest checksum mismatch')
        manifest = json.loads(manifest_raw)
        if (set(manifest) != {'version', 'scope', 'reference_commit', 'source_root', 'pipeline_version',
                             'generation', 'fingerprint', 'sources', 'tables'}
                or type(manifest['version']) is not int or manifest['version'] != 1
                or manifest['scope'] != SCOPE or manifest['reference_commit'] != REVIVAL_COMMIT
                or type(manifest['generation']) is not int or not 1 <= manifest['generation'] <= 99999999
                or type(manifest['pipeline_version']) is not int or manifest['pipeline_version'] < 1
                or not isinstance(manifest['source_root'], str) or not Path(manifest['source_root']).is_absolute()
                or not re.fullmatch(r'[a-f0-9]{64}', manifest['fingerprint'])
                or ref['directory'] != f"{manifest['generation']:08d}-{manifest['fingerprint']}"
                or set(manifest['sources']) != rules.BY_NAME.keys()
                or set(manifest['tables']) != rules.BY_NAME.keys()):
            raise ValueError('unsupported manifest')
        outputs, versions, files = {}, {}, {}
        for name, entry in manifest['tables'].items():
            table = rules.BY_NAME[name]
            version, base = entry['version'], entry['source_version']
            if (set(entry) != {'path', 'version', 'source_version', 'size', 'sha256', 'md5', 'changed_rows'}
                    or type(version) is not int or type(base) is not int or base < 1 or version > 2147483647
                    or version != base + rules.VERSION_OFFSET + manifest['generation'] * rules.VERSION_STEP
                    or entry['path'] != table.path(version) or type(entry['size']) is not int or entry['size'] < 1
                    or type(entry['changed_rows']) is not int or entry['changed_rows'] < 0):
                raise ValueError('invalid table identity: ' + name)
            path = private_path(config.root, directory.relative_to(config.root) / entry['path'])
            if not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError('table escapes its generation: ' + name)
            raw = path.read_bytes()
            if len(raw) != entry['size'] or _sha(raw) != entry['sha256'] or hashlib.md5(raw).hexdigest() != entry['md5']:
                raise ValueError('table checksum mismatch: ' + name)
            outputs[name], versions[name], files[entry['path']] = raw, version, raw
        rules.validate(outputs, versions)
        return PreparedTables(directory, manifest, files)
    except (OSError, KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ValueError(f'Invalid native table snapshot: {exc}') from exc


def verify_data(config):
    """Read-only verification of the snapshot and its current preparation inputs."""
    try:
        snapshot = load_prepared(config)
        if snapshot is None:
            return {'ok': False, 'scope': SCOPE, 'prepared': False, 'gameplay_ready': False,
                    'error': 'No native table snapshot. Run prepare-data with the selected --data root.'}
        _, records, fingerprint = _inputs(config)
        if (snapshot.manifest['fingerprint'] != fingerprint or snapshot.manifest['sources'] != records
                or snapshot.manifest['source_root'] != str(config.data)
                or snapshot.manifest['pipeline_version'] != rules.PIPELINE_VERSION):
            raise ValueError('Native table inputs changed. Run prepare-data to publish a new generation.')
        return {**snapshot.describe(), 'prepared': True}
    except (OSError, ValueError) as exc:
        return {'ok': False, 'scope': SCOPE, 'error': str(exc), 'gameplay_ready': False}


def _publish(config, manifest, outputs):
    pointer = private_path(config.root, POINTER)
    parent = pointer.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    identity = f"{manifest['generation']:08d}-{manifest['fingerprint']}"
    destination = private_path(config.root, 'assets/tables/' + identity)
    stage = Path(tempfile.mkdtemp(prefix='.building-', dir=parent))
    temp_pointer = None
    try:
        for name, raw in outputs.items():
            path = stage / manifest['tables'][name]['path']
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        manifest_raw = _json(manifest)
        with (stage / 'manifest.json').open('wb') as stream:
            stream.write(manifest_raw)
            stream.flush()
            os.fsync(stream.fileno())
        if destination.exists():
            # An interrupted pointer replacement may leave this same immutable generation.
            expected = {entry['path']: outputs[name] for name, entry in manifest['tables'].items()}
            expected['manifest.json'] = manifest_raw
            for relative, raw in expected.items():
                path = private_path(config.root, destination.relative_to(config.root) / relative)
                if path.read_bytes() != raw:
                    raise ValueError('Conflicting unpublished native table generation.')
            shutil.rmtree(stage)
        else:
            os.replace(stage, destination)
        with tempfile.NamedTemporaryFile(prefix='.current-', dir=parent, delete=False) as stream:
            temp_pointer = Path(stream.name)
            stream.write(_json({'version': 1, 'directory': identity, 'manifest_sha256': _sha(manifest_raw)}))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_pointer, pointer)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
        if temp_pointer is not None and temp_pointer.exists():
            temp_pointer.unlink()
    return destination


def prepare_data(config):
    """Build and validate first, then publish under the exclusive private-runtime lock."""
    with InstanceLock(config.root):
        current = load_prepared(config)
        sources, records, fingerprint = _inputs(config)
        if current is not None and current.manifest['fingerprint'] == fingerprint:
            if (current.manifest['sources'] != records or current.manifest['source_root'] != str(config.data)
                    or current.manifest['pipeline_version'] != rules.PIPELINE_VERSION):
                raise ValueError('Invalid native table snapshot provenance.')
            return {**current.describe(), 'prepared': True, 'prepared_now': False}
        generation = current.manifest['generation'] + 1 if current else 1
        outputs, versions, changes = rules.build(sources, generation)
        manifest = {'version': 1, 'scope': SCOPE, 'reference_commit': REVIVAL_COMMIT,
                    'source_root': str(config.data), 'pipeline_version': rules.PIPELINE_VERSION,
                    'generation': generation, 'fingerprint': fingerprint, 'sources': records, 'tables': {}}
        for table in rules.TABLES:
            raw = outputs[table.name]
            manifest['tables'][table.name] = {'path': table.path(versions[table.name]),
                'version': versions[table.name], 'source_version': sources[table.name][0], 'size': len(raw),
                'sha256': _sha(raw), 'md5': hashlib.md5(raw).hexdigest(), 'changed_rows': changes[table.name]}
        destination = _publish(config, manifest, outputs)
        snapshot = PreparedTables(destination, manifest, {manifest['tables'][name]['path']: raw for name, raw in outputs.items()})
        return {**snapshot.describe(), 'prepared': True, 'prepared_now': True}
