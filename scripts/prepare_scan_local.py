"""Add only the local scan service credential to ignored config; never print it."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    path=ROOT/'data/processed/backend-local.json'
    backend=json.loads(path.read_text(encoding='utf-8-sig'))
    if backend.get('scan_service_key'):
        print('Private local scan key already configured; preserved.')
        return
    local=json.loads((ROOT/'data/processed/supabase-local.json').read_text(encoding='utf-8-sig'))
    if backend['supabase_url']!='http://127.0.0.1:54321' or local['API_URL']!=backend['supabase_url']:
        raise ValueError('This helper only supports the fixed dedicated local stack')
    backend['scan_service_key']=local['SERVICE_ROLE_KEY']
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(backend,indent=2)+'\n',encoding='utf-8'); temp.replace(path)
    print('Private local scan key configured; no credential output. Runtime predictor remains unavailable.')


if __name__=='__main__': main()
