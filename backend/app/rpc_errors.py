"""Map only known DB domain errors; never pass SQL error text/details to clients."""
from .errors import ApiError,dependency_unavailable,unauthorized

INVALID={'INVALID_INPUT','INVALID_FOOD','INVALID_TIMEZONE','INVALID_TIMESTAMP','INVALID_CURSOR','INVALID_LIMIT',
 'INVALID_TIME_RANGE','DUPLICATE_DETECTION','INVALID_CONFIRMATION'}


def rpc_error(response):
    try: body=response.json()
    except ValueError: return dependency_unavailable()
    if not isinstance(body,dict): return dependency_unavailable()
    if body.get('code')=='P0001':
        code=body.get('message')
        if code=='UNAUTHENTICATED': return unauthorized()
        if code=='NOT_FOUND': return ApiError(404,code,'Resource was not found.')
        if code=='IF_MATCH_REQUIRED': return ApiError(428,code,'If-Match is required.')
        if code=='VERSION_CONFLICT': return ApiError(412,code,'Resource revision has changed.')
        if code=='SCAN_NOT_COMPLETED': return ApiError(409,code,'Scan is not completed.')
        if code in INVALID: return ApiError(422,code,'Request is invalid for this operation.')
    if body.get('code')=='23505': return ApiError(409,'RESOURCE_CONFLICT','Request conflicts with existing data.')
    if body.get('code') in ('23502','23503','23514','22P02','22008','22007'):
        return ApiError(422,'INVALID_INPUT','Request violates a data constraint.')
    return dependency_unavailable()
