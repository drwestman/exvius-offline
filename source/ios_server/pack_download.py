"""Resumable, bounded pack transfer; never publishes content or imports the engine."""
import http.client
import os
import re
import urllib.request

from ios_server.pack_manifest import file_digest, web_url


def fetch(pack, target, *, opener=urllib.request.urlopen, progress=lambda message: None):
    """Keep interrupted partials; promote only exact-size, SHA-256-verified bytes."""
    partial = target.with_suffix('.part')
    for path in (target, partial):
        if path.is_symlink():
            raise ValueError('Invalid pack download link: ' + str(path))
    if target.exists():
        if target.stat().st_size == pack.size and file_digest(target) == pack.sha256:
            return target
        target.unlink()
    have = partial.stat().st_size if partial.exists() else 0
    if have > pack.size:
        partial.unlink(); have = 0
    if have < pack.size:
        request = urllib.request.Request(pack.url, headers={'Accept-Encoding': 'identity',
                                                         **({'Range': f'bytes={have}-'} if have else {})})
        try:
            with opener(request, timeout=30) as response:
                if not web_url(response.geturl()):
                    raise ValueError('Unsafe pack download redirect')
                if response.status == 200:
                    have = 0
                elif response.status == 206:
                    match = re.fullmatch(r'bytes ([0-9]+)-([0-9]+)/([0-9]+)', response.headers.get('Content-Range', ''))
                    if not match or tuple(map(int, match.groups())) != (have, pack.size - 1, pack.size):
                        raise ValueError('Invalid pack download Content-Range')
                else:
                    raise ValueError('Unexpected pack download status: ' + str(response.status))
                length = response.headers.get('Content-Length')
                if length is not None and (not length.isascii() or not length.isdigit() or int(length) != pack.size - have):
                    raise ValueError('Invalid pack download Content-Length')
                mode = 'ab' if have else 'wb'
                shown = -1
                with partial.open(mode) as stream:
                    while True:
                        block = response.read(min(1024 * 1024, pack.size - have + 1))
                        if not block:
                            break
                        if len(block) > pack.size - have:
                            raise ValueError('Pack download exceeds declared size')
                        stream.write(block); have += len(block)
                        percent = have * 100 // pack.size
                        if percent // 10 != shown:
                            shown = percent // 10
                            progress(f'{pack.id}: {have}/{pack.size} bytes ({percent}%)')
                    stream.flush(); os.fsync(stream.fileno())
        except http.client.HTTPException as exc:
            raise OSError(f'Interrupted pack download; rerun fetch-data: {exc}') from exc
    if not partial.exists() or partial.stat().st_size != pack.size:
        raise OSError('Incomplete pack download; rerun fetch-data to resume: ' + pack.id)
    if file_digest(partial) != pack.sha256:
        partial.unlink()
        raise ValueError('Pack SHA-256 mismatch; rerun fetch-data to download again: ' + pack.id)
    os.replace(partial, target)
    return target
