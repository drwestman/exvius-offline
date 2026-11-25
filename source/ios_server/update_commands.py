"""Explicit update orchestration (CQRS command side): stop -> apply -> normalize -> prepare -> verify."""
from pathlib import Path
import sys
from types import SimpleNamespace
import urllib.request

from ios_server import (
    banner_snapshots,
    commands,
    home_banners,
    pack_manifest,
    preparation,
    sound_snapshots,
)
from ios_server.update_layouts import AutoLayoutWriter
from ios_server.update_normalize import DefaultCompatibilityNormalizer
from ios_server.update_queries import UpdateQueryHandler
from ios_server.update_types import (
    CompatibilityNormalizer,
    DataLayoutWriter,
    SnapshotCheck,
    SnapshotPreparer,
)


def _default_emit(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _default_stop(config) -> dict:
    return commands.lifecycle(config, SimpleNamespace(command='stop'))


class DefaultSnapshotPreparer:
    """Dependency-ordered snapshot preparation: sounds -> banners -> home_banners -> data."""

    def prepare_stale(
        self,
        config,
        checks: dict[str, SnapshotCheck],
        *,
        force_data: bool = False,
        emit=_default_emit,
    ) -> dict:
        prepared = {}
        skipped = []
        sounds_changed = False

        for name, fn in (
            ('sounds', lambda: sound_snapshots.prepare(config)),
            ('banners', lambda: banner_snapshots.prepare(config)),
            ('home_banners', lambda: home_banners.prepare(config)),
        ):
            check = checks.get(name)
            if check is not None and check.ok:
                skipped.append(name)
                continue
            emit(f'[update] preparing {name}')
            res = fn()
            prepared[name] = res
            if name == 'sounds' and res.get('prepared_now', True):
                sounds_changed = True

        data_check = checks.get('data')
        if force_data or sounds_changed or data_check is None or not data_check.ok:
            emit('[update] preparing data (vortex-art, sounds)')
            prepared['data'] = preparation.prepare_data(config, vortex_art=True, sounds=True)
        else:
            skipped.append('data')

        return {'prepared': prepared, 'skipped': skipped}


class UpdateCommandHandler:
    """Orchestrates explicit updates while delegating queries, layouts, normalization, and snapshots."""

    def __init__(
        self,
        query_handler: UpdateQueryHandler | None = None,
        service_stopper=None,
        layout_writer: DataLayoutWriter | None = None,
        compat_normalizer: CompatibilityNormalizer | None = None,
        snapshot_preparer: SnapshotPreparer | None = None,
    ):
        self._query_handler = query_handler or UpdateQueryHandler()
        self._service_stopper = service_stopper or _default_stop
        self._layout_writer = layout_writer or AutoLayoutWriter()
        self._compat_normalizer = compat_normalizer or DefaultCompatibilityNormalizer()
        self._snapshot_preparer = snapshot_preparer or DefaultSnapshotPreparer()

    def execute(
        self,
        config,
        manifest_path: Path = pack_manifest.DEFAULT,
        *,
        archive_dir: Path | None = None,
        opener=urllib.request.urlopen,
        emit=_default_emit,
    ) -> dict:
        manifest_path = Path(manifest_path)
        self._service_stopper(config)

        initial = self._query_handler.check(config, manifest_path)
        if not initial.get('ok'):
            return {**initial, 'ok': False, 'updated_now': False}
        if not initial.get('update_needed'):
            return {**initial, 'ok': True, 'updated_now': False}

        pack_result = None
        packs_changed = False
        if initial.get('packs_needed') or not initial.get('layout_valid', True):
            emit('[update] applying data packs')
            pack_result = self._layout_writer.apply(
                config,
                manifest_path,
                archive_dir=archive_dir,
                opener=opener,
                emit=emit,
            )
            packs_changed = bool(pack_result.get('installed_now') or pack_result.get('updated_packs'))

        norm_result = None
        norm_changed = False
        post_pack_status = self._query_handler.check(config, manifest_path) if packs_changed else initial
        if post_pack_status.get('normalization', {}).get('any_needed') or packs_changed:
            if post_pack_status.get('normalization', {}).get('any_needed'):
                emit('[update] normalizing iOS compatibility invariants')
            norm_result = self._compat_normalizer.normalize(config)
            norm_changed = bool(norm_result.get('normalized_now'))

        # Re-read snapshot verification after pack/normalization changes so newly stale snapshots are rebuilt.
        current_status = self._query_handler.check(config, manifest_path)
        if not current_status.get('ok'):
            return {**current_status, 'ok': False, 'updated_now': True}

        checks = {
            name: SnapshotCheck(name=name, ok=bool(row.get('ok')), error=row.get('error'))
            for name, row in current_status.get('snapshots', {}).items()
        }
        if isinstance(self._snapshot_preparer, DefaultSnapshotPreparer):
            snap_result = self._snapshot_preparer.prepare_stale(
                config,
                checks,
                force_data=bool(packs_changed or norm_changed),
                emit=emit,
            )
        else:
            snap_result = self._snapshot_preparer.prepare_stale(config, checks, emit=emit)

        final = self._query_handler.check(config, manifest_path)
        failed_gates = [
            f"{name}: {row.get('error') or 'failed'}"
            for name, row in final.get('snapshots', {}).items()
            if not row.get('ok')
        ]
        if not final.get('ok') or failed_gates or final.get('update_needed'):
            detail = '; '.join(failed_gates) if failed_gates else '; '.join(final.get('reasons', ()))
            return {
                **final,
                'ok': False,
                'updated_now': True,
                'packs_result': pack_result,
                'normalization_result': norm_result,
                'snapshots_result': snap_result,
                'error': final.get('error') or detail or 'Final update verification failed',
            }

        return {
            **final,
            'ok': True,
            'updated_now': True,
            'packs_result': pack_result,
            'normalization_result': norm_result,
            'snapshots_result': snap_result,
        }


def run_update(
    config,
    manifest_path: Path = pack_manifest.DEFAULT,
    *,
    archive_dir: Path | None = None,
    opener=urllib.request.urlopen,
    emit=_default_emit,
) -> dict:
    """Default update command entrypoint."""
    return UpdateCommandHandler().execute(
        config,
        manifest_path,
        archive_dir=archive_dir,
        opener=opener,
        emit=emit,
    )
