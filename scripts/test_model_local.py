"""Real trained detector -> Auth/FastAPI/private Storage/scan confirmation/description acceptance.

No seeded detections or fabricated scores. Only this script's users/objects are
removed. Reports contain counts/versions, never tokens, passwords or signed URLs.
"""
from datetime import datetime,timezone
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from uuid import uuid4

import httpx

ROOT=Path(__file__).resolve().parents[1]


def run(bundle,dataset,deadline=None):
    sys.path.insert(0,str(ROOT))
    from ml.activate_local import prepare
    from ml.processes import stop_child
    from ml.local_stack import ensure_local_stack
    ensure_local_stack()
    config=prepare(bundle)
    manifest=json.loads((bundle/'manifest.json').read_text(encoding='utf-8'))
    extension=manifest['class_count']==75
    prefix='ML-05' if extension else 'ML-03'
    preflight=manifest.get('training',{}).get('scope')=='checkpoint_smoke_fixture'
    sample_scope='original_train_preflight_only' if preflight else 'effective_test_holdout'
    local=json.loads((ROOT/'data/processed/supabase-local.json').read_text(encoding='utf-8-sig'))
    if local['API_URL']!='http://127.0.0.1:54321':raise ValueError('Dedicated local stack only')
    with socket.socket() as reserve:reserve.bind(('127.0.0.1',0));port=reserve.getsockname()[1]
    origin=f'http://127.0.0.1:{port}'
    log=(ROOT/'data/processed'/(prefix+'-integration-server.log')).open('w',encoding='utf-8')
    server=subprocess.Popen([sys.executable,'-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port',str(port),'--no-access-log'],
                            cwd=ROOT,env=dict(os.environ,FOODLENS_CONFIG_PATH=str(config)),stdout=log,stderr=subprocess.STDOUT,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    admin={'apikey':local['ANON_KEY'],'Authorization':'Bearer '+local['SERVICE_ROLE_KEY']}
    users=[];paths=[];scan_ids=[];checks=[];detection_counts=[];analyze_times=[];correct_new={}
    def check(name,valid,observed=None):
        if not valid:
            (ROOT/'data/processed'/(prefix+'-model-integration-failure.json')).write_text(json.dumps(dict(
                status='failed',failed_check=name,checks_passed=checks,real_detection_counts=detection_counts,
                model_bundle=str(bundle.resolve()),observed=observed),indent=2)+'\n',encoding='utf-8')
            raise AssertionError(name)
        checks.append(name)
    def body(r):
        if r.status_code>=400:raise RuntimeError('Fixture operation failed with HTTP '+str(r.status_code))
        return r.json()
    try:
        with httpx.Client(timeout=40,trust_env=False) as client:
            for _ in range(180):
                if server.poll() is not None:raise RuntimeError('Temporary ML server exited')
                try:
                    if client.get(origin+'/health').status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.5)
            else:raise RuntimeError('Temporary ML server startup timed out')
            ready=client.get(origin+'/health/ready')
            check('real_model_and_storage_writer_ready',ready.status_code==200 and ready.json()['model']=='ready' and ready.json()['capabilities']['scan'])
            tokens=[]
            for label in ('a','b'):
                email='ml03-'+uuid4().hex+'-'+label+'@example.invalid';password=secrets.token_urlsafe(32)
                user=body(client.post(local['API_URL']+'/auth/v1/admin/users',headers=admin,
                                     json=dict(email=email,password=password,email_confirm=True,app_metadata={'ml03_test':True})))
                users.append(user['id'])
                session=body(client.post(local['API_URL']+'/auth/v1/token?grant_type=password',headers={'apikey':local['ANON_KEY']},json=dict(email=email,password=password)))
                tokens.append(session['access_token'])
            a,b=({'Authorization':'Bearer '+token} for token in tokens)
            check('anonymous_analyze_rejected',client.post(origin+'/v1/scans/analyze',content=b'invalid').status_code==401)
            invalid=client.post(origin+'/v1/scans/analyze',headers=a,files={'file':('bad.jpg',b'not image','image/jpeg')})
            check('ready_model_rejects_corrupt_bytes',invalid.status_code==422 and invalid.json()['error']['code']=='INVALID_IMAGE',
                  observed={'http_status':invalid.status_code,'error_code':invalid.json().get('error',{}).get('code')})
            unsupported=client.post(origin+'/v1/scans/analyze',headers=a,files={'file':('bad.gif',b'not image','image/gif')})
            check('ready_model_rejects_unsupported_mime',unsupported.status_code==415)
            first_detection=None
            first_scan=None
            files=sorted((dataset/'images/test').glob('*.jpg'))[:8]
            if extension:
                files=[Path(p) for p in (dataset/'legacy_test.txt').read_text(encoding='utf-8').splitlines()][:8]
                files += [Path(p) for p in (dataset/'extension_test.txt').read_text(encoding='utf-8').splitlines()]
                from backend.app.predictor import ClassMap
                mapping=ClassMap(manifest['class_map_version'])
                catalog=body(client.get(origin+'/v1/foods',headers=a,params={'limit':100}))['items']
                check('catalog_has_75_exact_canonical_identities',len(catalog)==75 and {f['id'] for f in catalog}=={f['id'] for f in mapping.foods.values()})
            for index,path in enumerate(files):
                if deadline is not None and datetime.now(timezone.utc)>=deadline:
                    raise RuntimeError('Owner deadline reserve reached; cleaning own test fixtures')
                started=time.perf_counter()
                r=client.post(origin+'/v1/scans/analyze',headers=a,files={'file':('photo.jpg',path.read_bytes(),'image/jpeg')},data={'input_source':'gallery'})
                analyze_times.append((time.perf_counter()-started)*1000)
                check('actual_'+sample_scope+'_photo_analyzed_'+str(index),r.status_code==201)
                scan=r.json();scan_ids.append(scan['id'])
                stored=body(client.get(local['API_URL']+'/rest/v1/scans',headers=admin,
                                       params={'select':'image_path','id':'eq.'+scan['id'],'user_id':'eq.'+users[0]}))
                if stored and stored[0]['image_path']:paths.append(stored[0]['image_path'])
                check('real_model_version_and_completed_'+str(index),scan['status']=='completed' and scan['model_version']==manifest['model_version'])
                if extension:
                    check('map75_and_nullable_original_ids_'+str(index),scan['class_map_version']==mapping.version and all(
                        d['predicted_food_id']==mapping.foods[d['training_class_id']]['id']
                        and d['original_class_id']==mapping.foods[d['training_class_id']]['original_class_id'] for d in scan['detections']))
                    label=path.parent.parent.parent/'labels'/path.parent.name/(path.stem+'.txt')
                    truth=[]
                    for line in label.read_text(encoding='utf-8').splitlines():
                        c,x,y,w,h=map(float,line.split());truth.append((int(c),[x-w/2,y-h/2,x+w/2,y+h/2]))
                    def iou(x,y):
                        area=max(0,min(x[2],y[2])-max(x[0],y[0]))*max(0,min(x[3],y[3])-max(x[1],y[1]))
                        union=(x[2]-x[0])*(x[3]-x[1])+(y[2]-y[0])*(y[3]-y[1])-area
                        return area/union if union>0 else 0
                    for d in scan['detections']:
                        c=d['training_class_id']
                        if c>=67 and c not in correct_new and any(c==t and iou(d['bbox'],box)>=.5 for t,box in truth):
                            correct_new[c]=(scan,d)
                detection_counts.append(len(scan['detections']))
                check('only_real_scores_no_fabricated_alternatives_'+str(index),all(0<=d['confidence']<=1 and 'alternatives' not in d for d in scan['detections']))
                check('owner_signed_image_download_'+str(index),isinstance(scan['image_url'],str) and client.get(scan['image_url']).status_code==200)
                check('other_owner_cannot_read_scan_'+str(index),client.get(origin+'/v1/scans/'+scan['id'],headers=b).status_code==404)
                if scan['detections'] and first_detection is None and (not extension or index<8):
                    first_detection=scan['detections'][0];first_scan=scan
            check('trained_model_detects_at_least_one_'+sample_scope+'_object',first_detection is not None)
            if extension:
                check('all_eight_new_classes_have_real_correct_holdout_api_detections',sorted(correct_new)==list(range(67,75)),observed=sorted(correct_new))
                for c,(new_scan,new_detection) in sorted(correct_new.items()):
                    confirmation={'confirmations':[{'detection_id':new_detection['detection_id'],'food_id':new_detection['predicted_food_id']}]}
                    confirmed=client.patch(origin+'/v1/scans/'+new_scan['id']+'/result',headers=a|{'If-Match':'"'+str(new_scan['revision'])+'"'},json=confirmation)
                    check('new_class_confirm_preserves_prediction_'+str(c),confirmed.status_code==200 and confirmed.json()['detections']==new_scan['detections'])
                    info=client.get(origin+'/v1/foods/'+new_detection['predicted_food_id']+'/description',headers=a)
                    check('new_class_description_lookup_'+str(c),info.status_code==200 and info.json()['food_id']==new_detection['predicted_food_id']
                        and info.json()['status'] in ('available','description_unavailable'))
            confirm={'confirmations':[{'detection_id':first_detection['detection_id'],'food_id':first_detection['predicted_food_id']}]}
            r=client.patch(origin+'/v1/scans/'+first_scan['id']+'/result',headers=a|{'If-Match':'"'+str(first_scan['revision'])+'"'},json=confirm)
            check('confirm_real_detection',r.status_code==200 and r.json()['detections']==first_scan['detections'])
            check('other_owner_cannot_confirm',client.patch(origin+'/v1/scans/'+first_scan['id']+'/result',headers=b|{'If-Match':'"1"'},json=confirm).status_code==404)
            info=client.get(origin+'/v1/foods/'+first_detection['predicted_food_id']+'/description',headers=a)
            check('real_detection_joins_canonical_description',info.status_code==200 and info.json()['food_id']==first_detection['predicted_food_id'])
            check('description_requires_user_token',client.get(origin+'/v1/foods/'+first_detection['predicted_food_id']+'/description').status_code==401)
            history_ids=set();cursor=None
            while True:
                params={'limit':100}
                if cursor:params['cursor']=cursor
                page=body(client.get(origin+'/v1/scans',headers=a,params=params))
                history_ids.update(s['id'] for s in page['items'])
                cursor=page['next_cursor']
                if not cursor:break
            check('real_scan_history_contains_created_scans',set(scan_ids).issubset(history_ids))
            result=dict(task=prefix,status='passed',checks_passed=len(checks),checks=checks,
                        model_bundle=str(bundle.resolve()),model_version=manifest['model_version'],real_photo_count=len(files),
                        real_detection_counts=detection_counts,first_description_status=info.json()['status'],
                        evidence_scope=manifest.get('quality_status'),training_scope=manifest.get('training',{}).get('scope'),
                        sample_scope=sample_scope,
                        analyze_http_latency_ms=dict(samples=len(analyze_times),mean=sum(analyze_times)/len(analyze_times),
                            min=min(analyze_times),max=max(analyze_times),includes='client upload, Auth, canonical decode, inference, database and private Storage'),
                        generated_at=datetime.now(timezone.utc).isoformat(),quality_scope='functional real inference; quantitative coverage/metrics are in evaluation.json',
                        not_checked=['Mobile/device/production deployment','Full 67-class independent holdout','Human review of every description'])
            if extension:result.update(correct_new_classes=sorted(correct_new),weights_sha256=manifest['weights_sha256'],
                legacy_weights_sha256=manifest['legacy_weights_sha256'],evaluation_sha256=manifest['evaluation_sha256'],
                sample_scope='8 unchanged legacy test scenes plus every new test region; fixed model; functional tests, not an accuracy estimate')
    finally:
        cleanup=True
        try:
            with httpx.Client(timeout=15,trust_env=False) as client:
                # Reconcile own rows even if a response was lost before path collection.
                for uid in users:
                    r=client.get(local['API_URL']+'/rest/v1/scans',headers=admin,params={'select':'image_path','user_id':'eq.'+uid})
                    if r.status_code==200:paths.extend(row['image_path'] for row in r.json() if row['image_path'])
                    else:cleanup=False
                if paths:cleanup=client.request('DELETE',local['API_URL']+'/storage/v1/object/food-scans',headers=admin,json={'prefixes':sorted(set(paths))}).status_code<400 and cleanup
                for uid in users:cleanup=client.delete(local['API_URL']+'/auth/v1/admin/users/'+uid,headers=admin).status_code<400 and cleanup
        finally:
            stop_child(server)
            log.close()
        if not cleanup:raise RuntimeError('Own Auth/Storage fixture cleanup failed')
    result['fixture_cleanup']='only own Auth IDs/cascades/Storage objects removed; existing user/catalog data preserved'
    report=json.dumps(result,indent=2)+'\n'
    (ROOT/'data/processed'/(prefix+'-model-integration.json')).write_text(report,encoding='utf-8')
    if preflight:(ROOT/'data/processed/ML-03-preflight-model-integration.json').write_text(report,encoding='utf-8')
    print('Real model/Auth/Storage/description integration passed; own fixtures cleaned.',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--deadline-utc')
    a=p.parse_args()
    try:run(a.bundle.resolve(),a.dataset.resolve(),datetime.fromisoformat(a.deadline_utc) if a.deadline_utc else None)
    except (AssertionError,RuntimeError,ValueError,KeyError,httpx.HTTPError):
        print('Real model integration did not pass; inspect private local evidence. Backend core remains available.',file=sys.stderr)
        raise SystemExit(1)
