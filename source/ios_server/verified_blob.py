"""Shared query-side contract for verified, descriptor-backed blob delivery."""
import hashlib
import os
import stat
from typing import NamedTuple, Protocol

CHUNK = 256 * 1024


class VerifiedBlob(NamedTuple):
    """A verified, rewound descriptor and the exact number of bytes to deliver."""
    stream: object
    size: int


class VerifiedBlobSource(Protocol):
    """What table_delivery needs from any file-backed source (queries only)."""
    def verified_size(self, relative: str) -> int | None: ...
    def open_verified(self, relative: str):
        """Context manager yielding None (unknown path) or a VerifiedBlob."""


def open_regular(path):
    """Open without following links or blocking; accept regular files only."""
    # O_NONBLOCK keeps a FIFO from hanging the request thread; regular files ignore it.
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    stream = os.fdopen(descriptor, 'rb')
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError('Prepared blob is not a regular file')
        return stream
    except BaseException:
        stream.close()
        raise


def verify_and_rewind(stream, size, sha256, message):
    """Hash at most size+1 bytes in bounded chunks, check them, then rewind.

    Every request rehashes: same-size edits must never hit a stat cache.
    """
    digest, seen = hashlib.sha256(), 0
    while seen <= size:
        block = stream.read(min(CHUNK, size + 1 - seen))
        if not block:
            break
        digest.update(block)
        seen += len(block)
    if seen != size or digest.hexdigest() != sha256:
        raise ValueError(message)
    stream.seek(0)
