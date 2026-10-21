"""BE-01 HTTP integration with local Auth fixtures; catalog is read-only.

Starts a temporary loopback FastAPI process, cleans only its own Auth accounts.
Passwords/JWTs/keys/signed URLs are never printed or included in reports.
"""
from concurrent.futures import ThreadPoolExecutor
import argparse
from datetime import datetime,timezone
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

ROOT=Path(__file__).resolve().parents[1]


def main(class_count=67):
    local=json.loads((ROOT/'data/processed/supabase-local.json').read_text(encoding='utf-8-sig'))
    if local['API_URL']!='http://127.0.0.1:54321': raise ValueError('Local integration only')
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1',0)); port=reserved.getsockname()[1]
    origin=f'http://127.0.0.1:{port}'
    env=dict(os.environ,FOODLENS_CONFIG_PATH=str(ROOT/'data/processed/backend-local.json'))
    log=(ROOT/'data/processed/BE-01-integration-server.log').open('w',encoding='utf-8')
    proc=subprocess.Popen([sys.executable,'-m','uvicorn','backend.app.main:app','--host','127.0.0.1',
                           '--port',str(port),'--no-access-log'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    users=[]; checks=[]
    report=ROOT/'data/processed/BE-01-integration.json'
    admin_headers={'apikey':local['ANON_KEY'],'Authorization':'Bearer '+local['SERVICE_ROLE_KEY']}
    def check(name,condition):
        if not condition: raise AssertionError(name)
        checks.append(name)
    def safe_ok(response):
        if response.status_code>=400: raise RuntimeError('Fixture HTTP operation failed: '+str(response.status_code))
        return response.json()
    try:
        with httpx.Client(timeout=5,trust_env=False) as client:
            for _ in range(60):
                if proc.poll() is not None: raise RuntimeError('Temporary backend process exited; inspect local server log')
                try:
                    if client.get(origin+'/health').status_code==200: break
                except httpx.HTTPError: pass
                time.sleep(.2)
            else: raise RuntimeError('Backend startup timeout')
            check('actual_liveness',client.get(origin+'/health').json()=={'status':'alive'})
            r=client.get(origin+'/health/ready')
            check('actual_database_readiness',r.status_code==200 and r.json()==dict(status='ready',database='ready',model='not_ready',capabilities=dict(catalog=True,scan=False)))
            for label in ('a','b'):
                email=f'be01-{uuid.uuid4().hex}-{label}@example.invalid'; password=secrets.token_urlsafe(32)
                account=safe_ok(client.post(local['API_URL']+'/auth/v1/admin/users',headers=admin_headers,
                    json=dict(email=email,password=password,email_confirm=True,app_metadata={'be01_test':True})))
                users.append(account['id'])
                session=safe_ok(client.post(local['API_URL']+'/auth/v1/token?grant_type=password',headers={'apikey':local['ANON_KEY']},json=dict(email=email,password=password)))
                if label=='a': access_a=session['access_token']
                else: access_b=session['access_token']
            headers_a={'Authorization':'Bearer '+access_a}; headers_b={'Authorization':'Bearer '+access_b}
            check('anonymous_backend_catalog_rejected',client.get(origin+'/v1/foods').status_code==401)
            for invalid in ('malformed',access_a[:-12]+'X'*12,local['ANON_KEY'],local['SERVICE_ROLE_KEY']):
                check('invalid_or_non_user_token_rejected_'+str(len(checks)),client.get(origin+'/v1/foods',headers={'Authorization':'Bearer '+invalid}).status_code==401)
            ids=[]; pages=0; cursor=None
            while True:
                params={'limit':13}
                if cursor: params['cursor']=cursor
                r=client.get(origin+'/v1/foods',headers=headers_a,params=params)
                check('authenticated_catalog_page_'+str(pages),r.status_code==200)
                data=r.json(); ids.extend(f['id'] for f in data['items']); pages+=1
                check('page_has_no_raw_mapping_metadata_'+str(pages),all('source_mapping_metadata' not in f and 'nutrition_status' not in f for f in data['items']))
                cursor=data['next_cursor']
                if not cursor: break
                if pages>10: raise AssertionError('pagination failed to terminate')
            check('pagination_returns_all_'+str(class_count)+'_once',len(ids)==class_count and len(set(ids))==class_count)
            if class_count==75:
                mapping=json.loads((ROOT/'docs/dataset/food-identities-v2.json').read_text(encoding='utf-8'))
                check('catalog_matches_exact_75_uuids',set(ids)=={f['id'] for f in mapping['foods']})
                for f in mapping['foods'][67:]:
                    detail=safe_ok(client.get(origin+'/v1/foods/'+f['id'],headers=headers_a))
                    check('new_catalog_identity_'+f['slug'],detail['training_class_id']==f['training_class_id'] and detail['original_class_id'] is None and detail['class_map_version']==mapping['class_map_version'])
                    info=safe_ok(client.get(origin+'/v1/foods/'+f['id']+'/description',headers=headers_a))
                    check('new_description_lookup_'+f['slug'],info['food_id']==f['id'] and info['status'] in ('available','description_unavailable'))
            r=client.get(origin+'/v1/foods',headers=headers_b,params={'q':'Cơm'})
            check('vietnamese_search_and_second_auth_user',r.status_code==200 and any(f['slug']=='com' for f in r.json()['items']))
            for q in ['%','*','"),active.eq.false','\\','no_match_BE01_xyz']:
                r=client.get(origin+'/v1/foods',headers=headers_a,params={'q':q})
                check('search_syntax_is_literal_'+str(len(checks)),r.status_code==200 and r.json()['items']==[])
            first=client.get(origin+'/v1/foods',headers=headers_a,params={'limit':1}).json()['next_cursor']
            for params in [dict(cursor=first,q='different'),dict(cursor=('A' if first[0]!='A' else 'B')+first[1:]),
                           dict(limit=0),dict(limit=101),dict(user_id=users[1])]:
                check('invalid_query_or_cursor_'+str(len(checks)),client.get(origin+'/v1/foods',headers=headers_a,params=params).status_code==422)
            rice='89cde1f5-b817-541d-b122-a6084f566261'
            r=client.get(origin+'/v1/foods/'+rice,headers=headers_a)
            check('food_detail',r.status_code==200 and r.json()['slug']=='com')
            check('nutrition_endpoint_removed',client.get(origin+'/v1/foods/'+rice+'/nutrition',headers=headers_a).status_code==404)
            for suffix,expected in [(str(uuid.uuid4()),404),('invalid',422)]:
                r=client.get(origin+'/v1/foods/'+suffix,headers=headers_a)
                check('detail_error_'+str(expected),r.status_code==expected and r.headers['x-request-id']==r.json()['error']['request_id'])
            with ThreadPoolExecutor(max_workers=4) as pool:
                responses=list(pool.map(lambda h:client.get(origin+'/v1/foods',headers=h),[headers_a,headers_b]*4))
            check('concurrent_auth_a_b_catalog_requests',all(r.status_code==200 for r in responses))
            spec=client.get(origin+'/openapi.json').json()
            check('runtime_openapi_core_paths_present',all(p in spec['paths'] for p in ['/health','/health/ready','/v1/foods','/v1/foods/{id}','/v1/foods/{id}/description']) and '/v1/foods/{id}/nutrition' not in spec['paths'] and '/v1/meals' not in spec['paths'])
            # Regression evidence is generated; accepted portable export is explicit in BE-04.
            (ROOT/'data/processed/BE-01-runtime-openapi.json').write_text(json.dumps(spec,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
            result=dict(task='BE-01',status='passed',checks_passed=len(checks),checks=checks,
                        generated_at=datetime.now(timezone.utc).isoformat(),not_checked=['Profile/scan APIs','Real model/mobile'])
    finally:
        cleanup_ok=True
        with httpx.Client(timeout=10,trust_env=False) as client:
            for uid in users:
                r=client.delete(local['API_URL']+'/auth/v1/admin/users/'+uid,headers=admin_headers)
                cleanup_ok=cleanup_ok and r.status_code<400
        proc.terminate()
        try: proc.wait(timeout=10)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)
        log.close()
        if not cleanup_ok: raise RuntimeError('Auth fixture cleanup failed')
    result['fixture_cleanup']='completed; catalog untouched'
    report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('BE-01 HTTP integration: '+str(len(checks))+' checks passed; fixture cleanup completed')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--class-count',type=int,choices=[67,75],default=67)
    try: main(parser.parse_args().class_count)
    except (AssertionError,RuntimeError,ValueError) as exc:
        print('BE-01 integration failed: '+str(exc),file=sys.stderr)
        raise SystemExit(1)
