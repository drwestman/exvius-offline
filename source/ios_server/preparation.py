"""Explicit native-table preparation and read-only verification.

Publish immutable generations through one atomic pointer under the private root.
Commands inspect economy settings without importing the engine, repairing saves,
downloading, or starting a service.
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

SCOPE = 'native-tables'
POINTER = 'assets/tables/current.json'


def _json(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')) + '\n').encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _inputs(config):
    from ios_server.native_inputs import collect
    try:
        return collect(config)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f'Invalid native preparation metadata: {exc}') from exc


def _complete_inputs(config, vortex_art=False, sounds=False):
    sources, records, fingerprint, context, labels = _inputs(config)
    art = None
    if vortex_art:
        from ios_server.vortex_art import collect
        try:
            art = collect(config, sources)
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError(f'Invalid Vortex preparation metadata: {exc}') from exc
        records = {**records, 'art': art.provenance}
        context = {**context, 'art': art.coverage}
        fingerprint = _sha(_json({'tables': fingerprint, 'art': art.provenance}))
    sound = None
    if sounds:
        from ios_server.native_sounds import collect
        sound = collect(config, sources)
        records = {**records, 'sound': sound.provenance}
        context = {**context, 'sound': sound.coverage}
        fingerprint = _sha(_json({'tables': fingerprint, 'sound': sound.provenance}))
    from ios_server import upfront_resources
    upfront = upfront_resources.collect(config, sources)
    records = {**records, 'upfront': upfront}
    context = {**context, 'upfront': upfront_resources.coverage(upfront)}
    fingerprint = _sha(_json({'tables': fingerprint, 'upfront': upfront}))
    return sources, records, fingerprint, context, labels, art, sound


def _entries(manifest):
    return {**manifest['tables'], **manifest.get('packs', {})}


@dataclass(frozen=True)
class PreparedTables:
    directory: Path
    manifest: dict
    files: dict
    sounds: object = None

    def lookup(self, relative):
        """Only exact published version paths resolve; no path rewriting or writes."""
        return self.files.get(relative)

    def project_versions(self, spec):
        """Overlay verified versions after the canonical response projection."""
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
        if self.manifest['version'] >= 3:
            # Global counters describe the application/bootstrap, not downloadable tables.
            allowed = versions.keys() | {'F_MST_VERSION', 'F_RSC_VERSION', 'F_APP_VERSION_IOS', 'F_APP_VERSION_AND'}
            unique = {}
            for row in out['c1qYg84Q']:
                if isinstance(row, dict) and row.get('a4hXTIm0') in allowed:
                    unique.setdefault(row['a4hXTIm0'], row)
            out['c1qYg84Q'] = list(unique.values())
        return out

    def describe(self):
        return {'ok': True, 'scope': self.manifest['scope'], 'generation': self.manifest['generation'],
                'directory': str(self.directory), 'tables': len(self.manifest['tables']),
                'changed_rows': {name: row['changed_rows'] for name, row in self.manifest['tables'].items()},
                'gameplay_ready': False, **({'preparation': copy.deepcopy(self.manifest['preparation'])}
                                           if self.manifest['version'] >= 2 else {}),
                **({'packs': len(self.manifest['packs'])} if 'packs' in self.manifest else {}),
                **({'sounds': len(self.manifest['sounds']['banks']), 'sound_delivery_ready': True}
                   if 'sounds' in self.manifest else {})}


def _validate_sources(manifest, registry):
    """Validate recorded source inventories and policy before reading outputs."""
    version = manifest['version']
    optional = ({'art'} if 'packs' in manifest else set()) | ({'sound'} if version == 5 else set())
    if version >= 3 and 'upfront' in manifest['sources']:
        optional |= {'upfront'}
    if version == 1:
        if set(manifest['sources']) != registry.keys():
            raise ValueError('invalid core source inventory')
        return
    if (set(manifest['sources']) != ({'tables', 'documents'} if version == 2 else
            {'tables', 'documents', 'registry'} | optional)
            or set(manifest['sources']['tables']) != {table.name for table in
                (rules.LABEL_INPUT_TABLES if version == 2 else rules.INPUT_TABLES)}):
        raise ValueError('invalid expanded source inventory')
    from revival_economy import settings
    context = manifest['preparation']
    policy = context['economy']
    if (set(context) != ({'economy', 'labels'} if version == 2 else
            {'economy', 'labels', 'coverage'} | optional)
            or set(policy) != {'source', 'slot', 'settings'}
            or policy['source'] not in ('provisional', 'campaign')
            or not re.fullmatch(r'[A-Za-z0-9_-]+', policy['slot'])):
        raise ValueError('invalid preparation policy')
    settings({'ios_economy': {'version': 1, 'settings': policy['settings']}})
    if 'upfront' in optional:
        from ios_server.upfront_resources import coverage
        if context['upfront'] != coverage(manifest['sources']['upfront']):
            raise ValueError('Invalid upfront resource coverage')
    if version >= 3:
        registration = manifest['sources']['registry']
        if (set(registration) != {'versions', 'sha256', 'definition_sha256'}
                or registration['definition_sha256'] != rules.REGISTRY_SHA256
                or set(registration['versions']) != registry.keys()
                or any(type(value) is not int or value < 1 for value in registration['versions'].values())):
            raise ValueError('invalid complete registry provenance')


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
        version = manifest['version']
        if type(version) is not int or version not in (1, 2, 3, 4, 5):
            raise ValueError('unsupported manifest version')
        tables = rules.CORE_TABLES if version == 1 else rules.LABEL_TABLES if version == 2 else rules.TABLES
        registry = {table.name: table for table in tables}
        keys = {'version', 'scope', 'reference_commit', 'source_root', 'pipeline_version',
                'generation', 'fingerprint', 'sources', 'tables'} | ({'preparation'} if version >= 2 else set())
        keys |= ({'packs'} if version == 4 or version == 5 and 'packs' in manifest else set())
        keys |= ({'sounds'} if version == 5 else set())
        if (set(manifest) != keys or manifest['scope'] != ('core-native-tables' if version == 1 else SCOPE)
                or manifest['reference_commit'] != REVIVAL_COMMIT
                or type(manifest['generation']) is not int or not 1 <= manifest['generation'] <= 99999999
                or type(manifest['pipeline_version']) is not int or manifest['pipeline_version'] < 1
                or not isinstance(manifest['source_root'], str) or not Path(manifest['source_root']).is_absolute()
                or not re.fullmatch(r'[a-f0-9]{64}', manifest['fingerprint'])
                or ref['directory'] != f"{manifest['generation']:08d}-{manifest['fingerprint']}"
                or set(manifest['tables']) != registry.keys()):
            raise ValueError('unsupported manifest')
        _validate_sources(manifest, registry)
        outputs, versions, files = {}, {}, {}
        for name, entry in manifest['tables'].items():
            table = registry[name]
            version, base = entry['version'], entry['source_version']
            floor = entry['version_floor'] if manifest['version'] >= 3 else base
            if (set(entry) != ({'path', 'version', 'source_version', 'size', 'sha256', 'md5', 'changed_rows'}
                              | ({'version_floor'} if manifest['version'] >= 3 else set()))
                    or type(version) is not int or type(base) is not int or base < 1 or version > 2147483647
                    or type(floor) is not int or floor < base
                    or manifest['version'] >= 3 and floor != max(base, manifest['sources']['registry']['versions'][name])
                    or version != floor + rules.VERSION_OFFSET + manifest['generation'] * rules.VERSION_STEP
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
        rules.validate(outputs, versions, tables=tables)
        if 'upfront' in manifest['sources']:
            from ios_server.upfront_resources import project
            project(manifest['sources']['upfront'], outputs, verify=True)
        if 'packs' in manifest:
            from ios_server import vortex_art
            files.update(vortex_art.load(config, directory, manifest, outputs))
        sound = None
        if manifest['version'] == 5:
            from ios_server import native_sounds
            sound = native_sounds.load(config, manifest, outputs)
        return PreparedTables(directory, manifest, files, sound)
    except (OSError, KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ValueError(f'Invalid native table snapshot: {exc}') from exc


def verify_data(config):
    """Read-only verification of the snapshot and its current preparation inputs."""
    try:
        snapshot = load_prepared(config)
        if snapshot is None:
            return {'ok': False, 'scope': SCOPE, 'prepared': False, 'gameplay_ready': False,
                    'error': 'No native table snapshot. Run prepare-data with the selected --data root.'}
        _, records, fingerprint, context, _, _, _ = _complete_inputs(config, 'packs' in snapshot.manifest,
                                                                   'sounds' in snapshot.manifest)
        if (snapshot.manifest['fingerprint'] != fingerprint or snapshot.manifest['sources'] != records
                or snapshot.manifest['source_root'] != str(config.data)
                or snapshot.manifest['pipeline_version'] != rules.PIPELINE_VERSION
                or snapshot.manifest.get('preparation') != context):
            raise ValueError('Native table inputs changed. Run prepare-data to publish a new generation.')
        return {**snapshot.describe(), 'prepared': True}
    except (OSError, ValueError) as exc:
        return {'ok': False, 'scope': SCOPE, 'error': str(exc), 'gameplay_ready': False}


def open_prepared(config):
    """Explicit consumer gate; require a current complete snapshot and recorded policy."""
    snapshot = load_prepared(config)
    if snapshot is None or snapshot.manifest['version'] not in (3, 4, 5):
        raise ValueError('Complete native tables are missing. Run prepare-data.')
    _, records, fingerprint, context, _, _, _ = _complete_inputs(config, 'packs' in snapshot.manifest,
                                                               'sounds' in snapshot.manifest)
    if (snapshot.manifest['fingerprint'] != fingerprint or snapshot.manifest['sources'] != records
            or snapshot.manifest['preparation'] != context or snapshot.manifest['source_root'] != str(config.data)
            or snapshot.manifest['pipeline_version'] != rules.PIPELINE_VERSION):
        raise ValueError('Native tables are stale. Run prepare-data for this slot.')
    if context['economy']['source'] != 'campaign':
        raise ValueError('Initialize this campaign, then run prepare-data before prepared engine delivery.')
    return snapshot


def _publish(config, manifest, outputs, *, pointer_name=POINTER, entries=None):
    """Atomically publish an immutable generation of already validated artifacts."""
    pointer = private_path(config.root, pointer_name)
    parent = pointer.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    identity = f"{manifest['generation']:08d}-{manifest['fingerprint']}"
    destination = private_path(config.root, parent.relative_to(config.root) / identity)
    stage = Path(tempfile.mkdtemp(prefix='.building-', dir=parent))
    temp_pointer = None
    entries = _entries(manifest) if entries is None else entries
    try:
        for name, raw in outputs.items():
            path = stage / entries[name]['path']
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
            expected = {entry['path']: outputs[name] for name, entry in entries.items()}
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


def prepare_data(config, *, vortex_art=False, sounds=False):
    """Build and validate first, then publish under the exclusive private-runtime lock."""
    if type(vortex_art) is not bool:
        raise ValueError('Vortex preparation must be explicitly enabled or disabled.')
    if type(sounds) is not bool:
        raise ValueError('Sound preparation must be explicitly enabled or disabled.')
    with InstanceLock(config.root):
        current = load_prepared(config)
        vortex_art = vortex_art or current is not None and 'packs' in current.manifest
        sounds = sounds or current is not None and 'sounds' in current.manifest
        sources, records, fingerprint, context, labels, art, sound = _complete_inputs(config, vortex_art, sounds)
        if current is not None and current.manifest['fingerprint'] == fingerprint:
            if (current.manifest['sources'] != records or current.manifest['source_root'] != str(config.data)
                    or current.manifest['pipeline_version'] != rules.PIPELINE_VERSION
                    or current.manifest.get('preparation') != context):
                raise ValueError('Invalid native table snapshot provenance.')
            return {**current.describe(), 'prepared': True, 'prepared_now': False}
        generation = current.manifest['generation'] + 1 if current else 1
        floors = records['registry']['versions']
        if current is not None:
            for name, entry in current.manifest['tables'].items():
                floor = max(sources[name][0], floors[name])
                generation = max(generation, (entry['version'] - floor - rules.VERSION_OFFSET) // rules.VERSION_STEP + 1)
            if art is not None and current.manifest.get('packs'):
                previous = next(iter(current.manifest['packs'].values()))['version']
                generation = max(generation, (previous - art.version - rules.VERSION_OFFSET) // rules.VERSION_STEP + 1)
        if sound is not None:
            from ios_server import native_sounds
            generation = native_sounds.advance(generation, sound, current.manifest.get('sounds') if current else None)
        outputs, versions, changes = rules.build(sources, generation, labels=labels,
            economy=context['economy']['settings'], floors=floors)
        from ios_server.upfront_resources import CHECKSUM, project
        changes[CHECKSUM] += project(records['upfront'], outputs)
        packs = {}
        if art is not None:
            from ios_server import vortex_art as art_rules
            entry, raw, converted = art_rules.prepare(art, generation, outputs)
            for name, count in converted.items():
                changes[name] += count
            packs[art_rules.PACK] = entry
            rules.validate(outputs, versions)
            outputs[art_rules.PACK] = raw
        sound_binding = None
        if sound is not None:
            sound_binding, converted = native_sounds.prepare(sound, generation, outputs)
            for name, count in converted.items():
                changes[name] += count
            rules.validate(outputs, versions)
        manifest = {'version': 5 if sound is not None else 4 if art is not None else 3,
                    'scope': SCOPE, 'reference_commit': REVIVAL_COMMIT,
                    'source_root': str(config.data), 'pipeline_version': rules.PIPELINE_VERSION,
                    'generation': generation, 'fingerprint': fingerprint, 'sources': records, 'preparation': context, 'tables': {}}
        for table in rules.TABLES:
            raw = outputs[table.name]
            manifest['tables'][table.name] = {'path': table.path(versions[table.name]),
                'version': versions[table.name], 'source_version': sources[table.name][0], 'size': len(raw),
                'sha256': _sha(raw), 'md5': hashlib.md5(raw).hexdigest(), 'changed_rows': changes[table.name]}
            manifest['tables'][table.name]['version_floor'] = max(sources[table.name][0], floors[table.name])
        if packs:
            manifest['packs'] = packs
        if sound_binding is not None:
            manifest['sounds'] = sound_binding
            # Validate the binding and both resource families before publishing.
            native_sounds.load(config, manifest, outputs)
        destination = _publish(config, manifest, outputs)
        snapshot = PreparedTables(destination, manifest, {_entries(manifest)[name]['path']: raw for name, raw in outputs.items()})
        return {**snapshot.describe(), 'prepared': True, 'prepared_now': True}
