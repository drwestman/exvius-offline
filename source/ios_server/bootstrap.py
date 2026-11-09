"""Explicit setup command for the separate, locked Python 3.12 environment."""
from pathlib import Path
import shutil
import subprocess
import sys


def _environment(project):
    project = Path(project)
    uv = shutil.which('uv')
    if uv is None:
        raise RuntimeError('Setup requires uv. Install uv, then run macos_ios_server.py setup again.')
    runtime = project / '.venv-ios/bin/python'
    if not runtime.is_file():
        candidates = [shutil.which('python3.12'), str(project / '.venv-browser/bin/python'), sys.executable]
        selected = '3.12'  # uv can install this interpreter when no local Python 3.12 is available.
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                version = subprocess.run([candidate, '-B', '-c', 'import sys; print(sys.version_info[:2])'],
                                         capture_output=True, text=True, timeout=10)
                if version.returncode == 0 and version.stdout.strip() == '(3, 12)':
                    selected = candidate
                    break
        subprocess.run([uv, 'venv', '--python', selected, str(runtime.parent.parent)],
                       stdout=sys.stderr, check=True)
    version = subprocess.run([str(runtime), '-B', '-c', 'import sys; print(sys.version_info[:2])'],
                             capture_output=True, text=True, check=True, timeout=10)
    if version.stdout.strip() != '(3, 12)':
        raise RuntimeError('The existing .venv-ios uses another Python version; prepare a Python 3.12 environment first.')
    subprocess.run([uv, 'pip', 'sync', '--python', str(runtime), '--require-hashes',
                    str(project / 'source/ios_server/requirements.lock')], stdout=sys.stderr, check=True)
    return runtime


def environment(project):
    try:
        return _environment(project)
    except subprocess.SubprocessError as exc:
        raise RuntimeError(f'iOS runtime setup failed: {exc}') from exc
