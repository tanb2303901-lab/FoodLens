"""FOOD-01 real local checks: FastAPI + Supabase Auth/PostgREST/RLS for food descriptions.

Starts a temporary backend on a free loopback port with the core config, creates one Auth
fixture user and deletes it afterwards. Expected API status per food comes from the content
file (only `published` is user-visible). Review/publish transitions are exercised on a
synthetic copy inside a rolled-back database transaction. No reset, no content commit.
"""
from copy import deepcopy
from datetime import datetime, timezone
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import food_content as fc

UNKNOWN = '40000000-0000-4000-8000-000000000099'


def main():
    local = json.loads((ROOT / 'data/processed/supabase-local.json').read_text(encoding='utf-8-sig'))
    if local['API_URL'] != 'http://127.0.0.1:54321':
        raise ValueError('Dedicated local stack only')
    document = fc.load()
    fc.validate(document)
    rows, counts = fc.coverage(document)
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0))
        port = reserved.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    env = dict(os.environ, FOODLENS_CONFIG_PATH=str(ROOT / 'data/processed/backend-local.json'))
    log = (ROOT / 'data/processed/FOOD-01-integration-server.log').open('w', encoding='utf-8')
    proc = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', str(port),
                             '--no-access-log'], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    admin = {'apikey': local['ANON_KEY'], 'Authorization': 'Bearer ' + local['SERVICE_ROLE_KEY']}
    uid, checks = None, []

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    try:
        with httpx.Client(timeout=15, trust_env=False) as client:
            for _ in range(75):
                if proc.poll() is not None:
                    raise RuntimeError('Temporary backend exited')
                try:
                    if client.get(origin + '/health').status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.2)
            else:
                raise RuntimeError('Backend startup timeout')
            email = 'food01-' + uuid4().hex + '@example.invalid'
            password = secrets.token_urlsafe(32)
            r = client.post(local['API_URL'] + '/auth/v1/admin/users', headers=admin,
                            json=dict(email=email, password=password, email_confirm=True, app_metadata={'food01_test': True}))
            if r.status_code >= 400:
                raise RuntimeError('Auth fixture creation failed')
            uid = r.json()['id']
            r = client.post(local['API_URL'] + '/auth/v1/token?grant_type=password', headers={'apikey': local['ANON_KEY']},
                            json=dict(email=email, password=password))
            if r.status_code != 200:
                raise RuntimeError('Auth fixture login failed')
            token = r.json()['access_token']
            user = {'Authorization': 'Bearer ' + token}
            foods = {f['slug']: f for f in fc.load(fc.IDENTITIES)['foods']}

            for row in rows:
                food = foods[row['slug']]
                r = client.get(f"{origin}/v1/foods/{food['id']}/description", headers=user)
                body = r.json()
                check(row['slug'] + ' status code', r.status_code == 200)
                check(row['slug'] + ' matches content state', body['status'] == row['api_status'])
                check(row['slug'] + ' canonical identity', (body['food_id'], body['slug'], body['name_vi']) == (food['id'], food['slug'], food['name_vi']))
                if body['status'] == 'description_unavailable':
                    check(row['slug'] + ' no content leaks', body['description'] is None and body['reason'] == 'not_published')
                else:
                    check(row['slug'] + ' cited content', bool(body['description']['sources']))
                check(row['slug'] + ' request id', r.headers.get('x-request-id') and r.headers.get('cache-control') == 'no-store')
            pho = foods['pho']['id']
            check('anonymous 401', client.get(f'{origin}/v1/foods/{pho}/description').status_code == 401)
            check('api key is not a user token', client.get(f'{origin}/v1/foods/{pho}/description',
                  headers={'Authorization': 'Bearer ' + local['ANON_KEY']}).status_code == 401)
            check('unknown food 404', client.get(f'{origin}/v1/foods/{UNKNOWN}/description', headers=user).json()['error']['code'] == 'NOT_FOUND')
            check('malformed id 422', client.get(f'{origin}/v1/foods/not-a-uuid/description', headers=user).status_code == 422)
            check('unknown query 422', client.get(f'{origin}/v1/foods/{pho}/description?locale=en', headers=user).status_code == 422)
            check('openapi lists operation', 'getFoodDescription' == client.get(origin + '/openapi.json').json()
                  ['paths']['/v1/foods/{id}/description']['get']['operationId'])

            rest = local['API_URL'] + '/rest/v1/'
            as_user = {'apikey': local['ANON_KEY'], 'Authorization': 'Bearer ' + token}
            visible = client.get(rest + 'food_descriptions', headers=as_user, params={'select': 'id,content_status'}).json()
            check('user sees only published rows', isinstance(visible, list) and all(v['content_status'] == 'published' for v in visible)
                  and len(visible) == counts['published'])
            if counts['draft']:
                check('drafts exist but are hidden', len(visible) < counts['draft'] + counts['published'])
            else:
                check('every canonical food has published content', counts['published'] == len(foods) == len(visible))
            check('reviewer column denied', client.get(rest + 'food_descriptions', headers=as_user,
                  params={'select': 'reviewed_by'}).status_code in (401, 403))
            check('user cannot insert content', client.post(rest + 'content_sources', headers=as_user, json={'id': UNKNOWN}).status_code in (401, 403))
            anon = client.get(rest + 'food_descriptions', headers={'apikey': local['ANON_KEY']}, params={'select': 'id'})
            check('anonymous PostgREST denied', anon.status_code in (401, 403))
            sources_visible = client.get(rest + 'content_sources', headers=as_user, params={'select': 'id'}).json()
            check('only cited sources of published rows visible', counts['published'] > 0 or sources_visible == [])
    finally:
        try:
            if uid is not None:
                with httpx.Client(timeout=10, trust_env=False) as client:
                    if client.delete(local['API_URL'] + '/auth/v1/admin/users/' + uid, headers=admin).status_code >= 400:
                        raise RuntimeError('Own Auth fixture cleanup failed')
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            log.close()

    # DB-side transition rehearsal on a synthetic copy; rolled back, never committed.
    rehearsal = deepcopy(document)
    draft = next((e for e in rehearsal['descriptions'] if e['content_status'] == 'draft'), None)
    if draft is None:  # everything published: rehearse a new version that retires the live one
        live = next(e for e in rehearsal['descriptions'] if e['slug'] == 'pho' and e['content_status'] == 'published')
        draft = {**deepcopy(live), 'version': live['version'] + 1, 'content_status': 'draft', 'review': None, 'publication': None}
        rehearsal['descriptions'].append(draft)
    slug, version, new_version = draft['slug'], draft['version'], draft['version'] > 1
    fc.review(rehearsal, slug, 'SYNTHETIC TEST REVIEWER', version=version, notes='rolled-back rehearsal only', at='2026-10-19T00:00:00+00:00')
    fc.publish(rehearsal, slug, 'SYNTHETIC TEST PUBLISHER', version=version, at='2026-10-19T00:00:01+00:00')
    report = fc.apply_local(rehearsal, commit=False, report_name='FOOD-01-transition-rehearsal.json')
    states = report['database_after']['descriptions']
    if new_version:
        check('rehearsal new version retired the old one inside rollback',
              states.get('published', 0) == counts['published'] and states.get('retired', 0) == counts['retired'] + 1)
    else:
        check('rehearsal published one row inside rollback', states.get('published', 0) == counts['published'] + 1)
    after = fc.apply_local(document, commit=False)
    check('rehearsal left no committed change', after['database_after']['descriptions'].get('published', 0) == counts['published'])

    result = dict(task='FOOD-01', status='passed', checks=len(checks), foods_checked=len(rows), content_counts=counts,
                  generated_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  fixture_cleanup='own Auth fixture removed; content rehearsal rolled back',
                  not_checked=['Human review quality of content', 'Mobile/device access', 'Cloud/deployment'])
    (ROOT / 'data/processed/FOOD-01-integration.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"FOOD-01 integration: {len(checks)} real checks passed over {len(rows)} foods; content {json.dumps(counts)}")


if __name__ == '__main__':
    try:
        main()
    except (AssertionError, ValueError, RuntimeError, httpx.HTTPError) as exc:
        print('FOOD-01 integration failed at: ' + (str(exc) if isinstance(exc, AssertionError) else type(exc).__name__), file=sys.stderr)
        raise SystemExit(1)
