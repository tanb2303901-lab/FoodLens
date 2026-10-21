import base64
from datetime import timezone
import hashlib
import hmac
import json
import re
from uuid import UUID
from .errors import ApiError


class CatalogCursor:
    def __init__(self,secret): self.secret=secret.encode('utf-8')

    def encode(self,q,slug,id):
        raw=json.dumps({'v':1,'q':q,'slug':slug,'id':str(id)},sort_keys=True,separators=(',',':')).encode()
        signed=raw+hmac.digest(self.secret,raw,'sha256')
        return base64.urlsafe_b64encode(signed).decode().rstrip('=')

    def decode(self,value,q):
        try:
            if len(value)>2048 or not re.fullmatch('[A-Za-z0-9_-]+',value): raise ValueError()
            signed=base64.b64decode(value+'='*(-len(value)%4),altchars=b'-_',validate=True)
            raw,sig=signed[:-32],signed[-32:]
            if not hmac.compare_digest(sig,hmac.digest(self.secret,raw,'sha256')): raise ValueError()
            body=json.loads(raw)
            if set(body)!= {'v','q','slug','id'} or body['v']!=1 or body['q']!=q: raise ValueError()
            if not isinstance(body['slug'],str) or not re.fullmatch('[a-z0-9]+(_[a-z0-9]+)*',body['slug']): raise ValueError()
            return body['slug'],str(UUID(body['id']))
        except (ValueError,TypeError,KeyError,UnicodeError):
            raise ApiError(422,'INVALID_CURSOR','Cursor is invalid or belongs to a different search.') from None


def stamp(value): return value.astimezone(timezone.utc).isoformat() if value else None


class TimeCursor:
    """Owner/filter-bound keyset cursor for time-ordered private lists (scan history)."""
    def __init__(self,secret,scope,time_key):
        self.secret=secret.encode(); self.scope=scope; self.time_key=time_key
    def encode(self,owner,start,end,at,id):
        body=dict(v=1,scope=self.scope,owner=str(owner),start=stamp(start),end=stamp(end),id=str(id))
        body[self.time_key]=stamp(at)
        raw=json.dumps(body,sort_keys=True,separators=(',',':')).encode()
        return base64.urlsafe_b64encode(raw+hmac.digest(self.secret,raw,'sha256')).decode().rstrip('=')
    def decode(self,token,owner,start,end):
        from .input_models import iso_timestamp
        try:
            if len(token)>2048 or not re.fullmatch('[A-Za-z0-9_-]+',token): raise ValueError()
            signed=base64.b64decode(token+'='*(-len(token)%4),altchars=b'-_',validate=True)
            raw,sig=signed[:-32],signed[-32:]
            if not hmac.compare_digest(sig,hmac.digest(self.secret,raw,'sha256')): raise ValueError()
            body=json.loads(raw)
            if set(body)!= {'v','scope','owner','start','end',self.time_key,'id'} or body['v']!=1 or body['scope']!=self.scope: raise ValueError()
            if (body['owner'],body['start'],body['end'])!=(str(owner),stamp(start),stamp(end)): raise ValueError()
            return iso_timestamp(body[self.time_key]),UUID(body['id'])
        except (ValueError,TypeError,KeyError,UnicodeError):
            raise ApiError(422,'INVALID_CURSOR','Cursor is invalid or belongs to a different owner or filter.') from None
