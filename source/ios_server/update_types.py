"""Contracts, DTOs, and segregated read/write protocols for the iOS data updater."""
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Protocol
import urllib.request


@dataclass(frozen=True)
class PackDelta:
    """One pack missing or changed relative to the installed layout receipt."""
    id: str
    url: str
    size: int
    unpacked_size: int
    sha256: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LayoutInspection:
    """Read-only inspection of the installed data layout against a release manifest."""
    layout: str
    installed_version: str | None
    target_version: str | None
    target_revision: int | None
    packs_needed: tuple[PackDelta, ...]
    download_bytes: int
    unpacked_bytes: int
    valid: bool
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            'layout': self.layout,
            'installed_version': self.installed_version,
            'target_version': self.target_version,
            'target_revision': self.target_revision,
            'packs_needed': [pack.to_dict() for pack in self.packs_needed],
            'download_bytes': self.download_bytes,
            'unpacked_bytes': self.unpacked_bytes,
            'valid': self.valid,
            'error': self.error,
        }


@dataclass(frozen=True)
class NormalizationReport:
    """Read-only compatibility audit for post-extract Android/iOS pack invariants."""
    unregistered_mst_files: tuple[str, ...]
    localized_index_mismatches: tuple[str, ...]
    registry_sync_needed: bool
    error: str | None = None

    @property
    def any_needed(self) -> bool:
        return bool(self.unregistered_mst_files or self.localized_index_mismatches or self.registry_sync_needed)

    def to_dict(self) -> dict:
        return {
            'unregistered_mst_files': list(self.unregistered_mst_files),
            'localized_index_mismatches': list(self.localized_index_mismatches),
            'registry_sync_needed': self.registry_sync_needed,
            'any_needed': self.any_needed,
            'error': self.error,
        }


@dataclass(frozen=True)
class SnapshotCheck:
    """Read-only result from one of the four prepared snapshot verifiers."""
    name: str
    ok: bool
    error: str | None = None

    def to_dict(self) -> dict:
        return {'name': self.name, 'ok': self.ok, 'error': self.error}


@dataclass(frozen=True)
class UpdateStatus:
    """Aggregated read-only update status returned by UpdateQueryHandler."""
    ok: bool
    update_needed: bool
    layout: str
    installed_version: str | None
    target_version: str | None
    target_revision: int | None
    packs_needed: tuple[PackDelta, ...]
    download_bytes: int
    unpacked_bytes: int
    normalization: NormalizationReport
    snapshots: dict[str, SnapshotCheck]
    reasons: tuple[str, ...]
    recommended_command: str
    layout_valid: bool = True
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            'ok': self.ok,
            'update_needed': self.update_needed,
            'layout': self.layout,
            'layout_valid': self.layout_valid,
            'installed_version': self.installed_version,
            'target_version': self.target_version,
            'target_revision': self.target_revision,
            'packs_needed': [pack.to_dict() for pack in self.packs_needed],
            'download_bytes': self.download_bytes,
            'unpacked_bytes': self.unpacked_bytes,
            'normalization': self.normalization.to_dict(),
            'snapshots': {name: check.to_dict() for name, check in self.snapshots.items()},
            'reasons': list(self.reasons),
            'recommended_command': self.recommended_command,
            'error': self.error,
        }


class DataLayoutReader(Protocol):
    """Read-only layout inspection contract."""
    def inspect(self, config, manifest_path: Path) -> LayoutInspection: ...


class DataLayoutWriter(Protocol):
    """Mutating layout installation/update contract."""
    def apply(
        self,
        config,
        manifest_path: Path,
        *,
        archive_dir: Path | None = None,
        opener: Callable = urllib.request.urlopen,
        emit: Callable[[str], None] = ...,
    ) -> dict: ...


class CompatibilityInspector(Protocol):
    """Read-only post-extract iOS compatibility audit contract."""
    def inspect(self, config) -> NormalizationReport: ...


class CompatibilityNormalizer(Protocol):
    """Mutating post-extract iOS compatibility normalizer contract."""
    def normalize(self, config) -> dict: ...


class SnapshotVerifier(Protocol):
    """Read-only verification across all prepared iOS snapshot gates."""
    def verify_all(self, config) -> dict[str, SnapshotCheck]: ...


class SnapshotPreparer(Protocol):
    """Mutating preparation for stale or missing iOS snapshot gates."""
    def prepare_stale(
        self,
        config,
        checks: dict[str, SnapshotCheck],
        *,
        emit: Callable[[str], None] = ...,
    ) -> dict: ...
