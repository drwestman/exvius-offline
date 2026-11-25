"""Coordinate native sound versions/sizes with immutable, file-backed artifacts."""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import re

from ios_server import native_tables as rules, sound_inputs, sound_snapshots, version_policy
from ios_server.runtime import private_path
from ios_server.table_codec import master_rows, patch_master
from ios_server.verified_blob import VerifiedBlob, VerifiedBlobSource, open_regular, verify_and_rewind

PIPELINE = 1


SoundSource = VerifiedBlobSource  # table_delivery needs queries only


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
    if previous is None:
        return generation
    by_identity = {}
    for path, row in previous['banks'].items():
        identity = versioned(path, 0)
        existing = by_identity.get(identity)
        if existing is None or row['version'] > existing.version:
            by_identity[identity] = version_policy.PriorArtifact(
                version=row['version'],
                sha256=row['sha256'],
                version_generation=row.get('version_generation', generation),
                managed=True,
            )
    pairs = []
    for path in inputs.snapshot.manifest['banks']:
        source = int(re.match(r'Ver([0-9]+)_', Path(path).name)[1])
        pairs.append((source, by_identity.get(versioned(path, 0))))
    return max(generation, version_policy.next_generation({'generation': generation - 1}, pairs))


def inventory(snapshot, generation, *, prior=None, include_generation=True):
    prior = prior or {}
    result = {}
    for source, bank in snapshot.manifest['banks'].items():
        base = int(re.match(r'Ver([0-9]+)_', Path(source).name)[1])
        identity = versioned(source, 0)
        resolved = version_policy.resolve_managed(
            base, bank['sha256'], prior.get(identity), generation, label='Native sound')
        entry = {'path': versioned(source, resolved.version), 'version': resolved.version,
                 'source_version': base, 'size': bank['size'], 'sha256': bank['sha256']}
        if include_generation:
            entry['version_generation'] = resolved.version_generation
        result[source] = entry
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


def prepare(inputs, generation, outputs, *, prior=None):
    banks = inventory(inputs.snapshot, generation, prior=prior)
    changes = _project(inputs.snapshot, banks, outputs)
    return {'snapshot': inputs.provenance['snapshot'], 'banks': banks}, changes


@dataclass(frozen=True)
class Delivery:
    root: Path
    snapshot: sound_snapshots.Sounds
    files: dict

    def _open(self, entry):
        path = private_path(self.root, self.snapshot.directory.relative_to(self.root) / entry['path'])
        if not path.resolve().is_relative_to(self.snapshot.directory.resolve()):
            raise ValueError('Sound bank escapes its generation')
        return open_regular(path)

    def _entry(self, relative):
        source = self.files.get(relative)
        return None if source is None else self.snapshot.manifest['banks'][source]

    def verified_size(self, relative):
        """Verify in bounded chunks without retaining a body or caching integrity."""
        with self.open_verified(relative) as opened:
            return None if opened is None else opened.size

    @contextmanager
    def open_verified(self, relative):
        """Verify then rewind the same descriptor for bounded, exact-byte delivery.

        The descriptor stays open through the response, so no second pathname is
        resolved and no bank is held in memory. Integrity is proven before headers;
        the generation directory is private, so later writers are out of scope.
        """
        entry = self._entry(relative)
        if entry is None:
            yield None
            return
        with self._open(entry) as stream:
            verify_and_rewind(stream, entry['size'], entry['sha256'], 'Prepared sound checksum mismatch')
            yield VerifiedBlob(stream, entry['size'])


def load(config, manifest, outputs):
    """Load the pinned generation, never the mutable current sound pointer."""
    binding, provenance = manifest['sounds'], manifest['sources']['sound']
    if (set(binding) != {'snapshot', 'banks'} or set(provenance) != {'pipeline', 'snapshot'}
            or type(provenance['pipeline']) is not int or provenance['pipeline'] < 1
            or binding['snapshot'] != provenance['snapshot']):
        raise ValueError('Invalid native sound binding')
    snapshot = sound_snapshots.load(config, reference=binding['snapshot'])
    if (snapshot.manifest['source_root'] != manifest['source_root']
            or manifest['preparation']['sound'] != coverage(snapshot)):
        raise ValueError('Invalid native sound inventory or provenance')
    if manifest['version'] < 6:
        if binding['banks'] != inventory(snapshot, manifest['generation'], include_generation=False):
            raise ValueError('Invalid native sound inventory or provenance')
    else:
        if set(binding['banks']) != set(snapshot.manifest['banks']):
            raise ValueError('Invalid native sound inventory or provenance')
        if len({row['path'] for row in binding['banks'].values()}) != len(binding['banks']):
            raise ValueError('Conflicting prepared sound paths')
        for source, entry in binding['banks'].items():
            bank = snapshot.manifest['banks'][source]
            base = int(re.match(r'Ver([0-9]+)_', Path(source).name)[1])
            if (not isinstance(entry, dict)
                    or set(entry) != {'path', 'version', 'source_version', 'version_generation', 'size', 'sha256'}
                    or entry['source_version'] != base
                    or entry['size'] != bank['size']
                    or entry['sha256'] != bank['sha256']
                    or entry['path'] != versioned(source, entry['version'])):
                raise ValueError('Invalid native sound bank entry: ' + source)
            version_policy.validate_version(
                entry['version'], entry['version_generation'], base,
                manifest['generation'], label='Native sound')
    for table in sound_inputs.TABLES:
        if snapshot.manifest['sources']['tables'][table.name] != manifest['sources']['tables'][table.name]:
            raise ValueError('Native and sound table provenance disagree: ' + table.name)
    _project(snapshot, binding['banks'], outputs, verify=True)
    return Delivery(config.root, snapshot, {row['path']: source for source, row in binding['banks'].items()})
