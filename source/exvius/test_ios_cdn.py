"""BDD for bounded ordinary CDN delivery in fresh iOS and legacy processes."""
import hashlib
from pathlib import Path
import unittest

import test_ios_server as harness


BOOT = '''
import builtins, hashlib, io, os, random, sys, tracemalloc
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
sys.path[:0] = sys.argv[1:3]
from ios_server.config import Configuration
from engine_profile import select_profile
config = Configuration(Path(sys.argv[3]), Path(sys.argv[4]))
select_profile(os.environ['EXVIUS_ENGINE_PROFILE'])
os.environ.update(config.engine_environment())
import capture_server as server
server.State.cdn_root = os.environ['CDN_ROOT']
server.State.cdn_overlay = os.environ['CDN_OVERLAY']
native = Path(server.State.cdn_root)
before = random.getstate()
def readonly(event, args):
    if event == 'open' and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
        raise AssertionError('CDN query attempted a write')
    if event in ('socket.bind', 'socket.connect'):
        raise AssertionError('CDN query attempted network access')
sys.addaudithook(readonly)
def fetch(path, method='GET', sink=None):
    result = server.Handler.__new__(server.Handler)
    result.path, result.command, result.headers = path, method, {}
    result.wfile = sink if sink is not None else io.BytesIO()
    result.response_headers = {}
    result.send_response = lambda code: setattr(result, 'status', code)
    result.send_header = lambda key, value: result.response_headers.update({key: value})
    result.end_headers = lambda: None
    result.send_error = lambda code, *args: setattr(result, 'status', code)
    result._cdn_fetch()
    return result
class Sink:
    def __init__(self):
        self.size = 0
        self.digest = hashlib.sha256()
    def write(self, raw):
        self.size += len(raw)
        self.digest.update(raw)
        return len(raw)
'''

UNCHANGED = '''
assert random.getstate() == before
assert server.State.player is None and server.State.requests == 0
assert not config.root.exists(), 'CDN query created runtime state'
'''


