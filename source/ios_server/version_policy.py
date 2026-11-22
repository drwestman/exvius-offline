"""Pure monotonic version resolution and schema-6 validation rules.

No filesystem or engine imports.
"""
from dataclasses import dataclass
from pathlib import PurePosixPath
import re

VERSION_OFFSET = 200000
VERSION_STEP = 10000
MAX_VERSION = 2147483647
MAX_GENERATION = 99999999


@dataclass(frozen=True)
class PriorArtifact:
    version: int
    sha256: str
    version_generation: int
    managed: bool = True


@dataclass(frozen=True)
class ResolvedVersion:
    version: int
    version_generation: int
    reused: bool
    managed: bool


@dataclass(frozen=True)
class ArtifactDecisionSummary:
    reused: int
    bumped: int
    stock: int = 0


def _unversioned_name(path: str) -> str:
    parsed = PurePosixPath(path)
    return str(parsed.with_name(re.sub(r'^Ver[0-9]+_', 'Ver0_', parsed.name)))


def _source_version_from_path(path: str) -> int:
    match = re.match(r'^Ver([0-9]+)_', PurePosixPath(path).name)
    if match is None:
        raise ValueError('Invalid versioned artifact path: ' + str(path))
    value = int(match[1])
    if value < 1:
        raise ValueError('Artifact source version must be positive: ' + str(path))
    return value


def check_bounds(floor: int, generation: int, *, label: str = 'Native') -> int:
    """Validate floor/generation and return the candidate minted version."""
    if type(floor) is not int or floor < 1:
        raise ValueError(f'{label} source version is out of range.')
    if type(generation) is not int or not 1 <= generation <= MAX_GENERATION:
        raise ValueError(f'{label} version generation is out of range.')
    candidate = floor + VERSION_OFFSET + generation * VERSION_STEP
    if candidate > MAX_VERSION:
        raise ValueError(f'{label} version generation is out of range.')
    return candidate


