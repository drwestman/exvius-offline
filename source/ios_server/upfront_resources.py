"""Read-only upfront CPK facts and pure iOS byte-size table projection."""
import hashlib
from pathlib import Path
import re

from ios_server import native_tables as rules
from ios_server.table_codec import master_rows, patch_master

CHECKSUM = 'F_RESOURCE_CHECKSUM_MST'
FIELDS = (('common_lang', 'OzT5lSz3', 'JwbkKrjA'), ('en', '86SWOBTb', 'MLOSu5E0'))
KEY = r'[1-9][0-9]*:(?:JwbkKrjA|MLOSu5E0)'


def safe_path(value):
    return (isinstance(value, str) and bool(value) and not any(c in value for c in '\\\0:')
            and all(part not in ('', '.', '..') for part in value.split('/')))


def validate(records):
    if (not isinstance(records, dict) or set(records) != {'policy', 'files', 'missing'}
            or type(records['policy']) is not int or records['policy'] != 1
            or not isinstance(records['files'], dict) or not isinstance(records['missing'], list)
            or records['missing'] != sorted(set(records['missing']))):
        raise ValueError('Invalid upfront CPK provenance')
    for key in [*records['files'], *records['missing']]:
        if not isinstance(key, str) or not re.fullmatch(KEY, key):
            raise ValueError('Invalid upfront CPK resource identity')
    if set(records['files']) & set(records['missing']):
        raise ValueError('Conflicting upfront CPK provenance')
    for row in records['files'].values():
        if (not isinstance(row, dict) or set(row) != {'path', 'size', 'sha256', 'advertised'}
                or not safe_path(row['path']) or not row['path'].endswith('.cpk')
                or type(row['size']) is not int or row['size'] < 1
                or type(row['advertised']) is not int or row['advertised'] < 0
                or not isinstance(row['sha256'], str) or not re.fullmatch(r'[a-f0-9]{64}', row['sha256'])):
            raise ValueError('Invalid upfront CPK file identity')


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


def collect(config, sources):
    versions = {row.get('9ZCEWn0z'): row for row in _rows(sources, 'F_RESOURCE_VERSION_MST_LOCALIZE')}
    checksums = {row.get('9ZCEWn0z'): row for row in _rows(sources, CHECKSUM)}
    env = config.engine_environment()
    roots = tuple(dict.fromkeys(Path(env[key]) for key in ('CDN_OVERLAY', 'CDN_ROOT')))
    files, missing = {}, []
    for row in _rows(sources, 'F_RESOURCE_MST'):
        name, identity = row.get('pJ56sAEo', ''), row.get('9ZCEWn0z', '')
        if (not isinstance(name, str) or not name.endswith('.cpk')
                or str(row.get('81fTkEDP', '')).upper() not in ('TUTO', 'PRE_TUTO') and name not in rules.UPFRONT_PACKS):
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
            path = _find(config, roots, f'{locale}/sd/{directory}/Ver{version}_{name}')
            if path is None:
                missing.append(key); continue
            advertised = checksums.get(identity, {}).get(size_field)
            if not isinstance(advertised, str) or not advertised.isascii() or not advertised.isdigit():
                raise ValueError('Missing upfront iOS resource size: ' + key)
            digest, size = hashlib.sha256(), 0
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block); size += len(block)
            files[key] = {'path': path.relative_to(config.data).as_posix(), 'size': size,
                          'sha256': digest.hexdigest(), 'advertised': int(advertised)}
    records = {'policy': 1, 'files': files, 'missing': sorted(missing)}
    validate(records)
    return records


def project(records, outputs, *, verify=False):
    validate(records)
    table = rules.BY_NAME[CHECKSUM]; seen = set()
    def update(row):
        identity = row.get('9ZCEWn0z')
        for _locale, _version, field in FIELDS:
            key = str(identity) + ':' + field
            if key in records['files']:
                if key in seen:
                    raise ValueError('Duplicate upfront checksum resource')
                seen.add(key)
                size = str(records['files'][key]['size'])
                if verify and row.get(field) != size:
                    raise ValueError('Upfront iOS resource size disagrees with served file: ' + key)
                row[field] = size
        return row
    raw, count = patch_master(outputs[CHECKSUM], table.key, update, mode=table.cipher)
    if seen != set(records['files']):
        raise ValueError('Upfront resource is missing from the checksum table')
    if not verify:
        outputs[CHECKSUM] = raw
    return count
