"""BE-01 behavior tests using synthetic signing keys and upstream HTTP fixtures."""
import asyncio
import base64
import json
import time
from uuid import UUID
import unittest

from cryptography.hazmat.primitives.asymmetric import ec,rsa
import httpx
import jwt
from fastapi.testclient import TestClient

from backend.app.auth import JwtVerifier
from backend.app.config import Settings
from backend.app.cursor import CatalogCursor
from backend.app.errors import ApiError
from backend.app.main import create_app

SECRET='BE01_SYNTHETIC_KEY_NEVER_USED_WITH_SUPABASE_0123456789'
USER_A='10000000-0000-4000-8000-000000000001'
USER_B='10000000-0000-4000-8000-000000000002'
RICE='89cde1f5-b817-541d-b122-a6084f566261'
OTHER='5a4c8735-e6fc-5ec1-879a-222752d7adec'


def settings(**overrides):
    defaults=dict(supabase_url='http://127.0.0.1:54321',public_key=jwt.encode({'role':'anon'},SECRET,algorithm='HS256'),
        jwt_issuer='http://127.0.0.1:54321/auth/v1',jwt_audience='authenticated',jwt_algorithm='HS256',
        jwt_secret=SECRET,cursor_secret='BE01_SYNTHETIC_CURSOR_KEY_0123456789')
    return Settings(**(defaults|overrides))


def claims(**overrides):
    return dict(sub=USER_A,role='authenticated',iss=settings().jwt_issuer,aud='authenticated',
                iat=int(time.time())-1,exp=int(time.time())+600)|overrides


def token(**overrides): return jwt.encode(claims(**overrides),SECRET,algorithm='HS256')


