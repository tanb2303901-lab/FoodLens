"""Acceptance artifact/schema checks; no server, keys or fake inference."""
from copy import deepcopy
import json
import re
from pathlib import Path

import pytest
from jsonschema import ValidationError

from backend.app.main import create_app
from scripts.contract_checks import assert_schema, validate_examples

ROOT = Path(__file__).resolve().parents[2]
SPEC = json.loads((ROOT / 'docs/architecture/openapi-backend-v1.json').read_text(encoding='utf-8'))
DOCUMENT = json.loads((ROOT / 'docs/handoff/api-examples-v1.json').read_text(encoding='utf-8'))
CASES = {c['id']: c for c in DOCUMENT['examples']}


def test_full_accepted_openapi_and_examples_match_current_app():
    assert create_app().openapi() == SPEC
    assert validate_examples(SPEC, DOCUMENT) == 15
    operations = {(m.upper(), p) for p, methods in SPEC['paths'].items() for m in methods if m in {'get', 'post', 'patch', 'delete'}}
    assert {(c['method'], c['path']) for c in DOCUMENT['examples']} == operations
    assert len(operations) == 11
    assert all(op.get('security') == [{'BearerAuth': []}]
               for p, methods in SPEC['paths'].items() if p.startswith('/v1/') for op in methods.values())


def test_removed_nutrition_meal_and_stats_surface_is_absent():
    text = json.dumps(SPEC)
    assert not any(p.startswith(('/v1/meals', '/v1/stats')) or p.endswith('/nutrition') for p in SPEC['paths'])
    for removed in ['MealCreate', 'Meal', 'FoodNutrition', 'NutritionProfile', 'DailyStats', 'Portion']:
        assert removed not in SPEC['components']['schemas']
    assert 'nutrition_status' not in SPEC['components']['schemas']['Food']['properties']
    assert set(SPEC['components']['schemas']['Capabilities']['properties']) == {'catalog', 'scan'}
    assert 'Idempotency-Key' not in text and 'manual_meals' not in text


@pytest.mark.parametrize('name,value', [('user_id', '10000000-0000-4000-8000-000000000002'), ('display_name', None),
                                        ('timezone', ''), ('display_name', 'x' * 101)])
def test_frontend_invalid_profile_inputs_fail_the_published_schema(name, value):
    body = deepcopy(CASES['profile_timezone']['request']['body'])
    body[name] = value
    with pytest.raises(ValidationError):
        assert_schema(SPEC, {'$ref': '#/components/schemas/ProfilePatch'}, body)


def test_generated_client_requires_revision_header_and_error_body():
    op = next(o for methods in SPEC['paths'].values() for o in methods.values() if o['operationId'] == 'confirmScan')
    assert {p['name'] for p in op['parameters'] if p['in'] == 'header' and p['required']} == {'If-Match'}
    assert all(o['responses']['500']['content']['application/json']['schema']['$ref'].endswith('/Error')
               for methods in SPEC['paths'].values() for o in methods.values())
    assert CASES['confirm_missing_revision']['response']['status'] == 428
    assert CASES['profile_invalid_timezone']['response']['body']['error']['code'] == 'INVALID_TIMEZONE'


def test_samples_show_description_states_and_do_not_imply_real_inference():
    assert CASES['analyze_model_missing']['response']['body']['error']['code'] == 'MODEL_NOT_READY'
    assert CASES['core_ready_model_missing']['response']['body']['capabilities'] == {'catalog': True, 'scan': False}
    description = CASES['food_description_unavailable']['response']['body']
    assert description['status'] == 'description_unavailable' and description['description'] is None
    published = CASES['food_description_available']['response']['body']
    assert published['status'] == 'available' and published['description']['content_status'] == 'published'
    assert published['description']['sources'] and all(s['url'].startswith('https://') for s in published['description']['sources'])


def test_face_cannot_validate_as_a_catalog_food():
    food = deepcopy(CASES['food_detail']['response']['body'])
    food['original_class_id'] = 27
    with pytest.raises(ValidationError):
        assert_schema(SPEC, {'$ref': '#/components/schemas/Food'}, food)


def test_artifacts_do_not_publish_credentials_private_paths_or_signed_urls():
    banned = {'access_token', 'refresh_token', 'password', 'user_id', 'image_path', 'scan_service_key', 'jwt_secret', 'cursor_secret', 'Authorization'}
    def walk(value):
        if isinstance(value, dict):
            assert not banned.intersection(value)
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)
        elif isinstance(value, str):
            assert not re.fullmatch(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', value)
            assert '/object/sign/' not in value and '?token=' not in value
    walk(DOCUMENT)


def test_illustrative_description_shape_matches_contract_and_runtime_dto():
    from backend.app.models import FoodDescription
    shape = json.loads((ROOT / 'docs/handoff/food-description-shape-example.json').read_text(encoding='utf-8'))
    assert shape['illustrative'] is True
    assert_schema(SPEC, {'$ref': '#/components/schemas/FoodDescription'}, shape['response'])
    assert FoodDescription.model_validate(shape['response']).status == 'available'
    real = CASES['food_description_unavailable']['response']['body']
    assert_schema(SPEC, {'$ref': '#/components/schemas/FoodDescription'}, real)
    uncited = deepcopy(shape['response'])
    uncited['description']['sources'][0]['supports'] = ['short_intro']
    with pytest.raises(ValueError):
        FoodDescription.model_validate(uncited)
