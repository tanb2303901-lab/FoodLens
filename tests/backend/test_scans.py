"""Synthetic adapter/HTTP fixtures test orchestration, never model accuracy."""
import asyncio
import io
import json
import unittest
from uuid import UUID,uuid4
from unittest.mock import patch
import httpx
import jwt
from PIL import Image
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.images import canonical_image
from backend.app.predictor import ClassMap,PredictorInfo,RawDetection
from backend.app.errors import ApiError
from backend.app.auth import UserContext
from backend.app.scan_writer import object_path
from backend.app.cursor import TimeCursor
from test_core import settings,token,USER_A,USER_B,RICE,OTHER,SECRET

SID='60000000-0000-4000-8000-000000000001'
DID='61000000-0000-4000-8000-000000000001'
NOW='2026-10-15T00:00:00Z'
SERVICE=jwt.encode({'role':'service_role'},SECRET,algorithm='HS256')


def image_bytes(fmt='PNG',size=(3,2)):
    out=io.BytesIO(); Image.new('RGB',size,'red').save(out,format=fmt); return out.getvalue()


def row(id=SID,owner=USER_A,status='completed'):
    d=dict(detection_id=DID,predicted_food_id=RICE,training_class_id=25,original_class_id=25,bbox=[0.,0.,1.,1.],confidence=.8)
    return dict(id=id,user_id=owner,status=status,input_source='gallery',revision=2,created_at=NOW,updated_at=NOW,
                model_version='SYNTHETIC_TEST_FIXTURE',class_map_version=ClassMap().version,detections=[d] if status=='completed' else [],
                confirmations=[],image_path=f'{owner}/{id}/{uuid4()}.jpg',error_code=None)


class TestAdapter:
    __test__=False
    def __init__(self,behavior='good',compatible=True):
        m=ClassMap(); self.info=PredictorInfo('SYNTHETIC_TEST_ONLY',m.version,m.digest if compatible else '0'*64)
        self.behavior=behavior; self.calls=0
    def status(self): return self.info
    async def predict(self,image,info):
        self.calls+=1
        assert info==self.info
        if self.behavior=='error': raise RuntimeError('SYNTHETIC SECRET MUST NOT LEAK')
        if self.behavior=='slow': await asyncio.sleep(1)
        if self.behavior=='empty': return []
        if self.behavior=='invalid': return [{'training_class_id':67,'bbox':[0.,0.,1.,1.],'confidence':.8}]
        return [RawDetection(training_class_id=27,bbox=[.1,.1,.9,.9],confidence=.8)]


