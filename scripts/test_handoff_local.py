"""BE-04 examples captured from real local Auth/FastAPI, without secrets.

Default verifies portable examples and the current runtime snapshot, then exercises
the sample flows. --write-artifacts explicitly refreshes portable artifacts.
Creates/deletes only its own Auth fixture; no reset or catalog writes.
"""
import argparse
from datetime import datetime, timezone
from io import BytesIO
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
from PIL import Image
from contract_checks import validate_examples

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / 'docs/architecture/openapi-backend-v1.json'
EXAMPLES = ROOT / 'docs/handoff/api-examples-v1.json'
RICE = '89cde1f5-b817-541d-b122-a6084f566261'
PHO = 'f3cb647a-925c-50d7-89cf-8960e141a11c'
SAMPLE_USER = '10000000-0000-4000-8000-000000000001'
ABSENT_SCAN = '40000000-0000-4000-8000-000000000001'
SAMPLE_REQUEST = '50000000-0000-4000-8000-000000000001'


def main(write_artifacts=False):
    local = json.loads((ROOT / 'data/processed/supabase-local.json').read_text(encoding='utf-8-sig'))
    if local['API_URL'] != 'http://127.0.0.1:54321':
        raise ValueError('Dedicated local stack only')
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0))
        port = reserved.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    env = dict(os.environ, FOODLENS_CONFIG_PATH=str(ROOT / 'data/processed/backend-local.json'))
    log = (ROOT / 'data/processed/BE-04-handoff-server.log').open('w', encoding='utf-8')
    proc = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1',
                             '--port', str(port), '--no-access-log'], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    admin = {'apikey': local['ANON_KEY'], 'Authorization': 'Bearer ' + local['SERVICE_ROLE_KEY']}
    uid = None
    examples = []
    aliases = {}
    try:
        with httpx.Client(timeout=10, trust_env=False) as client:
            for _ in range(60):
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
            spec = client.get(origin + '/openapi.json').json()
            if not write_artifacts:
                if spec != json.loads(SNAPSHOT.read_text(encoding='utf-8')):
                    raise ValueError('Runtime differs from accepted OpenAPI')
                validate_examples(spec, json.loads(EXAMPLES.read_text(encoding='utf-8')))
            email = 'be04-' + uuid4().hex + '@example.invalid'
            password = secrets.token_urlsafe(32)
            r = client.post(local['API_URL'] + '/auth/v1/admin/users', headers=admin,
                            json=dict(email=email, password=password, email_confirm=True, app_metadata={'be04_test': True}))
            if r.status_code >= 400:
                raise RuntimeError('Auth fixture creation failed')
            uid = r.json()['id']
            aliases[uid] = SAMPLE_USER
            r = client.post(local['API_URL'] + '/auth/v1/token?grant_type=password', headers={'apikey': local['ANON_KEY']},
                            json=dict(email=email, password=password))
            if r.status_code != 200:
                raise RuntimeError('Auth fixture login failed')
            authorization = {'Authorization': 'Bearer ' + r.json()['access_token']}

            def capture(label, method, path, status, *, path_params=None, query=None, headers=None, body=None, multipart=None, authenticated=True, invalid=False):
                actual = path
                for name, value in (path_params or {}).items():
                    actual = actual.replace('{' + name + '}', value)
                kwargs = dict(params=query, headers={**(authorization if authenticated else {}), **(headers or {})})
                if body is not None:
                    kwargs['json'] = body
                if multipart is not None:
                    raw = BytesIO()
                    Image.new('RGB', (2, 2), 'white').save(raw, format='JPEG')
                    kwargs['files'] = {'file': ('photo.jpg', raw.getvalue(), 'image/jpeg')}
                    kwargs['data'] = {'input_source': multipart['input_source']}
                response = client.request(method, origin + actual, **kwargs)
                if response.status_code != status:
                    raise AssertionError(label + ': unexpected HTTP status ' + str(response.status_code))
                request = {'authenticated': authenticated}
                for name, value in [('path_params', path_params), ('query', query), ('headers', headers), ('body', body), ('multipart', multipart)]:
                    if value is not None:
                        request[name] = value
                result = {'status': status, 'headers': {k: v for k, v in response.headers.items()
                          if k in ('x-request-id', 'cache-control', 'etag', 'idempotency-replayed', 'www-authenticate')}}
                if status != 204:
                    result['body'] = response.json()
                elif response.content:
                    raise AssertionError('DELETE response must be empty')
                case = dict(id=label, method=method, path=path, request=request, response=result)
                if invalid:
                    case['invalid_request'] = True
                examples.append(case)
                return result.get('body')

            capture('liveness', 'GET', '/health', 200, authenticated=False)
            capture('core_ready_model_missing', 'GET', '/health/ready', 200, authenticated=False)
            capture('anonymous_catalog', 'GET', '/v1/foods', 401, authenticated=False)
            capture('profile', 'GET', '/v1/me', 200)
            capture('profile_timezone', 'PATCH', '/v1/me', 200, body={'display_name': 'FoodLens demo', 'timezone': 'Asia/Ho_Chi_Minh'})
            capture('profile_invalid_timezone', 'PATCH', '/v1/me', 422, body={'timezone': 'Not/AZone'})
            capture('search_rice', 'GET', '/v1/foods', 200, query={'q': 'Cơm', 'limit': 1})
            capture('food_detail', 'GET', '/v1/foods/{id}', 200, path_params={'id': RICE})
            # FOOD-01: Cơm has only an unreviewed draft; Phở was reviewed and published by the owner.
            capture('food_description_unavailable', 'GET', '/v1/foods/{id}/description', 200, path_params={'id': RICE})
            capture('food_description_available', 'GET', '/v1/foods/{id}/description', 200, path_params={'id': PHO})
            capture('scan_history_empty', 'GET', '/v1/scans', 200, query={'limit': 20})
            capture('scan_absent', 'GET', '/v1/scans/{id}', 404, path_params={'id': ABSENT_SCAN})
            capture('confirm_missing_revision', 'PATCH', '/v1/scans/{id}/result', 428, path_params={'id': ABSENT_SCAN},
                    body={'confirmations': []})
            capture('confirm_absent_scan', 'PATCH', '/v1/scans/{id}/result', 404, path_params={'id': ABSENT_SCAN},
                    headers={'If-Match': '"1"'}, body={'confirmations': []})
            capture('analyze_model_missing', 'POST', '/v1/scans/analyze', 503,
                    multipart={'file': 'photo.jpg', 'input_source': 'gallery'})

            def portable(value):
                if isinstance(value, list):
                    return [portable(v) for v in value]
                if isinstance(value, dict):
                    return {k: SAMPLE_REQUEST if k in ('request_id', 'x-request-id') else
                            'OPAQUE_CURSOR_FROM_PREVIOUS_RESPONSE' if k == 'next_cursor' and v is not None else portable(v)
                            for k, v in value.items()}
                return aliases.get(value, value) if isinstance(value, str) else value

            document = {'contract_version': 'backend-v1-2026-10-20',
                        'provenance': 'Real dedicated-local HTTP responses; temporary user/request IDs and non-null cursors replaced with illustrative placeholders. No model inference; food descriptions are owner-reviewed published content or explicit unavailable states. Nutrition, meals and stats were removed (FOOD-02). Tokens, passwords and signed URLs omitted.',
                        'examples': portable(examples)}
            count = validate_examples(spec, document)
            expected = {(m.upper(), p) for p, methods in spec['paths'].items() for m in methods if m in ('get', 'post', 'patch', 'delete')}
            if {(c['method'], c['path']) for c in examples} != expected:
                raise ValueError('Examples do not cover every operation')
            if write_artifacts:
                SNAPSHOT.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                EXAMPLES.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    finally:
        try:
            if uid is not None:
                with httpx.Client(timeout=10, trust_env=False) as client:
                    cleanup = client.delete(local['API_URL'] + '/auth/v1/admin/users/' + uid, headers=admin)
                    if cleanup.status_code >= 400:
                        raise RuntimeError('Own Auth fixture cleanup failed')
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            log.close()
    report = dict(task='BE-04', status='passed', examples_checked=count, operations_covered=len(expected),
                  openapi_version=spec['openapi'], generated_at=datetime.now(timezone.utc).isoformat(),
                  fixture_cleanup='own Auth fixture and cascaded profile removed; catalog untouched',
                  not_checked=['Real inference', 'Mobile/device access', 'Cloud/deployment'])
    (ROOT / 'data/processed/BE-04-handoff.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'BE-04 handoff: {count} real HTTP examples, {len(expected)} operations validated; cleanup completed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--write-artifacts', action='store_true')
    args = parser.parse_args()
    try:
        main(args.write_artifacts)
    except (AssertionError, ValueError, RuntimeError, httpx.HTTPError):
        print('BE-04 handoff failed; inspect local evidence without sharing credentials.', file=sys.stderr)
        raise SystemExit(1)
