"""Queries inspect files only. They never import the state loader, which can repair saves."""
from datetime import datetime, timezone
from importlib.util import find_spec
import json
import sys

from engine_profile import REVIVAL_COMMIT
from replay_calendar import preview, read_anchor
from ios_server.runtime import read_service


def _saved(config):
    try:
        with config.state_file.open(encoding='utf-8') as stream:
            data = json.load(stream)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise ValueError(f'Cannot read iOS save {config.state_file}: {exc}') from exc
    if not isinstance(data, dict):
        raise ValueError('The iOS campaign save must be a JSON object.')
    read_anchor(data)
    return data


def status(config) -> dict:
    result = {'profile': 'ios-revival', 'root': str(config.root), 'state_file': str(config.state_file),
              'has_save': False, 'campaign_initialized': False,
              'hosting': 'stopped', 'ready': False, 'mode': 'connectivity-check', 'reference_commit': REVIVAL_COMMIT}
    try:
        data = _saved(config)
        result['has_save'] = data is not None
        result['campaign_initialized'] = data is not None and read_anchor(data) is not None
        service = read_service(config.root)
        if service:
            result.update(service)
    except ValueError as exc:
        result['error'] = str(exc)
    return result


def doctor(config) -> dict:
    result = status(config)
    result['missing_data'] = config.missing_data()
    result['python'] = '.'.join(map(str, sys.version_info[:3]))
    result['python_supported'] = sys.version_info[:2] == (3, 12)
    result['missing_dependencies'] = [package for module, package in
                                      (('yaml', 'PyYAML'), ('cryptography', 'cryptography'), ('dnslib', 'dnslib'))
                                      if find_spec(module) is None]
    result['game_data_ok'] = not result['missing_data']
    if find_spec('cryptography') is not None:
        from ios_server.certificates import CertificateStore
        result['certificates'] = CertificateStore(config.root).inspect()
    else:
        result['certificates'] = {'ok': False, 'action': 'Run macos_ios_server.py setup.'}
    result['ok'] = (result['python_supported'] and not result['missing_dependencies']
                    and result['certificates']['ok'] and 'error' not in result)
    result['scope'] = 'native-connectivity-check; gameplay hosting and iPhone acceptance pending'
    return result


def rotation(config, *, now=None, weeks=1) -> dict:
    return preview(_saved(config) or {}, now if now is not None else datetime.now(timezone.utc), weeks)
