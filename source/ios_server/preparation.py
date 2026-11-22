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
from ios_server import native_tables as rules, upfront_store, version_policy
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
    from ios_server.vortex_art import RESOURCE_ID as VORTEX_RESOURCE_ID
    exclude = (VORTEX_RESOURCE_ID,) if vortex_art else ()
    upfront = upfront_resources.collect(config, sources, exclude_resources=exclude)
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
    upfront: object = None

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
        extra = {}
        if self.manifest['version'] >= 6:
            generation = self.manifest['generation']

            def counts(entries):
                reused = sum(1 for row in entries if row['version_generation'] < generation)
                return {'reused': reused, 'bumped': len(entries) - reused}

            reuse = {'tables': counts(self.manifest['tables'].values())}
            if 'packs' in self.manifest:
                reuse['packs'] = counts(self.manifest['packs'].values())
            if 'sounds' in self.manifest:
                reuse['sounds'] = counts(self.manifest['sounds']['banks'].values())
            reuse['upfront_packs'] = counts(self.manifest.get('upfront_packs', {}).values())
            extra['version_reuse'] = reuse
            if 'upfront_packs' in self.manifest:
                extra['upfront_packs'] = len(self.manifest['upfront_packs'])
        return {'ok': True, 'scope': self.manifest['scope'], 'generation': self.manifest['generation'],
                'directory': str(self.directory), 'tables': len(self.manifest['tables']),
                'changed_rows': {name: row['changed_rows'] for name, row in self.manifest['tables'].items()},
                'gameplay_ready': False, **({'preparation': copy.deepcopy(self.manifest['preparation'])}
                                           if self.manifest['version'] >= 2 else {}),
                **({'packs': len(self.manifest['packs'])} if 'packs' in self.manifest else {}),
                **({'sounds': len(self.manifest['sounds']['banks']), 'sound_delivery_ready': True}
                   if 'sounds' in self.manifest else {}),
                **extra}


