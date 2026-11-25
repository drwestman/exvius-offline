"""Read-only, exact-version sound inventory from original encrypted masters."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from engine_profile import REVIVAL_COMMIT
from ios_server import native_tables as rules, sound_codec
from ios_server.table_codec import master_rows

FAMILIES = (('F_RESOURCE', '9ZCEWn0z'), ('F_RESOURCE_MAP', 'Nnb20keZ'))
TABLES = tuple(rules.BY_NAME[prefix + suffix] for prefix, _ in FAMILIES
               for suffix in ('_MST', '_VERSION_MST_LOCALIZE', '_CHECKSUM_MST'))


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _bank_identity(path):
    # Inventory retains facts only; do not allocate whole banks or cache hashes.
    # Count the bytes actually hashed, including a short final block.
    value, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block); size += len(block)
    return {'size': size, 'sha256': value.hexdigest()}


def positive(value):
    return isinstance(value, str) and value.isascii() and value.isdigit() and int(value) > 0


def nonnegative(value):
    return isinstance(value, str) and value.isascii() and value.isdigit()


def safe_bank(relative):
    return isinstance(relative, str) and bool(re.fullmatch(r'common_lang/sound/(?:[A-Za-z0-9_-]+/)+ios/Ver[1-9][0-9]*_[A-Za-z0-9_.-]+\.(?:acb|awb)', relative))


def contained(config, path):
    if not path.resolve().is_relative_to(config.data):
        raise ValueError('Sound source escapes shared data: ' + str(path))
    if path.is_symlink() and not path.is_file():
        raise ValueError('Invalid sound source link: ' + str(path))
    return path


def read(config, record):
    """Recheck content after inventory so concurrent source edits cannot publish."""
    relative = PurePosixPath(record['path'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Invalid sound source path')
    raw = contained(config, config.data / relative).read_bytes()
    if len(raw) != record['size'] or digest(raw) != record['sha256']:
        raise ValueError('Sound source changed during preparation: ' + str(relative))
    return raw


@dataclass(frozen=True)
class Inputs:
    sources: dict
    fingerprint: str


def collect(config):
    env = config.engine_environment()
    roots = list(dict.fromkeys(Path(env[key]) for key in ('CDN_OVERLAY', 'CDN_ROOT')))
    documents, tables = {}, {}
    for table in TABLES:
        path = None
        for root in roots:
            folder = contained(config, root / 'mst')
            matches = [(int(m[1]), candidate) for candidate in folder.glob('Ver*_' + table.token + '.dat')
                       if (m := re.fullmatch(r'Ver([1-9][0-9]*)_' + table.token + r'\.dat', candidate.name))]
            if matches:
                version, path = max(matches, key=lambda item: item[0])
                break
        if path is None:
            raise ValueError('Missing sound resource table: ' + table.name)
        raw = contained(config, path).read_bytes()
        documents[table.name] = {'path': str(path.relative_to(config.data)), 'version': version, 'sha256': digest(raw)}
        tables[table.name] = [row for _, row, _ in master_rows(raw, table.key, mode=table.cipher)]
    banks, resources = {}, {}
    for prefix, id_column in FAMILIES:
        def indexed(suffix):
            result = {}
            for row in tables[prefix + suffix]:
                identity = row.get(id_column)
                if not positive(identity) or identity in result:
                    raise ValueError('Invalid or duplicate sound resource identity: ' + prefix + suffix)
                result[identity] = row
            return result
        versions, checksums = indexed('_VERSION_MST_LOCALIZE'), indexed('_CHECKSUM_MST')
        for identity, row in indexed('_MST').items():
            family = row.get('3LHdc6Qa', '')
            if not isinstance(family, str) or not family.startswith('sound/'):
                continue
            version = versions.get(identity, {}).get('OzT5lSz3')
            checksum = checksums.get(identity, {})
            ios_size, android_size = checksum.get('JwbkKrjA'), checksum.get('mYtcPkQQ')
            name = row.get('pJ56sAEo')
            target = f'common_lang/{family}/ios/Ver{version}_{name}'
            if (not positive(version) or not nonnegative(ios_size) or not nonnegative(android_size)
                    or not safe_bank(target)):
                raise ValueError('Invalid sound resource path/version/size: ' + prefix + ':' + identity)
            resource = {'bank': target, 'version': int(version),
                        'ios_size': int(ios_size), 'android_size': int(android_size)}
            resources[prefix + ':' + identity] = resource
            if target in banks:
                continue
            path, native = None, False
            # Exact native iOS banks win across roots; never substitute a different version.
            for platform in ('ios', 'android'):
                relative = target.replace('/ios/', '/' + platform + '/')
                for root in roots:
                    candidate = contained(config, root / relative)
                    if candidate.is_file():
                        path, native = candidate, platform == 'ios'
                        break
                if path is not None:
                    break
            if path is None:
                raise ValueError('Missing exact sound source: ' + target)
            # These masters contain zero and stale sizes. Record them as facts;
            # validate bank structure/CRCs and measure bytes before later table repair.
            banks[target] = {'path': str(path.relative_to(config.data)), 'native': native,
                             **_bank_identity(path)}
    if not banks:
        raise ValueError('No sound resources in the selected data root')
    sources = {'pipeline': sound_codec.PIPELINE, 'reference_commit': REVIVAL_COMMIT,
               'tables': documents, 'banks': banks, 'resources': resources}
    return Inputs(sources, digest(encoded(sources)))
