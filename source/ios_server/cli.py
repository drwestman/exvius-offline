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
    parser = argparse.ArgumentParser(description='Exvius iPhone connection check, prepared gameplay hosting, and offline content commands.')
    parser.add_argument('command', choices=('setup', 'serve', 'start', 'stop', 'doctor', 'status', 'rotation', 'init-campaign',
                                           'prepare-data', 'verify-data', 'prepare-banners', 'verify-banners',
                                           'prepare-sounds', 'verify-sounds', 'prepare-home-banners', 'verify-home-banners',
                                           'plan-data', 'fetch-data', 'verify-packs'))
    parser.add_argument('--root', type=Path, default=default_root(), help='private iOS runtime directory')
    parser.add_argument('--data', type=Path, default=default_data(), help='shared prepared or static/native data')
    parser.add_argument('--slot', default='campaign')
    parser.add_argument('--manifest', type=Path, help='local release manifest for managed pack commands; defaults to data/latest.json')
    parser.add_argument('--archive-dir', type=Path, help='read-only local ZIP source for fetch-data; missing archives are downloaded')
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
    if args.manifest is not None and args.command not in ('plan-data', 'fetch-data', 'verify-packs'):
        parser.error('--manifest applies only to managed pack commands')
    if args.archive_dir is not None and args.command != 'fetch-data':
        parser.error('--archive-dir applies only to fetch-data')
    try:
        config = Configuration(args.root, args.data, args.slot)
        if args.command in ('plan-data', 'fetch-data', 'verify-packs'):
            from ios_server import pack_install, pack_manifest
            manifest = args.manifest if args.manifest is not None else pack_manifest.DEFAULT
            result = (pack_install.fetch(config, manifest, archive_dir=args.archive_dir) if args.command == 'fetch-data' else
                      pack_install.verify(config, manifest) if args.command == 'verify-packs' else pack_install.plan(config, manifest))
        elif args.command in ('setup', 'stop', 'init-campaign'):
            from ios_server.commands import lifecycle
            result = lifecycle(config, args)
        elif args.command in ('serve', 'start'):
            return serve(config, args)
        elif args.command.startswith(('prepare-', 'verify-')):
            from ios_server.commands import prepare
            result = prepare(config, args)
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
    application = None
    if args.command == 'start':
        from ios_server.hosting import Gameplay
        application = Gameplay(config)
    service = Service(config.root, network, application=application)
    current = read_service(config.root)
    if current:
        if json.dumps(current['configuration'], sort_keys=True) != json.dumps(service.configuration(), sort_keys=True):
            raise RuntimeError('Another iOS configuration is already running. Stop it before changing mode, data, slot, addresses or ports.')
        print(json.dumps(current, indent=2), flush=True)
        return 0
    previous, output = {}, sys.stdout
    # Canonical request diagnostics also go to stderr, including in worker threads.
    with redirect_stdout(sys.stderr):
        try:
            for name in (signal.SIGINT, signal.SIGTERM):
                previous[name] = signal.signal(name, lambda *_: service.stop_event.set())
            print(json.dumps(service.start(), indent=2), file=output, flush=True)
            check_at = time.monotonic() + 60
            while not service.stop_event.wait(.25):
                if not service.snapshot()['ready']:
                    raise RuntimeError('A required iOS listener stopped unexpectedly.')
                if time.monotonic() >= check_at:
                    discover(address=network.address, upstream=network.upstream)
                    service.maintain()
                    check_at = time.monotonic() + 60
            return 0
        finally:
            service.close()
            for name, previous_handler in previous.items():
                signal.signal(name, previous_handler)
