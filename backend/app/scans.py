import asyncio
from datetime import datetime,timedelta,timezone
import json
import logging
from urllib.parse import quote,urlsplit,unquote
from uuid import UUID,uuid4
import httpx
from starlette.concurrency import run_in_threadpool
from .errors import ApiError,dependency_unavailable
from .images import read_upload,canonical_image
from .cursor import TimeCursor,stamp
from .errors import parse_result
from .models import Scan,ScanSummary,ScanPage
from .predictor import ClassMap,model_not_ready
from .scan_writer import ScanWriter,object_path

LOGGER=logging.getLogger(__name__)
SUMMARY=['id','status','input_source','revision','created_at','updated_at']
COLUMNS=SUMMARY+['user_id','model_version','class_map_version','detections','confirmations','image_path','error_code']


class Scans:
    def __init__(self,settings,db,client,predictor=None):
        self.settings,self.db,self.client=settings,db,client
        from .detector import configured_predictor
        self.predictor=predictor if predictor is not None else configured_predictor(settings)
        try: self.map=ClassMap()
        except (OSError,ValueError,KeyError,TypeError):
            self.map=None; LOGGER.warning('Detector class map is unavailable; core APIs remain enabled.')
        self.writer=ScanWriter(settings,client)
        self.cursor=TimeCursor(settings.cursor_secret,scope='scans:created_at,id:desc',time_key='created_at')
        self.slots=asyncio.Semaphore(2)

    def model_info(self):
        if self.map is None: return None
        try: info=self.predictor.status()
        except Exception: return None
        if not self.map.compatible(info):
            try:
                mapping=ClassMap(info.class_map_version)
                if not mapping.compatible(info):return None
                self.map=mapping
            except (AttributeError,OSError,ValueError,KeyError,TypeError):return None
        return info

    async def raw(self,id,context):
        rows=await self.db.request('/rest/v1/scans',context,params=dict(select=','.join(COLUMNS),
            id='eq.'+str(id),user_id='eq.'+str(context.user_id),limit='1'))
        if not rows: return None
        row=rows[0]
        if row.get('user_id')!=str(context.user_id) or row.get('id')!=str(id): raise dependency_unavailable()
        return row

    async def signed_image(self,path,id,context):
        if path is None: return None,None
        object_path(context,id,path)
        endpoint='/storage/v1/object/sign/food-scans/'+quote(path,safe='/')
        headers={'apikey':self.settings.public_key,'Authorization':'Bearer '+context.token}
        try:
            r=await self.client.post(self.settings.supabase_url.rstrip('/')+endpoint,headers=headers,json={'expiresIn':self.settings.image_url_ttl})
            if r.status_code>=400:
                data=r.json()
                if r.status_code==404 or str(data.get('statusCode'))=='404': return None,None
                raise dependency_unavailable()
            value=r.json().get('signedURL') or r.json().get('signedUrl')
            if not isinstance(value,str): raise dependency_unavailable()
            if value.startswith('/object/sign/'): value=self.settings.supabase_url.rstrip('/')+'/storage/v1'+value
            elif value.startswith('/storage/v1/object/sign/'): value=self.settings.supabase_url.rstrip('/')+value
            url=urlsplit(value); origin=urlsplit(self.settings.supabase_url)
            if (url.scheme,url.netloc)!=(origin.scheme,origin.netloc) or url.username or url.password or url.fragment:
                raise dependency_unavailable()
            if unquote(url.path)!='/storage/v1/object/sign/food-scans/'+path or not url.query:
                raise dependency_unavailable()
            if self.settings.public_supabase_url:
                # Devices cannot open the server's loopback origin; hand them the reachable one.
                public=urlsplit(self.settings.public_supabase_url)
                value=url._replace(scheme=public.scheme,netloc=public.netloc).geturl()
            return value,datetime.now(timezone.utc)+timedelta(seconds=self.settings.image_url_ttl)
        except (httpx.HTTPError,ValueError,TypeError,AttributeError): raise dependency_unavailable() from None

    async def dto(self,row,context):
        if row.get('user_id')!=str(context.user_id): raise dependency_unavailable()
        try:
            id=UUID(row['id']); data={k:row[k] for k in COLUMNS if k not in ('user_id','image_path')}
            # Validate all stored fields before issuing an image URL.
            parsed=parse_result(Scan,dict(**data,image_url=None,image_url_expires_at=None))
            url,expires=await self.signed_image(row['image_path'],id,context)
            return parsed.model_copy(update={'image_url':url,'image_url_expires_at':expires})
        except (KeyError,TypeError,ValueError): raise dependency_unavailable() from None

    async def detail(self,id,context):
        row=await self.raw(id,context)
        if row is None: raise ApiError(404,'NOT_FOUND','Scan was not found.')
        return await self.dto(row,context)

    async def page(self,context,limit,start,end,cursor):
        if start and end and start>=end: raise ApiError(422,'INVALID_TIME_RANGE','from must be earlier than to.')
        params=dict(select=','.join(SUMMARY),user_id='eq.'+str(context.user_id),order='created_at.desc,id.desc',limit=str(limit+1))
        filters=[]
        if start: filters.append('created_at.gte.'+json.dumps(stamp(start)))
        if end: filters.append('created_at.lt.'+json.dumps(stamp(end)))
        if cursor:
            at,id=self.cursor.decode(cursor,context.user_id,start,end); date=json.dumps(stamp(at))
            filters.append(f'or(created_at.lt.{date},and(created_at.eq.{date},id.lt.{id}))')
        if filters: params['and']='('+','.join(filters)+')'
        data=await self.db.request('/rest/v1/scans',context,params=params)
        items=[parse_result(ScanSummary,r) for r in data[:limit]]
        next_cursor=self.cursor.encode(context.user_id,start,end,items[-1].created_at,items[-1].id) if len(data)>limit and items else None
        return ScanPage(items=items,next_cursor=next_cursor)

    async def confirm(self,id,context,revision,body):
        row=await self.db.rpc('confirm_scan',dict(p_scan_id=str(id),p_expected_revision=revision,
            p_request=body.model_dump(mode='json')),context)
        return await self.dto(row,context)

    async def compensate(self,context,id,path,info,failure):
        # Never delete an image until the database has confirmed this scan failed.
        try: row=await self.writer.finish(context,id,info,[],failure.code)
        except ApiError:
            try: row=await self.raw(id,context)
            except ApiError: row=None
        if row and row.get('user_id')==str(context.user_id) and row.get('id')==str(id):
            if row['status']=='completed': return row  # Completion response was lost; preserve real saved output/image.
            if row['status']=='failed':
                try: await self.writer.delete_image(context,id,path)
                except ApiError: LOGGER.warning('Scan image cleanup pending: scan_id=%s',id)
                raise ApiError(failure.status,failure.code,failure.message,[{'field':'scan_id','message':str(id)}])
        LOGGER.warning('Scan outcome requires reconciliation: scan_id=%s',id)
        raise ApiError(503,'SCAN_STATE_UNCERTAIN','Scan state could not be confirmed; check scan history.',[{'field':'scan_id','message':str(id)}])

    async def analyze(self,request,context):
        info=self.model_info()
        if info is None: raise model_not_ready()
        mapping=self.map  # Pin the matching map across awaits/concurrent requests.
        if not self.writer.enabled: raise dependency_unavailable()
        async with self.slots:
            try:
                async with asyncio.timeout(self.settings.http_timeout*2):
                    raw,mime,source=await read_upload(request,self.settings)
                    image=await run_in_threadpool(canonical_image,raw,mime,self.settings)
            except TimeoutError: raise ApiError(408,'UPLOAD_TIMEOUT','Image upload timed out.') from None
            id=uuid4(); path=f'{context.user_id}/{id}/{uuid4()}.jpg'
            try:
                await self.writer.start(context,id,path,source)
                await self.writer.upload(context,id,path,image)
                async with asyncio.timeout(self.settings.prediction_timeout):
                    output=await self.predictor.predict(image,info)
                detections=mapping.detections(output)
                row=await self.writer.finish(context,id,info,detections)
            except TimeoutError:
                row=await self.compensate(context,id,path,info,ApiError(504,'PREDICTION_TIMEOUT','Detector inference timed out.'))
            except ApiError as failure: row=await self.compensate(context,id,path,info,failure)
            except Exception:
                row=await self.compensate(context,id,path,info,ApiError(503,'PREDICTION_FAILED','Detector inference failed.'))
            return await self.dto(row,context)
