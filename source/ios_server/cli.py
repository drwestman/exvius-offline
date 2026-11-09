"""Staged native entrypoint: diagnostics and calendar previews are available first."""
import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys

from ios_server.config import Configuration, default_data, default_root
from ios_server.queries import doctor, rotation, status


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Exvius iOS server foundation (native hosting pending).')
    parser.add_argument('command', choices=('doctor', 'status', 'rotation', 'init-campaign'))
    parser.add_argument('--root', type=Path, default=default_root(), help='private iOS runtime directory')
    parser.add_argument('--data', type=Path, default=default_data(), help='shared prepared or static/native data')
    parser.add_argument('--slot', default='campaign')
    parser.add_argument('--weeks', type=int, default=1, help='rotation preview length, 1 to 52')
    args = parser.parse_args(argv)
    try:
        config = Configuration(args.root, args.data, args.slot)
        if args.command == 'init-campaign':
            from ios_server.engine import Engine
            engine = Engine(config)
            try:
                with redirect_stdout(sys.stderr):
                    initialized = engine.initialize_campaign()
                result = {**status(config), 'initialized_now': initialized}
            finally:
                engine.close()
        elif args.command == 'rotation':
            result = rotation(config, weeks=args.weeks)
        else:
            result = {'doctor': doctor, 'status': status}[args.command](config)
    except (ValueError, OSError, RuntimeError, ImportError) as exc:
        result = {'error': str(exc)}
    print(json.dumps(result, indent=2))
    return int('error' in result or result.get('ok') is False)
