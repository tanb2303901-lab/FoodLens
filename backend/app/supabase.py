"""Shared connection pool, immutable Authorization per request."""
import httpx
from .errors import dependency_unavailable,unauthorized


class Supabase:
    def __init__(self,settings,client): self.settings,self.client=settings,client

    async def request(self,path,context=None,params=None,method='GET',json=None):
        headers={'apikey':self.settings.public_key}
        if context is not None: headers['Authorization']='Bearer '+context.token
        try:
            r=await self.client.request(method,self.settings.supabase_url.rstrip('/')+path,headers=headers,params=params,json=json)
            if r.status_code==401: raise unauthorized()
            if r.status_code>=400:
                if path.startswith('/rest/v1/rpc/'):
                    from .rpc_errors import rpc_error
                    raise rpc_error(r)
                raise dependency_unavailable()
            return r.json()
        except (httpx.HTTPError,ValueError): raise dependency_unavailable() from None

    async def ready(self):
        return await self.request('/rest/v1/rpc/core_readiness',method='POST') is True

    async def rpc(self,name,args,context):
        return await self.request('/rest/v1/rpc/'+name,context,method='POST',json=args)
