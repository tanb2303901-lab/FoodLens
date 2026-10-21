"""Create the ignored dev backend config (core + scan writer + bundled model on CPU). No keys printed.

Run after `supabase status -o json` was saved to data/processed/supabase-local.json and
prepare_backend_local.py / prepare_scan_local.py created data/processed/backend-local.json.
--public-supabase-url sets the Supabase origin that a phone on the same Wi-Fi can reach, so
image links in scan history open on the device (e.g. http://192.168.1.20:54321).
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'ml/models/foodlens-yolo11n-20261016-extension4h-v2'
TARGET = ROOT / 'data/processed/backend-dev.json'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--public-supabase-url', help='Origin devices use for Supabase, e.g. http://192.168.1.20:54321')
    args = parser.parse_args(argv)
    base = json.loads((ROOT / 'data/processed/backend-local.json').read_text(encoding='utf-8-sig'))
    if not base.get('scan_service_key'):
        raise SystemExit('Run scripts/prepare_scan_local.py first')
    # Refresh from the current `supabase status` so a recreated local stack never leaves stale keys;
    # cursor_secret and other settings are kept.
    local = json.loads((ROOT / 'data/processed/supabase-local.json').read_text(encoding='utf-8-sig'))
    if local['API_URL'] != base['supabase_url']:
        raise SystemExit('Local Supabase URL changed; expected ' + base['supabase_url'])
    base = {**base, 'public_key': local['ANON_KEY'], 'scan_service_key': local['SERVICE_ROLE_KEY'],
            'jwt_issuer': local['API_URL'] + '/auth/v1'}
    if not (BUNDLE / 'manifest.json').is_file() or not (BUNDLE / 'weights.pt').is_file():
        raise SystemExit('Model bundle missing: ' + str(BUNDLE.relative_to(ROOT)))
    config = {**base, 'model_bundle_path': str(BUNDLE.resolve()), 'model_device': 'cpu'}
    if args.public_supabase_url:
        config['public_supabase_url'] = args.public_supabase_url.rstrip('/')
    else:
        config.pop('public_supabase_url', None)
    from backend.app.config import Settings  # validates the result before writing
    Settings(**config)
    TARGET.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    print('Dev backend config written to data/processed/backend-dev.json (model on CPU). No keys printed.')


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(ROOT))
    main()