class ImageTests(unittest.TestCase):
    def test_static_formats_decode_into_canonical_jpeg(self):
        for fmt,mime in [('PNG','image/png'),('JPEG','image/jpeg'),('WEBP','image/webp')]:
            image=canonical_image(image_bytes(fmt),mime,settings())
            with Image.open(io.BytesIO(image.data)) as decoded:
                self.assertEqual((decoded.format,decoded.mode,decoded.size),('JPEG','RGB',(3,2)))
        self.assertEqual(canonical_image(image_bytes(),'IMAGE/PNG; charset=binary',settings()).width,3)
    def test_corrupt_unsupported_mime_and_spoof(self):
        for raw,mime,status in [(b'corrupt','image/png',422),(image_bytes(),'text/plain',415),
                                (image_bytes('JPEG'),'image/png',415),(image_bytes('BMP'),'image/jpeg',415)]:
            with self.assertRaises(ApiError) as error: canonical_image(raw,mime,settings())
            self.assertEqual(error.exception.status,status)
    def test_byte_pixel_dimension_and_decoder_bomb_limits(self):
        for limits in [dict(image_max_bytes=10),dict(image_max_pixels=5),dict(image_max_dimension=2)]:
            with self.assertRaises(ApiError) as error: canonical_image(image_bytes(),'image/png',settings(**limits))
            self.assertEqual(error.exception.status,413)
        with patch.object(Image,'MAX_IMAGE_PIXELS',1):
            with self.assertRaises(ApiError) as error: canonical_image(image_bytes(),'image/png',settings())
            self.assertEqual(error.exception.status,413)
    def test_exif_orientation_and_private_metadata_removed(self):
        image=Image.new('RGB',(3,2),'red'); exif=Image.Exif(); exif[274]=6; exif[270]='SYNTHETIC PRIVATE DATA'
        out=io.BytesIO(); image.save(out,'JPEG',exif=exif)
        canonical=canonical_image(out.getvalue(),'image/jpeg',settings())
        self.assertEqual((canonical.width,canonical.height),(2,3))
        with Image.open(io.BytesIO(canonical.data)) as decoded: self.assertEqual(len(decoded.getexif()),0)
        self.assertNotIn(b'SYNTHETIC PRIVATE DATA',canonical.data)
    def test_animated_png_is_rejected(self):
        out=io.BytesIO(); Image.new('RGB',(2,2),'red').save(out,'PNG',save_all=True,append_images=[Image.new('RGB',(2,2),'blue')],duration=100)
        with self.assertRaises(ApiError) as error: canonical_image(out.getvalue(),'image/png',settings())
        self.assertEqual(error.exception.status,415)
    def test_transparent_pixels_are_composited_white(self):
        out=io.BytesIO(); Image.new('RGBA',(3,2),(255,0,0,0)).save(out,'PNG')
        canonical=canonical_image(out.getvalue(),'image/png',settings())
        with Image.open(io.BytesIO(canonical.data)) as decoded: self.assertEqual(decoded.getpixel((0,0)),(255,255,255))


