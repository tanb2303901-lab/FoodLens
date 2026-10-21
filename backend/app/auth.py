"""Cryptographic JWT verification; token headers never choose a signing URL."""
import asyncio
from dataclasses import dataclass,field
import math
import time
from uuid import UUID

import httpx
import jwt
from .errors import unauthorized,dependency_unavailable


@dataclass(frozen=True)
class UserContext:
    user_id: UUID
    token: str = field(repr=False)


class JwtVerifier:
    def __init__(self,settings,client):
        self.settings,self.client=settings,client
        self.keys={}; self.expires=0.; self.last_fetch=0.; self.lock=asyncio.Lock()

    async def signing_key(self,kid):
        async with self.lock:
            now=time.monotonic()
            if now < self.expires and kid in self.keys: return self.keys[kid]
            # One rotation fetch per 10s for unknown kids, instead of a request per attack token.
            if now < self.expires and now-self.last_fetch < 10: raise unauthorized()
            try:
                r=await self.client.get(self.settings.supabase_url.rstrip('/')+'/auth/v1/.well-known/jwks.json')
                r.raise_for_status()
                keys=r.json()['keys']
                if not isinstance(keys,list) or len(keys)>20: raise ValueError('Invalid JWKS')
                parsed={}
                for value in keys:
                    if not isinstance(value,dict): raise ValueError('Invalid JWK shape')
                    if (value.get('alg')==self.settings.jwt_algorithm and value.get('use','sig')=='sig'
                        and value.get('kid') and value.get('kty') in ('EC','RSA')):
                        key=jwt.PyJWK.from_dict(value,algorithm=self.settings.jwt_algorithm)
                        if key.key_id in parsed: raise ValueError('Duplicate kid')
                        parsed[key.key_id]=key.key
                self.keys=parsed; self.last_fetch=now; self.expires=now+self.settings.jwks_ttl
            except (httpx.HTTPError,ValueError,KeyError,TypeError,jwt.PyJWTError):
                raise dependency_unavailable() from None
            if kid not in self.keys: raise unauthorized()
            return self.keys[kid]

    async def verify(self,token):
        if len(token)>16384 or token.count('.')!=2: raise unauthorized()
        try:
            header=jwt.get_unverified_header(token)
            if header.get('alg')!=self.settings.jwt_algorithm or header.get('crit'):
                raise unauthorized()
            if self.settings.jwt_algorithm=='HS256': key=self.settings.jwt_secret
            else:
                kid=header.get('kid')
                if not isinstance(kid,str) or not kid or len(kid)>256: raise unauthorized()
                key=await self.signing_key(kid)
            claims=jwt.decode(token,key,algorithms=[self.settings.jwt_algorithm],
                              audience=self.settings.jwt_audience,issuer=self.settings.jwt_issuer,
                              options={'require':['exp','iat','iss','aud','sub','role']})
            if claims.get('role')!='authenticated': raise unauthorized()
            for c in ('exp','iat','nbf'):
                if c in claims and (type(claims[c]) not in (int,float) or not math.isfinite(claims[c])):
                    raise unauthorized()
            sub=UUID(claims['sub'])
            if sub.int==0 or str(sub)!=claims['sub']: raise unauthorized()
            return UserContext(sub,token)
        except (jwt.PyJWTError,ValueError,TypeError,KeyError,OverflowError):
            raise unauthorized() from None
