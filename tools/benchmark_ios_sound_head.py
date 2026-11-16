"""Compare prepared-sound delivery against a Git revision using disposable files.

The synthetic bank is opaque to delivery, which checks its bound size/SHA-256
without parsing audio. This measures handler time and Python allocations, not
network time, process RSS, preparation, or physical-iPhone performance.
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
import hashlib, json, os, sys, time, tracemalloc, types
from pathlib import Path
from types import SimpleNamespace
sys.path[:0] = ['source', 'source/server']
from ios_server import native_sounds, table_delivery
from ios_server.sound_snapshots import Sounds
request = json.load(sys.stdin)
if request['implementation'] == 'before':
    for name in ('native_sounds', 'table_delivery'):
        module = types.ModuleType('baseline_' + name)
        sys.modules[module.__name__] = module
        exec(compile(request[name], name + '.py', 'exec'), module.__dict__)
        globals()[name] = module
root = Path(request['root'])
relative = 'common_lang/sound/bgm/ios/Ver100001_benchmark.acb'
entry = {'path': 'banks/benchmark.acb', 'size': request['size'], 'sha256': request['sha256']}
sounds = Sounds(root / 'sounds', {'banks': {relative: entry}})
delivery = native_sounds.Delivery(root, sounds, {relative: relative})
snapshot = SimpleNamespace(manifest={'version': 5}, sounds=delivery)
class Sink:
    def __init__(self):
        self.size = 0
        self.digest = hashlib.sha256()
    def write(self, raw):
        self.size += len(raw)
        self.digest.update(raw)
        return len(raw)
def fetch():
    handler = SimpleNamespace(command=request['method'], headers={}, wfile=Sink())
    handler.send_response = lambda code: handler.headers.update(status=code)
    handler.send_header = lambda key, value: handler.headers.update({key: value})
    handler.end_headers = lambda: None
    assert table_delivery.serve(handler, snapshot, relative)
    assert handler.headers['status'] == 200
    assert handler.headers['Content-Length'] == str(request['size']) and handler.close_connection
    assert handler.wfile.size == (request['size'] if request['method'] == 'GET' else 0)
    expected = request['sha256'] if request['method'] == 'GET' else hashlib.sha256().hexdigest()
    assert handler.wfile.digest.hexdigest() == expected
def readonly(event, args):
    if event == 'open' and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
        raise AssertionError('Benchmark attempted a write')
    if event in ('socket.bind', 'socket.connect'):
        raise AssertionError('Benchmark attempted network access')
sys.addaudithook(readonly)
start = time.perf_counter(); fetch(); first = time.perf_counter() - start
warm = []
for _ in range(request['repetitions']):
    start = time.perf_counter(); fetch(); warm.append(time.perf_counter() - start)
tracemalloc.start(); fetch(); retained, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
assert not {'capture_server', 'data_paths', 'player_state'} & set(sys.modules)
print(json.dumps({'first_seconds': first, 'warm_seconds': warm,
                  'peak_traced_bytes': peak, 'retained_traced_bytes': retained}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, help='Git revision before the optimization')
    parser.add_argument('--trials', type=int, default=7)
    parser.add_argument('--repetitions', type=int, default=5)
    parser.add_argument('--size-mib', type=int, default=32)
    args = parser.parse_args()
    if min(args.trials, args.repetitions, args.size_mib) < 1:
        parser.error('trial, repetition and size values must be positive')
    baseline = {name: subprocess.check_output(
        ['git', 'show', args.baseline + ':source/ios_server/' + name + '.py'], text=True)
        for name in ('native_sounds', 'table_delivery')}
    results = {method: {'before': [], 'after': []} for method in ('GET', 'HEAD')}
    with tempfile.TemporaryDirectory(prefix='bolt-sound-head-') as temp:
        path = Path(temp) / 'sounds/banks/benchmark.acb'
        path.parent.mkdir(parents=True)
        block = bytes(range(256)) * 4096
        digest = hashlib.sha256()
        with path.open('wb') as stream:
            for _ in range(args.size_mib):
                stream.write(block); digest.update(block)
        clean = {key: value for key, value in os.environ.items() if not key.startswith(
            ('FFBE_', 'EXVIUS_', 'STATE_', 'OUT_', 'CDN_', 'MST_', 'TEXT_', 'ART_', 'GACHA_'))}
        for trial in range(args.trials):
            order = ('before', 'after') if trial % 2 == 0 else ('after', 'before')
            for method in results:
                for implementation in order:
                    request = {**baseline, 'implementation': implementation, 'method': method, 'root': temp,
                               'size': path.stat().st_size, 'sha256': digest.hexdigest(),
                               'repetitions': args.repetitions}
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
