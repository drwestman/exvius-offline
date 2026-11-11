"""Explicit sound commands; immutable file-backed generations, no engine imports."""
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile

from ios_server import sound_codec as codec, sound_inputs as inputs
from ios_server.runtime import InstanceLock, private_path

POINTER = 'assets/sounds/current.json'
SCOPE = 'native-sounds'
SHA = r'[a-f0-9]{64}'


def _relative(value):
    return (isinstance(value, str) and bool(value) and not PurePosixPath(value).is_absolute()
            and '..' not in PurePosixPath(value).parts and '\\' not in value)


def _sources(source):
    if (set(source) != {'pipeline', 'reference_commit', 'tables', 'banks', 'resources'}
            or type(source['pipeline']) is not int or source['pipeline'] < 1
            or source['reference_commit'] != inputs.REVIVAL_COMMIT
            or set(source['tables']) != {table.name for table in inputs.TABLES}
            or not source['banks'] or not source['resources']):
        raise ValueError('Invalid sound source inventory')
    for row in source['tables'].values():
        if (set(row) != {'path', 'version', 'sha256'} or not _relative(row['path'])
                or type(row['version']) is not int or row['version'] < 1 or not re.fullmatch(SHA, row['sha256'])):
            raise ValueError('Invalid sound table provenance')
    for target, row in source['banks'].items():
        if (not inputs.safe_bank(target) or set(row) != {'path', 'native', 'size', 'sha256'}
                or not _relative(row['path']) or type(row['native']) is not bool
                or type(row['size']) is not int or row['size'] < 1 or not re.fullmatch(SHA, row['sha256'])):
            raise ValueError('Invalid sound bank provenance')
        expected = target if row['native'] else target.replace('/ios/', '/android/')
        if not (row['path'] == expected or row['path'].endswith('/' + expected)):
            raise ValueError('Sound bank platform provenance disagrees')
    seen = set()
    for key, row in source['resources'].items():
        if (not re.fullmatch(r'F_RESOURCE(?:_MAP)?:[1-9][0-9]*', key)
                or set(row) != {'bank', 'version', 'ios_size', 'android_size'} or row['bank'] not in source['banks']
                or type(row['version']) is not int or row['version'] < 1
                or any(type(row[key]) is not int or row[key] < 0 for key in ('ios_size', 'android_size'))
                or not Path(row['bank']).name.startswith('Ver' + str(row['version']) + '_')):
            raise ValueError('Invalid sound resource provenance')
        seen.add(row['bank'])
    if seen != set(source['banks']):
        raise ValueError('Unreferenced sound bank')


@dataclass(frozen=True)
class Sounds:
    directory: Path
    manifest: dict

    def describe(self):
        rows = list(self.manifest['banks'].values())
        return {'ok': True, 'scope': SCOPE, 'prepared': True, 'generation': self.manifest['generation'],
                'directory': str(self.directory), 'banks': len(rows),
                'resources': len(self.manifest['sources']['resources']), 'bytes': sum(row['size'] for row in rows),
                **{name: sum(row[name] for row in rows) for name in ('waveforms', 'decrypted', 'reflagged')},
                'native_banks': sum(row['native'] for row in self.manifest['sources']['banks'].values()),
                'ios_size_updates': sum(row['ios_size'] != self.manifest['banks'][row['bank']]['size']
                                        for row in self.manifest['sources']['resources'].values()),
                'android_size_disagreements': sum(row['android_size'] != self.manifest['sources']['banks'][row['bank']]['size']
                                                  for row in self.manifest['sources']['resources'].values()
                                                  if not self.manifest['sources']['banks'][row['bank']]['native']),
                'delivery_ready': False, 'gameplay_ready': False}


def _bank(config, directory, entry, source):
    if (set(entry) != {'path', 'sha256', 'size', 'waveforms', 'decrypted', 'reflagged'}
            or not re.fullmatch(SHA, entry['sha256'])
            or entry['path'] != 'banks/' + entry['sha256'] + Path(source['path']).suffix
            or type(entry['size']) is not int or entry['size'] != source['size']
            or any(type(entry[key]) is not int or entry[key] < 0 for key in ('waveforms', 'decrypted', 'reflagged'))
            or max(entry['decrypted'], entry['reflagged']) > entry['waveforms']
            or source['native'] and (entry['sha256'] != source['sha256'] or entry['decrypted'] or entry['reflagged'])):
        raise ValueError('Invalid prepared sound identity')
    path = private_path(config.root, directory.relative_to(config.root) / entry['path'])
    if not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError('Sound bank escapes its generation')
    raw = path.read_bytes()
    if len(raw) != entry['size'] or inputs.digest(raw) != entry['sha256']:
        raise ValueError('Prepared sound checksum mismatch')
    if codec.validate(raw, native=source['native']) != entry['waveforms']:
        raise ValueError('Prepared sound waveform count disagrees')