def food(id=RICE,slug='com'):
    return dict(id=id,slug=slug,name_vi='SYNTHETIC TEST',name_en=None,scope_kind='prepared_food',
                original_class_id=25,training_class_id=25,class_map_version='vietfood-67-2026-10-12-v1')


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.rows=[food(),food(OTHER,'cu_kieu')]; self.seen=[]; self.outage=False
        async def upstream(req):
            self.seen.append(req)
            if self.outage: raise httpx.ConnectError('synthetic upstream credential MUST NOT LEAK',request=req)
            if req.url.path.endswith('/core_readiness'): return httpx.Response(200,json=True)
            if req.url.path.endswith('/foods'):
                rows=self.rows
                if 'id' in req.url.params: rows=[r for r in rows if 'eq.'+r['id']==req.url.params['id']]
                return httpx.Response(200,json=rows)
            return httpx.Response(500,json={'message':'unsafe upstream body'})
        self.client=TestClient(create_app(settings(),httpx.MockTransport(upstream)))
        self.client.__enter__()
    def tearDown(self): self.client.__exit__(None,None,None)
    def get(self,url,access=None): return self.client.get(url,headers={'Authorization':'Bearer '+(access or token())})

    def test_liveness_no_upstream(self):
        self.assertEqual(self.client.get('/health').json(),{'status':'alive'}); self.assertEqual(self.seen,[])

    def test_readiness_capabilities_truthful_and_no_user_or_service_token(self):
        r=self.client.get('/health/ready')
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['capabilities'],dict(catalog=True,scan=False))
        self.assertEqual(r.json()['model'],'not_ready'); self.assertNotIn('authorization',self.seen[0].headers)

    def test_readiness_outage_503_liveness_alive(self):
        self.outage=True
        self.assertEqual(self.client.get('/health/ready').status_code,503)
        self.assertEqual(self.client.get('/health').status_code,200)

    def test_missing_wrong_scheme_and_malformed_jwt(self):
        for headers in ({},{'Authorization':'Basic aaa'},{'Authorization':'Bearer malformed'}):
            r=self.client.get('/v1/foods',headers=headers)
            self.assertEqual(r.status_code,401); self.assertEqual(r.headers['www-authenticate'],'Bearer')
            self.assertEqual(r.json()['error']['code'],'UNAUTHENTICATED')
        self.assertEqual(self.seen,[])

    def test_invalid_signature_and_none_algorithm(self):
        wrong=jwt.encode(claims(),'different synthetic key 0123456789012345',algorithm='HS256')
        unsigned=jwt.encode(claims(),key=None,algorithm='none')
        for access in (wrong,unsigned): self.assertEqual(self.get('/v1/foods',access).status_code,401)

    def test_expired_future_issuer_audience_subject_and_role(self):
        for changes in [dict(exp=1),dict(iat=time.time()+1000),dict(nbf=time.time()+1000),dict(iss='https://other/auth/v1'),
                        dict(aud='other'),dict(sub='not-a-uuid'),dict(sub='00000000-0000-0000-0000-000000000000'),
                        dict(role='service_role'),dict(role='anon'),dict(exp=True),dict(exp=float('inf'))]:
            self.assertEqual(self.get('/v1/foods',token(**changes)).status_code,401,changes)

    def test_required_claims(self):
        for name in ['exp','iat','iss','aud','sub','role']:
            c=claims(); c.pop(name)
            self.assertEqual(self.get('/v1/foods',jwt.encode(c,SECRET,algorithm='HS256')).status_code,401)

    def test_request_context_and_error_sanitization(self):
        self.outage=True; access=token()
        r=self.get('/v1/foods',access)
        self.assertEqual(r.status_code,503)
        self.assertEqual(r.headers['x-request-id'],r.json()['error']['request_id'])
        for value in [access,SECRET,'MUST NOT LEAK','unsafe upstream body']: self.assertNotIn(value,r.text)

    def test_request_headers_are_isolated(self):
        a,b=token(),token(sub=USER_B)
        self.get('/v1/foods',a); self.get('/v1/foods',b)
        self.assertEqual([r.headers.get('authorization') for r in self.seen],['Bearer '+a,'Bearer '+b])

    def test_catalog_returns_identity_only_and_nutrition_is_removed(self):
        r=self.get('/v1/foods'); self.assertEqual(r.status_code,200)
        self.assertNotIn('nutrition_status',r.json()['items'][0])
        self.assertNotIn('source_mapping_metadata',r.text)
        self.assertEqual(self.get('/v1/foods/'+RICE+'/nutrition').status_code,404)
        self.assertFalse(any('nutrition' in q.url.path or 'portion' in q.url.path for q in self.seen))

    def test_unknown_food_and_invalid_uuid(self):
        self.assertEqual(self.get('/v1/foods/'+USER_A).status_code,404)
        self.assertEqual(self.get('/v1/foods/not-uuid').status_code,422)

    def test_unknown_repeated_queries_and_limit_range(self):
        for url in ['/v1/foods?limit=0','/v1/foods?limit=101','/v1/foods?limit=1&limit=2',
                    '/v1/foods?user_id='+USER_B,'/v1/foods?q='+'a'*101,'/v1/foods/'+RICE+'?q=a']:
            self.assertEqual(self.get(url).status_code,422,url)

    def test_cursor_tamper_and_filter_binding(self):
        r=self.get('/v1/foods?limit=1'); value=r.json()['next_cursor']; self.assertIsInstance(value,str)
        bad=('A' if value[0]!='A' else 'B')+value[1:]
        self.assertEqual(self.get('/v1/foods?cursor='+bad).status_code,422)
        self.assertEqual(self.get('/v1/foods?q=changed&cursor='+value).status_code,422)

    def test_cursor_applies_keyset_and_active_filters(self):
        c=CatalogCursor(settings().cursor_secret).encode('','com',RICE)
        self.get('/v1/foods?cursor='+c)
        params=self.seen[0].url.params
        self.assertEqual(params['active'],'eq.true'); self.assertEqual(params['order'],'slug.asc,id.asc')
        self.assertIn('slug.gt.com',params['and'])

    def test_concurrent_tokens_do_not_replace_each_other(self):
        from concurrent.futures import ThreadPoolExecutor
        a,b=token(),token(sub=USER_B)
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses=list(pool.map(lambda access:self.get('/v1/foods',access),[a,b]*5))
        self.assertTrue(all(r.status_code==200 for r in responses))
        from collections import Counter
        values=Counter(r.headers['authorization'] for r in self.seen)
        self.assertEqual(values,{'Bearer '+a:5,'Bearer '+b:5})

    def test_openapi_only_implemented_paths_and_bearer(self):
        spec=self.client.get('/openapi.json').json()
        self.assertEqual(set(spec['paths']),{'/health','/health/ready','/v1/foods','/v1/foods/{id}','/v1/foods/{id}/description',
                                           '/v1/me','/v1/scans/analyze','/v1/scans','/v1/scans/{id}','/v1/scans/{id}/result'})
        self.assertEqual(spec['paths']['/v1/foods']['get']['security'],[{'BearerAuth':[]}])
        self.assertNotIn('security',spec['paths']['/health']['get'])


