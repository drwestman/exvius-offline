"""Private instance lock and local control channel; query functions never create files."""
import errno
import fcntl
import http.client
import json
import os
from pathlib import Path
import socket
import stat


def private_path(root, relative):
    root = Path(root).resolve()
    path = root / relative
    if not path.resolve().is_relative_to(root):
        raise ValueError(f'Private iOS path escapes the runtime root: {path}')
    return path


class InstanceLock:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.stream = None

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        path = private_path(self.root, 'instance.lock')
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        stream = os.fdopen(descriptor, 'a+b')
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            stream.close()
            if exc.errno in (errno.EAGAIN, errno.EACCES):
                raise RuntimeError('Another iOS instance owns this runtime; stop it before starting another instance.') from None
            raise
        self.stream = stream
        return self

    def __exit__(self, *_):
        if self.stream is not None:
            self.stream.close()
            self.stream = None


class UnixHTTP(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__('localhost', timeout=2)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(str(self.path))


def instance_busy(root):
    """Read-only lock probe; a closed control socket alone does not mean shutdown is complete."""
    path = private_path(root, 'instance.lock')
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return False
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        return False
    finally:
        os.close(descriptor)


def read_service(root, *, stop=False):
    """GET is a query; stop=True explicitly sends the shutdown command. No PID-based signalling."""
    path = private_path(root, 'control.sock')
    if not path.exists():
        return None
    mode = path.lstat()
    parent = path.parent.stat()
    if (not stat.S_ISSOCK(mode.st_mode) or mode.st_uid != os.getuid()
            or parent.st_uid != os.getuid() or parent.st_mode & 0o077):
        raise ValueError('The iOS control socket must be owned by this user in a private directory.')
    connection = UnixHTTP(path)
    try:
        connection.request('POST' if stop else 'GET', '/stop' if stop else '/status')
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError('Unexpected response from the private iOS control socket.')
        return json.loads(response.read(65536))
    except (FileNotFoundError, ConnectionRefusedError, ConnectionResetError,
            BrokenPipeError, http.client.RemoteDisconnected):
        return None
    finally:
        connection.close()
