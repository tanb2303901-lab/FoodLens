"""Validate and import the pinned FoodLens catalog (67 VietFood foods) into the local Docker DB.

Dry-run is the default. No URL, password, service key or cloud destination accepted.
FOOD-02: nutrition references and candidate links are no longer imported; the nutrition CSVs
in the source package are left untouched and unread.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import uuid

import validate_dataset as vd

PROJECT = Path(__file__).resolve().parents[1]
PROCESSED = PROJECT / 'data/processed'
VERSION = 'foodlens-source-2026-10-12-v1'
CLASS_VERSION = 'vietfood-67-2026-10-12-v1'
CONTAINER = 'supabase_db_foodlens-local'
FOOD_COLS = ['id','slug','name_vi','name_en','scope_kind','original_class_id',
             'training_class_id','class_map_version','source_mapping_metadata']
METADATA_KEYS = ('slug','scope_kind','food_name_vi','original_class_id','training_class_id')


def build_payload(classes, identity):
    if identity.get('source_data_version') != VERSION or identity.get('class_map_version') != CLASS_VERSION:
        raise ValueError('Unsupported identity/source version')
    expected = identity['foods']
    by_slug = {f['slug']: f for f in expected}
    if len(expected) != 67 or len(by_slug) != 67:
        raise ValueError('Identity artifact must contain 67 unique foods')
    if len(classes) != 67 or len({r['slug'] for r in classes}) != 67:
        raise ValueError('Expected 67 unique class rows')
    foods = []
    for r in classes:
        f = by_slug.get(r['slug'])
        if f is None or f['id'] != str(uuid.uuid5(uuid.NAMESPACE_URL, 'urn:foodlens:food:'+r['slug'])):
            raise ValueError('Food UUID does not match the portable identity contract')
        for key, source in [('training_class_id','training_class_id'),('original_class_id','original_class_id'),
                            ('scope_kind','scope_kind'),('name_vi','food_name_vi'),('name_en','food_name_en')]:
            value = vd.parse_integer(r[source]) if key.endswith('_class_id') else r[source]
            if value != f[key]: raise ValueError('Class row differs from identity artifact')
        # Identity provenance only; the class CSV carries no nutrition fields.
        foods.append({**f, 'class_map_version':CLASS_VERSION,'source_mapping_metadata':{k: r[k] for k in METADATA_KEYS}})
    if len({f['id'] for f in foods}) != 67: raise ValueError('Duplicate food identity')
    return dict(foods=foods)


def identity_classes(identity):
    """Class rows equivalent to foodlens_classes.csv, derived from the committed identity map."""
    return [dict(slug=f['slug'], training_class_id=str(f['training_class_id']), original_class_id=str(f['original_class_id']),
                 food_name_vi=f['name_vi'], food_name_en=f['name_en'], scope_kind=f['scope_kind']) for f in identity['foods']]


def snapshot(root, baseline, identity):
    # Hold the class CSV in memory and verify the exact bytes used to parse.
    raw = (root/vd.CLASSES).read_bytes()
    expected = next(e for e in baseline['files'] if e['name']==vd.CLASSES)
    if hashlib.sha256(raw).hexdigest()!=expected['sha256']:
        raise ValueError('Source changed after validation: '+vd.CLASSES)
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'),newline=''),strict=True))
    if len(rows)!=expected['data_rows'] or any(None in r or None in r.values() for r in rows):
        raise ValueError('Invalid source row shape')
    if identity['source_class_sha256'] != expected['sha256']:
        raise ValueError('Identity class checksum differs from baseline')
    return build_payload(rows, identity)


def literal(value):
    return "'"+value.replace("'","''")+"'"


def import_sql(payload, checksums, *, commit=True):
    # No identifiers or operators originate in CSV input. Data is a quoted JSON literal.
    encoded=json.dumps(payload['foods'],ensure_ascii=False,allow_nan=False,separators=(',',':'))
    digest=literal(json.dumps(checksums,sort_keys=True,separators=(',',':')))+'::jsonb'
    old=','.join('e.'+c for c in FOOD_COLS); new=','.join('s.'+c for c in FOOD_COLS); columns=','.join(FOOD_COLS)
    return f"""begin; set local standard_conforming_strings=on; set local lock_timeout='15s';
select pg_advisory_xact_lock(hashtextextended('foodlens:import:{VERSION}',0));
create temp table stage_foods on commit drop as select * from jsonb_populate_recordset(null::public.foods,{literal(encoded)}::jsonb);
do $$ begin
  if exists(select 1 from foodlens_private.import_runs where dataset_version='{VERSION}' and status='completed'
    and (file_checksums is distinct from {digest} or class_map_version<>'{CLASS_VERSION}'))
  then raise exception 'IMPORT_VERSION_CHECKSUM_CONFLICT'; end if;
end $$;
do $$ begin
  if exists(select 1 from public.foods e join stage_foods s on e.id=s.id where ({old}) is distinct from ({new}))
  then raise exception 'IMPORT_EXISTING_SOURCE_CONFLICT:foods'; end if;
