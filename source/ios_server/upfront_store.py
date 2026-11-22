"""Content-addressed private upfront CPK blob store and read-only delivery."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Protocol

from ios_server.runtime import private_path

BLOB_DIR = 'assets/upfront/blobs'
BLOB_PATTERN = re.compile(r'^assets/upfront/blobs/[a-f0-9]{64}\.cpk$')
STAGE_CHUNK = 1024 * 1024
HEAD_CHUNK = 256 * 1024


class UpfrontBlobWriter(Protocol):
    """Command-side contract for staging immutable private upfront CPK blobs."""
    def stage(self, source_path: Path, expected_sha256: str, expected_size: int) -> str: ...


class UpfrontBlobReader(Protocol):
    """Query/delivery-side contract for verifying and streaming private upfront CPK blobs."""
    def owns(self, relative: str) -> bool: ...
    def verified_size(self, relative: str) -> int | None: ...
    def open_verified(self, relative: str): ...


def unversioned_path(relative: str) -> str:
    """Normalize Ver<N>_<name> in a CDN relative path to Ver0_<name>."""
    parent, sep, name = relative.rpartition('/')
    return f"{parent}{sep}{re.sub(r'^Ver[0-9]+_', 'Ver0_', name)}"


def _hash_fd(fd: int, expected_size: int, chunk_size: int) -> tuple[int, str]:
    digest, size = hashlib.sha256(), 0
    while size <= expected_size:
        block = os.read(fd, min(chunk_size, expected_size + 1 - size))
        if not block:
            break
        digest.update(block)
        size += len(block)
    return size, digest.hexdigest()


@dataclass(frozen=True)
class BlobStore:
    """Command-side atomic copy into assets/upfront/blobs/<sha256>.cpk."""
    root: Path
    data_root: Path

    def stage(self, source_path: Path, expected_sha256: str, expected_size: int) -> str:
        if not isinstance(expected_sha256, str) or not re.fullmatch(r'[a-f0-9]{64}', expected_sha256):
            raise ValueError('Invalid upfront CPK blob digest.')
        if type(expected_size) is not int or expected_size < 1:
            raise ValueError('Invalid upfront CPK blob size.')
        source_path = Path(source_path)
        data_root = self.data_root.resolve()
        if not source_path.resolve().is_relative_to(data_root):
            raise ValueError('Upfront CPK escapes shared content: ' + str(source_path))
        blob_rel = f'{BLOB_DIR}/{expected_sha256}.cpk'
        assets_dir = private_path(self.root, 'assets')
        upfront_dir = private_path(self.root, 'assets/upfront')
        blobs_dir = private_path(self.root, BLOB_DIR)
        dest = private_path(self.root, blob_rel)
        if not dest.resolve().is_relative_to(blobs_dir.resolve()):
            raise ValueError('Upfront CPK blob escapes private blob store')

        src_fd = os.open(source_path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            if not stat.S_ISREG(os.fstat(src_fd).st_mode):
                raise ValueError('Upfront CPK source is not a regular file: ' + str(source_path))
            for folder in (assets_dir, upfront_dir, blobs_dir):
                folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            upfront_dir.chmod(0o700)
            blobs_dir.chmod(0o700)

            if dest.exists() or dest.is_symlink():
                try:
                    existing_fd = os.open(dest, os.O_RDONLY | os.O_NOFOLLOW)
                except OSError as exc:
                    raise ValueError('Corrupt private upfront CPK blob: ' + blob_rel) from exc
                try:
                    if not stat.S_ISREG(os.fstat(existing_fd).st_mode):
                        raise ValueError('Corrupt private upfront CPK blob: ' + blob_rel)
                    size, digest = _hash_fd(existing_fd, expected_size, STAGE_CHUNK)
                finally:
                    os.close(existing_fd)
                if size != expected_size or digest != expected_sha256:
                    raise ValueError('Corrupt private upfront CPK blob: ' + blob_rel)
                return blob_rel

            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(prefix='.staging-', dir=blobs_dir, delete=False) as stream:
                    temp_path = Path(stream.name)
                    digest, written = hashlib.sha256(), 0
                    while True:
                        block = os.read(src_fd, STAGE_CHUNK)
                        if not block:
                            break
                        stream.write(block)
                        digest.update(block)
                        written += len(block)
                    if written != expected_size or digest.hexdigest() != expected_sha256:
                        raise ValueError('Upfront CPK source changed during staging: ' + str(source_path))
                    stream.flush()
                    os.fchmod(stream.fileno(), 0o600)
                    os.fsync(stream.fileno())
                os.replace(temp_path, dest)
                temp_path = None
            finally:
                if temp_path is not None and temp_path.exists():
                    temp_path.unlink()
            return blob_rel
        finally:
            os.close(src_fd)


@dataclass(frozen=True)
class UpfrontDelivery:
    """Query/HTTP-side read-only verifier and streamed file server for bumped upfront CPKs."""
    root: Path
    files: dict[str, dict]
    owned_identities: frozenset[str]

    @classmethod
    def from_manifest(cls, root: Path, upfront_packs: dict[str, dict]):
        files = {}
        identities = set()
        for entry in upfront_packs.values():
            rel = entry['path']
            ident = unversioned_path(rel)
            if rel in files or ident in identities:
                raise ValueError('Conflicting bumped upfront CPK paths')
            files[rel] = entry
            identities.add(ident)
        return cls(Path(root).resolve(), files, frozenset(identities))

    def owns(self, relative: str) -> bool:
        return unversioned_path(relative) in self.owned_identities

    def _open_and_verify(self, entry: dict):
        blob_rel = entry.get('blob')
        if not isinstance(blob_rel, str) or not BLOB_PATTERN.fullmatch(blob_rel):
            raise ValueError('Invalid upfront CPK blob path')
        blobs_dir = private_path(self.root, BLOB_DIR).resolve()
        path = private_path(self.root, blob_rel)
        if not path.resolve().is_relative_to(blobs_dir):
            raise ValueError('Upfront CPK blob escapes private blob store')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        stream = os.fdopen(fd, 'rb')
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError('Upfront CPK blob is not a regular file')
            digest, size = hashlib.sha256(), 0
            expected_size = entry['size']
            while size <= expected_size:
                block = stream.read(min(HEAD_CHUNK, expected_size + 1 - size))
                if not block:
                    break
                digest.update(block)
                size += len(block)
            if size != expected_size or digest.hexdigest() != entry['sha256']:
                raise ValueError('Prepared upfront CPK checksum mismatch')
            stream.seek(0)
            return stream
        except BaseException:
            stream.close()
            raise

    def verified_size(self, relative: str) -> int | None:
        entry = self.files.get(relative)
        if entry is None:
            return None
        with self._open_and_verify(entry):
            return entry['size']

    @contextmanager
    def open_verified(self, relative: str):
        entry = self.files.get(relative)
        if entry is None:
            yield None
            return
        with self._open_and_verify(entry) as stream:
            yield stream, entry['size']

    @classmethod
    def verify_all(cls, config, upfront_packs: dict[str, dict]):
        delivery = cls.from_manifest(config.root, upfront_packs)
        for entry in upfront_packs.values():
            delivery.verified_size(entry['path'])
        return delivery
