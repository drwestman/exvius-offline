"""Read-only managed installation records, pinned content paths and file verification."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from ios_server import pack_manifest as policy

POINTER = 'ios-current.json'
GENERATIONS = '.ios-generations'
LAYERS = '.ios-layers'
DOWNLOADS = '.ios-downloads'


def path(root, relative):
    root = Path(root).resolve()
    if (not isinstance(relative, str) or not relative or any(c in relative for c in '\\\0:')
            or any(part in ('', '.', '..') for part in relative.split('/'))):
        raise ValueError('Invalid managed content path')
    target = root
    for part in relative.split('/'):
        target = target / part
        if target.is_symlink():
            raise ValueError('Managed content path is a symlink: ' + str(target))
    if not target.resolve().is_relative_to(root):
        raise ValueError('Managed content path escapes its root')
    return target


def validate_inventory(files):
    if not isinstance(files, dict):
        raise ValueError('Invalid managed file inventory')
    seen = set()
    for relative, entry in files.items():
        original = 'metadata/registry.json' if relative == 'registry.json' else relative
        if policy.destination(original) != relative or policy.collision_key(relative) in seen:
            raise ValueError('Conflicting managed content paths')
        seen.add(policy.collision_key(relative))
        if (set(entry) != {'size', 'sha256'} or type(entry['size']) is not int or entry['size'] < 0
                or not re.fullmatch(policy.SHA, entry['sha256'])):
            raise ValueError('Invalid managed file identity')
    for relative in files:
        parts = relative.split('/')
        if any(policy.collision_key('/'.join(parts[:i])) in seen for i in range(1, len(parts))):
            raise ValueError('Managed file conflicts with a parent directory')


def verify_files(directory, files, *, extras=()):
    validate_inventory(files)
    actual = set()
    for item in directory.rglob('*'):
        relative = item.relative_to(directory).as_posix()
        path(directory, relative)
        if item.is_file() and relative not in extras:
            key = policy.collision_key(relative)
            if key in actual:
                raise ValueError('Case or Unicode collision in managed content')
            actual.add(key)
    if actual != {policy.collision_key(relative) for relative in files}:
        raise ValueError('Managed content file inventory differs from its record')
    for relative, entry in files.items():
        source = path(directory, relative)
        if source.stat().st_size != entry['size'] or policy.file_digest(source) != entry['sha256']:
            raise ValueError('Managed content checksum mismatch: ' + relative)


def validate_layout(directory, files):
    for prefix in ('static/mst_decoded/', 'static/text_decoded/', 'native/mst/', 'native/common_lang/'):
        if not any(name.startswith(prefix) for name in files):
            raise ValueError('Managed pack set is incomplete: ' + prefix)
    for name in ('registry.json', 'static/client/shared_prefs/gamedata.xml'):
        if name not in files:
            raise ValueError('Managed pack set is incomplete: ' + name)
    try:
        doc = ET.fromstring(path(directory, 'static/client/shared_prefs/gamedata.xml').read_bytes())
        registry = json.loads(path(directory, 'registry.json').read_bytes())
        rows = [row for row in doc if row.get('name', '').startswith('keyF_')]
        values = {row.get('name'): row.text for row in rows}
        if (doc.tag != 'map' or not values or len(values) != len(rows) or values != registry
                or any(row.tag != 'string' or not isinstance(row.text, str) or not row.text.isascii()
                       or not row.text.isdigit() for row in rows)):
            raise ValueError('native registry disagrees with gamedata.xml')
    except (ET.ParseError, ValueError) as exc:
        raise ValueError(f'Invalid managed native registry: {exc}') from exc


def project_registry(directory, files):
    """Mirror Android's post-extraction registry update, without changing a layer."""
    for required in ('registry.json', 'static/client/shared_prefs/gamedata.xml'):
        if required not in files:
            raise ValueError('Managed pack set is incomplete: ' + required)
    try:
        source = ET.fromstring(path(directory, 'static/client/shared_prefs/gamedata.xml').read_bytes())
        registry = json.loads(path(directory, 'registry.json').read_bytes())
        rows = [row for row in source if row.get('name', '').startswith('keyF_')]
        if (source.tag != 'map' or len({row.get('name') for row in rows}) != len(rows)
                or any(row.tag != 'string' or not isinstance(row.text, str) or not row.text.isascii() or not row.text.isdigit() for row in rows)
                or not isinstance(registry, dict) or not registry
                or any(not isinstance(key, str) or not re.fullmatch(r'keyF_[A-Za-z0-9_]+', key)
                       or not isinstance(value, str) or not value.isascii() or not value.isdigit()
                       for key, value in registry.items())):
            raise ValueError('invalid native registry data')
    except (ET.ParseError, ValueError) as exc:
        raise ValueError(f'Invalid managed native registry: {exc}') from exc
    result = ET.Element('map')
    for key, value in sorted(registry.items()):
        ET.SubElement(result, 'string', {'name': key}).text = value
    raw = ET.tostring(result, encoding='utf-8', xml_declaration=True)
    relative = 'static/client/shared_prefs/gamedata.xml'
    target = path(directory, relative); temporary = target.with_suffix('.projecting')
    with temporary.open('wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    temporary.chmod(0o444)
    os.replace(temporary, target)
    return {**files, relative: {'size': len(raw), 'sha256': policy.digest(raw)}}


@dataclass(frozen=True)
class Installation:
    directory: Path
    manifest: policy.Manifest
    record: dict

    def describe(self):
        return {'ok': True, 'scope': 'managed-packs', 'installed': True,
                'directory': str(self.directory), 'manifest_sha256': self.manifest.sha256,
                'revision': self.manifest.document['revision'], 'packs': len(self.manifest.packs),
                'files': len(self.record['files']), 'bytes': sum(row['size'] for row in self.record['files'].values()),
                'gameplay_ready': False}


def load(root, *, verify=False):
    pointer = path(root, POINTER)
    if not pointer.exists():
        return None
    try:
        ref = json.loads(pointer.read_bytes())
        if (set(ref) != {'version', 'directory', 'installation_sha256'} or type(ref['version']) is not int
                or ref['version'] != 1 or not re.fullmatch(GENERATIONS + '/' + policy.SHA, ref['directory'])):
            raise ValueError('invalid installation pointer')
        directory = path(root, ref['directory'])
        raw = path(directory, 'installation.json').read_bytes()
        if policy.digest(raw) != ref['installation_sha256']:
            raise ValueError('installation record checksum mismatch')
        record = json.loads(raw)
        manifest = policy.parse(path(directory, 'manifest.json').read_bytes())
        if (set(record) != {'version', 'policy', 'manifest_sha256', 'layers', 'files'}
                or type(record['version']) is not int or record['version'] != 1
                or type(record['policy']) is not int or record['policy'] != policy.POLICY
                or record['manifest_sha256'] != manifest.sha256 or directory.name != manifest.generation
                or set(record['layers']) != {pack.sha256 for pack in manifest.packs}
                or any(not re.fullmatch(policy.SHA, value) for value in record['layers'].values())):
            raise ValueError('invalid installation metadata')
        validate_inventory(record['files'])
        if verify:
            verify_files(directory, record['files'], extras=('installation.json', 'manifest.json'))
            validate_layout(directory, record['files'])
        return Installation(directory, manifest, record)
    except (OSError, KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ValueError(f'Invalid managed installation: {exc}') from exc


def resolve(root):
    snapshot = load(root)
    return snapshot.directory if snapshot is not None else root
