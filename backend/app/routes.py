import re
from typing import Annotated
from fastapi import Depends,Request
from .auth import UserContext
from .errors import ApiError
from .input_models import ProfilePatch
from .models import Error,Profile


def revision(request,value):
    if value is None: raise ApiError(428,'IF_MATCH_REQUIRED','If-Match is required.')
    if len(request.headers.getlist('if-match'))!=1 or len(value)>12 or not re.fullmatch(r'"[1-9][0-9]*"',value):
        raise ApiError(422,'INVALID_INPUT','If-Match must be a quoted positive revision.')
    n=int(value[1:-1])
    if n>2147483647: raise ApiError(422,'INVALID_INPUT','If-Match revision is outside its valid range.')
    return n


def register_private_routes(app,user,allowed_query):
    User=Annotated[UserContext,Depends(user)]
    errors={401:{'model':Error},404:{'model':Error},422:{'model':Error},503:{'model':Error}}

    @app.get('/v1/me',response_model=Profile,operation_id='getMe',tags=['profile'],responses=errors)
    async def me(request:Request,context:User):
        await allowed_query(request,set())
        return await app.state.profiles.profile(context)

    @app.patch('/v1/me',response_model=Profile,operation_id='patchMe',tags=['profile'],responses=errors)
    async def patch_me(body:ProfilePatch,request:Request,context:User):
        await allowed_query(request,set())
        return await app.state.profiles.profile(context,body)
