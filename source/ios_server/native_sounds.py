"""Coordinate native sound versions/sizes with immutable, file-backed artifacts."""
from dataclasses import dataclass
import os
from pathlib import Path
import re

from ios_server import native_tables as rules, sound_inputs, sound_snapshots
from ios_server.runtime import private_path
from ios_server.table_codec import master_rows, patch_master

PIPELINE = 1


def owns(relative):
    # Claim the whole iOS sound namespace, including unknown/stale filenames.
    return relative.startswith('common_lang/sound/') and '/ios/' in relative


def versioned(path, version):
    return str(Path(path).with_name(re.sub(r'^Ver[0-9]+_', f'Ver{version}_', Path(path).name)))


def reference(snapshot):
    return {'version': 1, 'directory': snapshot.directory.name,
            'manifest_sha256': sound_inputs.digest(sound_inputs.encoded(snapshot.manifest))}


def coverage(snapshot):
    rows = snapshot.manifest['banks']
    return {'banks': len(rows), 'resources': len(snapshot.manifest['sources']['resources']),
            'bytes': sum(row['size'] for row in rows.values())}


@dataclass(frozen=True)
class Inputs:
    snapshot: sound_snapshots.Sounds
    provenance: dict
    coverage: dict


def collect(config, sources):
    """Bind original table facts to a current explicit sound preparation."""
    snapshot = sound_snapshots.current(config)
    for table in sound_inputs.TABLES:
        source = snapshot.manifest['sources']['tables'][table.name]
        version, raw = sources[table.name]
        if version != source['version'] or sound_inputs.digest(raw) != source['sha256']:
            raise ValueError('Native and sound source tables disagree. Run prepare-sounds: ' + table.name)
    return Inputs(snapshot, {'pipeline': PIPELINE, 'snapshot': reference(snapshot)}, coverage(snapshot))


def advance(generation, inputs, previous):
    """Keep client file identities monotonic even when source versions decrease."""
    if previous is not None:
        old = previous['banks']
        by_identity = {}
        for path, row in old.items():
            identity = versioned(path, 0)
            by_identity[identity] = max(by_identity.get(identity, 0), row['version'])
        for path in inputs.snapshot.manifest['banks']:
            prior = by_identity.get(versioned(path, 0))
            if prior is not None:
                source = int(re.match(r'Ver([0-9]+)_', Path(path).name)[1])
                generation = max(generation, (prior - source - rules.VERSION_OFFSET) // rules.VERSION_STEP + 1)
    return generation


def inventory(snapshot, generation):
    result = {}
    for source, bank in snapshot.manifest['banks'].items():
        base = int(re.match(r'Ver([0-9]+)_', Path(source).name)[1])
        version = base + rules.VERSION_OFFSET + generation * rules.VERSION_STEP
        if version > 2147483647:
            raise ValueError('Native sound version generation is out of range.')
        result[source] = {'path': versioned(source, version), 'version': version,
                          'source_version': base, 'size': bank['size'], 'sha256': bank['sha256']}
    if len({row['path'] for row in result.values()}) != len(result):
        raise ValueError('Conflicting prepared sound paths')
    return result


def _project(snapshot, banks, outputs, *, verify=False):
    """Only common file versions and iOS sizes change; retain every other field."""
    resources = snapshot.manifest['sources']['resources']
    changes = {}
    for prefix, id_column in sound_inputs.FAMILIES:
        wanted = {key.split(':')[1]: banks[row['bank']] for key, row in resources.items() if key.startswith(prefix + ':')}
        for suffix, field, value in (('_MST', None, None), ('_VERSION_MST_LOCALIZE', 'OzT5lSz3', 'version'),
                                      ('_CHECKSUM_MST', 'JwbkKrjA', 'size')):
            table = rules.BY_NAME[prefix + suffix]
            seen = set()
            def update(row):
                identity = row.get(id_column)
                if identity in wanted:
                    if identity in seen:
                        raise ValueError('Duplicate prepared sound resource: ' + table.name)
                    seen.add(identity)
                    if field is not None:
                        expected = str(wanted[identity][value])
                        if verify and row.get(field) != expected:
                            raise ValueError('Sound table disagrees with prepared bank: ' + table.name)
                        row[field] = expected
                    else:
                        path = f"common_lang/{row.get('3LHdc6Qa')}/ios/Ver{wanted[identity]['source_version']}_{row.get('pJ56sAEo')}"
                        if path not in banks or wanted[identity] != banks[path]:
                            raise ValueError('Sound resource path disagrees with prepared bank: ' + table.name)
                elif suffix == '_MST' and str(row.get('3LHdc6Qa', '')).startswith('sound/'):
                    raise ValueError('Unbound sound resource: ' + table.name)
                return row
            raw, count = patch_master(outputs[table.name], table.key, update, mode=table.cipher)
            if seen != set(wanted):
                raise ValueError('Missing prepared sound resource rows: ' + table.name)
            if not verify:
                outputs[table.name] = raw
            changes[table.name] = count
    return changes


def prepare(inputs, generation, outputs):
    banks = inventory(inputs.snapshot, generation)
    changes = _project(inputs.snapshot, banks, outputs)
    return {'snapshot': inputs.provenance['snapshot'], 'banks': banks}, changes


@dataclass(frozen=True)
class Delivery:
    root: Path
    snapshot: sound_snapshots.Sounds
    files: dict

    def read(self, relative):
        """Read one pinned bank; recheck containment and integrity before any reply."""
        source = self.files.get(relative)
        if source is None:
            return None
        entry = self.snapshot.manifest['banks'][source]
        path = private_path(self.root, self.snapshot.directory.relative_to(self.root) / entry['path'])
        if not path.resolve().is_relative_to(self.snapshot.directory.resolve()):
            raise ValueError('Sound bank escapes its generation')
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, 'rb') as stream:
            raw = stream.read(entry['size'] + 1)
        if len(raw) != entry['size'] or sound_inputs.digest(raw) != entry['sha256']:
            raise ValueError('Prepared sound checksum mismatch')
        return raw


def load(config, manifest, outputs):
    """Load the pinned generation, never the mutable current sound pointer."""
    binding, provenance = manifest['sounds'], manifest['sources']['sound']
    if (set(binding) != {'snapshot', 'banks'} or set(provenance) != {'pipeline', 'snapshot'}
            or type(provenance['pipeline']) is not int or provenance['pipeline'] < 1
            or binding['snapshot'] != provenance['snapshot']):
        raise ValueError('Invalid native sound binding')
    snapshot = sound_snapshots.load(config, reference=binding['snapshot'])
    if (snapshot.manifest['source_root'] != manifest['source_root']
            or manifest['preparation']['sound'] != coverage(snapshot)
            or binding['banks'] != inventory(snapshot, manifest['generation'])):
        raise ValueError('Invalid native sound inventory or provenance')
    for table in sound_inputs.TABLES:
        if snapshot.manifest['sources']['tables'][table.name] != manifest['sources']['tables'][table.name]:
            raise ValueError('Native and sound table provenance disagree: ' + table.name)
    _project(snapshot, binding['banks'], outputs, verify=True)
    return Delivery(config.root, snapshot, {row['path']: source for source, row in binding['banks'].items()})
