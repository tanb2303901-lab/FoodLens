from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self,status,code,message,details=None):
        self.status,self.code,self.message,self.details=status,code,message,details or []


def error_response(request:Request,status,code,message,details=None):
    headers={'WWW-Authenticate':'Bearer'} if status==401 else {}
    return JSONResponse(status_code=status,headers=headers,content={'error':dict(
        code=code,message=message,details=details or [],request_id=request.state.request_id)})


def unauthorized():
    return ApiError(401,'UNAUTHENTICATED','A valid Supabase user access token is required.')


def dependency_unavailable():
    return ApiError(503,'DEPENDENCY_UNAVAILABLE','A required backend dependency is unavailable.')


def parse_result(model,data):
    """Validate a trusted dependency response; malformed upstream data is a dependency failure."""
    from pydantic import ValidationError
    try: return model.model_validate(data)
    except ValidationError: raise dependency_unavailable() from None
