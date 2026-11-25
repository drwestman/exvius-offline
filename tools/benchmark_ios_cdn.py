"""Compare ordinary iOS CDN delivery with a Git revision using disposable data.

Run from the repository root with .venv-ios/bin/python -B. The synthetic CPK is
opaque to this route, just like shipped movie packs. A hashing sink consumes the
body without retaining it; this measures handler work, not network or phone time.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile


WORKER = r'''
import ast, contextlib, hashlib, io, json, os, sys, time, tracemalloc
from pathlib import Path
sys.path[:0] = ['source', 'source/server']
request = json.load(sys.stdin)
from ios_server.config import Configuration
from engine_profile import select_profile
config = Configuration(Path(request['root']) / 'runtime', Path(request['root']) / 'content')
select_profile('ios-revival')
os.environ.update(config.engine_environment())
import capture_server as server
if request['implementation'] == 'before':
    # Use the original Handler with the same unchanged engine dependencies.
    tree = ast.parse(request['baseline'])
    handler = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Handler')
    exec(compile(ast.Module(body=[handler], type_ignores=[]), server.__file__, 'exec'), server.__dict__)
server.State.cdn_root = os.environ['CDN_ROOT']
server.State.cdn_overlay = os.environ['CDN_OVERLAY']
class Sink:
    def __init__(self):
        self.size = 0
        self.digest = hashlib.sha256()
    def write(self, raw):
        self.size += len(raw)
        self.digest.update(raw)
        return len(raw)
def fetch():
    handler = server.Handler.__new__(server.Handler)
    handler.path, handler.command, handler.headers = '/common_lang/movie/Ver1_benchmark.cpk', request['method'], {}
    handler.wfile = Sink()
    headers = {}
    handler.send_response = lambda code: headers.update(status=code)
    handler.send_header = lambda key, value: headers.update({key: value})
    handler.end_headers = lambda: None
    handler._cdn_fetch()
    assert headers['status'] == 200 and headers['Content-Length'] == str(request['size'])
    assert handler.close_connection
    assert handler.wfile.size == (request['size'] if request['method'] == 'GET' else 0)
    assert handler.wfile.digest.hexdigest() == (request['sha256'] if request['method'] == 'GET' else hashlib.sha256().hexdigest())
def readonly(event, args):
    if event == 'open' and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
        raise AssertionError('Benchmark attempted a write')
    if event in ('socket.bind', 'socket.connect'):
        raise AssertionError('Benchmark attempted network access')
sys.addaudithook(readonly)
with contextlib.redirect_stdout(io.StringIO()):
    start = time.perf_counter(); fetch(); first = time.perf_counter() - start
    warm = []
    for _ in range(request['repetitions']):
        start = time.perf_counter(); fetch(); warm.append(time.perf_counter() - start)
    tracemalloc.start(); fetch(); retained, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
assert not config.root.exists()
print(json.dumps({'first_seconds': first, 'warm_seconds': warm,
                  'peak_traced_bytes': peak, 'retained_traced_bytes': retained}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, help='Git revision before the optimization')
    parser.add_argument('--trials', type=int, default=7)
    parser.add_argument('--repetitions', type=int, default=5)
    parser.add_argument('--size-mib', type=int, default=160)
    args = parser.parse_args()
    if min(args.trials, args.repetitions, args.size_mib) < 1:
        parser.error('trial, repetition and size values must be positive')
    baseline = subprocess.check_output(
        ['git', 'show', args.baseline + ':source/server/capture_server.py'], text=True)
    results = {method: {'before': [], 'after': []} for method in ('GET', 'HEAD')}
    with tempfile.TemporaryDirectory(prefix='bolt-cdn-') as temp:
        path = Path(temp) / 'content/client/files/common_lang/movie/Ver1_benchmark.cpk'
        path.parent.mkdir(parents=True)
        block = bytes(range(256)) * 4096
        digest = hashlib.sha256()
        with path.open('wb') as stream:
            for _ in range(args.size_mib):
                stream.write(block)
                digest.update(block)
        for trial in range(args.trials):
            order = ('before', 'after') if trial % 2 == 0 else ('after', 'before')
            for method in results:
                for implementation in order:
                    request = {'baseline': baseline, 'root': temp, 'implementation': implementation,
                               'method': method, 'size': path.stat().st_size, 'sha256': digest.hexdigest(),
                               'repetitions': args.repetitions}
                    clean = {k: v for k, v in os.environ.items() if not k.startswith(
                        ('FFBE_', 'EXVIUS_', 'STATE_', 'OUT_', 'CDN_', 'MST_', 'TEXT_', 'ART_', 'GACHA_'))}
                    run = subprocess.run([sys.executable, '-B', '-c', WORKER], input=json.dumps(request),
                                         env=clean, text=True, capture_output=True, check=True)
                    results[method][implementation].append(json.loads(run.stdout))
            print(f'Completed trial {trial + 1}/{args.trials}', file=sys.stderr, flush=True)
    summary = {}
    for method, variants in results.items():
        summary[method] = {}
        for label, samples in variants.items():
            values = {key: [row[key] for row in samples] for key in samples[0] if key != 'warm_seconds'}
            values['warm_seconds'] = [value for row in samples for value in row['warm_seconds']]
            summary[method][label] = {key: {'median': statistics.median(numbers),
                                          'min': min(numbers), 'max': max(numbers)}
                                      for key, numbers in values.items()}
    print(json.dumps({'python': sys.version, 'baseline': args.baseline, 'trials': args.trials,
                      'warm_repetitions_per_process': args.repetitions, 'bytes': args.size_mib * 1024 * 1024,
                      'cache': 'fresh application process per sample; OS file cache not evicted',
                      'sink': 'SHA-256, no retained response body; no sockets',
                      'summary': summary, 'samples': results}, indent=2))


if __name__ == '__main__':
    main()
