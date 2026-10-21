"""FOOD-01: preflight and apply the food-description migration to the existing local stack.

Default runs the migration plus supabase/tests/005 in one rolled-back transaction.
--apply then commits the exact preflighted migration once, journals it like the
Supabase CLI, and proves catalog/nutrition/scan/meal fingerprints are unchanged.
No reset, reimport, remote project or content seed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from import_dataset import literal, local_db

VERSION = '20261019000100'
NAME = 'foodlens_food_descriptions'
MIGRATION = ROOT / 'supabase/migrations/20261019000100_foodlens_food_descriptions.sql'
TESTS = ROOT / 'supabase/tests/005_food_descriptions.sql'
PROCESSED = ROOT / 'data/processed'
PREFLIGHT = PROCESSED / 'FOOD-01-database-preflight.json'
APPLIED = PROCESSED / 'FOOD-01-database-migration.json'
# Tables whose rows must not change during FOOD-01 content work. Nutrition and meal tables
# were removed by FOOD-02 (20261020000100), so they are no longer part of the fingerprint.
PRESERVED = [
    ('foods', 'public.foods', 'id'),
    ('profiles', 'public.profiles', 'id'), ('scans', 'public.scans', 'id'),
]


def execute(sql):
    result = local_db(sql)
    if result.returncode:
        raise RuntimeError('Local SQL operation failed; inspect local database diagnostics')
    return result.stdout.strip()


def body(path, opening, closing):
    text = path.read_text(encoding='utf-8')
    if text.count(opening) != 1 or text.count(closing) != 1:
        raise ValueError('Expected exactly one transaction in ' + path.name)
    return text.replace(opening, '', 1).replace(closing, '', 1)


def snapshot():
    entries = {}
    for name, table, order in PRESERVED:
        sql = (f"select jsonb_build_object('rows',count(*),'fingerprint',md5(coalesce(string_agg(md5(to_jsonb(t)::text),'' "
               f"order by {order}),''))) from {table} t;")
        entries[name] = json.loads(execute(sql))
    return entries


def digests():
    return {'migration_sha256': hashlib.sha256(MIGRATION.read_bytes()).hexdigest(),
            'tests_sha256': hashlib.sha256(TESTS.read_bytes()).hexdigest()}


def applied_checksum():
    return execute("select coalesce((select encode(sha256(convert_to(statements[1],'UTF8')),'hex') from "
                   "supabase_migrations.schema_migrations where version='" + VERSION + "'),'');")


def preflight():
    if applied_checksum():
        raise ValueError('Migration already applied; run supabase/tests/005 directly instead')
    sql = 'begin;\n' + body(MIGRATION, 'begin;', 'commit;') + '\n' + body(TESTS, 'begin;', 'rollback;') + '\nrollback;\n'
    output = execute(sql)
    lines = [line for line in output.splitlines() if re.match(r'^(not )?ok \d+', line)]
    failed = [line for line in lines if line.startswith('not ok')]
    if not lines or failed or 'Looks like' in output:
        raise RuntimeError('Transactional preflight failed: ' + '; '.join(failed[:5]))
    report = dict(task='FOOD-01', status='passed', checks=len(lines), rolled_back=True, **digests())
    PREFLIGHT.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'FOOD-01 preflight: {len(lines)} pgTAP checks passed inside a rolled-back transaction.')


def apply():
    report = json.loads(PREFLIGHT.read_text(encoding='utf-8'))
    current = digests()
    if report.get('status') != 'passed' or any(report.get(k) != v for k, v in current.items()):
        raise ValueError('Matching passing transactional preflight required')
    sql = MIGRATION.read_text(encoding='utf-8')
    existing = applied_checksum()
    if existing:
        if existing != current['migration_sha256']:
            raise ValueError('Applied migration checksum differs; do not overwrite/reset')
        print('Exact FOOD-01 migration already applied; no mutation.')
        return
    before = snapshot()
    if before['foods']['rows'] != 75:
        raise ValueError('Unexpected catalog baseline; do not reimport/reset')
    journal = ('insert into supabase_migrations.schema_migrations(version,name,statements) values(' + literal(VERSION)
               + ',' + literal(NAME) + ',array[' + literal(sql) + ']);\ncommit;')
    execute(sql.replace('commit;', journal))
    after = snapshot()
    if before != after:
        raise RuntimeError('Migration applied, but preserved-data fingerprints differ; review without reset')
    counts = json.loads(execute("select jsonb_build_object('sources',(select count(*) from public.content_sources),"
                                "'descriptions',(select count(*) from public.food_descriptions));"))
    APPLIED.write_text(json.dumps(dict(task='FOOD-01', status='passed', migration_version=VERSION, **current,
        preserved=before, all_preserved_fingerprints_match=True, content_rows_after=counts,
        reset_used=False, remote_project_used=False), indent=2) + '\n', encoding='utf-8')
    print('FOOD-01 migration applied atomically; catalog/profile/scan fingerprints unchanged.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    apply() if args.apply else preflight()
