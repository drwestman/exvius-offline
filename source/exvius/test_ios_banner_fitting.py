"""BDD for explicit summon fitting, immutable filenames and native projection."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import test_ios_preparation as native_harness
import test_ios_server as engine_harness
from PIL import Image
from ios_server import banner_fit as fit, banner_inputs as inputs, banner_snapshots as snapshots
from ios_server.banner_delivery import serve
from ios_server.config import Configuration
from ios_server.runtime import InstanceLock


def png(size=(640, 160), color=(80, 160, 240, 255)):
    out = io.BytesIO(); Image.new('RGBA', size, color).save(out, 'PNG')
    return out.getvalue()


class NativeBannerFit(unittest.TestCase):
    def test_given_paid_short_or_tall_art_when_fitted_then_keep_source_pixels_centered_without_scaling(self):
        for size, expected in (((640, 160), (640, 183)), ((640, 392), (1371, 392))):
            raw = png(size); result = fit.render(raw, 'paid')
            self.assertEqual(fit.inspect(result), expected)
            with Image.open(io.BytesIO(result)) as image:
                left, top = ((expected[0] - size[0]) // 2, (expected[1] - size[1]) // 2)
                self.assertEqual(image.crop((left, top, left + size[0], top + size[1])).tobytes(),
                                 Image.open(io.BytesIO(raw)).tobytes())

    def test_given_base_or_near_matching_art_when_fitted_then_preserve_exact_source_bytes(self):
        for size, mode in (((640, 392), 'base'), ((640, 183), 'paid'), ((640, 180), 'paid')):
            raw = png(size)
            self.assertEqual(fit.render(raw, mode), raw)
        self.assertEqual(fit.inspect(fit.render(png(), 'base')), (640, 392))

    def test_given_corrupt_or_non_png_when_fitted_then_fail_visibly(self):
        for raw in (b'', b'not PNG', png()[:-8]):
            with self.assertRaises(ValueError): fit.render(raw, 'paid')
        out = io.BytesIO(); Image.new('RGB', (10, 10)).save(out, 'JPEG')
        with self.assertRaises(ValueError): fit.render(out.getvalue(), 'paid')

    def test_given_catalogue_overrides_and_english_variants_when_collected_then_keep_original_identity_precedence(self):
        docs = {name:{'banners':[]} for name in inputs.DOCUMENTS}
        docs[inputs.DOCUMENTS[0]]['banners'] = [{'id':'1', 'art':{'detail_banner':'obsolete.png'}}]
        docs[inputs.DOCUMENTS[4]]['banners'] = [{'id':'1', 'art':{'banner':'main.png', 'detail_banner':'jp.png',
            'detail_banner_en':'english.PNG', 'detail_extra':['step.png']}}]
        docs[inputs.DOCUMENTS[5]]['banners'] = [{'id':'1', 'art':{'detail_banner':'ignored.png'}},
            {'id':'2', 'serve':False, 'art':{'detail_banner':'disabled.png'}}]
        wanted, count = inputs.names(docs, inputs.DEFAULT)
        self.assertEqual((wanted, count), (['english.PNG','jp.png','step.png'], 1))


class BannerSnapshotBehavior(unittest.TestCase):
    setUp = native_harness.NativePreparation.setUp
    child = engine_harness.IosServerBehavior.child

    def artwork(self, managed=False):
        self.documents = self.root/'documents'; self.documents.mkdir(exist_ok=True)
        docs = {name:{'banners':[]} for name in inputs.DOCUMENTS}
        docs[inputs.DOCUMENTS[0]]['banners'] = [
            {'id':'1', 'art':{'banner':'list.png', 'detail_banner':'short.png', 'detail_extra':['tall.png','missing.png']}},
            {'id':'2', 'art':{'banner':'list.png', 'detail_banner':'tall.png'}}]
        for name, doc in docs.items(): (self.documents/name).write_text(json.dumps(doc))
        self.enterContext(patch.object(inputs, 'HERE', self.documents))
        env = self.config.engine_environment()
        self.art = Path(env['ART_ROOT'])/'en/banner/pack'; self.art.mkdir(parents=True)
        (self.art/'short.png').write_bytes(png())
        (self.art/'tall.png').write_bytes(png((640,392)))
        (self.art/'list.png').write_bytes(png((600,120)))

    def pointer(self): return self.config.root/snapshots.POINTER

    def test_given_each_layout_when_prepared_then_publish_both_frames_without_source_or_query_writes(self):
        for managed in (False, True):
            with self.subTest(managed=managed):
                data = self.root/('data-'+str(managed))
                if managed: (data/'static').mkdir(parents=True)
                self.config = Configuration(self.root/('private-'+str(managed)), data)
                self.artwork(managed)
                before = {p:p.read_bytes() for p in data.rglob('*') if p.is_file()}; modules = set(sys.modules)
                report = snapshots.prepare(self.config); pack = snapshots.load(self.config)
                self.assertEqual((report['sources'],report['images'],report['missing']), (2,4,['missing.png']))
                self.assertFalse(report['gameplay_ready']); self.assertFalse(self.config.state_file.exists())
                self.assertEqual(len(pack.files),4)
                with patch.object(fit, 'render', side_effect=AssertionError('query fitted')), \
                        patch.object(Path, 'mkdir', side_effect=AssertionError('query wrote')):
                    self.assertTrue(snapshots.verify(self.config)['ok'])
                self.assertEqual(before, {p:p.read_bytes() for p in data.rglob('*') if p.is_file()})
                self.assertFalse({'capture_server','player_state','data_paths'} & (set(sys.modules)-modules))
                for row in pack.manifest['images'].values():
                    self.assertIn(hashlib.sha256(pack.files[row['path']]).hexdigest(), row['path'])

    def test_given_same_inputs_or_same_size_edits_when_prepared_then_reuse_or_publish_new_content_names(self):
        self.artwork(); (self.art/'short.png').write_bytes(png((10,10),(1,1,1,255)))
        snapshots.prepare(self.config); old = snapshots.load(self.config); pointer = self.pointer().read_bytes()
        self.assertFalse(snapshots.prepare(self.config)['prepared_now']); self.assertEqual(self.pointer().read_bytes(),pointer)
        edited = png((10,10),(2,2,2,255))
        self.assertEqual(len(edited), len((self.art/'short.png').read_bytes()))
        (self.art/'short.png').write_bytes(edited)
        self.assertFalse(snapshots.verify(self.config)['ok']); snapshots.prepare(self.config)
        new = snapshots.load(self.config)
        self.assertNotEqual(new.manifest['images']['paid:short.png']['path'],old.manifest['images']['paid:short.png']['path'])
        for relative, raw in old.files.items(): self.assertEqual((old.directory/relative).read_bytes(),raw)

    def test_given_missing_source_when_added_then_clear_gap_without_changing_unrelated_files(self):
        self.artwork(); snapshots.prepare(self.config); old = snapshots.load(self.config)
        (self.art/'missing.png').write_bytes(png((600,100)))
        report = snapshots.prepare(self.config); new = snapshots.load(self.config)
        self.assertEqual(report['missing'],[])
        self.assertEqual(new.manifest['images']['paid:short.png'],old.manifest['images']['paid:short.png'])

    def test_given_unsafe_metadata_or_source_symlink_when_prepared_then_refuse_without_publishing(self):
        self.artwork(); snapshots.prepare(self.config); before = self.pointer().read_bytes()
        path = self.art/'short.png'; raw = path.read_bytes(); path.unlink()
        outside = self.config.root/'private.png'; outside.write_bytes(raw); path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError,'escapes'): snapshots.prepare(self.config)
        path.unlink(); path.write_bytes(raw)
        doc = self.documents/inputs.DOCUMENTS[0]
        value = json.loads(doc.read_bytes()); value['banners'][0]['art']['detail_banner'] = '../private.png'; doc.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'filename'): snapshots.prepare(self.config)
        self.assertEqual(self.pointer().read_bytes(),before)

    def test_given_corrupt_source_or_invalid_render_when_preparing_then_keep_active_generation(self):
        self.artwork(); snapshots.prepare(self.config); before = self.pointer().read_bytes()
        source = self.art/'short.png'; source.write_bytes(b'broken')
        with self.assertRaises(ValueError): snapshots.prepare(self.config)
        source.write_bytes(png(color=(1,2,3,255)))
        with patch.object(fit,'render',return_value=png((1,1))),self.assertRaisesRegex(ValueError,'dimensions'):
            snapshots.prepare(self.config)
        self.assertEqual(self.pointer().read_bytes(),before)

    def test_given_exact_overlay_and_duplicate_basename_when_prepared_then_follow_native_url_precedence(self):
        self.artwork();env=self.config.engine_environment()
        original=inputs.collect(self.config)
        path=Path(env['CDN_OVERLAY'])/inputs.DETAIL_URL/'short.png';path.parent.mkdir(parents=True)
        path.write_bytes(png(color=(10,20,30,255)))
        selected=inputs.collect(self.config)
        self.assertNotEqual(selected.images['short.png'],original.images['short.png'])
        self.assertEqual(selected.sources['images']['short.png']['path'],str(path.relative_to(self.config.data)))

    def test_given_damaged_pointer_or_inventory_when_read_then_fail_without_repair(self):
        self.artwork();snapshots.prepare(self.config);before=self.pointer().read_bytes()
        ref=json.loads(before);ref['directory']='../private';self.pointer().write_text(json.dumps(ref))
        with self.assertRaises(ValueError):snapshots.load(self.config)
        self.pointer().write_bytes(before);pack=snapshots.load(self.config)
        doc=copy.deepcopy(pack.manifest);doc['images'].pop(next(iter(doc['images'])))
        raw=json.dumps(doc).encode();(pack.directory/'manifest.json').write_bytes(raw)
        ref=json.loads(before);ref['manifest_sha256']=hashlib.sha256(raw).hexdigest();self.pointer().write_text(json.dumps(ref))
        self.assertFalse(snapshots.verify(self.config)['ok'])

    def test_given_busy_runtime_when_preparing_then_refuse_before_publication(self):
        self.artwork()
        with InstanceLock(self.config.root),self.assertRaisesRegex(RuntimeError,'Another iOS'):
            snapshots.prepare(self.config)
        self.assertFalse(self.pointer().exists())

    def test_given_failed_image_write_or_pointer_when_preparing_then_preserve_and_retry(self):
        self.artwork(); snapshots.prepare(self.config); before = self.pointer().read_bytes()
        (self.art/'short.png').write_bytes(png(color=(1,2,3,255)))
        original = Path.open
        def opening(path,*args,**kwargs):
            if path.name.startswith('ios-fit-') and args and args[0]=='wb':raise OSError('image disk full')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',opening),self.assertRaisesRegex(OSError,'disk full'):snapshots.prepare(self.config)
        replace = os.replace
        def replacing(source,target):
            if Path(target)==self.pointer():raise OSError('pointer failure')
            return replace(source,target)
        with patch('ios_server.preparation.os.replace',replacing),self.assertRaisesRegex(OSError,'pointer failure'):
            snapshots.prepare(self.config)
        self.assertEqual(self.pointer().read_bytes(),before)
        self.assertTrue(snapshots.prepare(self.config)['prepared_now']);self.assertTrue(snapshots.verify(self.config)['ok'])

    def test_given_corrupt_or_escaping_published_image_when_verified_then_fail_without_repair(self):
        self.artwork(); snapshots.prepare(self.config); pack=snapshots.load(self.config)
        relative,raw=next(iter(pack.files.items()));path=pack.directory/relative
        path.write_bytes(b'broken');self.assertFalse(snapshots.verify(self.config)['ok']);self.assertEqual(path.read_bytes(),b'broken')
        path.unlink();outside=self.config.root/'outside.png';outside.write_bytes(raw);path.symlink_to(outside)
        self.assertFalse(snapshots.verify(self.config)['ok'])

    def test_given_native_layout_and_carousel_when_projected_then_fit_only_prepared_detail_fields(self):
        self.artwork();snapshots.prepare(self.config);pack=snapshots.load(self.config)
        spec={'PcUrGH13':[{'X1IuZnj2':'1','7xBNR2MH':'1'},{'X1IuZnj2':'2'}],
              'IC0ueV5s':[{'X1IuZnj2':'1','4yT7FUqj':'0:short.png','cost':'unchanged'},
                         {'X1IuZnj2':'2','4yT7FUqj':'0:tall.png'}],
              '4D5k8dpI':[{'X1IuZnj2':'1','4yT7FUqj':'list.png,0:short.png,1:tall.png,2:missing.png'}]}
        before=copy.deepcopy(spec);out=pack.project(spec)
        self.assertEqual(spec,before);self.assertEqual(pack.project(out),out)
        self.assertEqual(out['IC0ueV5s'][1]['4yT7FUqj'],'0:'+Path(pack.manifest['images']['base:tall.png']['path']).name)
        self.assertTrue(out['4D5k8dpI'][0]['4yT7FUqj'].startswith('list.png,0:ios-fit-'))
        self.assertTrue(out['4D5k8dpI'][0]['4yT7FUqj'].endswith(',2:missing.png'))
        self.assertEqual(out['IC0ueV5s'][0]['cost'],'unchanged')
        self.assertEqual(out['PcUrGH13'],spec['PcUrGH13'])

    def test_given_content_addressed_requests_when_served_then_exact_get_head_aliases_and_unknown_404(self):
        self.artwork();snapshots.prepare(self.config);pack=snapshots.load(self.config)
        entry=pack.manifest['images']['paid:short.png'];name=Path(entry['path']).name
        for method in ('GET','HEAD'):
            handler=type('Handler',(),{'command':method,'wfile':io.BytesIO(),'headers':{}})()
            handler.send_response=lambda value:setattr(handler,'status',value)
            handler.send_header=lambda key,value:handler.headers.update({key:value})
            handler.end_headers=lambda:None
            for prefix in ('banner/en/','en/','banner/common_lang/','common_lang/'):
                handler.wfile=io.BytesIO()
                self.assertTrue(serve(handler,pack,prefix+'sd/static_banner/gacha/sub/'+name))
                self.assertEqual(handler.status,200)
                self.assertEqual(handler.wfile.getvalue(),pack.files[entry['path']] if method=='GET' else b'')
                self.assertEqual(handler.headers['Content-Type'],'image/png')
            self.assertTrue(serve(handler,pack,snapshots.PREFIX+'ios-fit-'+'0'*64+'.png'));self.assertEqual(handler.status,404)
            self.assertFalse(serve(handler,pack,'banner/en/sd/static_banner/gacha/main/'+name))
        handler.command='POST';self.assertFalse(serve(handler,pack,entry['path']))

    def test_given_unconfigured_query_when_verified_then_no_directories_or_processes(self):
        with patch.object(Path,'mkdir',side_effect=AssertionError('write')):
            self.assertFalse(snapshots.verify(self.config)['ok'])
        self.assertFalse(self.config.root.exists())

    def test_given_cli_prepare_and_verify_when_run_then_stdout_is_one_json_document(self):
        self.artwork()
        script='''
import sys,json,io
from pathlib import Path
from contextlib import redirect_stdout
sys.path[:0]=sys.argv[1:3]
from ios_server import banner_inputs
from ios_server.cli import main
banner_inputs.HERE=Path(sys.argv[5])
for command in ('prepare-banners','verify-banners','prepare-banners'):
    out=io.StringIO()
    with redirect_stdout(out):code=main([command,'--root',sys.argv[3],'--data',sys.argv[4]])
    result=json.loads(out.getvalue());assert code==0 and result['images']==4,result
assert not {'capture_server','player_state','data_paths'}&set(sys.modules)
'''
        done=self.child(script,str(self.config.root),str(self.config.data),str(self.documents))
        self.assertEqual(done.returncode,0,done.stdout+done.stderr)


class PreparedBannerEngine(unittest.TestCase):
    setUp = native_harness.NativePreparation.setUp
    artwork = BannerSnapshotBehavior.artwork
    child = engine_harness.IosServerBehavior.child

    def test_given_prepared_engine_when_querying_entry_steps_and_boxes_then_fitted_native_names_resolve_without_query_writes(self):
        native_harness.NativePreparation.fixture(self)
        self.artwork()
        for relative in ('mst_decoded','text_decoded','client/files/common_lang'):
            (self.config.data/relative).mkdir(parents=True,exist_ok=True)
        engine_harness.IosServerBehavior.write_masters(self,self.config.data/'mst_decoded')
        prefix='''
import sys,json,os,copy
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=sys.argv[1:3]
sys.path.insert(0,str(Path(sys.argv[1])/'exvius'))
from ios_server.config import Configuration
from ios_server.engine import Engine
from ios_server import banner_inputs
banner_inputs.HERE=Path(sys.argv[5])
config=Configuration(Path(sys.argv[3]),Path(sys.argv[4]))
'''
        done=self.child(prefix+'''
engine=Engine(config)
try:engine.initialize_campaign()
finally:engine.close()
''',str(self.config.root),str(self.config.data),str(self.documents))
        self.assertEqual(done.returncode,0,done.stdout+done.stderr)
        from ios_server.preparation import prepare_data
        prepare_data(self.config);snapshots.prepare(self.config)
        done=self.child(prefix+'''
from local_game import LocalGame
from test_ios_summons import banner
from ios_server import banner_fit
import ffbe_crypto as crypto
engine=Engine(config,prepared=True)
try:
    server=engine.initialize();snapshot=engine.banners
    assert server.State.native_banners is snapshot
    endpoints=json.loads((Path(sys.argv[2])/'endpoints.json').read_text())['by_class']
    def request(name):
        ep=endpoints[name];key=crypto.key16(ep['encode_key'])
        body={'TEAYk6R1':{'z5hB3P01':ep['request_id'],'ytHoz4E2':'1','9K0Pzcpd':'1167'},
              't7n6cVWf':{'qrVcDe48':crypto.cbc_encrypt(key,b'{}',double_pad=True)}}
        response=LocalGame.request(engine,'POST',ep['url'],json.dumps(body));assert response.status==200
        encoded=json.loads(response.body)['t7n6cVWf']['qrVcDe48']
        return json.JSONDecoder().raw_decode(crypto.cbc_decrypt(key,encoded).decode())[0]
    request('InitializeRequest')
    import ffbe_gacha as gacha
    import gacha_box
    common={'banner':'list.png','detail_banner':'short.png','detail_extra':['tall.png']}
    rows=[banner(9800001,art=common),banner(9800002,art=dict(common,detail_banner='tall.png'),gacha_layout=0),
          banner(9800003,art=common,type='step',steps=[{'cost':{'kind':'lapis','amount':1}},{'cost':{'kind':'lapis','amount':2}}]),
          banner(9800004,art=common,boxes=[[],[]],box_base_id=800000)]
    saved=config.state_file.read_bytes();player=server.State.player;before=copy.deepcopy(player.data)
    query=True
    def guard(event,args):
        if not query:return
        if event.startswith('socket.'):raise AssertionError('query network')
        # Preserve the canonical POST request recorder; artwork and campaign writes remain forbidden.
        if event=='open' and len(args)>2 and isinstance(args[2],int) and args[2] & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):
            if not Path(args[0]).resolve().is_relative_to(config.root/'requests'):raise AssertionError('query write')
        if event in ('os.mkdir','os.rename','os.remove'):
            if event!='os.mkdir' or Path(args[0]).resolve()!=config.root/'requests':raise AssertionError('query filesystem mutation')
    sys.addaudithook(guard)
    with patch.object(gacha,'all_banners',return_value=rows),patch('gacha_archive.visible_banners',side_effect=lambda player,rows:rows),patch.object(banner_fit,'render',side_effect=AssertionError('query fitted')):
        out=request('GachaEntryRequest')
        def check(output):
            for row in output['IC0ueV5s']+output['4D5k8dpI']:
                for part in row['4yT7FUqj'].split(','):
                    if ':' not in part:assert part=='list.png';continue
                    name=part.split(':')[1];assert name.startswith('ios-fit-'),name
                    path='banner/en/sd/static_banner/gacha/sub/'+name
                    for method in ('GET','HEAD'):
                        response=LocalGame.request(engine,method,'/'+path)
                        assert response.status==200 and response.body==(snapshot.lookup(path) if method=='GET' else b'')
                        assert response.headers['Content-Length']==str(len(snapshot.lookup(path)))
        check(out)
        base=next(row for row in out['IC0ueV5s'] if row['X1IuZnj2']=='9800002')
        assert base['4yT7FUqj']=='0:'+Path(snapshot.manifest['images']['base:tall.png']['path']).name
        with patch.object(player,'gacha_step',return_value=1):
            next_step=gacha.gacha_groups([rows[2]]);check(next_step)
            assert next_step['IC0ueV5s'][0]['4yT7FUqj']=='0:'+Path(snapshot.manifest['images']['paid:tall.png']['path']).name
        assert config.state_file.read_bytes()==saved and player.data==before
        unknown='banner/en/sd/static_banner/gacha/sub/ios-fit-'+'0'*64+'.png'
        assert LocalGame.request(engine,'GET','/'+unknown).status==404
        assert LocalGame.request(engine,'GET','/banner/en/sd/static_banner/gacha/sub/%2e%2e/private.png').status==400
        query=False
        next_box=gacha_box.next_box({}, {'5yLD4dYI':[{'X1IuZnj2':'9800004','nqzG3b2v':gacha_box.detail_id(player,rows[3])}]})
        check(next_box)
finally:engine.close()
assert server.State.native_banners is None
''',str(self.config.root),str(self.config.data),str(self.documents))
        self.assertEqual(done.returncode,0,done.stdout[-6000:]+done.stderr)
        (self.art/'short.png').write_bytes(png(color=(1,2,3,255)))
        done=self.child(prefix+'''
from ios_server.runtime import InstanceLock
engine=Engine(config,prepared=True)
try:engine.initialize()
except ValueError as exc:assert 'stale' in str(exc),str(exc)
else:raise AssertionError('stale artwork accepted')
assert not {'capture_server','data_paths','player_state'}&set(sys.modules)
assert engine.banners is None
with InstanceLock(config.root):pass
''',str(self.config.root),str(self.config.data),str(self.documents))
        self.assertEqual(done.returncode,0,done.stdout+done.stderr)


if __name__=='__main__':unittest.main()
