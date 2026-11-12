"""Explicit installation commands; no engine imports or query-side installation."""
import os
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request
from urllib.parse import urlsplit
import re

from ios_server import managed_content as content, pack_manifest as policy, pack_layers, pack_download
from ios_server.runtime import InstanceLock


def progress(message):
    print('[fetch-data] ' + message, file=sys.stderr, flush=True)


def plan(config, manifest_path=policy.DEFAULT):
    manifest = policy.read(manifest_path)
    current = content.load(config.data_root)
    missing = [pack for pack in manifest.packs if pack_layers.load(config.data_root, pack) is None]
    return {'ok': True, 'scope': 'managed-packs', 'data_root': str(config.data_root),
            'revision': manifest.document['revision'], 'version': manifest.document['version'],
            'manifest_sha256': manifest.sha256, 'packs': len(manifest.packs),
            'packs_to_fetch': len(missing), 'download_bytes': sum(pack.size for pack in missing),
            'new_content_bytes': sum(pack.unpacked_size for pack in missing),
            'installed': current is not None, 'current': current is not None and current.manifest.sha256 == manifest.sha256,
            'skipped': ['client-assets'] if any(row['id'] == 'client-assets' for row in manifest.document['packs']) else [],
            'gameplay_ready': False}


def verify(config, manifest_path=policy.DEFAULT):
    try:
        manifest = policy.read(manifest_path)
        installed = content.load(config.data_root, verify=True)
        if installed is None:
            return {'ok': False, 'scope': 'managed-packs', 'installed': False, 'gameplay_ready': False,
                    'error': 'No managed installation. Run fetch-data with a separate managed --data directory.'}
        if installed.manifest.sha256 != manifest.sha256:
            raise ValueError('Managed packs are stale for this manifest. Run fetch-data.')
        return {**installed.describe(), 'verified': True}
    except (OSError, ValueError) as exc:
        return {'ok': False, 'scope': 'managed-packs', 'gameplay_ready': False, 'error': str(exc)}


def _archive(root, pack, archive_dir, opener, emit):
    if archive_dir is not None:
        cache = Path(archive_dir).expanduser().resolve()
        names = [pack.sha256 + '.zip', pack.id + '.zip']
        published = urlsplit(pack.url).path.rsplit('/', 1)[-1]
        if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.zip', published):
            names.append(published)
        for name in dict.fromkeys(names):
            path = content.path(cache, name)
            if path.is_file():
                emit('using local archive ' + pack.id)
                return path, False, False
    directory = content.path(root, content.DOWNLOADS); directory.mkdir(parents=True, exist_ok=True)
    target = content.path(root, content.DOWNLOADS + '/' + pack.sha256 + '.zip')
    transferred = False
    def transfer(*args, **kwargs):
        nonlocal transferred
        transferred = True
        return opener(*args, **kwargs)
    return pack_download.fetch(pack, target, opener=transfer, progress=emit), True, transferred


def _layers(root, manifest, current, archive_dir, opener, emit):
    result, downloaded = [], 0
    for index, pack in enumerate(manifest.packs, 1):
        emit(f'{index}/{len(manifest.packs)} {pack.id}')
        expected = current.record['layers'].get(pack.sha256) if current is not None else None
        layer = pack_layers.load(root, pack, verify=True, expected=expected)
        if layer is None:
            archive, owned, transferred = _archive(root, pack, archive_dir, opener, emit)
            layer = pack_layers.extract(root, pack, archive)
            if owned:
                archive.unlink()
            downloaded += int(transferred)
        result.append(layer)
    return result, downloaded


def _write(path, raw):
    with path.open('wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


def _publish(root, stage, manifest, record):
    parent = content.path(root, content.GENERATIONS)
    destination = content.path(root, content.GENERATIONS + '/' + manifest.generation)
    raw = policy.encoded(record)
    _write(stage / 'manifest.json', manifest.raw)
    _write(stage / 'installation.json', raw)
    if destination.exists():
        if (content.path(destination, 'installation.json').read_bytes() != raw
                or content.path(destination, 'manifest.json').read_bytes() != manifest.raw):
            raise ValueError('Conflicting unpublished managed generation')
        content.verify_files(destination, record['files'], extras=('manifest.json', 'installation.json'))
    else:
        os.replace(stage, destination)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.ios-current-', dir=root, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(policy.encoded({'version': 1, 'directory': content.GENERATIONS + '/' + manifest.generation,
                                        'installation_sha256': policy.digest(raw)}))
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, content.path(root, content.POINTER))
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return destination


def fetch(config, manifest_path=policy.DEFAULT, *, archive_dir=None, opener=urllib.request.urlopen, emit=progress):
    """Retain old generations/layers; the pointer replacement is the only activation."""
    manifest = policy.read(manifest_path)
    root = config.data_root
    if any((root / name).exists() for name in ('static', 'native', 'mst_decoded', 'client/files')):
        raise ValueError('Existing prepared or flat managed data is read-only. Choose a separate managed --data directory.')
    with InstanceLock(config.root), InstanceLock(content.path(root, '.ios-installer')):
        current = content.load(root, verify=True)
        if current is not None and current.manifest.sha256 == manifest.sha256:
            return {**current.describe(), 'installed_now': False, 'downloaded_packs': 0}
        missing = [pack for pack in manifest.packs if pack_layers.load(root, pack) is None]
        needed = sum(pack.unpacked_size for pack in missing) + max((pack.size for pack in missing), default=0)
        if shutil.disk_usage(root).free < needed:
            raise OSError(f'Not enough free space for managed packs: need at least {needed} bytes.')
        layers, downloaded = _layers(root, manifest, current, archive_dir, opener, emit)
        parent = content.path(root, content.GENERATIONS); parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix='.building-', dir=parent))
        try:
            files = pack_layers.merge(stage, layers)
            record = {'version': 1, 'policy': policy.POLICY, 'manifest_sha256': manifest.sha256,
                      'layers': {pack.sha256: layer[2] for pack, layer in zip(manifest.packs, layers)}, 'files': files}
            content.verify_files(stage, files)
            directory = _publish(root, stage, manifest, record)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        installed = content.Installation(directory, manifest, record)
        return {**installed.describe(), 'installed_now': True, 'downloaded_packs': downloaded}
