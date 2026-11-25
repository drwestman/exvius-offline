"""Compare sound validation against a Git revision, using read-only shared inputs.

Run from the repository root with .venv-ios/bin/python -B. No engine, campaign,
prepared outputs or disk caches are loaded or created. Results are one JSON value.
"""
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile


WORKER = r'''
import hashlib, json, os, sys, time, tracemalloc, types
from pathlib import Path
sys.path[:0] = ['source', 'source/server']
from ios_server import sound_codec as codec
request = json.load(sys.stdin)
if request['implementation'] == 'before':
    def module(name, source):
        result = types.ModuleType(name)
        exec(compile(source, name + '.py', 'exec'), result.__dict__)
        return result
    old_cpk = module('baseline_cpk', request['cpk'])
    codec = module('baseline_sound_codec', request['codec'])
    codec.cpk = old_cpk
data = Path(request['data'])
banks = request['banks']
def readonly(event, args):
    if event == 'open' and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
        raise AssertionError('Benchmark attempted a file write')
    if event in ('socket.bind', 'socket.connect'):
        raise AssertionError('Benchmark attempted network access')
sys.addaudithook(readonly)
def inspect_bank(row):
    raw = (data / row['path']).read_bytes()
    assert len(raw) == row['size'] and hashlib.sha256(raw).hexdigest() == row['sha256']
    return codec.inspect(raw)
def scan():
    # A call boundary releases each bank before reading the next, like _bank().
    signature = hashlib.sha256()
    for row in banks:
        signature.update(json.dumps(inspect_bank(row), separators=(',', ':')).encode())
    return signature.hexdigest()
start = time.perf_counter(); first = scan(); first_s = time.perf_counter() - start
start = time.perf_counter(); warm = scan(); warm_s = time.perf_counter() - start
assert first == warm
largest = max(banks, key=lambda row: row['size'])
tracemalloc.start(); inspected = inspect_bank(largest); retained, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
raw = (data / largest['path']).read_bytes()
assert inspected == codec.inspect(raw)
tracemalloc.start(); codec.inspect(raw); _, inspect_peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
assert not {'capture_server', 'data_paths', 'ffbe_state'} & set(sys.modules)
print(json.dumps({'first_seconds': first_s, 'warm_seconds': warm_s,
    'peak_traced_bytes': peak, 'retained_traced_bytes': retained,
    'largest_inspect_peak_bytes': inspect_peak, 'signature': first}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('data', type=Path)
    parser.add_argument('--baseline', required=True, help='Git revision before the optimization')
    parser.add_argument('--trials', type=int, default=7)
    args = parser.parse_args()
    if args.trials < 1:
        parser.error('--trials must be positive')
    sys.path[:0] = ['source', 'source/server']
    from ios_server.config import Configuration
    from ios_server.sound_inputs import collect
    baseline = {key: subprocess.check_output(
        ['git', 'show', args.baseline + ':source/ios_server/' + name + '.py'], text=True)
        for key, name in (('cpk', 'cpk'), ('codec', 'sound_codec'))}
    with tempfile.TemporaryDirectory(prefix='bolt-utf-') as temp:
        config = Configuration(Path(temp) / 'runtime', args.data)
        inputs = collect(config)
        banks = list(inputs.sources['banks'].values())
        results = {'before': [], 'after': []}
        signature = None
        for trial in range(args.trials):
            order = ('before', 'after') if trial % 2 == 0 else ('after', 'before')
            for implementation in order:
                request = {**baseline, 'implementation': implementation, 'data': str(config.data), 'banks': banks}
                run = subprocess.run([sys.executable, '-B', '-c', WORKER], input=json.dumps(request),
                                     text=True, capture_output=True, check=True)
                sample = json.loads(run.stdout)
                if signature is None:
                    signature = sample['signature']
                assert sample.pop('signature') == signature
                results[implementation].append(sample)
                print(f'Completed trial {trial + 1}/{args.trials}: {implementation}', file=sys.stderr, flush=True)
        assert collect(config) == inputs, 'Shared inputs changed during the comparison'
        assert not config.root.exists()
    summary = {label: {key: {'median': statistics.median(row[key] for row in samples),
                            'min': min(row[key] for row in samples), 'max': max(row[key] for row in samples)}
                       for key in samples[0]} for label, samples in results.items()}
    print(json.dumps({'python': sys.version, 'baseline': args.baseline, 'trials': args.trials,
                      'banks': len(banks), 'bytes': sum(row['size'] for row in banks),
                      'largest_bank_bytes': max(row['size'] for row in banks),
                      'equal_layouts': True, 'samples': results, 'summary': summary}, indent=2))


if __name__ == '__main__':
    main()
