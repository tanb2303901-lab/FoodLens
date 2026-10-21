"""FOOD-02: preflight and apply the nutrition/meal removal migration on the dedicated local stack.

Default: migration + supabase/tests/001 inside one rolled-back transaction.
--apply: requires the matching preflight and the table backup, commits once with a
Supabase migration journal row, and proves catalog/profile/scan/description rows unchanged.
--metadata [--apply]: same flow for 20261020000200, which strips nutrition-mapping keys
from foods.source_mapping_metadata after backing the original metadata up; food identity
columns and the namespace/class-ID provenance must stay identical.
No reset; earlier migrations stay as history.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from apply_food_content_schema import body, execute
from import_dataset import literal

VERSION = '20261020000100'
NAME = 'foodlens_remove_nutrition_meals'
MIGRATION = ROOT / 'supabase/migrations/20261020000100_foodlens_remove_nutrition_meals.sql'
TESTS = ROOT / 'supabase/tests/001_foodlens.sql'
PROCESSED = ROOT / 'data/processed'
BACKUP = PROCESSED / 'FOOD-02-backup/nutrition-meals-tables.sql'
PREFLIGHT = PROCESSED / 'FOOD-02-database-preflight.json'
APPLIED = PROCESSED / 'FOOD-02-database-migration.json'
DROPPED = ('public.nutrition_references', 'public.food_nutrition_links', 'public.food_nutrition', 'public.food_portions',
           'public.meals', 'public.meal_items', 'foodlens_private.mutation_receipts')
KEPT = [('foods', 'public.foods', 'id'), ('profiles', 'public.profiles', 'id'), ('scans', 'public.scans', 'id'),
        ('descriptions', 'public.food_descriptions', 'id'), ('sources', 'public.content_sources', 'id'),
        ('links', 'public.food_description_sources', 'description_id,source_id')]


def snapshot():
    return {name: json.loads(execute(f"select jsonb_build_object('rows',count(*),'fingerprint',md5(coalesce(string_agg("
                                      f"md5(to_jsonb(t)::text),'' order by {order}),''))) from {table} t;"))
            for name, table, order in KEPT}


def digests():
    return {'migration_sha256': hashlib.sha256(MIGRATION.read_bytes()).hexdigest(),
            'tests_sha256': hashlib.sha256(TESTS.read_bytes()).hexdigest()}


def applied_checksum():
    return execute("select coalesce((select encode(sha256(convert_to(statements[1],'UTF8')),'hex') from "
                   "supabase_migrations.schema_migrations where version='" + VERSION + "'),'');")


def backup_rows():
    rows, table = {}, None
    for line in BACKUP.read_text(encoding='utf-8').splitlines():
        if line.startswith('COPY '):
            table = line.split()[1]
            rows[table] = 0
        elif line == '\\.':
            table = None
        elif table:
            rows[table] += 1
    return rows


def preflight():
    if applied_checksum():
        raise ValueError('Migration already applied; run supabase/tests/001 directly instead')
    sql = 'begin;\n' + body(MIGRATION, 'begin;', 'commit;') + '\n' + body(TESTS, 'begin;', 'rollback;') + '\nrollback;\n'
    output = execute(sql)
    lines = [line for line in output.splitlines() if re.match(r'^(not )?ok \d+', line)]
    failed = [line for line in lines if line.startswith('not ok')]
    if not lines or failed or 'Looks like' in output:
        raise RuntimeError('Transactional preflight failed: ' + '; '.join(failed[:5]))
    PREFLIGHT.write_text(json.dumps(dict(task='FOOD-02', status='passed', checks=len(lines), rolled_back=True, **digests()),
                                    indent=2) + '\n', encoding='utf-8')
    print(f'FOOD-02 preflight: {len(lines)} pgTAP checks passed inside a rolled-back transaction.')


def apply():
    report, current = json.loads(PREFLIGHT.read_text(encoding='utf-8')), digests()
    if report.get('status') != 'passed' or any(report.get(k) != v for k, v in current.items()):
        raise ValueError('Matching passing transactional preflight required')
    existing = applied_checksum()
    if existing:
        if existing != current['migration_sha256']:
            raise ValueError('Applied migration checksum differs; do not overwrite/reset')
        print('Exact FOOD-02 migration already applied; no mutation.')
        return
    live = {t: int(execute(f'select count(*) from {t};')) for t in DROPPED}
    if backup_rows() != live:
        raise ValueError('Backup row counts do not match the live tables; refresh the backup first')
    before = snapshot()
    sql = MIGRATION.read_text(encoding='utf-8')
    execute(sql.replace('commit;', 'insert into supabase_migrations.schema_migrations(version,name,statements) values('
                        + literal(VERSION) + ',' + literal(NAME) + ',array[' + literal(sql) + ']);\ncommit;'))
    after = snapshot()
    if before != after:
        raise RuntimeError('Migration applied, but kept-table fingerprints differ; review without reset')
    APPLIED.write_text(json.dumps(dict(task='FOOD-02', status='passed', migration_version=VERSION, **current,
        backup=str(BACKUP.relative_to(ROOT)), backup_sha256=hashlib.sha256(BACKUP.read_bytes()).hexdigest(),
        dropped_row_counts=live, kept=before, kept_fingerprints_match=True, reset_used=False), indent=2) + '\n', encoding='utf-8')
    print('FOOD-02 migration applied; backup verified; catalog/profile/scan/description fingerprints unchanged.')


META_VERSION = '20261020000200'
META_NAME = 'foodlens_strip_nutrition_metadata'
META_MIGRATION = ROOT / 'supabase/migrations/20261020000200_foodlens_strip_nutrition_metadata.sql'
META_BACKUP = PROCESSED / 'FOOD-02-backup/foods-metadata-before.json'
META_REPORT = PROCESSED / 'FOOD-02-metadata-migration.json'
IDENTITY = ("select md5(string_agg(md5(jsonb_build_array(id,slug,name_vi,name_en,scope_kind,original_class_id,training_class_id,"
            "class_map_version,active,source_mapping_metadata->'source_namespace',source_mapping_metadata->'source_class_id')::text),'' "
            "order by id)) from public.foods;")


def metadata(apply_changes):
    sha = hashlib.sha256(META_MIGRATION.read_bytes()).hexdigest()
    done = execute("select coalesce((select encode(sha256(convert_to(statements[1],'UTF8')),'hex') from "
                   "supabase_migrations.schema_migrations where version='" + META_VERSION + "'),'');")
    if done:
        if done != sha:
            raise ValueError('Applied metadata migration checksum differs; do not overwrite/reset')
        print('Exact FOOD-02 metadata migration already applied; no mutation.')
        return
    sql = META_MIGRATION.read_text(encoding='utf-8')
    if not apply_changes:
        execute('begin;\n' + body(META_MIGRATION, 'begin;', 'commit;') + '\nrollback;\n')
        print('FOOD-02 metadata preflight: migration and its own remaining-key check passed inside a rolled-back transaction.')
        return
    rows = json.loads(execute("select jsonb_agg(jsonb_build_object('id',id,'slug',slug,'source_mapping_metadata',source_mapping_metadata) "
                              "order by training_class_id) from public.foods;"))
    META_BACKUP.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    identity, others = execute(IDENTITY), {k: v for k, v in snapshot().items() if k != 'foods'}
    execute(sql.replace('commit;', 'insert into supabase_migrations.schema_migrations(version,name,statements) values('
                        + literal(META_VERSION) + ',' + literal(META_NAME) + ',array[' + literal(sql) + ']);\ncommit;'))
    if execute(IDENTITY) != identity or {k: v for k, v in snapshot().items() if k != 'foods'} != others:
        raise RuntimeError('Food identity or other kept tables changed; review without reset')
    META_REPORT.write_text(json.dumps(dict(task='FOOD-02', status='passed', migration_version=META_VERSION, migration_sha256=sha,
        backup=str(META_BACKUP.relative_to(ROOT)), backup_sha256=hashlib.sha256(META_BACKUP.read_bytes()).hexdigest(),
        foods_backed_up=len(rows), food_identity_unchanged=True, other_kept_tables_unchanged=True, reset_used=False),
        indent=2) + '\n', encoding='utf-8')
    print(f'FOOD-02 metadata migration applied; {len(rows)} food metadata rows backed up; identity unchanged.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--metadata', action='store_true')
    args = parser.parse_args()
    if args.metadata:
        metadata(args.apply)
    else:
        apply() if args.apply else preflight()
