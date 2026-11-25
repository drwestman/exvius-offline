"""Compare native master validation/normalization with a Git baseline, read-only.

Run from the repository root with .venv-ios/bin/python -B. Each sample uses a
fresh process and preloaded encrypted inputs. No campaign or prepared cache is
opened. tracemalloc reports additional Python allocations, not process RSS.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile


WORKER = r'''
import gc, hashlib, json, os, sys, time, tracemalloc, types
from pathlib import Path
sys.path[:0] = ['source', 'source/server']
from ios_server import table_codec as codec
request = json.load(sys.stdin)
if request['implementation'] == 'before':
    codec = types.ModuleType('baseline_table_codec')
    exec(compile(request['codec'], 'baseline_table_codec.py', 'exec'), codec.__dict__)
validate = getattr(codec, 'validate_master', codec.master_rows)
def readonly(event, args):
    if event == 'open' and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
        raise AssertionError('Benchmark attempted a file write')
    if event in ('socket.bind', 'socket.connect'):
        raise AssertionError('Benchmark attempted network access')
sys.addaudithook(readonly)
inputs = []
for row in request['tables']:
    raw = Path(row['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == row['sha256']
    inputs.append((row, raw))
def scan(operation):
    signature = hashlib.sha256()
    for row, raw in inputs:
        if operation == 'normalize':
            out = codec.normalize_master(raw, row['key'], mode=row['cipher'])
            assert out == raw.replace(b'\r\n', b'\n')
            signature.update(out)
        else:
            # Discard the result immediately, as native_tables.validate did.
            reader = codec.master_rows if operation == 'eager' else validate
            reader(raw, row['key'], mode=row['cipher'])
    return signature.hexdigest()
result, signatures = {}, {}
for operation in ('validate', 'normalize', 'eager'):
    for condition in ('first', 'warm'):
        gc.collect()
        start = time.perf_counter(); signature = scan(operation); elapsed = time.perf_counter() - start
        result[operation + '_' + condition + '_seconds'] = elapsed
        if operation in signatures:
            assert signatures[operation] == signature
        signatures[operation] = signature
largest = max(inputs, key=lambda item: len(item[1]))
row, raw = largest
for name, operation in (('validate', validate), ('normalize', codec.normalize_master)):
    gc.collect(); tracemalloc.start()
    operation(raw, row['key'], mode=row['cipher'])
    _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
    result[name + '_largest_peak_traced_bytes'] = peak
assert not {'capture_server', 'data_paths', 'ffbe_state'} & set(sys.modules)
print(json.dumps({'metrics': result, 'signature': signatures['normalize']}))
'''


def inventory(data):
    from ios_server.config import Configuration
    from ios_server import native_tables as rules
    with tempfile.TemporaryDirectory(prefix='bolt-master-') as temp:
        config = Configuration(Path(temp) / 'runtime', data)
        env = config.engine_environment()
        roots = tuple(dict.fromkeys(Path(env[key]) for key in ('CDN_OVERLAY', 'CDN_ROOT')))
        tables = []
        for table in rules.TABLES:
            if table.localized:
                continue
            for root in roots:
                candidates = list((root / 'mst').glob('Ver*_' + table.token + '.dat'))
                if not candidates:
                    continue
                path = max(candidates, key=lambda p: int(p.name.split('_', 1)[0][3:]))
                if not path.resolve().is_relative_to(config.data):
                    raise ValueError('Benchmark input escapes shared data')
                raw = path.read_bytes()
                tables.append({'name': table.name, 'key': table.key, 'cipher': table.cipher,
                               'path': str(path), 'size': len(raw), 'rows': len(raw.splitlines()),
                               'sha256': hashlib.sha256(raw).hexdigest()})
                break
            else:
                raise ValueError('Missing native master: ' + table.name)
        assert not config.root.exists()
    return tables


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('data', type=Path)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--trials', type=int, default=5)
    args = parser.parse_args()
    if args.trials < 1:
        parser.error('--trials must be positive')
    if sys.version_info[:2] != (3, 12):
        parser.error('Use the prepared Python 3.12 interpreter')
    sys.path[:0] = ['source', 'source/server']
    tables = inventory(args.data)
    baseline = subprocess.check_output(
        ['git', 'show', args.baseline + ':source/ios_server/table_codec.py'], text=True)
    results, signature = {'before': [], 'after': []}, None
    for trial in range(args.trials):
        order = ('before', 'after') if trial % 2 == 0 else ('after', 'before')
        for implementation in order:
            request = {'tables': tables, 'implementation': implementation, 'codec': baseline}
            run = subprocess.run([sys.executable, '-B', '-c', WORKER], input=json.dumps(request),
                                 text=True, capture_output=True, check=True)
            sample = json.loads(run.stdout)
            if signature is None:
                signature = sample['signature']
            assert sample['signature'] == signature
            results[implementation].append(sample['metrics'])
            print(f'Completed trial {trial + 1}/{args.trials}: {implementation}', file=sys.stderr, flush=True)
    assert inventory(args.data) == tables, 'Shared inputs changed during comparison'
    summary = {label: {key: {'median': statistics.median(row[key] for row in samples),
                            'min': min(row[key] for row in samples), 'max': max(row[key] for row in samples)}
                       for key in samples[0]} for label, samples in results.items()}
    largest = max(tables, key=lambda row: row['size'])
    print(json.dumps({'python': sys.version, 'baseline': args.baseline, 'trials': args.trials,
                      'masters': len(tables), 'bytes': sum(row['size'] for row in tables),
                      'rows': sum(row['rows'] for row in tables),
                      'largest': {key: largest[key] for key in ('name', 'size', 'rows')},
                      'equal_normalized_bytes': True, 'samples': results, 'summary': summary}, indent=2))


if __name__ == '__main__':
    main()
