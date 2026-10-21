"""Explicit settings, with secrets excluded from repr and startup messages."""
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    public_key: str = field(repr=False)
    jwt_issuer: str
    jwt_audience: str
    jwt_algorithm: str
    cursor_secret: str = field(repr=False)
    jwt_secret: str | None = field(default=None,repr=False)
    http_timeout: float = 5.0
    jwks_ttl: float = 600.0
    scan_service_key: str | None = field(default=None,repr=False)
    image_max_bytes: int = 10485760
    image_max_pixels: int = 20000000
    image_max_dimension: int = 8192
    image_url_ttl: int = 300
    prediction_timeout: float = 30.0
    model_bundle_path: str | None = None
    model_device: str = 'cpu'
    # Optional origin that phones use to reach Supabase (e.g. http://192.168.1.20:54321).
    # Only signed image URLs returned to clients are rewritten; the server keeps supabase_url.
    public_supabase_url: str | None = None

    def __post_init__(self):
        u=urlsplit(self.supabase_url)
        if (u.scheme not in ('http','https') or not u.hostname or u.username or u.password
            or u.query or u.fragment or u.path not in ('','/')
            or (u.scheme=='http' and u.hostname not in ('127.0.0.1','localhost','::1'))):
            raise ValueError('Invalid Supabase URL: HTTPS or local loopback origin required')
        if not self.public_key or self.public_key.startswith('sb_secret_'):
            raise ValueError('A public Supabase key is required')
        if not self.public_key.startswith('sb_publishable_'):
            import jwt
            try:
                key_claims=jwt.decode(self.public_key,options={'verify_signature':False})
                if key_claims.get('role')!='anon': raise ValueError('Invalid public key role')
            except (jwt.PyJWTError,ValueError):
                raise ValueError('Legacy public key must have the anon role') from None
        if self.jwt_algorithm not in ('HS256','ES256','RS256'):
            raise ValueError('Unsupported configured signing algorithm')
        if self.jwt_algorithm=='HS256' and (not self.jwt_secret or len(self.jwt_secret)<32):
            raise ValueError('HS256 requires an explicit signing secret of at least 32 characters')
        if self.jwt_issuer != self.supabase_url.rstrip('/')+'/auth/v1' or self.jwt_audience!='authenticated':
            raise ValueError('Issuer/audience must match the configured Supabase Auth instance')
        if len(self.cursor_secret)<32 or not 0 < self.http_timeout <= 30 or not 1 <= self.jwks_ttl <= 3600:
            raise ValueError('Invalid cursor secret length, HTTP timeout or JWKS cache TTL')
        if self.scan_service_key is not None:
            import jwt
            try:
                if jwt.decode(self.scan_service_key,options={'verify_signature':False}).get('role')!='service_role':
                    raise ValueError()
            except (jwt.PyJWTError,ValueError): raise ValueError('Scan writer requires a private legacy service-role key') from None
        for value,maximum in [(self.image_max_bytes,10485760),(self.image_max_pixels,40000000),(self.image_max_dimension,16384)]:
            if type(value) is not int or not 1<=value<=maximum: raise ValueError('Invalid image size limits')
        if type(self.image_url_ttl) is not int or not 15<=self.image_url_ttl<=900 or not .1<=self.prediction_timeout<=120:
            raise ValueError('Invalid image URL TTL or prediction timeout')
        if self.public_supabase_url is not None:
            p=urlsplit(self.public_supabase_url) if isinstance(self.public_supabase_url,str) else None
            if (p is None or p.scheme not in ('http','https') or not p.hostname or p.username or p.password
                or p.query or p.fragment or p.path not in ('','/')):
                raise ValueError('public_supabase_url must be a plain http(s) origin')
        if self.model_device not in ('cpu','cuda:0') or (self.model_bundle_path is not None and
            (not isinstance(self.model_bundle_path,str) or not Path(self.model_bundle_path).is_absolute())):
            raise ValueError('Model bundle must be an explicit local absolute path with a supported device')

    @classmethod
    def load(cls,path=None):
        path=path or os.environ.get('FOODLENS_CONFIG_PATH')
        if not path: raise ValueError('Set FOODLENS_CONFIG_PATH to a private backend configuration file')
        try: return cls(**json.loads(Path(path).read_text(encoding='utf-8-sig')))
        except (OSError,TypeError,json.JSONDecodeError):
            raise ValueError('Cannot load valid backend configuration') from None