def _validate_sources(manifest, registry):
    """Validate recorded source inventories and policy before reading outputs."""
    version = manifest['version']
    optional = ({'art'} if 'packs' in manifest else set()) | (
        {'sound'} if (version == 5 or version >= 6 and 'sounds' in manifest) else set())
    if version >= 3 and 'upfront' in manifest['sources']:
        optional |= {'upfront'}
    if version >= 6 and 'upfront' not in optional:
        raise ValueError('invalid expanded source inventory')
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
    update_context = {'update'} if 'update' in context else set()
    if update_context:
        from revival_update import settings as update_settings
        update_settings({'ios_revival_update': dict(context['update'], version=1)})
    if (set(context) != ({'economy', 'labels'} if version == 2 else
            {'economy', 'labels', 'coverage'} | optional | update_context)
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
        manifest_version = manifest['version']
        if type(manifest_version) is not int or manifest_version not in (1, 2, 3, 4, 5, 6):
            raise ValueError('unsupported manifest version')
        tables = rules.CORE_TABLES if manifest_version == 1 else rules.LABEL_TABLES if manifest_version == 2 else rules.TABLES
        registry = {table.name: table for table in tables}
        keys = {'version', 'scope', 'reference_commit', 'source_root', 'pipeline_version',
                'generation', 'fingerprint', 'sources', 'tables'} | ({'preparation'} if manifest_version >= 2 else set())
        keys |= ({'packs'} if manifest_version == 4 or manifest_version >= 5 and 'packs' in manifest else set())
        keys |= ({'sounds'} if manifest_version == 5 or manifest_version >= 6 and 'sounds' in manifest else set())
        keys |= ({'upfront_packs'} if manifest_version >= 6 and 'upfront_packs' in manifest else set())
        if (set(manifest) != keys or manifest['scope'] != ('core-native-tables' if manifest_version == 1 else SCOPE)
                or manifest['reference_commit'] != REVIVAL_COMMIT
                or type(manifest['generation']) is not int or not 1 <= manifest['generation'] <= 99999999
                or type(manifest['pipeline_version']) is not int or manifest['pipeline_version'] < 1
                or not isinstance(manifest['source_root'], str) or not Path(manifest['source_root']).is_absolute()
                or not re.fullmatch(r'[a-f0-9]{64}', manifest['fingerprint'])
                or ref['directory'] != f"{manifest['generation']:08d}-{manifest['fingerprint']}"
                or set(manifest['tables']) != registry.keys()):
            raise ValueError('unsupported manifest')
        if manifest_version >= 6 and 'upfront_packs' in manifest:
            if not isinstance(manifest['upfront_packs'], dict) or not manifest['upfront_packs']:
                raise ValueError('invalid upfront_packs section')
        _validate_sources(manifest, registry)
        outputs, versions, files = {}, {}, {}
        expected_table_keys = {'path', 'version', 'source_version', 'size', 'sha256', 'md5', 'changed_rows'}
        if manifest_version >= 3:
            expected_table_keys |= {'version_floor'}
        if manifest_version >= 6:
            expected_table_keys |= {'version_generation'}
        for name, entry in manifest['tables'].items():
            table = registry[name]
            table_version, base = entry['version'], entry['source_version']
            floor = entry['version_floor'] if manifest_version >= 3 else base
            if (set(entry) != expected_table_keys
                    or type(table_version) is not int or type(base) is not int or base < 1 or table_version > 2147483647
                    or type(floor) is not int or floor < base
                    or manifest_version >= 3 and floor != max(base, manifest['sources']['registry']['versions'][name])
                    or entry['path'] != table.path(table_version) or type(entry['size']) is not int or entry['size'] < 1
                    or type(entry['changed_rows']) is not int or entry['changed_rows'] < 0):
                raise ValueError('invalid table identity: ' + name)
            if manifest_version < 6:
                if table_version != floor + rules.VERSION_OFFSET + manifest['generation'] * rules.VERSION_STEP:
                    raise ValueError('invalid table identity: ' + name)
            else:
                version_policy.validate_version(
                    table_version, entry['version_generation'], floor, manifest['generation'], label='Native table')
            path = private_path(config.root, directory.relative_to(config.root) / entry['path'])
            if not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError('table escapes its generation: ' + name)
            raw = path.read_bytes()
            if len(raw) != entry['size'] or _sha(raw) != entry['sha256'] or hashlib.md5(raw).hexdigest() != entry['md5']:
                raise ValueError('table checksum mismatch: ' + name)
            outputs[name], versions[name], files[entry['path']] = raw, table_version, raw
        rules.validate(outputs, versions, tables=tables)
        upfront_delivery = None
        if manifest_version < 6:
            if 'upfront' in manifest['sources']:
                from ios_server.upfront_resources import project
                project(manifest['sources']['upfront'], outputs, verify=True)
        else:
            from ios_server.upfront_resources import verify_manifest
            verify_manifest(manifest, outputs)
            if 'upfront_packs' in manifest:
                upfront_delivery = upfront_store.UpfrontDelivery.verify_all(config, manifest['upfront_packs'])
        if 'packs' in manifest:
            from ios_server import vortex_art
            files.update(vortex_art.load(config, directory, manifest, outputs))
        sound = None
        if 'sounds' in manifest:
            from ios_server import native_sounds
            sound = native_sounds.load(config, manifest, outputs)
        return PreparedTables(directory, manifest, files, sound, upfront_delivery)
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
    if snapshot is None or snapshot.manifest['version'] not in (3, 4, 5, 6):
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


def _compute_generation(current, sources, floors, records, art, sound, priors):
    """Compute next monotonic generation and run pre-build overflow checks."""
    p_tables, p_pack, p_sounds, p_upfront = priors
    pairs = [(max(sources[t.name][0], floors[t.name]), p_tables.get(t.name)) for t in rules.TABLES]
    if art is not None:
        from ios_server import vortex_art as art_rules
        pairs.append((art.version, p_pack))
        vortex_upfront = p_upfront.get(art_rules.RESOURCE_ID + ':MLOSu5E0')
        if vortex_upfront is not None and vortex_upfront.managed:
            pairs.append((art.version, vortex_upfront))
    if sound is not None:
        from ios_server import native_sounds
        for src in sound.snapshot.manifest['banks']:
            base = int(re.match(r'Ver([0-9]+)_', Path(src).name)[1])
            pairs.append((base, p_sounds.get(native_sounds.versioned(src, 0))))
    for key, row in records['upfront']['files'].items():
        prior_u = p_upfront.get(key)
        if prior_u is not None and (prior_u.managed or row['size'] != row['advertised'] or row['sha256'] != prior_u.sha256):
            pairs.append((row['source_version'], version_policy.PriorArtifact(
                prior_u.version, prior_u.sha256, prior_u.version_generation, managed=True)))
    generation = version_policy.next_generation(current.manifest if current is not None else None, pairs)
    for table in rules.TABLES:
        version_policy.check_bounds(max(sources[table.name][0], floors[table.name]), generation, label='Native table')
    if art is not None:
        version_policy.check_bounds(art.version, generation, label='Native pack')
    if sound is not None:
        for src in sound.snapshot.manifest['banks']:
            base = int(re.match(r'Ver([0-9]+)_', Path(src).name)[1])
            version_policy.check_bounds(base, generation, label='Native sound')
    for key, row in records['upfront']['files'].items():
        prior_u = p_upfront.get(key)
        if row['size'] != row['advertised'] or (prior_u is not None and row['sha256'] != prior_u.sha256):
            version_policy.check_bounds(row['source_version'], generation, label='Upfront CPK')
    return generation


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
        # Stage 0: Collect inputs + compute generation + overflow pre-check
        sources, records, fingerprint, context, labels, art, sound = _complete_inputs(config, vortex_art, sounds)
        if current is not None and current.manifest['fingerprint'] == fingerprint:
            if (current.manifest['sources'] != records or current.manifest['source_root'] != str(config.data)
                    or current.manifest['pipeline_version'] != rules.PIPELINE_VERSION
                    or current.manifest.get('preparation') != context):
                raise ValueError('Invalid native table snapshot provenance.')
            return {**current.describe(), 'prepared': True, 'prepared_now': False}
        floors = records['registry']['versions']
        prior_manifest = current.manifest if current is not None else None
        p_tables = version_policy.prior_tables(prior_manifest)
        p_pack = version_policy.prior_pack(prior_manifest)
        p_sounds = version_policy.prior_sounds(prior_manifest)
        p_upfront = version_policy.prior_upfront(prior_manifest)
        generation = _compute_generation(
            current, sources, floors, records, art, sound, (p_tables, p_pack, p_sounds, p_upfront))

        # Stage 1: Leaf artifacts (upfront CPKs, Vortex CPK, sound banks, localized text tables)
        from ios_server import upfront_resources
        upfront_packs = upfront_resources.resolve(records['upfront'], generation, p_upfront)
        packs = {}
        pack_entry = pack_raw = None
        if art is not None:
            from ios_server import vortex_art as art_rules
            pack_entry, pack_raw = art_rules.build_pack(art, generation, prior=p_pack)
        sound_banks = sound_binding = None
        if sound is not None:
            from ios_server import native_sounds
            sound_banks = native_sounds.inventory(sound.snapshot, generation, prior=p_sounds)
        outputs, changes, localized_resolved = rules.build_localized(
            sources, generation, labels=labels, floors=floors, prior=p_tables)

        # Stage 2: Master table projections
        localized_versions = {name: item.version for name, item in localized_resolved.items()}
        rules.build_masters(sources, outputs, changes, localized_versions,
                            economy=context['economy']['settings'], update=context.get('update'))
        for name, count in upfront_resources.project(records['upfront'], outputs, bumped=upfront_packs).items():
            changes[name] += count
        if art is not None:
            for name, count in art_rules.project(outputs, pack_entry['version'], pack_raw).items():
                changes[name] += count
            art_rules.validate(outputs, pack_entry, pack_raw, schema_version=6)
            packs[art_rules.PACK] = pack_entry
            outputs[art_rules.PACK] = pack_raw
        if sound is not None:
            for name, count in native_sounds._project(sound.snapshot, sound_banks, outputs).items():
                changes[name] += count
            sound_binding = {'snapshot': sound.provenance['snapshot'], 'banks': sound_banks}

        # Stage 3: Master table version resolution against prior generation
        versions, table_resolved = rules.resolve_masters(
            outputs, sources, generation, localized_resolved, floors=floors, prior=p_tables)

        # Stage 4: In-memory cross-validation
        rules.validate(outputs, versions)
        manifest = {'version': 6,
                    'scope': SCOPE, 'reference_commit': REVIVAL_COMMIT,
                    'source_root': str(config.data), 'pipeline_version': rules.PIPELINE_VERSION,
                    'generation': generation, 'fingerprint': fingerprint, 'sources': records,
                    'preparation': context, 'tables': {}}
        for table in rules.TABLES:
            raw = outputs[table.name]
            manifest['tables'][table.name] = {
                'path': table.path(versions[table.name]),
                'version': versions[table.name],
                'source_version': sources[table.name][0],
                'version_generation': table_resolved[table.name].version_generation,
                'size': len(raw),
                'sha256': _sha(raw),
                'md5': hashlib.md5(raw).hexdigest(),
                'changed_rows': changes[table.name],
                'version_floor': max(sources[table.name][0], floors[table.name]),
            }
        if packs:
            manifest['packs'] = packs
        if sound_binding is not None:
            manifest['sounds'] = sound_binding
        if upfront_packs:
            manifest['upfront_packs'] = upfront_packs
        upfront_resources.verify_manifest(manifest, outputs)
        sound_delivery = None
        if sound_binding is not None:
            sound_delivery = native_sounds.load(config, manifest, outputs)

        # Stage 5: Atomic publication (stage upfront blobs -> stage generation dir -> swap current.json)
        upfront_delivery = None
        if upfront_packs:
            blob_store = upfront_store.BlobStore(config.root, config.data)
            for key, entry in upfront_packs.items():
                src_path = config.data / records['upfront']['files'][key]['path']
                staged_blob = blob_store.stage(src_path, entry['sha256'], entry['size'])
                if staged_blob != entry['blob']:
                    raise ValueError('Upfront CPK blob path mismatch: ' + key)
            upfront_delivery = upfront_store.UpfrontDelivery.from_manifest(config.root, upfront_packs)
        destination = _publish(config, manifest, outputs)
        snapshot = PreparedTables(
            destination, manifest,
            {_entries(manifest)[name]['path']: raw for name, raw in outputs.items()},
            sound_delivery, upfront_delivery,
        )
        return {**snapshot.describe(), 'prepared': True, 'prepared_now': True}
