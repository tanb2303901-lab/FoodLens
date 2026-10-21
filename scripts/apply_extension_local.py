"""Apply reviewed ML-05 catalog migration only to the existing local stack.

No reset/reimport, no model activation. Preserve baseline/history fingerprints.
"""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from import_dataset import local_db, literal

VERSION='20261016000100'
MIGRATION=ROOT/'supabase/migrations/20261016000100_foodlens_extension75.sql'
TESTS=ROOT/'supabase/tests/004_extension75.sql'
PROCESSED=ROOT/'data/processed'


def execute(sql):
    result=local_db(sql)
    if result.returncode:raise RuntimeError('Local SQL operation failed; inspect local database diagnostics')
    return result.stdout.strip()


def snapshot():
    entries={}
    for name,table,where,order in [
        ('legacy_foods','public.foods',"where class_map_version='vietfood-67-2026-10-12-v1'",'id'),
        ('references','public.nutrition_references','','record_id,source_data_version'),
        ('candidates','public.food_nutrition_links','','food_id,record_id,source_data_version'),
        ('nutrition','public.food_nutrition','','id'),('portions','public.food_portions','','id'),
        ('scans','public.scans','','id'),('meals','public.meals','','id'),('items','public.meal_items','','id')]:
        sql=f"select jsonb_build_object('rows',count(*),'fingerprint',md5(coalesce(string_agg(md5(to_jsonb(t)::text),'' order by {order}),''))) from {table} t {where};"
        entries[name]=json.loads(execute(sql))
    return entries


def main():
    preflight=json.loads((PROCESSED/'ML-05-database-preflight.json').read_text())
    raw=MIGRATION.read_bytes();sha=hashlib.sha256(raw).hexdigest()
    if preflight.get('status')!='passed' or preflight.get('migration_sha256')!=sha or preflight.get('tests_sha256')!=hashlib.sha256(TESTS.read_bytes()).hexdigest():
        raise ValueError('Matching passing transactional SQL preflight required')
    existing=execute("select coalesce((select encode(sha256(convert_to(statements[1],'UTF8')),'hex') from supabase_migrations.schema_migrations where version='"+VERSION+"'),'');")
    if existing:
        if existing!=sha:raise ValueError('Applied migration checksum differs; do not overwrite/reset')
        print('Exact extension migration already applied; no mutation.');return
    before=snapshot()
    if before['legacy_foods']['rows']!=67 or before['references']['rows']!=9115 or before['candidates']['rows']!=109:
        raise ValueError('Unexpected import baseline; do not reimport/reset')
    if execute("select count(*) from public.foods where class_map_version='foodlens-75-2026-10-16-v2';")!='0':
        raise ValueError('Untracked extension rows require reconciliation before mutation')
    sql=raw.decode('utf-8')
    if sql.count('commit;')!=1:raise ValueError('Expected one atomic migration transaction')
    journal="insert into supabase_migrations.schema_migrations(version,name,statements) values("+literal(VERSION)+",'foodlens_extension75',array["+literal(sql)+"]);\ncommit;"
    execute(sql.replace('commit;',journal))
    after=snapshot()
    if before!=after:raise RuntimeError('Migration applied, but preserved-data fingerprints differ; review without reset')
    count=int(execute('select count(*) from public.foods;'))
    if count!=75:raise RuntimeError('Unexpected final catalog count')
    report=dict(task='ML-05',status='passed',migration_version=VERSION,migration_sha256=sha,
        catalog_count=count,preserved_baseline_and_history=before,all_preserved_fingerprints_match=True,
        model_activated=False,source_mutated=False,remote_project_used=False,reset_used=False)
    (PROCESSED/'ML-05-database-migration.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Local migration applied atomically:75 foods; all legacy/reference/nutrition/meal/scan fingerprints unchanged.')


if __name__=='__main__':main()
