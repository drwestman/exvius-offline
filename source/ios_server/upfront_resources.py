"""Read-only upfront CPK facts and pure iOS byte-size/version table projection."""
import hashlib
from pathlib import Path
import re

from ios_server import native_tables as rules, version_policy
from ios_server.table_codec import master_rows, patch_master
from ios_server.upfront_store import BLOB_PATTERN, unversioned_path

CHECKSUM = 'F_RESOURCE_CHECKSUM_MST'
VERSIONS = 'F_RESOURCE_VERSION_MST_LOCALIZE'
FIELDS = (('common_lang', 'OzT5lSz3', 'JwbkKrjA'), ('en', '86SWOBTb', 'MLOSu5E0'))
KEY = r'[1-9][0-9]*:(?:JwbkKrjA|MLOSu5E0)'
POLICY_KEYS = {
    1: {'path', 'size', 'sha256', 'advertised'},
    2: {'path', 'relative', 'source_version', 'size', 'sha256', 'advertised'},
}
UPFRONT_PACK_KEYS = {'path', 'version', 'source_version', 'version_generation', 'size', 'sha256', 'advertised', 'blob'}


def safe_path(value):
    return (isinstance(value, str) and bool(value) and not any(c in value for c in '\\\0:')
            and all(part not in ('', '.', '..') for part in value.split('/')))


def versioned_relative(relative: str, version: int) -> str:
    parent, sep, name = relative.rpartition('/')
    return f"{parent}{sep}{re.sub(r'^Ver[0-9]+_', f'Ver{version}_', name)}"


def validate(records):
    if (not isinstance(records, dict) or set(records) != {'policy', 'files', 'missing'}
            or type(records['policy']) is not int or records['policy'] not in (1, 2)
            or not isinstance(records['files'], dict) or not isinstance(records['missing'], list)
            or records['missing'] != sorted(set(records['missing']))):
        raise ValueError('Invalid upfront CPK provenance')
    for key in [*records['files'], *records['missing']]:
        if not isinstance(key, str) or not re.fullmatch(KEY, key):
            raise ValueError('Invalid upfront CPK resource identity')
    if set(records['files']) & set(records['missing']):
        raise ValueError('Conflicting upfront CPK provenance')
    expected_keys = POLICY_KEYS[records['policy']]
    for row in records['files'].values():
        if (not isinstance(row, dict) or set(row) != expected_keys
                or not safe_path(row['path']) or not row['path'].endswith('.cpk')
                or type(row['size']) is not int or row['size'] < 1
                or type(row['advertised']) is not int or row['advertised'] < 0
                or not isinstance(row['sha256'], str) or not re.fullmatch(r'[a-f0-9]{64}', row['sha256'])):
            raise ValueError('Invalid upfront CPK file identity')
        if records['policy'] >= 2:
            if (not safe_path(row['relative']) or not row['relative'].endswith('.cpk')
                    or type(row['source_version']) is not int or row['source_version'] < 1
                    or not Path(row['relative']).name.startswith(f"Ver{row['source_version']}_")
                    or not (row['path'] == row['relative'] or row['path'].endswith('/' + row['relative']))):
                raise ValueError('Invalid upfront CPK relative identity')


def coverage(records):
    validate(records)
    return {'checked': len(records['files']), 'corrected': sum(row['size'] != row['advertised'] for row in records['files'].values()),
            'missing': list(records['missing'])}


def _rows(sources, name):
    table = rules.BY_NAME[name]
    return [row for _, row, _ in master_rows(sources[name][1], table.key, mode=table.cipher)]


def _find(config, roots, relative):
    if not safe_path(relative):
        raise ValueError('Invalid upfront CPK path')
    for root in roots:
        path = root / relative
        if not path.resolve().is_relative_to(config.data):
            raise ValueError('Upfront CPK escapes shared content')
        if path.is_file():
            return path
    return None


def collect(config, sources, *, exclude_resources=()):
    excluded = frozenset(exclude_resources)
    versions = {row.get('9ZCEWn0z'): row for row in _rows(sources, VERSIONS)}
    checksums = {row.get('9ZCEWn0z'): row for row in _rows(sources, CHECKSUM)}
    env = config.engine_environment()
    roots = tuple(dict.fromkeys(Path(env[key]) for key in ('CDN_OVERLAY', 'CDN_ROOT')))
    files, missing = {}, []
    for row in _rows(sources, 'F_RESOURCE_MST'):
        name, identity = row.get('pJ56sAEo', ''), row.get('9ZCEWn0z', '')
        if (not isinstance(name, str) or not name.endswith('.cpk') or identity in excluded
                or str(row.get('81fTkEDP', '')).upper() not in ('TUTO', 'PRE_TUTO') and not rules.is_upfront_pack(row)):
            continue
        if not isinstance(identity, str) or not identity.isascii() or not identity.isdigit() or int(identity) < 1:
            raise ValueError('Invalid upfront CPK resource ID')
        directory = row.get('3LHdc6Qa') or ('resources' if name in rules.EARLY_PACKS else '')
        for locale, version_field, size_field in FIELDS:
            version = versions.get(identity, {}).get(version_field, '0')
            if not isinstance(version, str) or not version.isascii() or not version.isdigit() or int(version) < 1:
                continue
            key = identity + ':' + size_field
            if key in files or key in missing:
                raise ValueError('Duplicate upfront CPK resource identity')
            relative = f'{locale}/sd/{directory}/Ver{version}_{name}'
            path = _find(config, roots, relative)
            if path is None:
                missing.append(key); continue
            advertised = checksums.get(identity, {}).get(size_field)
            if not isinstance(advertised, str) or not advertised.isascii() or not advertised.isdigit():
                raise ValueError('Missing upfront iOS resource size: ' + key)
            digest, size = hashlib.sha256(), 0
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block); size += len(block)
            files[key] = {'path': path.relative_to(config.data).as_posix(), 'relative': relative,
                          'source_version': int(version), 'size': size,
                          'sha256': digest.hexdigest(), 'advertised': int(advertised)}
    records = {'policy': 2, 'files': files, 'missing': sorted(missing)}
    validate(records)
    return records


