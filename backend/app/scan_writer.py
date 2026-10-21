"""Privileged writes with explicit verified owner/scan/path guards."""
import re
from urllib.parse import quote
import httpx
from .auth import UserContext
from .errors import dependency_unavailable


def object_path(context,scan_id,path):
    if not isinstance(context,UserContext): raise dependency_unavailable()
    parts=path.split('/')
    if len(parts)!=3 or parts[:2]!=[str(context.user_id),str(scan_id)] or not re.fullmatch(r'[0-9a-f-]{36}\.(jpg|png|webp)',parts[2]):
        raise dependency_unavailable()
    from uuid import UUID
    try: UUID(parts[2].rsplit('.',1)[0])
    except ValueError: raise dependency_unavailable() from None
    return path


class ScanWriter:
    def __init__(self,settings,client): self.settings,self.client=settings,client
    @property
    def enabled(self): return self.settings.scan_service_key is not None
    async def request(self,path,method='POST',json=None,content=None,mime=None):
        if not self.enabled: raise dependency_unavailable()
        headers={'apikey':self.settings.public_key,'Authorization':'Bearer '+self.settings.scan_service_key}
        if mime: headers['Content-Type']=mime
        try:
            r=await self.client.request(method,self.settings.supabase_url.rstrip('/')+path,headers=headers,json=json,content=content)
            if r.status_code>=400: raise dependency_unavailable()
            return r.json() if r.content else None
        except (httpx.HTTPError,ValueError): raise dependency_unavailable() from None
    async def start(self,context,id,path,source):
        object_path(context,id,path)
        return await self.request('/rest/v1/rpc/start_scan',json=dict(p_owner=str(context.user_id),p_scan_id=str(id),p_image_path=path,p_input_source=source))
    async def upload(self,context,id,path,image):
        object_path(context,id,path)
        return await self.request('/storage/v1/object/food-scans/'+quote(path,safe='/'),content=image.data,mime='image/jpeg')
    async def finish(self,context,id,info,detections,error=None):
        if not isinstance(context,UserContext): raise dependency_unavailable()
        return await self.request('/rest/v1/rpc/finish_scan',json=dict(p_owner=str(context.user_id),p_scan_id=str(id),
            p_model_version=info.model_version,p_class_map_version=info.class_map_version,p_detections=detections,p_error_code=error))
    async def delete_image(self,context,id,path):
        object_path(context,id,path)
        return await self.request('/storage/v1/object/food-scans',method='DELETE',json={'prefixes':[path]})
