"""Explicit application commands, kept separate from read-only diagnostics."""
from contextlib import redirect_stdout
import sys
import time


def lifecycle(config, args):
    if args.command == 'setup':
        from ios_server.certificates import CertificateStore
        from ios_server.runtime import InstanceLock
        with InstanceLock(config.root):
            return {'root': str(config.root), 'mode': 'connectivity-check',
                    'certificates': CertificateStore(config.root).prepare(), 'next_command': 'serve'}
    if args.command == 'stop':
        from ios_server.runtime import instance_busy, read_service
        result = read_service(config.root, stop=True) or {'stopping': False, 'hosting': 'stopped'}
        deadline = time.monotonic() + 40
        while read_service(config.root) is not None or instance_busy(config.root):
            if time.monotonic() >= deadline:
                raise RuntimeError('The iOS runtime is still busy. Check its foreground terminal before restarting.')
            time.sleep(.05)
        return result
    from ios_server.engine import Engine
    from ios_server.queries import status
    engine = Engine(config)
    try:
        with redirect_stdout(sys.stderr):
            initialized = engine.initialize_campaign()
        return {**status(config), 'initialized_now': initialized}
    finally:
        engine.close()


def prepare(config, args):
    if args.command in ('prepare-data', 'verify-data'):
        from ios_server.preparation import prepare_data, verify_data
        return prepare_data(config, vortex_art=args.vortex_art, sounds=args.sounds) if args.command == 'prepare-data' else verify_data(config)
    if args.command in ('prepare-banners', 'verify-banners'):
        from ios_server import banner_snapshots as operation
    elif args.command in ('prepare-sounds', 'verify-sounds'):
        from ios_server import sound_snapshots as operation
    else:
        from ios_server import home_banners as operation
    return operation.prepare(config) if args.command.startswith('prepare-') else operation.verify(config)