def load(config):
    """Verify recorded output facts one bank at a time, without consulting sources."""
    pointer = private_path(config.root, POINTER)
    if not pointer.exists():
        if pointer.is_symlink():
            raise ValueError('Invalid sound snapshot pointer')
        return None
    try:
        ref = json.loads(pointer.read_bytes())
        if (set(ref) != {'version', 'directory', 'manifest_sha256'} or type(ref['version']) is not int
                or ref['version'] != 1 or not re.fullmatch(r'[0-9]{8}-' + SHA, ref['directory'])):
            raise ValueError('Invalid sound pointer')
        directory = private_path(config.root, Path(POINTER).parent / ref['directory'])
        raw = private_path(config.root, directory.relative_to(config.root) / 'manifest.json').read_bytes()
        if inputs.digest(raw) != ref['manifest_sha256']:
            raise ValueError('Sound manifest checksum mismatch')
        doc = json.loads(raw)
        if (set(doc) != {'version', 'scope', 'source_root', 'generation', 'fingerprint', 'sources', 'banks'}
                or type(doc['version']) is not int or doc['version'] != 1 or doc['scope'] != SCOPE
                or not isinstance(doc['source_root'], str) or not Path(doc['source_root']).is_absolute()
                or type(doc['generation']) is not int or not 1 <= doc['generation'] <= 99999999
                or not re.fullmatch(SHA, doc['fingerprint'])
                or doc['fingerprint'] != inputs.digest(inputs.encoded(doc['sources']))
                or ref['directory'] != f"{doc['generation']:08d}-{doc['fingerprint']}"
                or set(doc['banks']) != set(doc['sources']['banks'])):
            raise ValueError('Invalid sound manifest')
        _sources(doc['sources'])
        for target, entry in doc['banks'].items():
            _bank(config, directory, entry, doc['sources']['banks'][target])
        return Sounds(directory, doc)
    except (OSError, KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ValueError(f'Invalid sound snapshot: {exc}') from exc


def _current(config, snapshot):
    current = inputs.collect(config)
    if (snapshot.manifest['source_root'] != str(config.data)
            or snapshot.manifest['fingerprint'] != current.fingerprint
            or snapshot.manifest['sources'] != current.sources):
        raise ValueError('Sound inputs changed. Run prepare-sounds.')


def verify(config):
    """No locks, initialization, repair, conversion, cache writes or downloads."""
    try:
        snapshot = load(config)
        if snapshot is None:
            return {'ok': False, 'scope': SCOPE, 'prepared': False, 'gameplay_ready': False,
                    'error': 'No sound snapshot. Run prepare-sounds.'}
        _current(config, snapshot)
        return snapshot.describe()
    except (OSError, ValueError) as exc:
        return {'ok': False, 'scope': SCOPE, 'error': str(exc), 'gameplay_ready': False}


def _write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _publish(config, stage, doc):
    """The stage already contains validated files; replace the pointer last."""
    pointer = private_path(config.root, POINTER)
    identity = f"{doc['generation']:08d}-{doc['fingerprint']}"
    destination = private_path(config.root, pointer.parent.relative_to(config.root) / identity)
    raw = inputs.encoded(doc)
    _write(stage / 'manifest.json', raw)
    if destination.exists():
        # Reuse a fully built generation left by an interrupted pointer replacement.
        recorded = private_path(config.root, destination.relative_to(config.root) / 'manifest.json')
        if recorded.read_bytes() != raw:
            raise ValueError('Conflicting unpublished sound generation')
        for target, entry in doc['banks'].items():
            _bank(config, destination, entry, doc['sources']['banks'][target])
    else:
        os.replace(stage, destination)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.current-', dir=pointer.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(inputs.encoded({'version': 1, 'directory': identity, 'manifest_sha256': inputs.digest(raw)}))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, pointer)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return destination


def _build(config, stage, sources):
    banks = {}
    for target, source in sources['banks'].items():
        try:
            raw, facts = codec.prepare(inputs.read(config, source), native=source['native'])
            codec.validate(raw, native=source['native'])
        except ValueError as exc:
            raise ValueError(f'{target}: {exc}') from exc
        sha = inputs.digest(raw)
        entry = {'path': 'banks/' + sha + Path(source['path']).suffix, 'sha256': sha, 'size': len(raw), **facts}
        if len(raw) != source['size']:
            raise ValueError('Sound conversion changed the file length: ' + target)
        _write(stage / entry['path'], raw)
        banks[target] = entry
    return banks


def prepare(config):
    with InstanceLock(config.root):
        old = load(config)
        collected = inputs.collect(config)
        if old is not None and old.manifest['fingerprint'] == collected.fingerprint:
            if old.manifest['sources'] != collected.sources or old.manifest['source_root'] != str(config.data):
                raise ValueError('Invalid sound snapshot provenance')
            return {**old.describe(), 'prepared_now': False}
        generation = old.manifest['generation'] + 1 if old else 1
        if generation > 99999999:
            raise ValueError('Sound generation is out of range')
        pointer = private_path(config.root, POINTER)
        pointer.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        stage = Path(tempfile.mkdtemp(prefix='.building-', dir=pointer.parent))
        try:
            banks = _build(config, stage, collected.sources)
            if inputs.collect(config) != collected:
                raise ValueError('Sound inputs changed during preparation; retry prepare-sounds.')
            doc = {'version': 1, 'scope': SCOPE, 'source_root': str(config.data), 'generation': generation,
                   'fingerprint': collected.fingerprint, 'sources': collected.sources, 'banks': banks}
            destination = _publish(config, stage, doc)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        return {**Sounds(destination, doc).describe(), 'prepared_now': True}
