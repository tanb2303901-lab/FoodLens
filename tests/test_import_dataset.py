"""Catalog import transformation and destination safety tests (FOOD-02: foods only)."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import import_dataset as imp


class ImportTests(unittest.TestCase):
    def fixture(self):
        identity=json.loads((imp.PROJECT/'docs/dataset/food-identities-v1.json').read_text(encoding='utf-8'))
        classes=[dict(slug=f['slug'],training_class_id=str(f['training_class_id']),original_class_id=str(f['original_class_id']),
                      food_name_vi=f['name_vi'],food_name_en=f['name_en'],scope_kind=f['scope_kind']) for f in identity['foods']]
        return classes,identity

    def test_report_outside_processed_denied(self):
        with self.assertRaises(ValueError): imp.output_path(imp.PROJECT/'README.json')
        with self.assertRaises(ValueError): imp.output_path(imp.PROCESSED/'report.csv')

    def test_local_destination_guard(self):
        with patch.object(Path,'read_text',return_value='project_id="cloud-project"'):
            with self.assertRaises(ValueError): imp.local_db('select 1;')

    def test_data_escaping_and_foods_only(self):
        evil="x'); delete from public.foods; --\\$tag$\nTiếng Việt"
        p=dict(foods=[{'name_vi':evil}])
        sql=imp.import_sql(p,{'x':'a'*64})
        self.assertIn(imp.literal(json.dumps(p['foods'],ensure_ascii=False,separators=(',',':'))),sql)
        self.assertIn('on conflict do nothing',sql)
        self.assertNotIn('do update',sql)
        for removed in ('nutrition_references','food_nutrition','food_portions'):
            self.assertNotIn(removed,sql)

    def test_rollback_mode(self):
        sql=imp.import_sql(dict(foods=[]),{},commit=False)
        self.assertTrue(sql.rstrip().endswith('rollback;'))
        self.assertIn('pg_advisory_xact_lock',sql)

    def test_identity_guards(self):
        with self.assertRaises(ValueError): imp.build_payload([],{'source_data_version':'other'})
        with self.assertRaises(ValueError): imp.build_payload([],dict(source_data_version=imp.VERSION,class_map_version=imp.CLASS_VERSION,foods=[]))

    def test_portable_identity_and_identity_only_metadata(self):
        out=imp.build_payload(*self.fixture())
        self.assertEqual(set(out),{'foods'}); self.assertEqual(len(out['foods']),67)
        f=next(f for f in out['foods'] if f['training_class_id']==27)
        self.assertEqual(f['original_class_id'],28)
        self.assertEqual(set(f['source_mapping_metadata']),set(imp.METADATA_KEYS))
        self.assertEqual(f['source_mapping_metadata']['training_class_id'],'27')

    def test_artifact_uuid_class_drift_and_duplicates_denied(self):
        for kind in ('uuid','class','duplicate'):
            c,i=self.fixture()
            if kind=='uuid': i['foods'][0]['id']='00000000-0000-4000-8000-000000000000'
            elif kind=='class': c[0]['original_class_id']='27'
            else: c[1]=dict(c[0])
            with self.assertRaises(ValueError): imp.build_payload(c,i)

    def test_source_bytes_drift_denied_before_parse(self):
        with patch.object(Path,'read_bytes',return_value=b'changed source'):
            with self.assertRaises(ValueError):
                imp.snapshot(imp.PROJECT,{'files':[{'name':imp.vd.CLASSES,'sha256':'0'*64}]},{})


if __name__=='__main__': unittest.main()
