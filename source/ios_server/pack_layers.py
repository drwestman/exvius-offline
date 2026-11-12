"""Validate release ZIPs and publish reusable immutable pack payloads."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import zipfile

from ios_server import managed_content as content, pack_manifest as policy


def load(root, pack, *, verify=False, expected=None):
    directory = content.path(root, content.LAYERS + '/' + pack.sha256)
    if not directory.exists():
        return None
    try:
        raw = content.path(directory, 'layer.json').read_bytes()
        if expected is not None and policy.digest(raw) != expected:
            raise ValueError('layer record checksum mismatch')
        doc = json.loads(raw)
        if (set(doc) != {'version', 'archive_sha256', 'archive_size', 'unpacked_size', 'files'}
                or type(doc['version']) is not int or doc['version'] != 1
                or doc['archive_sha256'] != pack.sha256 or type(doc['archive_size']) is not int
                or doc['archive_size'] != pack.size or type(doc['unpacked_size']) is not int
                or doc['unpacked_size'] != pack.unpacked_size):
            raise ValueError('invalid layer metadata')
        content.validate_inventory(doc['files'])
        if sum(row['size'] for row in doc['files'].values()) != pack.unpacked_size:
            raise ValueError('expanded layer size mismatch')
        if verify:
            content.verify_files(directory, doc['files'], extras=('layer.json',))
        return directory, doc, policy.digest(raw)
    except (OSError, KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ValueError(f'Invalid managed pack layer {pack.id}: {exc}') from exc


def members(archive, pack):
    entries = archive.infolist()
    if len(entries) > 100000:
        raise ValueError('Data pack has too many ZIP entries')
    files = {}
    for entry in entries:
        mode = stat.S_IFMT(entry.external_attr >> 16)
        if entry.flag_bits & 1 or mode not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise ValueError('Unsupported encrypted or special ZIP entry')
        if entry.is_dir():
            clean = entry.filename[:-1]
            parents = {'static', 'native', 'metadata', 'static/client', 'static/client/shared_prefs', 'static/gacha_community'}
            if clean not in parents:
                policy.destination(clean + '/placeholder')
            continue
        if mode == stat.S_IFDIR:
            raise ValueError('Invalid ZIP directory entry')
        relative = policy.destination(entry.filename)
        if relative in files:
            raise ValueError('Duplicate data pack entry: ' + relative)
        files[relative] = entry
    content.validate_inventory({name: {'size': row.file_size, 'sha256': '0' * 64} for name, row in files.items()})
    if sum(row.file_size for row in files.values()) != pack.unpacked_size:
        raise ValueError('Data pack expanded size disagrees with manifest: ' + pack.id)
    return files


def _extract(archive, stage, entries):
    files = {}
    for relative, entry in entries.items():
        target = content.path(stage, relative); target.parent.mkdir(parents=True, exist_ok=True)
        total, digest = 0, hashlib.sha256()
        with archive.open(entry) as source, target.open('wb') as output:
            while True:
                block = source.read(1024 * 1024)
                if not block:
                    break
                total += len(block)
                if total > entry.file_size:
                    raise ValueError('Data pack entry exceeds declared size')
                output.write(block); digest.update(block)
            output.flush(); os.fsync(output.fileno())
        if total != entry.file_size:
            raise ValueError('Truncated data pack entry')
        target.chmod(0o444)
        files[relative] = {'size': total, 'sha256': digest.hexdigest()}
    return files


def extract(root, pack, archive_path):
    if archive_path.stat().st_size != pack.size or policy.file_digest(archive_path) != pack.sha256:
        raise ValueError('Data pack archive checksum mismatch: ' + pack.id)
    parent = content.path(root, content.LAYERS); parent.mkdir(parents=True, exist_ok=True)
    destination = content.path(root, content.LAYERS + '/' + pack.sha256)
    stage = Path(tempfile.mkdtemp(prefix='.building-', dir=parent))
    try:
        try:
            with zipfile.ZipFile(archive_path) as archive:
                entries = members(archive, pack)
                files = _extract(archive, stage, entries)
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError) as exc:
            raise ValueError(f'Invalid data pack ZIP {pack.id}: {exc}') from exc
        doc = {'version': 1, 'archive_sha256': pack.sha256, 'archive_size': pack.size,
               'unpacked_size': pack.unpacked_size, 'files': files}
        raw = policy.encoded(doc)
        with (stage / 'layer.json').open('wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(stage, destination)
        return destination, doc, policy.digest(raw)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def merge(stage, layers):
    """Rebuild the ordered overlay view, including restoration of removed overrides."""
    selected, spellings = {}, {}
    for directory, record, _sha in layers:
        for relative, entry in record['files'].items():
            key = policy.collision_key(relative)
            if key in spellings and spellings[key] != relative:
                raise ValueError('Case or Unicode collision between data packs: ' + relative)
            spellings[key] = relative
            selected[relative] = (directory, entry)
    files = {relative: entry for relative, (_directory, entry) in selected.items()}
    content.validate_inventory(files)
    for relative, (directory, _entry) in selected.items():
        target = content.path(stage, relative); target.parent.mkdir(parents=True, exist_ok=True)
        os.link(content.path(directory, relative), target)
    files = content.project_registry(stage, files)
    content.validate_layout(stage, files)
    return files