end $$;
insert into public.foods({columns}) select {columns} from stage_foods on conflict do nothing;
-- ON CONFLICT could hide a secondary identity collision: ensure every source row is present exactly.
do $$ begin
  if (select count(*) from public.foods e join stage_foods s on e.id=s.id where ({old}) is not distinct from ({new}))
     <> (select count(*) from stage_foods) then raise exception 'IMPORT_INCOMPLETE:foods'; end if;
end $$;
insert into foodlens_private.import_runs(dataset_version,file_checksums,class_map_version,status,observed_counts,operator,finished_at)
  select '{VERSION}',{digest},'{CLASS_VERSION}','completed',jsonb_build_object('foods',67),'local catalog importer',now()
  where not exists(select 1 from foodlens_private.import_runs where dataset_version='{VERSION}' and status='completed');
select jsonb_build_object('foods',(select count(*) from public.foods where class_map_version='{CLASS_VERSION}'),
  'completed_runs',(select count(*) from foodlens_private.import_runs where dataset_version='{VERSION}' and status='completed'));
{'commit' if commit else 'rollback'};"""


def local_db(sql):
    import tomllib
    cfg=tomllib.loads((PROJECT/'supabase/config.toml').read_text(encoding='utf-8'))
    if cfg.get('project_id')!='foodlens-local': raise ValueError('Refusing a different Supabase project')
    return subprocess.run(['docker','exec','-i',CONTAINER,'psql','-X','-qAt','-v','ON_ERROR_STOP=1',
                           '-U','postgres','-d','postgres'],input=sql,encoding='utf-8',capture_output=True,timeout=180)


def output_path(path):
    resolved=path.resolve()
    if not resolved.is_relative_to(PROCESSED.resolve()) or resolved.suffix!='.json':
        raise ValueError('Reports must be JSON inside ignored data/processed')
    return resolved


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--config',type=Path,help='Machine config with csv_root of the received CSV package')
    source.add_argument('--from-identities',action='store_true',
                        help='Teammate/dev setup: build the 67 foods from the portable identity map in the repo, no CSV package')
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--apply',action='store_true',help='Commit to foodlens-local (default: dry-run)')
    parser.add_argument('--check-database',action='store_true',help='Run the import inside a rolled-back transaction')
    args=parser.parse_args(argv)
    try:
        report_path=output_path(args.report)
        baseline_path=PROJECT/'docs/dataset/source-baseline.json'
        identity=vd.load_json((PROJECT/'docs/dataset/food-identities-v1.json').read_text(encoding='utf-8'))
        if args.from_identities:
            baseline=vd.load_json(baseline_path.read_text(encoding='utf-8'))
            payload=build_payload(identity_classes(identity),identity)
        else:
            config=vd.load_json(args.config.read_text(encoding='utf-8-sig'))
            root=Path(config['csv_root'])
            if not root.is_absolute(): root=args.config.resolve().parent/root
            root=root.resolve()
            validation_path=output_path(report_path.with_name(report_path.stem+'-validation.json'))
            vd.protect_paths(args.config,baseline_path,report_path,root)
            vd.protect_paths(args.config,baseline_path,validation_path,root)
            if vd.aliases(report_path,validation_path): raise ValueError('Report paths must differ')
            code=vd.main(['--config',str(args.config),'--baseline',str(baseline_path),'--report',str(validation_path)])
            if code: raise ValueError('Source validation failed; see validation report')
            baseline=vd.load_json(baseline_path.read_text(encoding='utf-8'))
            payload=snapshot(root,baseline,identity)
        if baseline['baseline_version']!=VERSION: raise ValueError('Unsupported baseline version')
        # The recorded import-run checksums cover the whole received package.
        checksums={e['name']:e['sha256'] for e in baseline['files']}
        mode='apply' if args.apply else ('database-check' if args.check_database else 'dry-run')
        report=dict(task='DATA-02',mode=mode,source='identity_map' if args.from_identities else 'csv_package',status='validated',generated_at=datetime.now(timezone.utc).isoformat(),
                    source_data_version=VERSION,class_map_version=CLASS_VERSION,file_checksums=checksums,
                    planned_counts=dict(foods=67),not_checked=['Vision/model','FastAPI/mobile'])
        if args.apply or args.check_database:
            result=local_db(import_sql(payload,checksums,commit=args.apply))
            if result.returncode:
                report.update(status='failed',transaction='rolled_back',error='Local database import failed (no success provenance committed)')
                vd.write_report(report_path,report)
                print('IMPORT_FAILED: transaction rolled back; no keys or SQL payload printed',file=sys.stderr)
                return 1
            report.update(status='completed' if args.apply else 'checked',transaction='committed' if args.apply else 'rolled_back',
                          observed_counts=vd.load_json(result.stdout.strip().splitlines()[-1]))
        else:
            report['database_accessed']=False
        vd.write_report(report_path,report)
        print('Catalog import '+report['status']+': 67 foods; '+str(report_path))
        return 0
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:
        # Input/daemon errors have no credential-bearing arguments or SQL content.
        print('IMPORT_ERROR: '+str(exc),file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