class AdapterTests(unittest.TestCase):
    def test_training27_maps_to_original28_and_no_invented_top3(self):
        m=ClassMap(); d=m.detections([{'training_class_id':27,'bbox':[0.,0.,1.,1.],'confidence':.5}])[0]
        self.assertEqual(d['original_class_id'],28); self.assertEqual(d['predicted_food_id'],OTHER)
        self.assertNotIn('alternatives',d)
    def test_explicit_alternatives_preserve_supplied_scores(self):
        m=ClassMap(); d=m.detections([dict(training_class_id=25,bbox=[0.,0.,1.,1.],confidence=.8,
                                        alternatives=[dict(training_class_id=27,confidence=.2)])])[0]
        self.assertEqual(d['alternatives'],[dict(food_id=OTHER,confidence=.2)])
    def test_invalid_raw_outputs_and_geometry_rejected(self):
        base=dict(training_class_id=25,bbox=[0.,0.,1.,1.],confidence=.8)
        for data in [base|{'training_class_id':67},base|{'training_class_id':True},base|{'confidence':float('nan')},
                     base|{'bbox':[.8,0.,.2,1.]},base|{'bbox':[0.,0.,2.,1.]}]:
            with self.assertRaises(ApiError): ClassMap().detections([data])
    def test_class_map_digest_and_model_info_must_match(self):
        m=ClassMap()
        self.assertFalse(m.compatible(PredictorInfo('version','wrong',m.digest)))
        self.assertFalse(m.compatible(PredictorInfo('version',m.version,'0'*64)))
        self.assertFalse(m.compatible(PredictorInfo('',m.version,m.digest)))
    def test_service_credential_hidden_and_foreign_paths_denied(self):
        s=settings(scan_service_key=SERVICE); self.assertNotIn(SERVICE,repr(s))
        context=UserContext(UUID(USER_A),'SYNTHETIC_USER_TOKEN')
        for path in [f'{USER_B}/{SID}/{uuid4()}.jpg',f'{USER_A}/{SID}/../bad.jpg',f'{USER_A}/{uuid4()}/{uuid4()}.jpg']:
            with self.assertRaises(ApiError): object_path(context,UUID(SID),path)


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.seen=[]; self.rows={}; self.upload_fail=False; self.finish_lost=False; self.cleanup_fail=False
        self.uploaded=False; self.deleted=False; self.missing_image=False; self.sign_error=False; self.bad_sign_origin=False; self.raw_failure=False
        def upstream(req):
            self.seen.append(req)
            if req.url.path.endswith('/core_readiness'): return httpx.Response(200,json=True)
            role=jwt.decode(req.headers['authorization'][7:],SECRET,algorithms=['HS256'],options={'verify_aud':False})
            path=req.url.path; args=json.loads(req.content) if req.content and req.headers.get('content-type','').startswith('application/json') else {}
            if path.endswith('/start_scan'):
                self.assertEqual(role['role'],'service_role'); id=args['p_scan_id']
                current=row(id,args['p_owner'],'processing'); current.update(revision=1,image_path=args['p_image_path'],input_source=args['p_input_source'])
                self.rows[id]=current; return httpx.Response(200,json=current)
            if path.endswith('/finish_scan'):
                self.assertEqual(role['role'],'service_role'); current=self.rows.get(args['p_scan_id'])
                if not current or current['status']!='processing': return httpx.Response(400,json={'code':'P0001','message':'NOT_FOUND'})
                current.update(status='failed' if args.get('p_error_code') else 'completed',detections=args['p_detections'],revision=2,
                               model_version=args['p_model_version'],class_map_version=args['p_class_map_version'],error_code=args.get('p_error_code'))
                if self.finish_lost and current['status']=='completed': return httpx.Response(503,json={'message':'SYNTHETIC LOST RESPONSE'})
                return httpx.Response(200,json=current)
            if path.endswith('/confirm_scan'):
                current=self.rows.get(args['p_scan_id'])
                code=None
                if not current or current['user_id']!=role.get('sub'): code='NOT_FOUND'
                elif current['status']!='completed': code='SCAN_NOT_COMPLETED'
                elif current['revision']!=args['p_expected_revision']: code='VERSION_CONFLICT'
                elif any(c['detection_id']!=DID for c in args['p_request']['confirmations']): code='INVALID_CONFIRMATION'
                if code: return httpx.Response(400,json={'code':'P0001','message':code})
                current.update(revision=current['revision']+1,confirmations=[dict(detection_id=c['detection_id'],confirmed_food_id=c['food_id']) for c in args['p_request']['confirmations']])
                return httpx.Response(200,json=current)
            if path.endswith('/scans'):
                if self.raw_failure: return httpx.Response(503,json={'message':'SYNTHETIC STATE QUERY FAILURE'})
                values=[r for r in self.rows.values() if 'eq.'+r['user_id']==req.url.params['user_id']]
                if 'id' in req.url.params: values=[r for r in values if 'eq.'+r['id']==req.url.params['id']]
                columns=req.url.params['select'].split(',')
                return httpx.Response(200,json=[{k:r[k] for k in columns} for r in values])
            if '/object/sign/' in path:
                self.assertEqual(role['role'],'authenticated')
                if self.missing_image: return httpx.Response(400,json={'statusCode':'404','message':'Object not found'})
                if self.sign_error: return httpx.Response(503,json={'message':'SYNTHETIC STORAGE SECRET'})
                value=path[len('/storage/v1'):]+ '?token=SYNTHETIC_SIGNED_TEST_TOKEN'
                if self.bad_sign_origin: value='https://attacker.invalid'+value
                return httpx.Response(200,json={'signedURL':value})
            if path.endswith('/object/food-scans') and req.method=='DELETE':
                self.assertEqual(role['role'],'service_role')
                if self.cleanup_fail: return httpx.Response(503,json={'message':'SYNTHETIC CLEANUP FAILED'})
                self.deleted=True; self.uploaded=False; return httpx.Response(200,json=[])
            if '/object/food-scans/' in path:
                self.assertEqual(role['role'],'service_role')
                if self.upload_fail: return httpx.Response(503,json={'message':'SYNTHETIC UPLOAD SECRET'})
                with Image.open(io.BytesIO(req.content)) as image: self.assertEqual(image.format,'JPEG')
                self.uploaded=True; return httpx.Response(200,json={'key':'fixture'})
            return httpx.Response(500,json={'message':'UNEXPECTED TEST REQUEST'})
        self.transport=httpx.MockTransport(upstream)
        self.client=None
    def start(self,adapter=None,**overrides):
        self.client=TestClient(create_app(settings(**({'scan_service_key':SERVICE}|overrides)),self.transport,predictor=adapter))
        self.client.__enter__(); return self.client
    def tearDown(self):
        if self.client: self.client.__exit__(None,None,None)
    def headers(self): return {'Authorization':'Bearer '+token()}
    def analyze(self,raw=None,mime='image/png',data=None):
        return self.client.post('/v1/scans/analyze',headers=self.headers(),files={'file':('ignored-client-path.png',image_bytes() if raw is None else raw,mime)},data=data or {})
    def detail(self): return self.client.get('/v1/scans/'+SID,headers=self.headers())

    def test_auth_then_missing_model_precedes_multipart_and_no_writes(self):
        self.start()
        self.assertEqual(self.client.post('/v1/scans/analyze',content=b'bad').status_code,401)
        with patch('backend.app.scans.read_upload',side_effect=AssertionError('must not parse')):
            r=self.client.post('/v1/scans/analyze',headers=self.headers(),content=b'bad')
        self.assertEqual(r.status_code,503); self.assertEqual(r.json()['error']['code'],'MODEL_NOT_READY')
        self.assertEqual(self.seen,[]); self.assertEqual(self.rows,{})
    def test_wrong_class_map_is_not_ready(self):
        self.start(TestAdapter(compatible=False)); r=self.analyze()
        self.assertEqual(r.json()['error']['code'],'MODEL_NOT_READY'); self.assertEqual(self.seen,[])
    def test_missing_map_does_not_disable_core_readiness(self):
        with patch('backend.app.scans.ClassMap',side_effect=ValueError('SYNTHETIC_INVALID_MAP')): self.start()
        r=self.client.get('/health/ready')
        self.assertEqual(r.status_code,200); self.assertEqual(r.json()['model'],'not_ready')
        self.assertEqual(self.analyze().json()['error']['code'],'MODEL_NOT_READY')
    def test_missing_service_credential_does_not_enable_scan(self):
        self.start(TestAdapter(),scan_service_key=None)
        self.assertFalse(self.client.get('/health/ready').json()['capabilities']['scan'])
        self.assertEqual(self.analyze().status_code,503)
        self.assertFalse(any('/start_scan' in r.url.path for r in self.seen))
    def test_validated_test_pipeline_maps_food_and_private_url(self):
        adapter=TestAdapter(); self.start(adapter); r=self.analyze(data={'input_source':'camera'})
        self.assertEqual(r.status_code,201); self.assertEqual(r.headers['etag'],'"2"')
        value=r.json(); self.assertEqual(value['detections'][0]['original_class_id'],28)
        self.assertEqual(value['detections'][0]['predicted_food_id'],OTHER); self.assertEqual(value['input_source'],'camera')
        self.assertNotIn('image_path',value); self.assertNotIn('user_id',value)
        self.assertEqual(adapter.calls,1); self.assertTrue(self.uploaded)
    def test_empty_supplied_output_not_replaced_with_fake_predictions(self):
        self.start(TestAdapter('empty')); r=self.analyze()
        self.assertEqual(r.status_code,201); self.assertEqual(r.json()['detections'],[])
    def test_corrupt_image_or_unsafe_form_prevents_all_writes(self):
        adapter=TestAdapter(); self.start(adapter)
        self.assertEqual(self.analyze(raw=b'corrupt').status_code,422)
        self.assertEqual(self.analyze(data={'user_id':USER_B}).status_code,422)
        self.assertEqual(self.analyze(data={'input_source':'invalid'}).status_code,422)
        self.assertEqual(adapter.calls,0); self.assertEqual(self.seen,[])
    def test_multipart_byte_bound_enforced_before_decode(self):
        self.start(TestAdapter(),image_max_bytes=1024)
        r=self.analyze(raw=b'X'*(1024+65537))
        self.assertEqual(r.status_code,413); self.assertEqual(self.seen,[])
    def test_upload_failure_marks_failed_without_predictions(self):
        adapter=TestAdapter(); self.start(adapter); self.upload_fail=True; r=self.analyze()
        self.assertEqual(r.status_code,503); self.assertEqual(adapter.calls,0)
        current=next(iter(self.rows.values())); self.assertEqual(current['status'],'failed'); self.assertEqual(current['detections'],[])
        self.assertTrue(self.deleted); self.assertNotIn('UPLOAD SECRET',r.text)
    def test_predictor_failure_and_invalid_output_compensated(self):
        self.start(TestAdapter('error')); r=self.analyze()
        self.assertEqual(r.status_code,503); self.assertTrue(self.deleted); self.assertNotIn('MUST NOT LEAK',r.text)
        self.assertEqual(next(iter(self.rows.values()))['error_code'],'PREDICTION_FAILED')
    def test_invalid_output_not_completed(self):
        self.start(TestAdapter('invalid')); r=self.analyze()
        self.assertEqual(r.json()['error']['code'],'PREDICTION_INVALID_OUTPUT')
        self.assertEqual(next(iter(self.rows.values()))['status'],'failed'); self.assertTrue(self.deleted)
    def test_prediction_timeout_marked_failed(self):
        self.start(TestAdapter('slow'),prediction_timeout=.1); r=self.analyze()
        self.assertEqual(r.status_code,504); self.assertEqual(next(iter(self.rows.values()))['error_code'],'PREDICTION_TIMEOUT')
    def test_lost_finish_response_preserves_completed_image(self):
        self.start(TestAdapter()); self.finish_lost=True; r=self.analyze()
        self.assertEqual(r.status_code,201); self.assertTrue(self.uploaded); self.assertFalse(self.deleted)
    def test_unknown_completion_state_never_deletes_saved_image(self):
        self.start(TestAdapter()); self.finish_lost=True; self.raw_failure=True; r=self.analyze()
        self.assertEqual(r.status_code,503); self.assertEqual(r.json()['error']['code'],'SCAN_STATE_UNCERTAIN')
        self.assertTrue(self.uploaded); self.assertFalse(self.deleted)
    def test_failed_cleanup_retains_failed_record_and_private_image(self):
        self.start(TestAdapter('error')); self.cleanup_fail=True; r=self.analyze()
        self.assertEqual(r.status_code,503); self.assertEqual(next(iter(self.rows.values()))['status'],'failed')
        self.assertTrue(self.uploaded); self.assertFalse(self.deleted)
    def test_detail_signs_only_owned_image_and_drops_private_columns(self):
        self.start(); self.rows[SID]=row(); r=self.detail()
        self.assertEqual(r.status_code,200); self.assertNotIn('image_path',r.json()); self.assertEqual(r.headers['etag'],'"2"')
        signed=[req for req in self.seen if '/object/sign/' in req.url.path][0]
        # Compare with the actual request token; a new token can cross a second.
        self.assertEqual(signed.headers['authorization'],r.request.headers['authorization'])
    def test_public_supabase_origin_rewrites_only_returned_image_url(self):
        self.start(); self.rows[SID]=row(); default=self.detail().json()['image_url']
        self.assertTrue(default.startswith('http://127.0.0.1:54321/storage/v1/object/sign/'))
        self.client.__exit__(None,None,None); self.seen.clear()
        self.start(public_supabase_url='http://10.0.2.2:54321'); r=self.detail()
        url=r.json()['image_url']
        self.assertTrue(url.startswith('http://10.0.2.2:54321/storage/v1/object/sign/'))
        self.assertEqual(url.split('54321',1)[1],default.split('54321',1)[1])
        signed=[req for req in self.seen if '/object/sign/' in req.url.path][0]
        self.assertEqual(signed.url.host,'127.0.0.1')
        for bad in ['ftp://10.0.2.2:54321','http://10.0.2.2:54321/path','http://user:pw@10.0.2.2:54321']:
            with self.assertRaises(ValueError): settings(public_supabase_url=bad)
    def test_cross_owner_returns_404_without_signing(self):
        self.start(); self.rows[SID]=row(owner=USER_B); r=self.detail()
        self.assertEqual(r.status_code,404); self.assertFalse(any('/object/sign/' in r.url.path for r in self.seen))
    def test_corrupt_path_never_signed(self):
        self.start(); self.rows[SID]=row(); self.rows[SID]['image_path']=row(owner=USER_B)['image_path']
        self.assertEqual(self.detail().status_code,503); self.assertFalse(any('/object/sign/' in r.url.path for r in self.seen))
    def test_missing_image_url_null_and_storage_errors_safe(self):
        self.start(); self.rows[SID]=row(); self.missing_image=True
        self.assertIsNone(self.detail().json()['image_url'])
        self.missing_image=False; self.sign_error=True; r=self.detail()
        self.assertEqual(r.status_code,503); self.assertNotIn('STORAGE SECRET',r.text)
    def test_foreign_sign_origin_rejected(self):
        self.start(); self.rows[SID]=row(); self.bad_sign_origin=True
        self.assertEqual(self.detail().status_code,503)
    def test_confirmation_preserves_detections_and_writes_nothing_else(self):
        self.start(); self.rows[SID]=row(); original=self.rows[SID]['detections'].copy()
        r=self.client.patch('/v1/scans/'+SID+'/result',headers=self.headers()|{'If-Match':'"2"'},json={'confirmations':[dict(detection_id=DID,food_id=OTHER)]})
        self.assertEqual(r.status_code,200); self.assertEqual(r.headers['etag'],'"3"'); self.assertEqual(r.json()['detections'],original)
        self.assertTrue(all(q.method=='GET' or q.url.path.endswith('/rpc/confirm_scan') or '/object/sign/' in q.url.path for q in self.seen))
    def test_confirm_header_duplicates_unknown_input_and_pending_state(self):
        self.start(); self.rows[SID]=row(status='processing'); url='/v1/scans/'+SID+'/result'
        self.assertEqual(self.client.patch(url,headers=self.headers(),json={'confirmations':[]}).status_code,428)
        self.assertEqual(self.client.patch(url,headers=self.headers()|{'If-Match':'"2"'},json={'confirmations':[]}).status_code,409)
        duplicate=dict(detection_id=DID,food_id=OTHER)
        self.assertEqual(self.client.patch(url,headers=self.headers()|{'If-Match':'"2"'},json={'confirmations':[duplicate,duplicate]}).status_code,422)
        self.assertEqual(self.client.patch(url,headers=self.headers()|{'If-Match':'"2"'},json={'detections':[]}).status_code,422)
    def test_history_scope_cursor_does_not_accept_other_scope_cursor(self):
        self.start(); self.rows[SID]=row()
        c=TimeCursor(settings().cursor_secret,'other:eaten_at,id:desc','eaten_at').encode(USER_A,None,None,__import__('datetime').datetime.fromisoformat(NOW.replace('Z','+00:00')),SID)
        r=self.client.get('/v1/scans',headers=self.headers(),params={'cursor':c})
        self.assertEqual(r.status_code,422)
    def test_openapi_10_paths_and_multipart_contract(self):
        self.start(); spec=self.client.get('/openapi.json').json()
        self.assertEqual(len(spec['paths']),10); self.assertEqual(sum(len(v) for v in spec['paths'].values()),11)
        schema=spec['paths']['/v1/scans/analyze']['post']['requestBody']['content']['multipart/form-data']['schema']
        self.assertEqual(schema['required'],['file']); self.assertFalse(schema['additionalProperties'])


if __name__=='__main__': unittest.main()
