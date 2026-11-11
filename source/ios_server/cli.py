"""Staged native entrypoint: diagnostics and calendar previews are available first."""
import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import signal
import sys
import time

from ios_server.config import Configuration, default_data, default_root
from ios_server.queries import doctor, rotation, status


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Exvius iPhone connection check and offline table preparation. Gameplay hosting is pending.')
    parser.add_argument('command', choices=('setup', 'serve', 'stop', 'doctor', 'status', 'rotation', 'init-campaign',
                                           'prepare-data', 'verify-data', 'prepare-banners', 'verify-banners',
                                           'prepare-sounds', 'verify-sounds', 'prepare-home-banners', 'verify-home-banners'))
    parser.add_argument('--root', type=Path, default=default_root(), help='private iOS runtime directory')
    parser.add_argument('--data', type=Path, default=default_data(), help='shared prepared or static/native data')
    parser.add_argument('--slot', default='campaign')
    parser.add_argument('--vortex-art', action='store_true', help='include the native Vortex banner pack during prepare-data')
    parser.add_argument('--sounds', action='store_true', help='bind already prepared sound banks during prepare-data')
    parser.add_argument('--weeks', type=int, default=1, help='rotation preview length, 1 to 52')
    parser.add_argument('--lan-address', help='Mac IPv4 address on the selected home network')
    parser.add_argument('--upstream-dns', help='upstream IPv4 DNS resolver; defaults to the Mac resolver')
    parser.add_argument('--dns-port', type=int, default=53)
    parser.add_argument('--http-port', type=int, default=80)
    parser.add_argument('--https-port', type=int, default=443)
    args = parser.parse_args(argv)
    if args.vortex_art and args.command != 'prepare-data':
        parser.error('--vortex-art applies only to prepare-data')
    if args.sounds and args.command != 'prepare-data':
        parser.error('--sounds applies only to prepare-data')
    try:
        config = Configuration(args.root, args.data, args.slot)
        if args.command == 'setup':
            from ios_server.certificates import CertificateStore
            from ios_server.runtime import InstanceLock
            with InstanceLock(config.root):
                result = {'root': str(config.root), 'mode': 'connectivity-check',
                          'certificates': CertificateStore(config.root).prepare(), 'next_command': 'serve'}
        elif args.command == 'serve':
            return serve(config, args)
        elif args.command == 'stop':
            from ios_server.runtime import instance_busy, read_service
            result = read_service(config.root, stop=True) or {'stopping': False, 'hosting': 'stopped'}
            deadline = time.monotonic() + 5
            while read_service(config.root) is not None or instance_busy(config.root):
                if time.monotonic() >= deadline:
                    raise RuntimeError('The iOS runtime is still busy. Check its foreground terminal before restarting.')
                time.sleep(.05)
        elif args.command == 'init-campaign':
            from ios_server.engine import Engine
            engine = Engine(config)
            try:
                with redirect_stdout(sys.stderr):
                    initialized = engine.initialize_campaign()
                result = {**status(config), 'initialized_now': initialized}
            finally:
                engine.close()
        elif args.command in ('prepare-data', 'verify-data'):
            from ios_server.preparation import prepare_data, verify_data
            result = prepare_data(config, vortex_art=args.vortex_art, sounds=args.sounds) if args.command == 'prepare-data' else verify_data(config)
        elif args.command in ('prepare-banners', 'verify-banners'):
            from ios_server.banner_snapshots import prepare, verify
            result = prepare(config) if args.command == 'prepare-banners' else verify(config)
        elif args.command in ('prepare-sounds', 'verify-sounds'):
            from ios_server.sound_snapshots import prepare, verify
            result = prepare(config) if args.command == 'prepare-sounds' else verify(config)
        elif args.command in ('prepare-home-banners', 'verify-home-banners'):
            from ios_server.home_banners import prepare, verify
            result = prepare(config) if args.command == 'prepare-home-banners' else verify(config)
        elif args.command == 'rotation':
            result = rotation(config, weeks=args.weeks)
        else:
            result = {'doctor': doctor, 'status': status}[args.command](config)
    except (ValueError, OSError, RuntimeError, ImportError) as exc:
        result = {'error': str(exc)}
    print(json.dumps(result, indent=2))
    return int('error' in result or result.get('ok') is False)


def serve(config, args):
    """Command orchestration; diagnostics never call discovery or start this lifecycle."""
    from ios_server.network import discover
    from ios_server.runtime import read_service
    from ios_server.service import Service
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError('Run macos_ios_server.py setup to prepare the Python 3.12 iOS environment.')
    for port in (args.dns_port, args.http_port, args.https_port):
        if not 1 <= port <= 65535:
            raise ValueError('Choose listener ports between 1 and 65535.')
    network = discover(address=args.lan_address, upstream=args.upstream_dns,
                       dns_port=args.dns_port, http_port=args.http_port, https_port=args.https_port)
    current = read_service(config.root)
    if current:
        if json.dumps(current['configuration'], sort_keys=True) != json.dumps(network.configuration(), sort_keys=True):
            raise RuntimeError('Another iOS configuration is already running. Stop it before changing addresses or ports.')
        print(json.dumps(current, indent=2), flush=True)
        return 0
    service = Service(config.root, network)
    previous = {}
    try:
        for name in (signal.SIGINT, signal.SIGTERM):
            previous[name] = signal.signal(name, lambda *_: service.stop_event.set())
        print(json.dumps(service.start(), indent=2), flush=True)
        check_at = time.monotonic() + 60
        while not service.stop_event.wait(.25):
            if not service.snapshot()['ready']:
                raise RuntimeError('A required connectivity listener stopped unexpectedly.')
            if time.monotonic() >= check_at:
                discover(address=network.address, upstream=network.upstream)
                service.maintain()
                check_at = time.monotonic() + 60
        return 0
    finally:
        service.close()
        for name, handler in previous.items():
            signal.signal(name, handler)
