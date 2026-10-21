"""BE-03 real Auth/Storage/scan API checks with labeled synthetic stored fixtures.

Default runtime never enables a fake detector. Analyze is tested as MODEL_NOT_READY.
Seeded scans test history/confirmation/ownership, not real inference or accuracy.
"""
from datetime import datetime,timezone
import io
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import uuid
import httpx
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
RICE='89cde1f5-b817-541d-b122-a6084f566261'
OTHER='5a4c8735-e6fc-5ec1-879a-222752d7adec'


def main():
    local=json.loads((ROOT/'data/processed/supabase-local.json').read_text(encoding='utf-8-sig'))
    if local['API_URL']!='http://127.0.0.1:54321': raise ValueError('Local integration only')
    with socket.socket() as reserved: reserved.bind(('127.0.0.1',0)); port=reserved.getsockname()[1]
    origin=f'http://127.0.0.1:{port}'
    log=(ROOT/'data/processed/BE-03-integration-server.log').open('w',encoding='utf-8')
    proc=subprocess.Popen([sys.executable,'-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port',str(port),'--no-access-log'],
        cwd=ROOT,env=dict(os.environ,FOODLENS_CONFIG_PATH=str(ROOT/'data/processed/backend-local.json')),
        stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    users=[]; objects=[]; checks=[]
    admin={'apikey':local['ANON_KEY'],'Authorization':'Bearer '+local['SERVICE_ROLE_KEY']}
    out=io.BytesIO(); Image.new('RGB',(2,2),'red').save(out,'PNG'); png=out.getvalue()
    def check(name,condition):
        if not condition: raise AssertionError(name)
        checks.append(name)
    def ok(response):
        if response.status_code>=400: raise RuntimeError('Local fixture operation failed; HTTP '+str(response.status_code))
        return response.json()
    try:
        with httpx.Client(timeout=10,trust_env=False) as client:
            for _ in range(60):
                if proc.poll() is not None: raise RuntimeError('Temporary backend exited')
                try:
                    if client.get(origin+'/health').status_code==200: break
                except httpx.HTTPError: pass
                time.sleep(.2)
            else: raise RuntimeError('Temporary server startup timeout')
            tokens=[]
            for label in ('a','b'):
                email=f'be03-{uuid.uuid4().hex}-{label}@example.invalid'; password=secrets.token_urlsafe(32)
                account=ok(client.post(local['API_URL']+'/auth/v1/admin/users',headers=admin,json=dict(email=email,password=password,email_confirm=True,app_metadata={'be03_test':True})))
                users.append(account['id'])
                session=ok(client.post(local['API_URL']+'/auth/v1/token?grant_type=password',headers={'apikey':local['ANON_KEY']},json=dict(email=email,password=password)))
                tokens.append(session['access_token'])
            a,b=tokens
            def headers(token=a): return {'Authorization':'Bearer '+token}
            def api(method,path,token=a,data=None,params=None,match=None):
                h=headers(token)
                if match: h['If-Match']=match
                return client.request(method,origin+path,headers=h,json=data,params=params)
            ready=client.get(origin+'/health/ready').json()
            check('missing_model_readiness_truthful',ready['model']=='not_ready' and ready['capabilities']==dict(catalog=True,scan=False))
            check('anonymous_analyze_before_parse_401',client.post(origin+'/v1/scans/analyze',content=b'not multipart').status_code==401)
            check('invalid_jwt_analyze_401',client.post(origin+'/v1/scans/analyze',headers=headers('invalid'),content=b'not multipart').status_code==401)
            for content in [b'',b'not multipart',b'X'*(10485760+1)]:
                r=client.post(origin+'/v1/scans/analyze',headers=headers(),content=content)
                check('missing_model_precedes_body_'+str(len(checks)),r.status_code==503 and r.json()['error']['code']=='MODEL_NOT_READY')
            r=client.post(origin+'/v1/scans/analyze',headers=headers(),files={'file':('fixture.png',png,'image/png')})
            check('valid_image_still_model_not_ready',r.status_code==503 and r.json()['error']['code']=='MODEL_NOT_READY')
            check('no_scan_row_created_by_unavailable_model',api('GET','/v1/scans').json()['items']==[])
            storage=ok(client.post(local['API_URL']+'/storage/v1/object/list/food-scans',headers=admin,json={'prefix':users[0],'limit':100}))
            check('no_image_object_created_by_unavailable_model',storage==[])

            fixtures=[]
            for owner,created,status in [(users[0],'2026-10-15T00:00:00Z','completed'),(users[0],'2026-10-15T00:00:00Z','completed'),
                                         (users[0],'2026-10-15T12:00:00Z','completed'),(users[0],'2026-10-16T00:00:00Z','completed'),
                                         (users[0],'2026-10-15T13:00:00Z','processing'),(users[1],'2026-10-15T00:00:00Z','completed')]:
                id,detection=str(uuid.uuid4()),str(uuid.uuid4()); path=f'{owner}/{id}/{uuid.uuid4()}.png' if status=='completed' else None
                payload=dict(id=id,user_id=owner,status=status,input_source='gallery',created_at=created,revision=1,
                    image_path=path,detections=[],confirmations=[])
                if status=='completed': payload.update(model_version='BE03_SYNTHETIC_FIXTURE_NOT_INFERENCE',class_map_version='vietfood-67-2026-10-12-v1',
                    detections=[dict(detection_id=detection,predicted_food_id=RICE,training_class_id=25,original_class_id=25,bbox=[.1,.1,.9,.9],confidence=.8)])
                response=client.post(local['API_URL']+'/rest/v1/scans',headers=admin,json=payload)
                check('seed_labeled_synthetic_scan_'+str(len(checks)),response.status_code==201)
                if path:
                    ok(client.post(local['API_URL']+'/storage/v1/object/food-scans/'+path,headers=admin|{'Content-Type':'image/png'},content=png))
                    objects.append(path)
                fixtures.append(dict(id=id,det=detection,owner=owner,path=path,status=status))
            own=fixtures[0]; other=fixtures[-1]; pending=fixtures[-2]
            r=api('GET','/v1/scans/'+own['id']); value=r.json()
            check('owner_get_etag_private_columns_omitted',r.status_code==200 and r.headers['etag']=='"1"' and 'image_path' not in value and 'user_id' not in value)
            check('stored_fixture_label_not_claimed_real_inference',value['model_version']=='BE03_SYNTHETIC_FIXTURE_NOT_INFERENCE')
            check('no_invented_alternative_scores','alternatives' not in value['detections'][0])
            check('owner_signed_download_bytes_match',client.get(value['image_url']).content==png)
            expires=datetime.fromisoformat(value['image_url_expires_at'].replace('Z','+00:00'))
            check('short_signed_url_ttl',250<(expires-datetime.now(timezone.utc)).total_seconds()<=310)
            check('cross_owner_get_404',api('GET','/v1/scans/'+own['id'],b).status_code==404)
            check('unknown_scan_404',api('GET','/v1/scans/'+str(uuid.uuid4())).status_code==404)
            check('processing_scan_has_no_image_url',api('GET','/v1/scans/'+pending['id']).json()['image_url'] is None)
            check('private_public_url_denied',client.get(local['API_URL']+'/storage/v1/object/public/food-scans/'+own['path']).status_code>=400)
            h_b={'apikey':local['ANON_KEY'],'Authorization':'Bearer '+b}
            check('storage_b_cannot_sign_a',client.post(local['API_URL']+'/storage/v1/object/sign/food-scans/'+own['path'],headers=h_b,json={'expiresIn':300}).status_code>=400)
            url='/v1/scans/'+own['id']+'/result'; confirmation={'confirmations':[dict(detection_id=own['det'],food_id=OTHER)]}
            check('confirm_if_match_required',api('PATCH',url,data=confirmation).status_code==428)
            check('confirm_other_owner_404',api('PATCH',url,b,confirmation,match='"1"').status_code==404)
            check('confirm_pending_409',api('PATCH','/v1/scans/'+pending['id']+'/result',data={'confirmations':[]},match='"1"').status_code==409)
            check('confirm_unknown_detection_422',api('PATCH',url,data={'confirmations':[dict(detection_id=str(uuid.uuid4()),food_id=OTHER)]},match='"1"').status_code==422)
            check('confirm_unknown_food_422',api('PATCH',url,data={'confirmations':[dict(detection_id=own['det'],food_id=str(uuid.uuid4()))]},match='"1"').status_code==422)
            check('confirm_duplicate_detection_422',api('PATCH',url,data={'confirmations':confirmation['confirmations']*2},match='"1"').status_code==422)
            check('confirm_cannot_overwrite_predictions',api('PATCH',url,data={'detections':[]},match='"1"').status_code==422)
            r=api('PATCH',url,data=confirmation,match='"1"')
            check('confirm_preserves_predicted_snapshot',r.status_code==200 and r.headers['etag']=='"2"' and r.json()['detections']==value['detections'] and r.json()['confirmations'][0]['confirmed_food_id']==OTHER)
            check('confirm_stale_revision_412',api('PATCH',url,data={'confirmations':[]},match='"1"').status_code==412)
            filters={'from':'2026-10-15T00:00:00Z','to':'2026-10-16T00:00:00Z','limit':2}
            all_rows=[]; cursor=None; first_cursor=None
            for _ in range(10):
                r=api('GET','/v1/scans',params=filters|({'cursor':cursor} if cursor else {}))
                check('scan_history_page_'+str(len(checks)),r.status_code==200)
                page=r.json(); all_rows+=page['items']; cursor=page['next_cursor']; first_cursor=first_cursor or cursor
                if not cursor: break
            check('scan_history_filtered_owner_once',len(all_rows)==4 and len({s['id'] for s in all_rows})==4 and other['id'] not in {s['id'] for s in all_rows})
            ordering=[(s['created_at'],s['id']) for s in all_rows]
            check('history_created_at_id_desc_with_ties',ordering==sorted(ordering,reverse=True))
            check('cursor_bound_to_owner',api('GET','/v1/scans',b,params=filters|{'cursor':first_cursor}).status_code==422)
            check('cursor_bound_to_filters',api('GET','/v1/scans',params=filters|{'cursor':first_cursor,'to':'2026-10-17T00:00:00Z'}).status_code==422)
            for params in [{'limit':0},{'limit':101},{'user_id':users[1]},{'from':'2026-10-15'},
                           {'from':'2026-10-16T00:00:00Z','to':'2026-10-15T00:00:00Z'}]:
                check('invalid_scan_history_query_'+str(len(checks)),api('GET','/v1/scans',params=params).status_code==422)
            check('confirmed_food_description_lookup',api('GET','/v1/foods/'+OTHER+'/description').status_code==200)
            # Missing object yields nullable URL, preserving readable scan metadata.
            ok(client.request('DELETE',local['API_URL']+'/storage/v1/object/food-scans',headers=admin,json={'prefixes':[own['path']]}))
            check('deleted_image_metadata_still_readable_null_url',api('GET','/v1/scans/'+own['id']).json()['image_url'] is None)
            spec=client.get(origin+'/openapi.json').json()
            check('runtime_10_paths_11_operations',len(spec['paths'])==10 and sum(len(p) for p in spec['paths'].values())==11)
            (ROOT/'data/processed/BE-03-runtime-openapi.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            result=dict(task='BE-03',status='passed',checks_passed=len(checks),checks=checks,generated_at=datetime.now(timezone.utc).isoformat(),
                model_status='not_ready: runtime analyze made no predictions',fixture_scope='Stored scans explicitly SYNTHETIC; tests history/confirmation/Storage only',
                not_checked=['Real detector inference/accuracy/latency','Trained weights','Mobile'])
    finally:
        cleanup=True
        with httpx.Client(timeout=10,trust_env=False) as client:
            if objects: cleanup=client.request('DELETE',local['API_URL']+'/storage/v1/object/food-scans',headers=admin,json={'prefixes':objects}).status_code<400
            for uid in users: cleanup=client.delete(local['API_URL']+'/auth/v1/admin/users/'+uid,headers=admin).status_code<400 and cleanup
        proc.terminate()
        try: proc.wait(timeout=10)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)
        log.close()
        if not cleanup: raise RuntimeError('Local fixture cleanup failed')
    result['fixture_cleanup']='completed: own Storage paths and Auth cascades; catalog unchanged'
    (ROOT/'data/processed/BE-03-integration.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('BE-03 real HTTP/Auth/Storage: '+str(len(checks))+' checks passed; production predictor unavailable; fixtures cleaned')


if __name__=='__main__':
    try: main()
    except (AssertionError,RuntimeError,ValueError,KeyError) as error:
        print('BE-03 integration failed: '+str(error),file=sys.stderr); raise SystemExit(1)
    except httpx.HTTPError:
        print('BE-03 integration failed: local network operation failed',file=sys.stderr); raise SystemExit(1)
