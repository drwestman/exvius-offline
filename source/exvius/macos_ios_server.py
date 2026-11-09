#!/usr/bin/env python3
"""Native iOS entrypoint; queries do not initialize Python environments or campaigns."""
from pathlib import Path
import os
import sys

if __name__ == '__main__':
    sys.dont_write_bytecode = True
    source = Path(__file__).resolve().parents[1]
    sys.path[:0] = [str(source), str(source / 'server')]
    command = sys.argv[1] if len(sys.argv) > 1 else ''
    runtime = source.parent / '.venv-ios/bin/python'
    try:
        if command == 'setup' and os.environ.pop('EXVIUS_IOS_BOOTSTRAPPED', None) != '1':
            from ios_server.bootstrap import environment
            runtime = environment(source.parent)
            env = dict(os.environ, EXVIUS_IOS_BOOTSTRAPPED='1')
            os.execve(str(runtime), [str(runtime), '-B', str(Path(__file__).resolve()), *sys.argv[1:]], env)
        elif command in ('serve', 'init-campaign', 'doctor', 'status', 'rotation', 'stop') and runtime.is_file() and Path(sys.executable) != runtime:
            os.execv(str(runtime), [str(runtime), '-B', str(Path(__file__).resolve()), *sys.argv[1:]])
    except (OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
    from ios_server.cli import main
    raise SystemExit(main())
