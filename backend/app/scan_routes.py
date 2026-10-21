from typing import Annotated
from uuid import UUID
from fastapi import Depends,Header,Query,Request,Response
from .auth import UserContext
from .input_models import ScanResultPatch,Timestamp
from .models import Error,Scan,ScanPage
from .routes import revision


def register_scan_routes(app,user,allowed_query):
    User=Annotated[UserContext,Depends(user)]
    errors={401:{'model':Error},422:{'model':Error},503:{'model':Error}}
    etag={'ETag':{'schema':{'type':'string'}}}
    multipart={'requestBody':{'required':True,'content':{'multipart/form-data':{'schema':{'type':'object',
        'properties':{'file':{'type':'string','format':'binary'},'input_source':{'type':'string','enum':['camera','gallery','share'],'default':'gallery'}},
        'required':['file'],'additionalProperties':False}}}}}

    # No File/Form dependency: authentication + readiness precede body parsing.
    @app.post('/v1/scans/analyze',response_model=Scan,status_code=201,operation_id='analyzeScan',tags=['scans'],
              responses={**errors,408:{'model':Error},413:{'model':Error},415:{'model':Error},504:{'model':Error},201:{'headers':etag}},openapi_extra=multipart)
    async def analyze(request:Request,context:User,response:Response):
        await allowed_query(request,set())
        scan=await app.state.scans.analyze(request,context)
        response.headers['ETag']='"'+str(scan.revision)+'"'
        return scan

    @app.get('/v1/scans',response_model=ScanPage,operation_id='listScans',tags=['scans'],responses=errors)
    async def history(request:Request,context:User,limit:Annotated[int,Query(ge=1,le=100)]=20,
                      cursor:Annotated[str | None,Query(max_length=2048)]=None,
                      start:Annotated[Timestamp | None,Query(alias='from')]=None,end:Annotated[Timestamp | None,Query(alias='to')]=None):
        await allowed_query(request,{'limit','cursor','from','to'})
        return await app.state.scans.page(context,limit,start,end,cursor)

    @app.get('/v1/scans/{id}',response_model=Scan,operation_id='getScan',tags=['scans'],responses={**errors,404:{'model':Error},200:{'headers':etag}})
    async def detail(id:UUID,request:Request,context:User,response:Response):
        await allowed_query(request,set())
        scan=await app.state.scans.detail(id,context)
        response.headers['ETag']='"'+str(scan.revision)+'"'
        return scan

    @app.patch('/v1/scans/{id}/result',response_model=Scan,operation_id='confirmScan',tags=['scans'],
               responses={**errors,404:{'model':Error},409:{'model':Error},412:{'model':Error},428:{'model':Error},200:{'headers':etag}})
    async def confirm(id:UUID,body:ScanResultPatch,request:Request,context:User,response:Response,
                      match:Annotated[str | None,Header(alias='If-Match')]=None):
        await allowed_query(request,set())
        scan=await app.state.scans.confirm(id,context,revision(request,match),body)
        response.headers['ETag']='"'+str(scan.revision)+'"'
        return scan
