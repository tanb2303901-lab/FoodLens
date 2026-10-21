"""Create ignored backend config from existing local status, without printing keys."""
from pathlib import Path
import json
import secrets

ROOT=Path(__file__).resolve().parents[1]


def main():
    target=ROOT/'data/processed/backend-local.json'
    if target.exists():
        print('Backend local config already exists; preserved.')
        return
    source=json.loads((ROOT/'data/processed/supabase-local.json').read_text(encoding='utf-8-sig'))
    if source['API_URL']!='http://127.0.0.1:54321': raise ValueError('Refusing non-local source')
    config=dict(supabase_url=source['API_URL'],public_key=source['ANON_KEY'],jwt_issuer=source['API_URL']+'/auth/v1',
                jwt_audience='authenticated',jwt_algorithm='ES256',cursor_secret=secrets.token_urlsafe(48))
    target.write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
    print('Ignored backend local config created. No keys printed.')


if __name__=='__main__': main()
