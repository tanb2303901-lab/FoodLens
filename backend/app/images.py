"""Bounded multipart parsing and canonical static RGB image validation."""
from dataclasses import dataclass
import io
import warnings
from PIL import Image,ImageOps,UnidentifiedImageError
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.requests import Request,ClientDisconnect
from .errors import ApiError

MIMES={'JPEG':'image/jpeg','PNG':'image/png','WEBP':'image/webp'}
# Preserve the strict Pillow decoder before an optional detector library replaces
# Image.open globally with a lazy HEIF-plugin fallback. Invalid uploads must keep
# returning INVALID_IMAGE, without importing unsupported codecs at request time.
_pillow_open=Image.open


@dataclass(frozen=True)
class CanonicalImage:
    data:bytes
    width:int
    height:int


async def read_upload(request,settings):
    if request.headers.get('content-type','').split(';',1)[0].strip().lower()!='multipart/form-data':
        raise ApiError(415,'UNSUPPORTED_IMAGE','A multipart image upload is required.')
    limit=settings.image_max_bytes+65536
    chunks=[]; size=0
    try:
        async for chunk in request.stream():
            size+=len(chunk)
            if size>limit: raise ApiError(413,'IMAGE_TOO_LARGE','Image upload exceeds its byte limit.')
            chunks.append(chunk)
    except ClientDisconnect: raise ApiError(422,'INVALID_MULTIPART','Incomplete multipart upload.') from None
    data=b''.join(chunks)
    async def receive(): return {'type':'http.request','body':data,'more_body':False}
    bounded=Request(request.scope,receive=receive)
    try:
        async with bounded.form(max_files=1,max_fields=1,max_part_size=1024) as form:
            if any(k not in {'file','input_source'} or len(form.getlist(k))!=1 for k in form):
                raise ApiError(422,'INVALID_MULTIPART','Unknown or repeated multipart field.')
            file=form.get('file'); source=form.get('input_source','gallery')
            if not isinstance(file,UploadFile) or source not in ('camera','gallery','share'):
                raise ApiError(422,'INVALID_MULTIPART','An image file and valid input_source are required.')
            raw=await file.read(settings.image_max_bytes+1)
            if len(raw)>settings.image_max_bytes: raise ApiError(413,'IMAGE_TOO_LARGE','Image exceeds its byte limit.')
            return raw,file.content_type,source
    except (HTTPException,ValueError): raise ApiError(422,'INVALID_MULTIPART','Malformed multipart upload.') from None


def canonical_image(raw,mime,settings):
    if len(raw)>settings.image_max_bytes: raise ApiError(413,'IMAGE_TOO_LARGE','Image exceeds its byte limit.')
    mime=mime.split(';',1)[0].strip().lower() if isinstance(mime,str) else None
    if mime not in MIMES.values(): raise ApiError(415,'UNSUPPORTED_IMAGE','Only JPEG, PNG and WebP are supported.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with _pillow_open(io.BytesIO(raw)) as image:
                if image.format not in MIMES or MIMES[image.format]!=mime:
                    raise ApiError(415,'UNSUPPORTED_IMAGE','Image content does not match its declared supported type.')
                w,h=image.size
                if w*h>settings.image_max_pixels or max(w,h)>settings.image_max_dimension:
                    raise ApiError(413,'IMAGE_TOO_LARGE','Image exceeds pixel or dimension limits.')
                if getattr(image,'n_frames',1)!=1: raise ApiError(415,'UNSUPPORTED_IMAGE','Animated images are unsupported.')
                image.verify()
            with _pillow_open(io.BytesIO(raw)) as image:
                image.load()
                oriented=ImageOps.exif_transpose(image)
                rgba=oriented.convert('RGBA')
                rgb=Image.new('RGB',rgba.size,'white'); rgb.paste(rgba,mask=rgba.getchannel('A'))
                output=io.BytesIO(); rgb.save(output,format='JPEG',quality=90,exif=b'',icc_profile=None)
                encoded=output.getvalue()
                if len(encoded)>settings.image_max_bytes: raise ApiError(413,'IMAGE_TOO_LARGE','Canonical image exceeds its byte limit.')
                return CanonicalImage(encoded,rgb.width,rgb.height)
    except (Image.DecompressionBombWarning,Image.DecompressionBombError):
        raise ApiError(413,'IMAGE_TOO_LARGE','Image exceeds decoder safety limits.') from None
    except (UnidentifiedImageError,OSError,SyntaxError,ValueError):
        raise ApiError(422,'INVALID_IMAGE','Image content is corrupt or cannot be decoded.') from None
