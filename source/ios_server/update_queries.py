"""Read-only update detection (CQRS query side): zero writes, zero network, zero locks."""
from pathlib import Path

from ios_server import banner_snapshots, home_banners, pack_manifest, preparation, sound_snapshots
from ios_server.update_layouts import AutoLayoutReader, detect_layout
from ios_server.update_normalize import DefaultCompatibilityInspector
from ios_server.update_types import (
    CompatibilityInspector,
    DataLayoutReader,
    NormalizationReport,
    SnapshotCheck,
    SnapshotVerifier,
    UpdateStatus,
)


class DefaultSnapshotVerifier:
    """Runs all four read-only prepared snapshot verifiers."""

    def verify_all(self, config) -> dict[str, SnapshotCheck]:
        checks = {}
        for name, verifier in (
            ('sounds', sound_snapshots.verify),
            ('banners', banner_snapshots.verify),
            ('home_banners', home_banners.verify),
            ('data', preparation.verify_data),
        ):
            try:
                res = verifier(config)
                checks[name] = SnapshotCheck(name=name, ok=bool(res.get('ok')), error=res.get('error'))
            except (OSError, ValueError, RuntimeError) as exc:
                checks[name] = SnapshotCheck(name=name, ok=False, error=str(exc))
        return checks


class UpdateQueryHandler:
    """Aggregates read-only layout, compatibility, and snapshot status checks."""

    def __init__(
        self,
        layout_reader: DataLayoutReader | None = None,
        compat_inspector: CompatibilityInspector | None = None,
        snapshot_verifier: SnapshotVerifier | None = None,
    ):
        self._layout_reader = layout_reader or AutoLayoutReader()
        self._compat_inspector = compat_inspector or DefaultCompatibilityInspector()
        self._snapshot_verifier = snapshot_verifier or DefaultSnapshotVerifier()

    def check(self, config, manifest_path: Path = pack_manifest.DEFAULT) -> dict:
        recommended = f'python3 source/exvius/macos_ios_server.py update --data "{config.data_root}"'
        try:
            layout = self._layout_reader.inspect(config, Path(manifest_path))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            empty_norm = NormalizationReport((), (), False)
            return UpdateStatus(
                ok=False,
                update_needed=False,
                layout=detect_layout(config),
                installed_version=None,
                target_version=None,
                target_revision=None,
                packs_needed=(),
                download_bytes=0,
                unpacked_bytes=0,
                normalization=empty_norm,
                snapshots={},
                reasons=(str(exc),),
                recommended_command=recommended,
                layout_valid=False,
                error=str(exc),
            ).to_dict()

        normalization = self._compat_inspector.inspect(config)
        snapshots = self._snapshot_verifier.verify_all(config)

        reasons = []
        if layout.packs_needed:
            mb = layout.download_bytes / (1024 * 1024)
            reasons.append(f'{len(layout.packs_needed)} data pack(s) need update ({mb:.1f} MiB download)')
        elif not layout.valid:
            reasons.append(layout.error or 'Installed data layout needs refresh')

        if normalization.unregistered_mst_files:
            reasons.append(f'{len(normalization.unregistered_mst_files)} unregistered mst .dat file(s) need pruning')
        if normalization.localized_index_mismatches:
            reasons.append('Localized text index checksum mismatch: ' + ', '.join(normalization.localized_index_mismatches))
        if normalization.registry_sync_needed:
            reasons.append('Registry gamedata.xml needs sync with registry.json')
        if normalization.error:
            reasons.append('Compatibility inspection error: ' + normalization.error)

        for name, check in snapshots.items():
            if not check.ok:
                reasons.append(f"Snapshot '{name}' is stale or missing: {check.error or 'verification failed'}")

        update_needed = bool(
            layout.packs_needed
            or not layout.valid
            or normalization.any_needed
            or normalization.error
            or any(not s.ok for s in snapshots.values())
        )
        return UpdateStatus(
            ok=True,
            update_needed=update_needed,
            layout=layout.layout,
            installed_version=layout.installed_version,
            target_version=layout.target_version,
            target_revision=layout.target_revision,
            packs_needed=layout.packs_needed,
            download_bytes=layout.download_bytes,
            unpacked_bytes=layout.unpacked_bytes,
            normalization=normalization,
            snapshots=snapshots,
            reasons=tuple(reasons),
            recommended_command=recommended,
            layout_valid=layout.valid,
            error=None,
        ).to_dict()


def format_summary(status: dict) -> str:
    """Format compact human-readable reasons for stderr/launcher display."""
    if not status.get('ok'):
        return f"iOS update check failed: {status.get('error') or 'unknown error'}"
    if not status.get('update_needed'):
        return f"iOS data is up to date ({status.get('layout')} layout, version {status.get('target_version')})."
    lines = [
        f"iOS data update needed ({status.get('layout')} layout -> {status.get('target_version')}):"
    ]
    for reason in status.get('reasons', ()):
        lines.append('  - ' + reason)
    return '\n'.join(lines)


def check_update(config, manifest_path: Path = pack_manifest.DEFAULT) -> dict:
    """Default read-only update query entrypoint."""
    return UpdateQueryHandler().check(config, manifest_path)
