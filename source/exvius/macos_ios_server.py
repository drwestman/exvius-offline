#!/usr/bin/env python3
"""Native iOS entrypoint; queries do not initialize Python environments or campaigns."""
from pathlib import Path
import sys

if __name__ == '__main__':
    sys.dont_write_bytecode = True
    source = Path(__file__).resolve().parents[1]
    sys.path[:0] = [str(source), str(source / 'server')]
    from ios_server.cli import main
    raise SystemExit(main())
