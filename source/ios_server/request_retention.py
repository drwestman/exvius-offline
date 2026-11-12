"""Explicit maintenance of canonical request records under the private runtime."""
import re
import time

from ios_server.runtime import private_path


def prune(root, *, now=None, max_age=3 * 86400, max_bytes=300 * 1024 * 1024):
    now = time.time() if now is None else now
    directory = private_path(root, 'requests')
    if directory.is_symlink():
        raise ValueError('The private request directory must not be a symlink.')
    if not directory.exists():
        return {'removed': 0, 'bytes': 0}
    rows = []
    for file in directory.iterdir():
        if file.is_symlink() or not re.fullmatch(r'\d{8}T\d{6}_\d{4,}\.json', file.name) or not file.is_file():
            continue
        info = file.stat()
        rows.append((info.st_mtime, file.name, file, info.st_size))
    total, removed = sum(row[3] for row in rows), 0
    for modified, _name, file, size in sorted(rows):
        if modified < now - max_age or total > max_bytes:
            file.unlink(); total -= size; removed += 1
    return {'removed': removed, 'bytes': total}
