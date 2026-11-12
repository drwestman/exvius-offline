"""Read-only Vortex inputs and pure pack/table projection; no engine bindings."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib

from ios_server import cpk, native_tables as rules
from ios_server.runtime import private_path
from ios_server.table_codec import master_rows, patch_master

HERE = Path(__file__).resolve().parents[1] / 'server'
DOCUMENTS = ('event_art.json', 'event_archive.json', 'event_history.json', 'raid_archive.json')
PACK = 'spdungeon1.cpk'
RESOURCE_ID = '6108101'
PIPELINE = 2  # Preserve native UTF null-string offsets; invalidate older pack bytes.
RESOURCE = rules.RESOURCE
VERSIONS = rules.VERSIONS
CHECKSUM = rules.BY_NAME['F_RESOURCE_CHECKSUM_MST']
TABLES = (RESOURCE, VERSIONS, CHECKSUM)


def _image(name, raw):
    if not name.endswith('.png'):
        if not (raw.startswith(b'\xff\xd8') and raw.endswith(b'\xff\xd9')):
            raise ValueError('Invalid Vortex JPEG: ' + name)
        return
    if (len(raw) < 45 or raw[:16] != b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'
            or not all(struct.unpack_from('>II', raw, 16))):
        raise ValueError('Invalid Vortex PNG: ' + name)
    cursor = 8
    while cursor + 12 <= len(raw):
        size = struct.unpack_from('>I', raw, cursor)[0]
        end = cursor + 8 + size
        if end + 4 > len(raw) or zlib.crc32(raw[cursor + 4:end]) != struct.unpack_from('>I', raw, end)[0]:
            raise ValueError('Invalid Vortex PNG chunk: ' + name)
        kind = raw[cursor + 4:cursor + 8]
        cursor = end + 4
        if kind == b'IEND':
            if size == 0 and cursor == len(raw):
                return
            break
    raise ValueError('Invalid Vortex PNG ending: ' + name)


def pack_path(version):
    return f'en/sd/area/Ver{version}_{PACK}'


def owns(relative):
    return bool(re.fullmatch(r'en/sd/area/Ver[0-9]+_spdungeon1\.cpk', relative))


def resource(raw, table):
    rows = [row for _, row, _ in master_rows(raw, table.key, mode=table.cipher)
            if str(row.get('9ZCEWn0z')) == RESOURCE_ID]
    if len(rows) != 1:
        raise ValueError('Missing or duplicate Vortex resource row: ' + table.name)
    return rows[0]


@dataclass(frozen=True)
class Inputs:
    raw: bytes
    images: dict
    version: int
    provenance: dict
    coverage: dict


def collect(config, sources):
    """Hash content, not mtimes/sizes; preserve overlay precedence and containment."""
    resource_row = resource(sources[RESOURCE.name][1], RESOURCE)
    version = resource(sources[VERSIONS.name][1], VERSIONS).get('86SWOBTb')
    size = resource(sources[CHECKSUM.name][1], CHECKSUM).get('MLOSu5E0')
    if (resource_row.get('pJ56sAEo') != PACK or resource_row.get('3LHdc6Qa') != 'area'
            or not isinstance(version, str) or not version.isascii() or not version.isdigit() or int(version) < 1
            or not isinstance(size, str) or not size.isascii() or not size.isdigit()):
        raise ValueError('Invalid Vortex source resource identity/version/size')
    version = int(version)
    env = config.engine_environment()
    roots = list(dict.fromkeys(Path(env[key]) for key in ('CDN_OVERLAY', 'CDN_ROOT')))

    def read(relative, required=False):
        for root in roots:
            path = root / relative
            if not path.resolve().is_relative_to(config.data):
                raise ValueError('Vortex source escapes shared data: ' + str(path))
            if path.is_file():
                raw = path.read_bytes()
                return raw, {'path': str(path.relative_to(config.data)), 'sha256': hashlib.sha256(raw).hexdigest()}
            if path.is_symlink():
                raise ValueError('Invalid Vortex source link: ' + str(path))
        if required:
            raise ValueError('Missing Vortex source: ' + relative)
        return None, None

    raw, pack_record = read(pack_path(version), True)
    if len(raw) != int(size):
        raise ValueError('Vortex source size disagrees with resource checksum table')
    _, _, _, entries = cpk.inspect(raw)
    present = {row['FileName'].upper() for row in entries}
    # The canonical dummy is mounted from spdungeon1_common.cpk, not this English pack.
    docs, documents = {}, {}
    for name in DOCUMENTS:
        path = HERE / name
        content = path.read_bytes()
        docs[name] = json.loads(content)
        documents[name] = hashlib.sha256(content).hexdigest()
    names = {row['filename'] for section in ('events', 'dungeons')
             for row in docs['event_art.json'][section].values() if row.get('filename')}
    names.update(row['filename'] for row in docs['event_archive.json']['events'] if row.get('filename'))
    added = {row['filename'] for row in docs['event_history.json']['added'] if row.get('filename')}
    names.update(added)
    names.update(row['menu_background'] for row in docs['raid_archive.json']['events'] if row.get('menu_background'))
    if any(not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+\.(?:png|jpe?g)', name) for name in names):
        raise ValueError('Invalid Vortex artwork filename')
    images, records, missing = {}, {}, []
    for name in sorted(names):
        content, record = read('en/sd/area/' + name)
        if content is None:
            if name.upper() not in present:
                if name not in added:
                    raise ValueError('Missing required Vortex image: ' + name)
                missing.append(name)
            continue
        _image(name, content)
        images[name], records[name] = content, record
    coverage = {'named': len(names), 'available': len(names) - len(missing), 'missing_added': missing}
    provenance = {'pipeline': PIPELINE, 'pack': {**pack_record, 'version': version},
                  'images': records, 'documents': documents, 'coverage': coverage}
    return Inputs(raw, images, version, provenance, coverage)


def project(outputs, version, raw):
    """Coordinate the pack's upfront class, English version and exact byte size."""
    values = {RESOURCE.name: {'81fTkEDP': 'TUTO'}, VERSIONS.name: {'86SWOBTb': str(version)},
              CHECKSUM.name: {'MLOSu5E0': str(len(raw))}}
    changed = {}
    for table in TABLES:
        resource(outputs[table.name], table)
        def update(row):
            if str(row.get('9ZCEWn0z')) == RESOURCE_ID:
                row.update(values[table.name])
            return row
        outputs[table.name], changed[table.name] = patch_master(outputs[table.name], table.key, update, mode=table.cipher)
    return changed


