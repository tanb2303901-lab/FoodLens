from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID,uuid4
import logging

from fastapi import Depends,FastAPI,Query,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials,HTTPBearer
from starlette.exceptions import HTTPException
import httpx

from .auth import JwtVerifier,UserContext
from .catalog import Catalog
from .config import Settings
from .cursor import CatalogCursor
from .errors import ApiError,error_response,unauthorized
from .models import Capabilities,Error,Food,FoodDescription,FoodPage,Health,Readiness


def create_app(settings=None,transport=None,predictor=None):
    @asynccontextmanager
    async def lifespan(app):
        from .supabase import Supabase
        config=settings or Settings.load()
        async with httpx.AsyncClient(timeout=config.http_timeout,transport=transport,follow_redirects=False,trust_env=False) as client:
            app.state.db=Supabase(config,client)
            app.state.verifier=JwtVerifier(config,client)
            app.state.catalog=Catalog(app.state.db,CatalogCursor(config.cursor_secret))
            from .profiles import Profiles
            app.state.profiles=Profiles(app.state.db)
            from .scans import Scans
            app.state.scans=Scans(config,app.state.db,client,predictor)
            yield
    app=FastAPI(title='FoodLens API',version='0.7.0',description='Backend v1: profile, catalog, real-detector scan and scan-history APIs with versioned67/75 food identities, plus sourced food introductions served only after human review and publication. Nutrition, manual meals and stats were removed by owner decision (FOOD-02).',lifespan=lifespan)

    @app.middleware('http')
    async def request_context(request,call_next):
        request.state.request_id=str(uuid4())
        try: response=await call_next(request)
        except Exception as exc:
            # Report the exception class only; exception messages may contain
            # headers, credentials, signed URLs or dependency response bodies.
            logging.getLogger(__name__).error('Unexpected backend failure kind=%s request_id=%s',type(exc).__name__,request.state.request_id)
            response=error_response(request,500,'INTERNAL_ERROR','An unexpected backend error occurred.')
        response.headers['X-Request-ID']=request.state.request_id
        response.headers['Cache-Control']='no-store'
        return response

    @app.exception_handler(ApiError)
    async def api_error(request,exc): return error_response(request,exc.status,exc.code,exc.message,exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):
        # Never echo rejected input, Authorization or SQL exception text.
        details=[dict(field='.'.join(str(x) for x in e['loc']),message='Invalid value.') for e in exc.errors()]
        return error_response(request,422,'INVALID_INPUT','Request validation failed.',details)

    @app.exception_handler(HTTPException)
    async def http_error(request,exc):
        return error_response(request,exc.status_code,'NOT_FOUND' if exc.status_code==404 else 'HTTP_ERROR','Resource not found.' if exc.status_code==404 else 'Request could not be handled.')

    bearer=HTTPBearer(auto_error=False,scheme_name='BearerAuth')
    async def user(request:Request,credentials:Annotated[HTTPAuthorizationCredentials | None,Depends(bearer)]):
        if not credentials or credentials.scheme.lower()!='bearer': raise unauthorized()
        return await request.app.state.verifier.verify(credentials.credentials)
    User=Annotated[UserContext,Depends(user)]

    async def allowed_query(request:Request,fields:set):
        if any(k not in fields or len(request.query_params.getlist(k))!=1 for k in request.query_params):
            raise ApiError(422,'INVALID_INPUT','Unknown or repeated query parameter.')

    failures={401:{'model':Error},422:{'model':Error},503:{'model':Error}}

    @app.get('/health',response_model=Health,operation_id='getHealth',tags=['health'],responses={422:{'model':Error}})
    async def health(request:Request):
        await allowed_query(request,set())
        return Health()

    @app.get('/health/ready',response_model=Readiness,operation_id='getReadiness',tags=['health'],responses={422:{'model':Error},503:{'model':Readiness}})
    async def readiness(request:Request):
        await allowed_query(request,set())
        try: ready=await request.app.state.db.ready()
        except ApiError: ready=False
        model=app.state.scans.model_info() is not None
        value=Readiness(status='ready' if ready else 'not_ready',database='ready' if ready else 'not_ready',model='ready' if model else 'not_ready',
                        capabilities=Capabilities(catalog=ready,scan=ready and model and app.state.scans.writer.enabled))
        return JSONResponse(value.model_dump(),status_code=200 if ready else 503)

    @app.get('/v1/foods',response_model=FoodPage,operation_id='listFoods',tags=['catalog'],responses=failures)
    async def foods(request:Request,context:User,q:Annotated[str,Query(max_length=100)]='',
                    limit:Annotated[int,Query(ge=1,le=100)]=20,cursor:Annotated[str | None,Query(max_length=2048)]=None):
        await allowed_query(request,{'q','limit','cursor'})
        return await request.app.state.catalog.page(context,q.strip(),limit,cursor)

    @app.get('/v1/foods/{id}',response_model=Food,operation_id='getFood',tags=['catalog'],responses={**failures,404:{'model':Error}})
    async def food_detail(id:UUID,request:Request,context:User):
        await allowed_query(request,set())
        return await request.app.state.catalog.detail(id,context)

    @app.get('/v1/foods/{id}/description',response_model=FoodDescription,operation_id='getFoodDescription',tags=['catalog'],responses={**failures,404:{'model':Error}})
    async def description(id:UUID,request:Request,context:User):
        await allowed_query(request,set())
        return await request.app.state.catalog.description(id,context)

    from .routes import register_private_routes
    register_private_routes(app,user,allowed_query)
    from .scan_routes import register_scan_routes
    register_scan_routes(app,user,allowed_query)
    from .openapi import configure_openapi
    configure_openapi(app)
    return app


app=create_app()
