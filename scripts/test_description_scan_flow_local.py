"""FOOD-01 end-to-end smoke on the already-running local backend (default http://127.0.0.1:8000).

Real flow a client follows: analyze one image -> keep every detection box -> deduplicate
predicted_food_id -> one GET /v1/foods/{id}/description per canonical food. Creates its own
Auth fixture and removes its scan image and account afterwards. Does not start a server,
change the model or write content.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sys
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGE = ROOT / 'data/processed/food-extension-v2/yolo-75-v2/images/test/legacy-test__00000067_jpg.rf.f40488bb835aee27eb53fa5099175ba8.jpg'


def main(api, image):
    local = json.loads((ROOT / 'data/processed/supabase-local.json').read_text(encoding='utf-8-sig'))
    if local['API_URL'] != 'http://127.0.0.1:54321' or not api.startswith('http://127.0.0.1:'):
        raise ValueError('Dedicated loopback stack only')
    admin = {'apikey': local['ANON_KEY'], 'Authorization': 'Bearer ' + local['SERVICE_ROLE_KEY']}
    uid, image_path, result = None, None, {}
    with httpx.Client(timeout=60, trust_env=False) as client:
        try:
            ready = client.get(api + '/health/ready').json()
            if not ready['capabilities']['scan']:
                raise RuntimeError('Live backend scan capability is not ready')
            email, password = 'food01-flow-' + uuid4().hex + '@example.invalid', secrets.token_urlsafe(32)
            r = client.post(local['API_URL'] + '/auth/v1/admin/users', headers=admin,
                            json=dict(email=email, password=password, email_confirm=True, app_metadata={'food01_test': True}))
            r.raise_for_status()
            uid = r.json()['id']
            r = client.post(local['API_URL'] + '/auth/v1/token?grant_type=password', headers={'apikey': local['ANON_KEY']},
                            json=dict(email=email, password=password))
            r.raise_for_status()
            user = {'Authorization': 'Bearer ' + r.json()['access_token']}
            r = client.post(api + '/v1/scans/analyze', headers=user, data={'input_source': 'gallery'},
                            files={'file': (image.name, image.read_bytes(), 'image/jpeg')})
            if r.status_code != 201:
                raise RuntimeError('Analyze returned HTTP ' + str(r.status_code))
            scan = r.json()
            image_path = f"{uid}/{scan['id']}"
            detections = scan['detections']
            food_ids = list(dict.fromkeys(d['predicted_food_id'] for d in detections))
            cards = []
            for food_id in food_ids:
                d = client.get(f'{api}/v1/foods/{food_id}/description', headers=user)
                if d.status_code != 200:
                    raise RuntimeError('Description returned HTTP ' + str(d.status_code))
                body = d.json()
                cards.append(dict(food_id=food_id, name_vi=body['name_vi'], status=body['status'],
                                  boxes=sum(x['predicted_food_id'] == food_id for x in detections)))
            if sum(c['boxes'] for c in cards) != len(detections):
                raise AssertionError('Every detection box must stay attached to exactly one canonical food')
            result = dict(task='FOOD-01', status='passed', api=api, model_version=scan['model_version'],
                          class_map_version=scan['class_map_version'], detection_boxes=len(detections),
                          unique_foods=len(food_ids), description_calls=len(cards), foods=cards,
                          generated_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                          note='Smoke of the API join only; not model accuracy or content review evidence.')
        finally:
            if uid is not None:
                objects = client.post(local['API_URL'] + '/storage/v1/object/list/food-scans', headers=admin,
                                      json={'prefix': (image_path or uid), 'limit': 100})
                names = [f"{image_path}/{o['name']}" for o in objects.json()] if image_path and objects.status_code < 400 else []
                if names:
                    client.request('DELETE', local['API_URL'] + '/storage/v1/object/food-scans', headers=admin, json={'prefixes': names})
                client.delete(local['API_URL'] + '/auth/v1/admin/users/' + uid, headers=admin).raise_for_status()
                result['fixture_cleanup'] = f'{len(names)} private image object(s) and the Auth fixture (cascading its scan) removed'
    (ROOT / 'data/processed/FOOD-01-scan-flow.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api', default='http://127.0.0.1:8000')
    parser.add_argument('--image', type=Path, default=DEFAULT_IMAGE)
    args = parser.parse_args()
    try:
        main(args.api.rstrip('/'), args.image)
    except (AssertionError, ValueError, RuntimeError, httpx.HTTPError) as exc:
        print('FOOD-01 scan flow failed: ' + (str(exc) if not isinstance(exc, httpx.HTTPError) else type(exc).__name__), file=sys.stderr)
        raise SystemExit(1)