class ConfigurationTests(unittest.TestCase):
    def test_repr_hides_secrets(self):
        s=settings()
        for secret in [s.public_key,s.cursor_secret,s.jwt_secret]: self.assertNotIn(secret,repr(s))

    def test_reject_service_key_remote_http_and_confused_algorithms(self):
        for changes in [dict(public_key=jwt.encode({'role':'service_role'},SECRET,algorithm='HS256')),
                        dict(public_key='sb_secret_FORBIDDEN'),dict(supabase_url='http://remote.example'),
                        dict(jwt_algorithm='none'),dict(jwt_issuer='https://other'),dict(cursor_secret='short'),
                        dict(jwt_secret=None),dict(jwt_audience='anon')]:
            with self.assertRaises(ValueError): settings(**changes)

    def test_readiness_has_no_removed_capabilities(self):
        from backend.app.models import Capabilities
        self.assertEqual(set(Capabilities.model_fields),{'catalog','scan'})


class JwksTests(unittest.TestCase):
    def keys(self,kid):
        private=ec.generate_private_key(ec.SECP256R1())
        public=json.loads(jwt.algorithms.ECAlgorithm.to_jwk(private.public_key()))
        public.update(kid=kid,alg='ES256',use='sig')
        return private,public

    def test_es256_signature_cache_rotation_and_unknown_kid(self):
        async def run():
            private,public=self.keys('a'); next_private,next_public=self.keys('b'); requests=[]
            current=[public]
            def upstream(req): requests.append(req); return httpx.Response(200,json={'keys':current})
            async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
                verifier=JwtVerifier(settings(jwt_algorithm='ES256',jwt_secret=None),client)
                signed=jwt.encode(claims(),private,algorithm='ES256',headers={'kid':'a','jku':'https://attacker.invalid'})
                self.assertEqual((await verifier.verify(signed)).user_id,UUID(USER_A))
                await verifier.verify(signed); self.assertEqual(len(requests),1)
                self.assertEqual(str(requests[0].url),settings().supabase_url+'/auth/v1/.well-known/jwks.json')
                current[:]=[next_public]; verifier.last_fetch-=11
                changed=jwt.encode(claims(),next_private,algorithm='ES256',headers={'kid':'b'})
                await verifier.verify(changed); self.assertEqual(len(requests),2)
                forged=jwt.encode(claims(),private,algorithm='ES256',headers={'kid':'b'})
                with self.assertRaises(ApiError) as failure: await verifier.verify(forged)
                self.assertEqual(failure.exception.status,401)
                with self.assertRaises(ApiError): await verifier.verify(signed)
                self.assertEqual(len(requests),2)
        asyncio.run(run())

    def test_jwks_network_failure_is_dependency_503(self):
        async def run():
            private,_=self.keys('a')
            def upstream(req): raise httpx.ConnectError('SYNTHETIC SECRET',request=req)
            async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
                verifier=JwtVerifier(settings(jwt_algorithm='ES256',jwt_secret=None),client)
                with self.assertRaises(ApiError) as failure:
                    await verifier.verify(jwt.encode(claims(),private,algorithm='ES256',headers={'kid':'a'}))
                self.assertEqual(failure.exception.status,503); self.assertNotIn('SECRET',str(failure.exception))
        asyncio.run(run())

    def test_rs256_uses_configured_public_key(self):
        async def run():
            private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
            public=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
            public.update(kid='rsa-test',alg='RS256',use='sig')
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'keys':[public]}))) as client:
                verifier=JwtVerifier(settings(jwt_algorithm='RS256',jwt_secret=None),client)
                signed=jwt.encode(claims(),private,algorithm='RS256',headers={'kid':'rsa-test'})
                self.assertEqual((await verifier.verify(signed)).user_id,UUID(USER_A))
        asyncio.run(run())

    def test_malformed_jwks_fails_as_dependency(self):
        async def run():
            private,_=self.keys('a')
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'keys':[1]}))) as client:
                verifier=JwtVerifier(settings(jwt_algorithm='ES256',jwt_secret=None),client)
                with self.assertRaises(ApiError) as failure:
                    await verifier.verify(jwt.encode(claims(),private,algorithm='ES256',headers={'kid':'a'}))
                self.assertEqual(failure.exception.status,503)
        asyncio.run(run())


if __name__=='__main__': unittest.main()