def resolve(records, generation, prior_upfront=None):
    """Resolve version bumps/carry-forward for drifted or changed upfront CPKs."""
    validate(records)
    prior_upfront = prior_upfront or {}
    upfront_packs = {}
    seen_paths, seen_identities = set(), set()
    for key, row in records['files'].items():
        source_version = (row['source_version'] if 'source_version' in row
                          else int(re.match(r'^Ver([0-9]+)_', Path(row['path']).name)[1]))
        relative = row['relative'] if 'relative' in row else row['path']
        resolved = version_policy.resolve_upfront(
            source_version, row['size'], row['advertised'], row['sha256'], prior_upfront.get(key), generation)
        if resolved.managed:
            published_path = versioned_relative(relative, resolved.version)
            ident = unversioned_path(published_path)
            if published_path in seen_paths or ident in seen_identities:
                raise ValueError('Conflicting bumped upfront CPK paths')
            seen_paths.add(published_path)
            seen_identities.add(ident)
            upfront_packs[key] = {
                'path': published_path,
                'version': resolved.version,
                'source_version': source_version,
                'version_generation': resolved.version_generation,
                'size': row['size'],
                'sha256': row['sha256'],
                'advertised': row['advertised'],
                'blob': f"assets/upfront/blobs/{row['sha256']}.cpk",
            }
    return upfront_packs


def project(records, outputs, *, bumped=None, verify=False):
    validate(records)
    bumped = bumped or {}
    changes = {}
    for table_name, is_version in ((CHECKSUM, False), (VERSIONS, True)):
        table = rules.BY_NAME[table_name]
        seen = set()

        def update(row):
            identity = row.get('9ZCEWn0z')
            for _locale, version_field, size_field in FIELDS:
                key = str(identity) + ':' + size_field
                if key in records['files']:
                    if key in seen:
                        raise ValueError('Duplicate upfront checksum resource')
                    seen.add(key)
                    if not is_version:
                        expected = str(records['files'][key]['size'])
                        if verify and row.get(size_field) != expected:
                            raise ValueError('Upfront iOS resource size disagrees with served file: ' + key)
                        row[size_field] = expected
                    else:
                        if key in bumped:
                            expected = str(bumped[key]['version'])
                        elif 'source_version' in records['files'][key]:
                            expected = str(records['files'][key]['source_version'])
                        else:
                            expected = None
                        if expected is not None:
                            if verify and row.get(version_field) != expected:
                                raise ValueError('Upfront iOS resource version disagrees with served file: ' + key)
                            row[version_field] = expected
            return row

        raw, count = patch_master(outputs[table_name], table.key, update, mode=table.cipher)
        if seen != set(records['files']):
            raise ValueError('Upfront resource is missing from the resource table: ' + table_name)
        if not verify:
            outputs[table_name] = raw
        changes[table_name] = count
    return changes


def verify_manifest(manifest, outputs):
    """Validate schema-6 upfront provenance, bumped pack entries, and cross-table agreement."""
    records = manifest['sources']['upfront']
    validate(records)
    if records['policy'] != 2:
        raise ValueError('Schema 6 requires upfront provenance policy 2')
    upfront_packs = manifest.get('upfront_packs', {})
    if 'packs' in manifest:
        from ios_server.vortex_art import RESOURCE_ID
        if any(key.startswith(RESOURCE_ID + ':') for key in [*records['files'], *records['missing']]):
            raise ValueError('Vortex resource cannot also be owned by upfront resources')
    for key, row in records['files'].items():
        if row['size'] != row['advertised'] and key not in upfront_packs:
            raise ValueError('Drifted upfront CPK must be version-bumped: ' + key)
    seen_paths, seen_identities = set(), set()
    for key, entry in upfront_packs.items():
        if key not in records['files']:
            raise ValueError('Unknown upfront pack entry: ' + key)
        row = records['files'][key]
        if (not isinstance(entry, dict) or set(entry) != UPFRONT_PACK_KEYS
                or entry['source_version'] != row['source_version']
                or entry['size'] != row['size']
                or entry['sha256'] != row['sha256']
                or entry['advertised'] != row['advertised']
                or entry['path'] != versioned_relative(row['relative'], entry['version'])
                or not BLOB_PATTERN.fullmatch(entry['blob'])
                or entry['blob'] != f"assets/upfront/blobs/{entry['sha256']}.cpk"):
            raise ValueError('Invalid bumped upfront CPK entry: ' + key)
        version_policy.validate_version(
            entry['version'], entry['version_generation'], entry['source_version'],
            manifest['generation'], label='Upfront CPK')
        ident = unversioned_path(entry['path'])
        if entry['path'] in seen_paths or ident in seen_identities:
            raise ValueError('Conflicting bumped upfront CPK paths')
        seen_paths.add(entry['path'])
        seen_identities.add(ident)
    project(records, outputs, bumped=upfront_packs, verify=True)
