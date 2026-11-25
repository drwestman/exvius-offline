"""Pluggable data layout detection and read/write strategies for flat and managed trees."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Literal
import urllib.request
from urllib.parse import urlsplit
import zipfile

from ios_server import managed_content as content, pack_download, pack_install, pack_layers, pack_manifest as policy
from ios_server.runtime import InstanceLock
from ios_server.update_normalize import normalize_managed_stage
from ios_server.update_types import LayoutInspection, PackDelta

DAT_NAME = re.compile(r'Ver([0-9]+)_([A-Za-z0-9]{8})\.dat')


def detect_layout(config) -> Literal['managed', 'flat', 'uninstalled']:
    """Auto-detect the layout from --data without writing to disk."""
    root = config.data_root
    pointer = root / content.POINTER
    if pointer.exists() or pointer.is_symlink():
        return 'managed'
    flat_markers = (
        root / 'client/shared_prefs/gamedata.xml',
        root / '.web_setup/installed.json',
        root / 'client/files',
        root / 'mst_decoded',
    )
    if any(marker.exists() or marker.is_symlink() for marker in flat_markers):
        return 'flat'
    return 'uninstalled'


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(payload, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.' + path.name + '.', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _parse_flat_manifest(manifest_path: Path) -> tuple[dict, tuple[policy.Pack, ...]]:
    path = Path(manifest_path)
    raw = path.read_bytes()
    doc = json.loads(raw)
    if (type(doc.get('schema')) is not int or doc['schema'] != 1
            or type(doc.get('revision')) is not int or doc['revision'] < 1
            or not isinstance(doc.get('version'), str) or not doc['version']
            or not isinstance(doc.get('packs'), list) or not doc['packs']):
        raise ValueError('Invalid release manifest')
    packs, ids = [], set()
    for row in doc['packs']:
        identity = row['id']
        if (not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', identity)
                or identity in ids or not policy.web_url(row['url'])
                or type(row['size']) is not int or row['size'] < 1
                or type(row['unpackedSize']) is not int or row['unpackedSize'] < 0
                or not re.fullmatch(policy.SHA, row['sha256'])):
            raise ValueError('Invalid or duplicate data pack in release manifest')
        ids.add(identity)
        packs.append(policy.Pack(identity, row['url'], row['size'], row['unpackedSize'], row['sha256']))
    return doc, tuple(packs)


def _flat_destination(name: str, pack_id: str) -> str:
    """Map release pack ZIP paths into the flat browser-data tree."""
    if name == 'static/client/game-assets.apk' and pack_id == 'client-assets':
        return 'client/game-assets.apk'
    mapped = policy.destination(name)
    if mapped == 'registry.json':
        return 'registry.json'
    if mapped.startswith('static/'):
        return mapped[len('static/'):]
    if mapped.startswith('native/'):
        return 'client/files/' + mapped[len('native/'):]
    raise ValueError('Unsupported flat data pack entry: ' + name)


def _contained_flat_path(root: Path, relative: str) -> Path:
    return content.path(root, relative)


def _resolve_local_archive(pack: policy.Pack, archive_dir: Path | None, emit) -> Path | None:
    if archive_dir is None:
        return None
    cache = Path(archive_dir).expanduser().resolve()
    names = [pack.sha256 + '.zip', pack.id + '.zip']
    published = urlsplit(pack.url).path.rsplit('/', 1)[-1]
    if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.zip', published):
        names.append(published)
    for name in dict.fromkeys(names):
        candidate = content.path(cache, name)
        if candidate.is_file():
            emit('using local archive ' + pack.id)
            return candidate
    return None


def _extract_flat_pack(root: Path, pack: policy.Pack, archive_path: Path) -> tuple[dict[str, dict], list[str]]:
    if archive_path.stat().st_size != pack.size or policy.file_digest(archive_path) != pack.sha256:
        raise ValueError('Data pack archive checksum mismatch: ' + pack.id)
    extracted_files = {}
    spellings = {}
    with zipfile.ZipFile(archive_path) as archive:
        entries = archive.infolist()
        if len(entries) > 100000:
            raise ValueError('Data pack has too many ZIP entries: ' + pack.id)
        selected = {}
        for entry in entries:
            mode = stat.S_IFMT(entry.external_attr >> 16)
            if entry.flag_bits & 1 or mode not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError('Unsupported encrypted or special ZIP entry: ' + entry.filename)
            if entry.is_dir():
                clean = entry.filename[:-1]
                parents = {
                    'static', 'native', 'metadata', 'native/exvius',
                    'static/client', 'static/client/shared_prefs',
                    'static/gacha_community', 'static/summon_art',
                }
                if clean and clean not in parents:
                    _flat_destination(clean + '/placeholder', pack.id)
                continue
            if mode == stat.S_IFDIR:
                raise ValueError('Invalid ZIP directory entry: ' + entry.filename)
            rel = _flat_destination(entry.filename, pack.id)
            key = policy.collision_key(rel)
            if rel in selected or (key in spellings and spellings[key] != rel):
                raise ValueError('Duplicate or colliding flat data pack entry: ' + rel)
            spellings[key] = rel
            selected[rel] = entry
        for rel in selected:
            parts = rel.split('/')
            if any(policy.collision_key('/'.join(parts[:i])) in spellings for i in range(1, len(parts))):
                raise ValueError('Data pack file conflicts with a parent directory: ' + rel)
        if sum(entry.file_size for entry in selected.values()) != pack.unpacked_size:
            raise ValueError('Data pack expanded size disagrees with manifest: ' + pack.id)

        for rel, entry in selected.items():
            target = _contained_flat_path(root, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            total, digest = 0, hashlib.sha256()
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(prefix='.' + target.name + '.', dir=target.parent, delete=False) as out:
                    temporary = Path(out.name)
                    with archive.open(entry) as src:
                        while True:
                            block = src.read(1024 * 1024)
                            if not block:
                                break
                            total += len(block)
                            if total > entry.file_size:
                                raise ValueError('Data pack entry exceeds declared size: ' + rel)
                            out.write(block)
                            digest.update(block)
                    out.flush()
                    os.fsync(out.fileno())
                if total != entry.file_size:
                    raise ValueError('Truncated data pack entry: ' + rel)
                os.replace(temporary, target)
            finally:
                if temporary is not None and temporary.exists():
                    temporary.unlink()
            stat_res = target.stat()
            extracted_files[rel] = {
                'size': total,
                'sha256': digest.hexdigest(),
                'mtime_ns': stat_res.st_mtime_ns,
            }
    return extracted_files, sorted(selected)


class FlatBrowserDataStrategy:
    """DataLayoutReader + DataLayoutWriter for flat browser-data trees."""

    def inspect(self, config, manifest_path: Path) -> LayoutInspection:
        doc, packs = _parse_flat_manifest(manifest_path)
        root = config.data_root
        receipt_path = root / '.web_setup/installed.json'
        if not receipt_path.is_file():
            deltas = tuple(
                PackDelta(p.id, p.url, p.size, p.unpacked_size, p.sha256, 'missing-receipt')
                for p in packs
            )
            return LayoutInspection(
                layout='flat',
                installed_version=None,
                target_version=doc['version'],
                target_revision=doc['revision'],
                packs_needed=deltas,
                download_bytes=sum(p.size for p in deltas),
                unpacked_bytes=sum(p.unpacked_size for p in deltas),
                valid=False,
                error='Missing .web_setup/installed.json receipt',
            )
        try:
            receipt = json.loads(receipt_path.read_bytes())
            if not isinstance(receipt, dict):
                raise ValueError('receipt must be a JSON object')
        except (OSError, ValueError) as exc:
            deltas = tuple(
                PackDelta(p.id, p.url, p.size, p.unpacked_size, p.sha256, 'corrupt-receipt')
                for p in packs
            )
            return LayoutInspection(
                layout='flat',
                installed_version=None,
                target_version=doc['version'],
                target_revision=doc['revision'],
                packs_needed=deltas,
                download_bytes=sum(p.size for p in deltas),
                unpacked_bytes=sum(p.unpacked_size for p in deltas),
                valid=False,
                error=f'Corrupt .web_setup/installed.json: {exc}',
            )

        installed_version = receipt.get('version')
        completed = receipt.get('completed')
        completed_by_id = {}
        if isinstance(completed, list):
            for row in completed:
                if isinstance(row, dict) and isinstance(row.get('id'), str):
                    completed_by_id[row['id']] = row

        needed_by_id = {}
        for pack in packs:
            recorded = completed_by_id.get(pack.id)
            if recorded is None:
                needed_by_id[pack.id] = PackDelta(pack.id, pack.url, pack.size, pack.unpacked_size, pack.sha256, 'missing')
            elif recorded.get('sha256') != pack.sha256 or recorded.get('unpackedSize') != pack.unpacked_size:
                needed_by_id[pack.id] = PackDelta(pack.id, pack.url, pack.size, pack.unpacked_size, pack.sha256, 'changed')

        files_map = receipt.get('files')
        pack_files = receipt.get('pack_files') if isinstance(receipt.get('pack_files'), dict) else {}
        missing_files = []
        valid = True
        error = None

        if isinstance(files_map, dict) and files_map:
            try:
                for rel in files_map:
                    target = _contained_flat_path(root, rel)
                    if not target.is_file():
                        missing_files.append(rel)
            except ValueError as exc:
                valid = False
                error = str(exc)
        else:
            valid = False
            error = 'Flat receipt is missing file inventory'

        if missing_files:
            valid = False
            error = f'{len(missing_files)} installed file(s) missing (first: {missing_files[0]})'
            missing_set = set(missing_files)
            for pack in packs:
                if pack.id in needed_by_id:
                    continue
                owned = pack_files.get(pack.id)
                if isinstance(owned, list) and any(item in missing_set for item in owned):
                    needed_by_id[pack.id] = PackDelta(
                        pack.id, pack.url, pack.size, pack.unpacked_size, pack.sha256, 'missing-files',
                    )
            if not needed_by_id and not pack_files:
                for pack in packs:
                    needed_by_id[pack.id] = PackDelta(
                        pack.id, pack.url, pack.size, pack.unpacked_size, pack.sha256, 'missing-files',
                    )

        if valid and (installed_version != doc['version'] or not isinstance(files_map, dict) or not files_map):
            missing_dirs = config.missing_data()
            if missing_dirs:
                valid = False
                error = 'Missing required flat data paths: ' + ', '.join(missing_dirs)

        if valid and installed_version != doc['version'] and not needed_by_id:
            valid = False
            error = f'Installed flat version {installed_version!r} differs from manifest {doc["version"]!r}'

        deltas = tuple(needed_by_id[pack.id] for pack in packs if pack.id in needed_by_id)
        return LayoutInspection(
            layout='flat',
            installed_version=installed_version if isinstance(installed_version, str) else None,
            target_version=doc['version'],
            target_revision=doc['revision'],
            packs_needed=deltas,
            download_bytes=sum(p.size for p in deltas),
            unpacked_bytes=sum(p.unpacked_size for p in deltas),
            valid=valid and not deltas,
            error=error,
        )

    def apply(
        self,
        config,
        manifest_path: Path,
        *,
        archive_dir: Path | None = None,
        opener=urllib.request.urlopen,
        emit=lambda msg: None,
    ) -> dict:
        doc, packs = _parse_flat_manifest(manifest_path)
        root = config.data_root
        web_setup = root / '.web_setup'
        receipt_path = web_setup / 'installed.json'
        progress_path = web_setup / 'upgrade_progress.json'

        with InstanceLock(config.root), InstanceLock(root / '.ios-installer'):
            receipt = {}
            if receipt_path.is_file():
                try:
                    loaded = json.loads(receipt_path.read_bytes())
                    if isinstance(loaded, dict):
                        receipt = loaded
                except (OSError, ValueError):
                    receipt = {}
            files_map = dict(receipt.get('files')) if isinstance(receipt.get('files'), dict) else {}
            old_pack_files = dict(receipt.get('pack_files')) if isinstance(receipt.get('pack_files'), dict) else {}
            completed_list = receipt.get('completed') if isinstance(receipt.get('completed'), list) else []
            completed_by_id = {
                row['id']: row for row in completed_list
                if isinstance(row, dict) and isinstance(row.get('id'), str)
            }

            inspection = self.inspect(config, manifest_path)
            needed_ids = {delta.id for delta in inspection.packs_needed}
            if not needed_ids and inspection.valid:
                return {
                    'ok': True,
                    'layout': 'flat',
                    'installed_now': False,
                    'updated_packs': [],
                    'downloaded_packs': 0,
                    'removed_files': [],
                    'version': doc['version'],
                    'revision': doc['revision'],
                }

            progress = {}
            if progress_path.is_file():
                try:
                    loaded_prog = json.loads(progress_path.read_bytes())
                    if (isinstance(loaded_prog, dict)
                            and loaded_prog.get('revision') == doc['revision']
                            and loaded_prog.get('version') == doc['version']):
                        progress = loaded_prog
                except (OSError, ValueError):
                    progress = {}
            done_in_progress = dict(progress.get('completed', {})) if isinstance(progress.get('completed'), dict) else {}

            to_install = [
                pack for pack in packs
                if pack.id in needed_ids and done_in_progress.get(pack.id) != pack.sha256
            ]
            free_needed = sum(p.unpacked_size for p in to_install) + max((p.size for p in to_install), default=0)
            root.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(root).free < free_needed:
                raise OSError(f'Not enough free space for flat packs: need at least {free_needed} bytes.')

            new_pack_files = {}
            for pack in packs:
                if pack.id not in needed_ids and isinstance(old_pack_files.get(pack.id), list):
                    new_pack_files[pack.id] = list(old_pack_files[pack.id])

            downloaded = 0
            updated_packs = []
            for idx, pack in enumerate(to_install, 1):
                emit(f'[update] {idx}/{len(to_install)} {pack.id}')
                local = _resolve_local_archive(pack, archive_dir, emit)
                owned = False
                if local is not None:
                    archive_path = local
                else:
                    web_setup.mkdir(parents=True, exist_ok=True)
                    target = _contained_flat_path(root, '.web_setup/' + pack.sha256 + '.zip')
                    transferred = False

                    def track(*args, **kwargs):
                        nonlocal transferred
                        transferred = True
                        return opener(*args, **kwargs)

                    archive_path = pack_download.fetch(pack, target, opener=track, progress=emit)
                    owned = True
                    downloaded += int(transferred)

                try:
                    extracted, rel_list = _extract_flat_pack(root, pack, archive_path)
                finally:
                    if owned and archive_path.exists():
                        archive_path.unlink()

                files_map.update(extracted)
                new_pack_files[pack.id] = rel_list
                updated_packs.append(pack.id)
                done_in_progress[pack.id] = pack.sha256
                _atomic_write_json(progress_path, {
                    'revision': doc['revision'],
                    'version': doc['version'],
                    'completed': done_in_progress,
                })

            # Remove superseded .dat files not owned by the active pack set.
            active_owned = {rel for rels in new_pack_files.values() for rel in rels}
            removed_files = []
            active_pack_ids = {pack.id for pack in packs}
            for old_id, old_rels in old_pack_files.items():
                if not isinstance(old_rels, list):
                    continue
                if old_id in updated_packs or old_id not in active_pack_ids:
                    for rel in old_rels:
                        if rel not in active_owned and rel.endswith('.dat'):
                            candidate = _contained_flat_path(root, rel)
                            if candidate.is_file():
                                candidate.unlink()
                            files_map.pop(rel, None)
                            removed_files.append(rel)

            # Fallback for legacy receipts lacking pack_files: prune strictly older mst Ver*_<token>.dat
            # superseded by a newly extracted pack in client/files/mst/.
            if updated_packs:
                new_mst_tokens = {}
                for pack_id in updated_packs:
                    if pack_id in old_pack_files:
                        continue
                    for rel in new_pack_files.get(pack_id, ()):
                        if rel.startswith('client/files/mst/'):
                            match = DAT_NAME.fullmatch(Path(rel).name)
                            if match is not None:
                                new_mst_tokens[match[2]] = max(new_mst_tokens.get(match[2], 0), int(match[1]))
                if new_mst_tokens:
                    mst_dir = root / 'client/files/mst'
                    if mst_dir.is_dir():
                        for candidate in sorted(mst_dir.glob('Ver*_*.dat')):
                            match = DAT_NAME.fullmatch(candidate.name)
                            if match is not None and match[2] in new_mst_tokens and int(match[1]) < new_mst_tokens[match[2]]:
                                rel = candidate.relative_to(root).as_posix()
                                if rel not in active_owned:
                                    candidate.unlink()
                                    files_map.pop(rel, None)
                                    removed_files.append(rel)

            # Prune missing entries from files_map if any remained.
            for rel in list(files_map):
                if not _contained_flat_path(root, rel).is_file():
                    files_map.pop(rel, None)

            completed_out = [
                {'id': pack.id, 'sha256': pack.sha256, 'unpackedSize': pack.unpacked_size}
                for pack in packs
            ]
            new_receipt = {
                'version': doc['version'],
                'revision': doc['revision'],
                'completed': completed_out,
                'files': files_map,
                'pack_files': new_pack_files,
            }
            _atomic_write_json(receipt_path, new_receipt)
            if progress_path.exists():
                progress_path.unlink()

            return {
                'ok': True,
                'layout': 'flat',
                'installed_now': True,
                'updated_packs': updated_packs,
                'downloaded_packs': downloaded,
                'removed_files': sorted(set(removed_files)),
                'version': doc['version'],
                'revision': doc['revision'],
            }


class ManagedPackStrategy:
    """DataLayoutReader + DataLayoutWriter for immutable managed pack generations."""

    def inspect(self, config, manifest_path: Path) -> LayoutInspection:
        manifest = policy.read(manifest_path)
        plan_info = pack_install.plan(config, manifest_path)
        verify_info = pack_install.verify(config, manifest_path)

        current = None
        try:
            current = content.load(config.data_root, verify=False)
        except ValueError:
            current = None

        installed_version = current.manifest.document.get('version') if current is not None else None
        reason = 'changed' if current is not None else 'missing'
        deltas = tuple(
            PackDelta(pack.id, pack.url, pack.size, pack.unpacked_size, pack.sha256, reason)
            for pack in manifest.packs
            if pack_layers.load(config.data_root, pack) is None
        )
        valid = bool(verify_info.get('ok')) and bool(plan_info.get('current'))
        error = None if valid else verify_info.get('error')
        return LayoutInspection(
            layout='managed' if (config.data_root / content.POINTER).exists() else 'uninstalled',
            installed_version=installed_version,
            target_version=manifest.document['version'],
            target_revision=manifest.document['revision'],
            packs_needed=deltas,
            download_bytes=sum(pack.size for pack in deltas),
            unpacked_bytes=sum(pack.unpacked_size for pack in deltas),
            valid=valid,
            error=error,
        )

    def apply(
        self,
        config,
        manifest_path: Path,
        *,
        archive_dir: Path | None = None,
        opener=urllib.request.urlopen,
        emit=lambda msg: None,
    ) -> dict:
        config.data_root.mkdir(parents=True, exist_ok=True)
        return pack_install.fetch(
            config,
            manifest_path,
            archive_dir=archive_dir,
            opener=opener,
            emit=emit,
            normalize=normalize_managed_stage,
        )


class AutoLayoutReader:
    """DataLayoutReader delegating to FlatBrowserDataStrategy or ManagedPackStrategy."""

    def __init__(self, flat: FlatBrowserDataStrategy | None = None, managed: ManagedPackStrategy | None = None):
        self._flat = flat or FlatBrowserDataStrategy()
        self._managed = managed or ManagedPackStrategy()

    def inspect(self, config, manifest_path: Path) -> LayoutInspection:
        layout = detect_layout(config)
        strategy = self._flat if layout == 'flat' else self._managed
        return strategy.inspect(config, manifest_path)


class AutoLayoutWriter:
    """DataLayoutWriter delegating to FlatBrowserDataStrategy or ManagedPackStrategy."""

    def __init__(self, flat: FlatBrowserDataStrategy | None = None, managed: ManagedPackStrategy | None = None):
        self._flat = flat or FlatBrowserDataStrategy()
        self._managed = managed or ManagedPackStrategy()

    def apply(
        self,
        config,
        manifest_path: Path,
        *,
        archive_dir: Path | None = None,
        opener=urllib.request.urlopen,
        emit=lambda msg: None,
    ) -> dict:
        layout = detect_layout(config)
        strategy = self._flat if layout == 'flat' else self._managed
        return strategy.apply(config, manifest_path, archive_dir=archive_dir, opener=opener, emit=emit)