class OrdinaryCdnDelivery(unittest.TestCase):
    setUp = harness.IosServerBehavior.setUp
    child = harness.IosServerBehavior.child
    prepared_data = harness.IosServerBehavior.prepared_data
    write_masters = harness.IosServerBehavior.write_masters

    def check_profiles(self, script):
        for profile in ('ios-revival', 'legacy'):
            with self.subTest(profile=profile):
                result = self.child(BOOT + script + UNCHANGED, str(self.config.root), str(self.config.data),
                                    env={'EXVIUS_ENGINE_PROFILE': profile})
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def resource(self, relative, raw):
        path = self.config.data / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return path

    def test_given_large_pack_when_get_or_head_then_exact_response_uses_bounded_memory_without_writes(self):
        block = bytes(range(256)) * 4096
        path = self.config.data / 'client/files/common_lang/movie/Ver1_large.cpk'
        path.parent.mkdir(parents=True)
        digest = hashlib.sha256()
        with path.open('wb') as stream:
            for _ in range(8):
                stream.write(block); digest.update(block)
            stream.write(b'partial last block'); digest.update(b'partial last block')
        self.check_profiles('''
# Warm only imports; no response cache exists or is permitted.
fetch('/missing.cpk')
for method in ('GET', 'HEAD'):
    sink = Sink()
    tracemalloc.start()
    response = fetch('/common_lang/movie/Ver1_large.cpk', method, sink)
    _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
    assert response.status == 200 and response.close_connection
    assert response.response_headers == {'Content-Type': 'application/octet-stream',
        'Content-Length': ''' + repr(str(path.stat().st_size)) + ''', 'Connection': 'close'}
    assert sink.size == (''' + str(path.stat().st_size) + ''' if method == 'GET' else 0)
    if method == 'GET': assert sink.digest.hexdigest() == ''' + repr(digest.hexdigest()) + '''
    assert peak < 2 * 1024 * 1024, (method, peak)
''')

    def test_given_fallbacks_empty_and_unsafe_paths_when_queried_then_keep_selection_and_head_contracts(self):
        self.resource('client/files/pack.cpk', b'stock')
        self.resource('overlay/pack.cpk', b'overlay\x00\xff')
        self.resource('client/files/empty.cpk', b'')
        self.resource('client/files/mst/Ver2_fixture.dat', b'token fallback')
        self.resource('cpk_extract/en/banner/public.png', b'indexed artwork')
        secret = self.resource('outside.pem', b'private fixture')
        (self.config.data / 'client/files/mst/Ver1_secret.dat').symlink_to(secret)
        (self.config.data / 'overlay/secret.cpk').symlink_to(secret)
        self.check_profiles('''
art = str(config.data / 'cpk_extract/en/banner/public.png')
secret = str(config.data / 'outside.pem')
with patch.object(server, 'banner_art_index', return_value={'public.png': art, 'secret.png': secret}), \
     patch.object(server, 'area_art_index', return_value={}):
    for path, expected in (('/pack.cpk?version=1', b'overlay\\x00\\xff'), ('/empty.cpk', b''),
                           ('/mst/Ver999_fixture.dat', b'token fallback'),
                           ('/banner/public.png', b'indexed artwork'),
                           ('/en/content/userpolicysin/index_a.html', (Path(server.HERE) / 'webcontent/userpolicy.html').read_bytes())):
        for method in ('GET', 'HEAD'):
            response = fetch(path, method)
            assert response.status == 200, (path, response.status)
            assert response.response_headers['Content-Length'] == str(len(expected))
            assert response.wfile.getvalue() == (expected if method == 'GET' else b'')
    for path in ('/mst/Ver999_secret.dat', '/secret.cpk', '/banner/secret.png', '/missing.cpk',
                 '/%2e%2e/outside.pem', '/%5csecret.cpk', '/x%00.cpk'):
        for method in ('GET', 'HEAD'):
            response = fetch(path, method)
            assert response.status in (400, 404), (path, response.status)
            assert response.wfile.getvalue() == b''
''')

    def test_given_head_or_disconnected_client_when_served_then_no_head_read_and_descriptors_close(self):
        self.resource('client/files/pack.cpk', b'pack fixture')
        self.check_profiles('''
opened, reads = [], []
original = builtins.open
def tracked(path, *args, **kwargs):
    stream = original(path, *args, **kwargs)
    if str(path).endswith('/pack.cpk'):
        opened.append(stream)
        if method == 'HEAD':
            read = stream.read
            def counted_read(*args):
                reads.append(args)
                return read(*args)
            stream.read = counted_read
    return stream
class Disconnected:
    def write(self, raw): raise BrokenPipeError('client disconnected')
for method in ('HEAD', 'GET'):
    with patch.object(builtins, 'open', side_effect=tracked):
        response = fetch('/pack.cpk', method, Disconnected() if method == 'GET' else None)
    assert response.status == 200
    assert response.close_connection
    assert opened and all(stream.closed for stream in opened)
    assert not reads, 'HEAD read file contents'
assert fetch('/pack.cpk').wfile.getvalue() == b'pack fixture'
''')

    def test_given_concurrent_gets_when_served_then_each_has_independent_complete_bytes(self):
        self.resource('client/files/pack.cpk', bytes(range(256)) * 4097)
        self.check_profiles('''
expected = (native / 'pack.cpk').read_bytes()
with ThreadPoolExecutor(max_workers=4) as pool:
    replies = list(pool.map(lambda _: fetch('/pack.cpk'), range(8)))
assert all(reply.status == 200 and reply.wfile.getvalue() == expected for reply in replies)
''')

    def test_given_source_changes_after_headers_when_streaming_then_pin_open_file_and_advertised_length(self):
        self.resource('client/files/pack.cpk', b'original pack')
        self.resource('client/files/replacement.cpk', b'replacement')
        # The scenario itself changes disposable source files; the other scenarios
        # enforce write-free queries with an audit hook.
        script = BOOT.replace('sys.addaudithook(readonly)', '') + '''
pack = native / 'pack.cpk'
original = pack.read_bytes()
for change in ('grow', 'replace'):
    pack.write_bytes(original)
    replacement = native / 'replacement.cpk'
    replacement.write_bytes(b'replacement')
    def changed_headers(handler):
        if change == 'grow':
            with pack.open('ab') as stream: stream.write(b'appended after headers')
        else:
            os.replace(replacement, pack)
    # Exercise the real response header boundary rather than a pre-read buffer.
    handler = server.Handler.__new__(server.Handler)
    handler.path, handler.command, handler.headers = '/pack.cpk', 'GET', {}
    handler.wfile = io.BytesIO()
    headers = {}
    handler.send_response = lambda code: headers.update(status=code)
    handler.send_header = lambda key, value: headers.update({key: value})
    handler.end_headers = lambda: changed_headers(handler)
    handler._cdn_fetch()
    assert headers['status'] == 200 and headers['Content-Length'] == str(len(original))
    assert handler.wfile.getvalue() == original
''' + UNCHANGED
        for profile in ('ios-revival', 'legacy'):
            with self.subTest(profile=profile):
                result = self.child(script, str(self.config.root), str(self.config.data),
                                    env={'EXVIUS_ENGINE_PROFILE': profile})
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_given_native_wrapper_or_legacy_adapter_when_fetching_then_real_headers_and_save_are_preserved(self):
        static, _ = self.prepared_data()
        self.write_masters(static / 'mst_decoded')
        expected = bytes(range(256)) * 4097
        self.resource('client/files/pack.cpk', expected)
        for profile in ('ios-revival', 'legacy'):
            with self.subTest(profile=profile):
                result = self.child('''
import copy, os, random, sys
from pathlib import Path
from types import SimpleNamespace
sys.path[:0] = sys.argv[1:3]
from ios_server.config import Configuration
from local_game import LocalGame
config = Configuration(Path(sys.argv[3]), Path(sys.argv[4]))
if os.environ['EXVIUS_ENGINE_PROFILE'] == 'ios-revival':
    from ios_server.engine import Engine
    from ios_server.game_http import handler
    engine = Engine(config)
    server = engine.initialize()
    game = SimpleNamespace(server=SimpleNamespace(Handler=handler(server.Handler), STATE_LOCK=server.STATE_LOCK))
    save = config.state_file
else:
    engine = None
    game = LocalGame(config.data)
    server = game.server
    save = config.data / 'state/campaign.json'
try:
    expected = (config.data / 'client/files/pack.cpk').read_bytes()
    before, rng = copy.deepcopy(server.State.player.data), random.getstate()
    saved = save.read_bytes() if save.exists() else None
    def readonly(event, args):
        if event == 'open' and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            raise AssertionError('Asset query attempted a write')
        if event in ('socket.bind', 'socket.connect'):
            raise AssertionError('Asset query attempted network access')
    sys.addaudithook(readonly)
    for method in ('GET', 'HEAD'):
        response = LocalGame.request(game, method, '/pack.cpk')
        assert response.status == 200
        assert response.headers['Content-Length'] == str(len(expected))
        assert response.headers['Content-Type'] == 'application/octet-stream'
        assert response.headers['Connection'] == 'close'
        assert response.body == (expected if method == 'GET' else b'')
    assert server.State.player.data == before and random.getstate() == rng
    assert (save.read_bytes() if save.exists() else None) == saved
finally:
    if engine is not None: engine.close()
''', str(self.config.root), str(self.config.data), env={'EXVIUS_ENGINE_PROFILE': profile})
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
