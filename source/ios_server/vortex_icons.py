"""Read-only native dungeon-icon dependencies for the upfront Vortex pack."""
import hashlib
import re

from ios_server import cpk, native_tables as rules
from ios_server.table_codec import master_rows


def _rows(sources, name):
    table = rules.BY_NAME[name]
    return [row for _, row, _ in master_rows(sources[name][1], table.key, mode=table.cipher)]


def collect(sources, dungeons, present, read, validate):
    """Copy available originals, never remap shared icon IDs or synthesize art."""
    icons = {row.get('0HUPxDf1'): row.get('qtkvrS60') for row in _rows(sources, 'F_ICON_MST')}
    names = {icons.get(row.get('0HUPxDf1')) for row in _rows(sources, 'F_DUNGEON_MST')
             if str(row.get('U9iHsau3')) in dungeons}
    names.discard(None)
    names.discard('')
    if any(not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+\.(?:png|jpe?g)', name) for name in names):
        raise ValueError('Invalid Vortex inner icon filename')
    remaining = {name.upper(): name for name in names if name.upper() not in present}
    images, records = {}, {}
    # English resources take precedence over common-language artwork. Each read
    # independently retains the configured overlay-before-native precedence.
    versions = {row.get('9ZCEWn0z'): row for row in _rows(sources, rules.VERSIONS.name)}
    resources = [(row, versions.get(row.get('9ZCEWn0z'), {}))
                 for row in _rows(sources, rules.RESOURCE.name)]
    map_versions = {row.get('Nnb20keZ'): row for row in _rows(sources, 'F_RESOURCE_MAP_VERSION_MST_LOCALIZE')}
    # Map resources also contain indexed/encrypted scene archives. Their flat
    # *_common.cpk companions supply the original menu icons without scene keys.
    resources.extend((row, map_versions.get(row.get('Nnb20keZ'), {}))
                     for row in _rows(sources, 'F_RESOURCE_MAP_MST')
                     if row.get('pJ56sAEo', '').endswith('_common.cpk'))
    resources.sort(key=lambda pair: str(pair[0].get('pJ56sAEo', '')))
    for locale, field in (('en', '86SWOBTb'), ('common_lang', 'OzT5lSz3')):
        for key, name in list(remaining.items()):
            raw, record = read(f'{locale}/sd/area/{name}')
            if raw is not None:
                validate(name, raw)
                images[name], records[name] = raw, record
                del remaining[key]
        for row, versions in resources:
            if not remaining:
                break
            name, directory = row.get('pJ56sAEo', ''), row.get('3LHdc6Qa')
            if directory not in ('area', 'banner') or not name.endswith('.cpk'):
                continue
            if not re.fullmatch(r'[A-Za-z0-9_.-]+\.cpk', name):
                raise ValueError('Invalid Vortex icon source pack name')
            version = versions.get(field, '0')
            if not isinstance(version, str) or not version.isascii() or not version.isdigit():
                raise ValueError('Invalid Vortex icon source version')
            if int(version) == 0:
                continue
            raw, record = read(f'{locale}/sd/{directory}/Ver{version}_{name}')
            if raw is None:
                continue
            header, _, _, entries = cpk.inspect(raw)
            for entry in entries:
                key = entry['FileName'].upper()
                if key not in remaining:
                    continue
                name = remaining[key]
                if entry['ExtractSize'] != entry['FileSize']:
                    # Compressed source images need a decoder; report the gap.
                    continue
                begin = header['TocOffset'] + entry['FileOffset']
                blob = raw[begin:begin + entry['FileSize']]
                validate(name, blob)
                images[name] = blob
                records[name] = {**record, 'member': entry['FileName'],
                                 'member_sha256': hashlib.sha256(blob).hexdigest()}
                del remaining[key]
    return images, records, {'required': len(names), 'available': len(names) - len(remaining),
                              'missing': sorted(remaining.values())}