def next_generation(current_manifest: dict | None, floor_prior_pairs) -> int:
    """Compute the smallest generation strictly advancing above every managed prior artifact."""
    generation = current_manifest['generation'] + 1 if current_manifest is not None else 1
    for floor, prior in floor_prior_pairs:
        if prior is not None and prior.managed:
            if floor + VERSION_OFFSET + generation * VERSION_STEP <= prior.version:
                generation = max(generation, (prior.version - floor - VERSION_OFFSET) // VERSION_STEP + 1)
    return generation


def resolve_managed(floor: int, output_sha256: str, prior: PriorArtifact | None, generation: int,
                    *, label: str = 'Native') -> ResolvedVersion:
    """Carry forward an unchanged managed artifact's version, or bump monotonically."""
    candidate = check_bounds(floor, generation, label=label)
    if (prior is not None and prior.managed and output_sha256 == prior.sha256
            and prior.version >= floor and prior.version >= VERSION_OFFSET + VERSION_STEP):
        return ResolvedVersion(prior.version, prior.version_generation, reused=True, managed=True)
    if prior is not None and candidate <= prior.version:
        raise ValueError(f'{label} candidate version failed monotonicity.')
    return ResolvedVersion(candidate, generation, reused=False, managed=True)


def resolve_upfront(source_version: int, size: int, advertised: int, sha256: str,
                    prior: PriorArtifact | None, generation: int) -> ResolvedVersion:
    """Resolve an upfront CPK to carried-forward bumped, newly bumped, or stock version."""
    if type(source_version) is not int or source_version < 1:
        raise ValueError('Upfront CPK source version must be positive.')
    if (prior is not None and prior.managed and sha256 == prior.sha256
            and prior.version >= source_version and prior.version >= VERSION_OFFSET + VERSION_STEP):
        return ResolvedVersion(prior.version, prior.version_generation, reused=True, managed=True)
    needs_bump = (
        size != advertised
        or (prior is not None and sha256 != prior.sha256)
        or (prior is not None and prior.managed and prior.version < source_version)
    )
    if needs_bump:
        candidate = check_bounds(source_version, generation, label='Upfront CPK')
        if prior is not None and candidate <= prior.version:
            raise ValueError('Upfront CPK candidate version failed monotonicity.')
        return ResolvedVersion(candidate, generation, reused=False, managed=True)
    return ResolvedVersion(source_version, version_generation=0, reused=True, managed=False)


def validate_version(version: int, version_generation: int, floor: int, manifest_generation: int,
                     *, label: str = 'Native') -> None:
    """Validate a schema-6 version and version_generation against current floor and generation."""
    if type(version) is not int or not 1 <= version <= MAX_VERSION:
        raise ValueError(f'Invalid {label} version.')
    if type(version_generation) is not int or not 1 <= version_generation <= manifest_generation:
        raise ValueError(f'Invalid {label} version generation.')
    if type(floor) is not int or floor < 1:
        raise ValueError(f'Invalid {label} version floor.')
    if version < floor or version < VERSION_OFFSET + VERSION_STEP:
        raise ValueError(f'{label} version is below floor.')
    if version_generation == manifest_generation:
        expected = check_bounds(floor, manifest_generation, label=label)
        if version != expected:
            raise ValueError(f'{label} version disagrees with generation formula.')


def prior_tables(manifest: dict | None) -> dict[str, PriorArtifact]:
    """Extract PriorArtifact descriptors for all tables from a schema 1-6 manifest."""
    if manifest is None:
        return {}
    generation = manifest['generation']
    return {
        name: PriorArtifact(
            version=entry['version'],
            sha256=entry['sha256'],
            version_generation=entry.get('version_generation', generation),
            managed=True,
        )
        for name, entry in manifest.get('tables', {}).items()
    }


def prior_pack(manifest: dict | None, name: str = 'spdungeon1.cpk') -> PriorArtifact | None:
    """Extract PriorArtifact for a prepared Vortex pack from a schema 4-6 manifest."""
    if manifest is None or name not in manifest.get('packs', {}):
        return None
    entry = manifest['packs'][name]
    return PriorArtifact(
        version=entry['version'],
        sha256=entry['sha256'],
        version_generation=entry.get('version_generation', manifest['generation']),
        managed=True,
    )


def prior_sounds(manifest: dict | None) -> dict[str, PriorArtifact]:
    """Extract PriorArtifact descriptors for sound banks keyed by unversioned bank path."""
    if manifest is None or 'sounds' not in manifest:
        return {}
    generation = manifest['generation']
    result = {}
    for source, entry in manifest['sounds'].get('banks', {}).items():
        identity = _unversioned_name(source)
        existing = result.get(identity)
        if existing is None or entry['version'] > existing.version:
            result[identity] = PriorArtifact(
                version=entry['version'],
                sha256=entry['sha256'],
                version_generation=entry.get('version_generation', generation),
                managed=True,
            )
    return result


def prior_upfront(manifest: dict | None) -> dict[str, PriorArtifact]:
    """Extract PriorArtifact descriptors for upfront CPKs from a schema 3-6 manifest."""
    if manifest is None:
        return {}
    upfront_files = manifest.get('sources', {}).get('upfront', {}).get('files', {})
    upfront_packs = manifest.get('upfront_packs', {})
    result = {}
    for key, row in upfront_files.items():
        if key in upfront_packs:
            entry = upfront_packs[key]
            result[key] = PriorArtifact(
                version=entry['version'],
                sha256=entry['sha256'],
                version_generation=entry['version_generation'],
                managed=True,
            )
        else:
            source_version = row['source_version'] if 'source_version' in row else _source_version_from_path(row['path'])
            result[key] = PriorArtifact(
                version=source_version,
                sha256=row['sha256'],
                version_generation=0,
                managed=False,
            )
    return result


def summarize(decisions) -> ArtifactDecisionSummary:
    """Count reused, bumped, and stock decisions from an iterable of ResolvedVersion."""
    reused = bumped = stock = 0
    for decision in decisions:
        if not decision.managed:
            stock += 1
        elif decision.reused:
            reused += 1
        else:
            bumped += 1
    return ArtifactDecisionSummary(reused=reused, bumped=bumped, stock=stock)
