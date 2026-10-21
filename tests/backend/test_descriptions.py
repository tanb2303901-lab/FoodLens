"""FOOD-01 description endpoint tests with synthetic upstream rows; no real content or keys."""
from copy import deepcopy
import unittest

import httpx
from fastapi.testclient import TestClient

from backend.app.main import create_app
from tests.backend.test_core import OTHER, RICE, USER_A, food, settings, token

COFFEE = '254cea80-105c-5827-85c3-3e0775a2c923'


def source(key='synthetic-source', supports=('short_intro', 'origin_text', 'ingredients_summary', 'characteristics')):
    return dict(supports=list(supports), locator='SYNTHETIC SECTION', content_sources=dict(
        source_key=key, title='SYNTHETIC TEST SOURCE', publisher='SYNTHETIC', url='https://example.invalid/source',
        language='vi', source_kind='other', revision_ref=None, accessed_on='2026-10-19', license_note='SYNTHETIC TEST ONLY'))


def published(**overrides):
    row = dict(locale='vi', version=1, content_status='published', is_current=True,
               short_intro='SYNTHETIC INTRO', origin_text='SYNTHETIC ORIGIN', ingredients_summary='SYNTHETIC INGREDIENTS',
               characteristics='SYNTHETIC TRAITS', scope_note=None, authoring_method='ai_assisted_draft',
               reviewed_at='2026-10-19T01:00:00Z', published_at='2026-10-19T02:00:00Z', updated_at='2026-10-19T02:00:00Z',
               food_description_sources=[source()])
    return row | overrides


class DescriptionTests(unittest.TestCase):
    def setUp(self):
        self.rows = []
        self.foods = [food(), food(OTHER, 'cu_kieu'), dict(id=COFFEE, slug='ca_phe', name_vi='Cà phê', name_en='Coffee',
            scope_kind='broad_food_category', original_class_id=None, training_class_id=73, class_map_version='foodlens-75-2026-10-16-v2')]
        self.seen = []
        self.outage = False

        async def upstream(req):
            self.seen.append(req)
            if self.outage:
                raise httpx.ConnectError('synthetic outage MUST NOT LEAK', request=req)
            if req.url.path.endswith('/food_descriptions'):
                return httpx.Response(200, json=self.rows)
            if req.url.path.endswith('/foods'):
                return httpx.Response(200, json=[r for r in self.foods if 'eq.' + r['id'] == req.url.params.get('id')])
            return httpx.Response(500, json={'message': 'unexpected upstream path'})
        self.client = TestClient(create_app(settings(), httpx.MockTransport(upstream)))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def get(self, id=RICE, access=None, suffix=''):
        return self.client.get('/v1/foods/' + id + '/description' + suffix, headers={'Authorization': 'Bearer ' + (access or token())})

    def test_unavailable_is_explicit_and_has_no_content(self):
        r = self.get()
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual((body['status'], body['reason'], body['description']), ('description_unavailable', 'not_published', None))
        self.assertEqual((body['food_id'], body['slug']), (RICE, 'com'))
        self.assertIn('không phải tư vấn sức khỏe', body['notice'])

    def test_published_content_and_sources_are_returned_sorted(self):
        self.rows = [published(food_description_sources=[source('zeta-source', ['characteristics']), source('alpha-source', ['short_intro', 'origin_text', 'ingredients_summary'])])]
        body = self.get().json()
        self.assertEqual(body['status'], 'available')
        self.assertIsNone(body['reason'])
        content = body['description']
        self.assertEqual([s['source_key'] for s in content['sources']], ['alpha-source', 'zeta-source'])
        self.assertEqual(content['sources'][0]['url'], 'https://example.invalid/source')
        for hidden in ['reviewed_by', 'published_by', 'drafted_by', 'review_notes', 'content_sha256', 'is_current']:
            self.assertNotIn(hidden, content)

    def test_query_requests_only_current_published_vietnamese_content(self):
        self.get()
        params = next(r for r in self.seen if r.url.path.endswith('/food_descriptions')).url.params
        self.assertEqual((params['content_status'], params['is_current'], params['locale'], params['food_id']),
                         ('eq.published', 'eq.true', 'eq.vi', 'eq.' + RICE))
        self.assertEqual(self.seen[-1].headers['authorization'], 'Bearer ' + token())

    def test_unpublished_or_inconsistent_upstream_rows_fail_closed(self):
        for row in [published(content_status='draft'), published(content_status='reviewed'), published(is_current=False),
                    published(food_description_sources=[]), published(food_description_sources=[source(supports=['short_intro'])]),
                    published(reviewed_at='2026-10-19T01:00:00'), published(food_description_sources=[{**source(), 'content_sources': {**source()['content_sources'], 'url': 'http://example.invalid'}}])]:
            self.rows = [row]
            r = self.get()
            self.assertEqual(r.status_code, 503, row)
            self.assertEqual(r.json()['error']['code'], 'DEPENDENCY_UNAVAILABLE')
        self.rows = [published(), published(version=2)]
        self.assertEqual(self.get().status_code, 503)

    def test_null_origin_needs_no_origin_source(self):
        self.rows = [published(origin_text=None, food_description_sources=[source(supports=['short_intro', 'ingredients_summary', 'characteristics'])])]
        body = self.get().json()
        self.assertEqual(body['status'], 'available')
        self.assertIsNone(body['description']['origin_text'])

    def test_broad_class_requires_scope_note(self):
        self.rows = [published()]
        self.assertEqual(self.get(COFFEE).status_code, 503)
        self.rows = [published(scope_note='SYNTHETIC SCOPE', food_description_sources=[source(supports=['short_intro', 'origin_text', 'ingredients_summary', 'characteristics', 'scope_note'])])]
        body = self.get(COFFEE).json()
        self.assertEqual((body['status'], body['scope_kind'], body['description']['scope_note']), ('available', 'broad_food_category', 'SYNTHETIC SCOPE'))

    def test_auth_unknown_food_invalid_input_and_outage(self):
        self.assertEqual(self.client.get('/v1/foods/' + RICE + '/description').status_code, 401)
        self.assertEqual(self.get(USER_A).status_code, 404)
        self.assertEqual(self.get('not-a-uuid').status_code, 422)
        self.assertEqual(self.get(suffix='?locale=en').status_code, 422)
        self.outage = True
        r = self.get()
        self.assertEqual(r.status_code, 503)
        self.assertNotIn('MUST NOT LEAK', r.text)

    def test_openapi_documents_operation(self):
        spec = self.client.app.openapi()
        op = spec['paths']['/v1/foods/{id}/description']['get']
        self.assertEqual(op['operationId'], 'getFoodDescription')
        self.assertEqual(op['security'], [{'BearerAuth': []}])
        self.assertEqual(set(op['responses']), {'200', '401', '404', '422', '500', '503'})
        notice = spec['components']['schemas']['FoodDescription']['properties']['notice']
        self.assertIn('const', notice)


if __name__ == '__main__':
    unittest.main()
