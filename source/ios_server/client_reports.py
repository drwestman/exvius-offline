"""Native diagnostic protocol adapted from revival ae07888; no gameplay writes.

Requests ride GameSetting only, following upstream's 590d4fb fix for repeated
uploads. Storage is opt-in and private; queued uploads are acknowledged when off.
"""
import json
import os
from pathlib import Path
import re
import tempfile
import uuid
from urllib.parse import unquote, urlsplit

from ios_server.runtime import private_path

REQUEST = '6611dc2f'
REPORT_BACK = '383e98ad'
ACK = {'cd87bd8b': [{'950510b8': '0'}]}
MAX_BODY = 64 * 1024 * 1024
MAX_STORED = 128 * 1024 * 1024
MAX_FILES = 3
OWNED = re.compile(r'report-[a-f0-9]{32}\.json')


def owns(route):
    try:
        route = unquote(urlsplit(route).path)
    except ValueError:
        return False
    return route in ('/actionSymbol/6611dc2f.php',
                     '/lapisProd/app/php/gme/actionSymbol/6611dc2f.php')


def project(spec, reply_id, *, enabled):
    """Pure projection: ask once per launch, never on periodic home updates."""
    if not isinstance(spec, dict):
        return spec
    if not enabled or reply_id != 'OTX6Fmvu':
        return {key: value for key, value in spec.items() if key != REPORT_BACK} if REPORT_BACK in spec else spec
    return {**spec, REPORT_BACK: [{'86f76840': '2020-01-01 00:00:00', 'da99ba05': '0'}]}


class ClientReports:
    owns = staticmethod(owns)

    def __init__(self, root, *, enabled=False):
        self.root = Path(root).resolve()
        self.enabled = enabled

    def project(self, spec, reply_id):
        return project(spec, reply_id, enabled=self.enabled)

    def receive(self, plaintext):
        """Diagnostic command: save one report, without entering the game pipeline."""
        if plaintext is None:
            return None
        if self.enabled:
            try:
                document = json.JSONDecoder().raw_decode(plaintext)[0]
                rows = document.get('a8035010') if isinstance(document, dict) else None
                if (not isinstance(rows, list) or not rows
                        or not all(isinstance(row, dict) and isinstance(row.get('FPGJbL8x'), str) for row in rows)):
                    raise ValueError('Missing native report log')
                raw = json.dumps(document, ensure_ascii=False).encode()
                if len(raw) > MAX_BODY:
                    raise ValueError('Native report exceeds storage limit')
                path = self.save(raw)
                print(f'CLIENT REPORT: saved {len(raw)} bytes as {path.name}', flush=True)
            except (ValueError, OSError) as exc:
                print(f'CLIENT REPORT: not saved ({type(exc).__name__})', flush=True)
                return None
        else:
            print(f'CLIENT REPORT: acknowledged queued log ({len(plaintext)} chars); diagnostics off', flush=True)
        return {'cd87bd8b': [{'950510b8': '0'}]}

    def save(self, raw):
        directory = private_path(self.root, 'client-reports')
        if directory.is_symlink():
            raise ValueError('The private report directory must not be a symlink')
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory.chmod(0o700)
        path = directory / ('report-' + uuid.uuid4().hex + '.json')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, prefix='.report-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self.prune()
        return path

    def prune(self):
        directory = private_path(self.root, 'client-reports')
        if directory.is_symlink():
            raise ValueError('The private report directory must not be a symlink')
        if not directory.exists():
            return
        rows = []
        for path in directory.iterdir():
            if OWNED.fullmatch(path.name) and not path.is_symlink() and path.is_file():
                info = path.stat()
                rows.append((info.st_mtime_ns, path.name, path, info.st_size))
        total = sum(row[3] for row in rows)
        for index, (_modified, _name, path, size) in enumerate(sorted(rows)):
            if len(rows) - index <= MAX_FILES and total <= MAX_STORED:
                break
            path.unlink(); total -= size


def decode(path):
    """Read/decrypt a saved report for diagnosis; creates no files or engine state."""
    from ffbe_crypto import cbc_decrypt
    body = json.loads(Path(path).read_bytes())
    for row in body['a8035010']:
        for line in row['FPGJbL8x'].splitlines():
            if line.strip():
                try:
                    raw = cbc_decrypt(b'FFBE2020DevsRGod', line)
                    # The report line may have its own manual PKCS#7 layer too.
                    if raw and 1 <= raw[-1] <= 16 and raw[-raw[-1]:] == bytes([raw[-1]]) * raw[-1]:
                        raw = raw[:-raw[-1]]
                    yield raw.decode('utf-8', errors='replace')
                except (ValueError, RuntimeError):
                    yield '<undecodable report line>'
