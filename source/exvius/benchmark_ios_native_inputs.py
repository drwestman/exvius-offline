"""Compare read-only native input collection with a Git baseline on Python 3.12.

Run from the repository root. Fresh workers distinguish the first collection
from a repeat with warm process-local metadata. The OS file cache is not evicted.
No campaign, prepared generation, network connection or disk cache is created.
"""
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile


WORKER = r'''
import gc, hashlib, json, os, sys, time, types
from pathlib import Path
sys.path[:0] = ['source', 'source/server']
from ios_server.config import Configuration
from ios_server.native_inputs import collect
request = json.load(sys.stdin)
if request['implementation'] == 'before':
    module = types.ModuleType('baseline_native_inputs')
    exec(compile(request['baseline'], 'baseline_native_inputs.py', 'exec'), module.__dict__)
    collect = module.collect
config = Configuration(Path(request['root']), Path(request['data']))
scans = 0
def readonly(event, args):
    global scans
    if event == 'os.scandir':
        scans += 1
    if event == 'open' and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
        raise AssertionError('Benchmark attempted a file write')
    if event in ('os.mkdir', 'os.remove', 'os.rename', 'os.rmdir', 'socket.bind', 'socket.connect', 'subprocess.Popen'):
        raise AssertionError('Benchmark attempted a filesystem mutation, network access or process launch')
sys.addaudithook(readonly)
metrics, signatures = {}, []
for condition in ('first', 'warm'):
    gc.collect(); scans = 0
    start = time.perf_counter()
    sources, records, fingerprint, context, labels = collect(config)
    metrics[condition + '_seconds'] = time.perf_counter() - start
    metrics[condition + '_directory_scans'] = scans
    # Compare every byte and returned fact outside the timed collection.
    facts = {'sources': {name: [version, hashlib.sha256(raw).hexdigest()]
                         for name, (version, raw) in sources.items()},
             'records': records, 'fingerprint': fingerprint, 'context': context, 'labels': labels}
    signatures.append(hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest())
    tables, size = len(sources), sum(len(raw) for _, raw in sources.values())
    del sources, records, context, labels, facts
assert signatures[0] == signatures[1], 'Inputs changed between collections'
assert not {'capture_server', 'data_paths', 'ffbe_state', 'player_state'} & set(sys.modules)
assert not config.root.exists()
print(json.dumps({'metrics': metrics, 'signature': signatures[0], 'tables': tables, 'bytes': size}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('data', type=Path)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--trials', type=int, default=7)
    args = parser.parse_args()
    if args.trials < 1:
        parser.error('--trials must be positive')
    if sys.version_info[:2] != (3, 12):
        parser.error('Use the prepared Python 3.12 interpreter')
    baseline = subprocess.check_output(
        ['git', 'show', args.baseline + ':source/ios_server/native_inputs.py'], text=True)
    results, signature = {'before': [], 'after': []}, None
    with tempfile.TemporaryDirectory(prefix='bolt-inputs-') as temp:
        for trial in range(args.trials):
            order = ('before', 'after') if trial % 2 == 0 else ('after', 'before')
            for implementation in order:
                request = {'implementation': implementation, 'baseline': baseline,
                           'data': str(args.data.resolve()), 'root': str(Path(temp) / 'runtime')}
                run = subprocess.run([sys.executable, '-B', '-c', WORKER], input=json.dumps(request),
                                     text=True, capture_output=True, check=True)
                sample = json.loads(run.stdout)
                if signature is None:
                    signature = sample['signature']
                assert sample['signature'] == signature, 'Collection outputs differ'
                results[implementation].append(sample['metrics'])
                print(f'Completed trial {trial + 1}/{args.trials}: {implementation}', file=sys.stderr, flush=True)
    summary = {label: {key: {'median': statistics.median(row[key] for row in samples),
                            'min': min(row[key] for row in samples), 'max': max(row[key] for row in samples)}
                       for key in samples[0]} for label, samples in results.items()}
    print(json.dumps({'python': sys.version, 'baseline': args.baseline, 'trials': args.trials,
                      'tables': sample['tables'], 'bytes': sample['bytes'], 'equal_outputs': True,
                      'samples': results, 'summary': summary}, indent=2))


if __name__ == '__main__':
    main()