def validate(outputs, entry, raw):
    expected = {'path', 'version', 'source_version', 'size', 'sha256', 'md5', 'files', 'added'}
    if (set(entry) != expected or type(entry['version']) is not int or not 1 <= entry['version'] <= 2147483647
            or type(entry['source_version']) is not int or entry['source_version'] < 1
            or entry['path'] != pack_path(entry['version']) or type(entry['size']) is not int or len(raw) != entry['size']
            or hashlib.sha256(raw).hexdigest() != entry['sha256'] or hashlib.md5(raw).hexdigest() != entry['md5']):
        raise ValueError('Invalid Vortex pack identity/checksum')
    header, _, _, entries = cpk.inspect(raw)
    if (header['FileSize'] != len(raw) or header['TotalDataSize'] != header['ContentSize']
            or type(entry['files']) is not int or entry['files'] != len(entries)
            or not isinstance(entry['added'], list) or len(set(entry['added'])) != len(entry['added'])
            or not set(entry['added']) <= {row['FileName'] for row in entries}):
        raise ValueError('Invalid Vortex pack inventory')
    expected = {RESOURCE.name: ('81fTkEDP', 'TUTO'), VERSIONS.name: ('86SWOBTb', str(entry['version'])),
                CHECKSUM.name: ('MLOSu5E0', str(len(raw)))}
    for table in TABLES:
        field, value = expected[table.name]
        if resource(outputs[table.name], table).get(field) != value:
            raise ValueError('Vortex table disagrees with prepared pack: ' + table.name)


def prepare(inputs, generation, outputs):
    """Build one validated artifact and its coordinated table projection in memory."""
    version = inputs.version + rules.VERSION_OFFSET + generation * rules.VERSION_STEP
    if version > 2147483647:
        raise ValueError('Native pack version generation is out of range.')
    raw, added = cpk.rebuild(inputs.raw, inputs.images)
    changes = project(outputs, version, raw)
    entry = {'path': pack_path(version), 'version': version, 'source_version': inputs.version,
             'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'md5': hashlib.md5(raw).hexdigest(),
             'files': cpk.inspect(raw)[0]['Files'], 'added': added}
    validate(outputs, entry, raw)
    return entry, raw, changes


def load(config, directory, manifest, outputs):
    """Read and validate the pack against the immutable generation's recorded facts."""
    if set(manifest['packs']) != {PACK}:
        raise ValueError('invalid prepared pack inventory')
    entry = manifest['packs'][PACK]
    source = manifest['sources']['art']
    if (set(source) != {'pipeline', 'pack', 'images', 'documents', 'coverage'}
            or type(source['pipeline']) is not int or source['pipeline'] < 1
            or source['coverage'] != manifest['preparation']['art']
            or entry['source_version'] != source['pack']['version']
            or entry['version'] != entry['source_version'] + rules.VERSION_OFFSET + manifest['generation'] * rules.VERSION_STEP
            or entry['path'] != pack_path(entry['version'])):
        raise ValueError('invalid Vortex pack provenance/version')
    path = private_path(config.root, directory.relative_to(config.root) / entry['path'])
    if not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError('pack escapes its generation')
    raw = path.read_bytes()
    validate(outputs, entry, raw)
    return {entry['path']: raw}
