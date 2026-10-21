"""Tests use synthetic small records; source files are never mutated."""

import contextlib
import copy
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scripts import validate_dataset as v


def fixture_directory(case):
    base = (PROJECT / 'data/processed/.data01-tests').resolve()
    base.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.TemporaryDirectory(dir=base)
    root = Path(temporary.name).resolve()
    # TemporaryDirectory performs recursive cleanup: constrain it to our test area.
    if not root.is_relative_to(base):
        raise RuntimeError('Unexpected fixture cleanup target')
    case.addCleanup(temporary.cleanup)
    return temporary, root


def food():
    return dict(training_class_id="27", original_class_id="28", slug="cu_kieu",
                food_name_vi="Củ kiệu", scope_kind="ingredient_or_component")


class ParseTests(unittest.TestCase):
    def test_bool_false_is_false(self):
        self.assertIs(v.parse_bool("false"), False)
        self.assertIs(v.parse_bool("true"), True)
        for value in ("False", "0", "", "yes"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                v.parse_bool(value)

    def test_findings_are_bounded_but_totals_complete(self):
        found = v.Findings()
        for i in range(300):
            found.add("same", "test.csv", "invalid", i)
        result = found.as_dict()
        self.assertEqual(result["total"], 300)
        self.assertEqual(result["by_code"], {"same": 300})
        self.assertEqual(len(result["samples"]), 5)
        self.assertTrue(result["samples_truncated"])


class ScopeTests(unittest.TestCase):
    def test_nutrition_files_are_out_of_scope(self):
        self.assertFalse(set(v.REMOVED_FILES) & set(v.FILES))
        self.assertFalse(set(v.REMOVED_FILES) & set(v.REQUIRED))
        self.assertFalse(hasattr(v.Validator, 'validate_references') or hasattr(v.Validator, 'validate_mapping'))

    def test_baseline_may_still_list_removed_files(self):
        entries = [dict(name=n, bytes=1, data_rows=0, sha256='0' * 64, columns=sorted(v.REQUIRED.get(n, {'id'})))
                   for n in (*v.FILES, *v.REMOVED_FILES)]
        kept = v.validate_baseline(dict(baseline_version='synthetic', files=entries))
        self.assertEqual({e['name'] for e in kept}, set(v.FILES))
        with self.assertRaises(ValueError):
            v.validate_baseline(dict(baseline_version='synthetic', files=entries[1:]))


class ClassTests(unittest.TestCase):
    def test_remapped_training_27_is_valid(self):
        check = v.Validator()
        check.validate_classes([(2, food())])
        self.assertEqual(check.errors.total, 0)

    def test_face_and_wrong_remap_rejected(self):
        for original, training in (("27", "27"), ("28", "28"), ("68", "66"), ("x", "27")):
            with self.subTest(original=original, training=training):
                r = food()
                r.update(original_class_id=original, training_class_id=training)
                check = v.Validator()
                check.validate_classes([(2, r)])
                self.assertGreater(check.errors.by_code["invalid_class_remap"], 0)

    def test_duplicate_class_keys(self):
        check = v.Validator()
        check.validate_classes([(2, food()), (3, food())])
        self.assertEqual(check.errors.by_code["duplicate_class_key"], 1)


class FileTests(unittest.TestCase):
    def setUp(self):
        self.temp, self.root = fixture_directory(self)

    def write_csv(self, text, name=v.CLASSES, cols=None, count=1):
        path = self.root / name
        path.write_bytes(text.encode("utf-8"))
        meta = dict(name=name, bytes=path.stat().st_size, sha256=v.file_digest(path),
                    data_rows=count, columns=cols or ["a", "b"])
        return path, meta

    def test_bom_quoted_comma_and_multiline_record(self):
        path, meta = self.write_csv('\ufeffa,b\r\n"one,two","line1\nline2"\r\n')
        check = v.Validator()
        rows = check.read_csv(path, meta)
        self.assertEqual(check.errors.total, 0)
        self.assertEqual(check.files[path.name]["data_rows"], 1)
        self.assertEqual(rows[0][1], {"a": "one,two", "b": "line1\nline2"})

    def test_manifest_rows_are_not_retained(self):
        path, meta = self.write_csv('a,b\n1,2\n3,4\n', name="foodlens_dataset.csv", count=2)
        check = v.Validator()
        self.assertEqual(check.read_csv(path, meta), [])
        self.assertEqual(check.files[path.name]["data_rows"], 2)
        self.assertEqual(check.errors.total, 0)

    def test_malformed_quotes_and_wrong_width(self):
        for text, expected in [('a,b\n"unclosed,2\n', 'csv_read_error'),
                               ('a,b\n1,2,3\n', 'invalid_row_width'),
                               ('a,b\n1\n', 'invalid_row_width')]:
            with self.subTest(text=text):
                path, meta = self.write_csv(text)
                check = v.Validator()
                check.read_csv(path, meta)
                self.assertIn(expected, check.errors.by_code)

    def test_duplicate_and_changed_header(self):
        for text, columns in [('a,a\n1,2\n', ['a', 'a']), ('a,c\n1,2\n', ['a', 'b'])]:
            path, meta = self.write_csv(text, cols=columns)
            check = v.Validator()
            check.read_csv(path, meta)
            self.assertIn('invalid_header', check.errors.by_code)

    def test_hash_bytes_and_row_drift_are_errors(self):
        path, meta = self.write_csv('a,b\n1,2\n')
        for key, value in [('sha256', '0' * 64), ('bytes', 1), ('data_rows', 2)]:
            with self.subTest(key=key):
                changed = dict(meta, **{key: value})
                check = v.Validator()
                check.read_csv(path, changed)
                self.assertIn('baseline_drift', check.errors.by_code)

    def test_missing_file_is_reported(self):
        check = v.Validator()
        check.read_csv(self.root / 'missing.csv', {})
        self.assertIn('csv_read_error', check.errors.by_code)


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.check = v.Validator()
        self.check.counts.update(foods=67)
        # Nutrition summary rows are still present in the source package but are ignored (FOOD-02).
        values = [('dataset', 'food_classes', '67'), ('nutrition', 'reference_records', '9115'),
                  ('nutrition', 'candidate_links', 'not-a-number')]
        self.rows = [(i + 2, dict(section=sec, entity_id='', metric=m, value_num=n, value_text=''))
                     for i, (sec, m, n) in enumerate(values)]

    def test_summary_matches_independent_counts_and_ignores_nutrition(self):
        self.check.validate_summary(self.rows)
        self.assertEqual(self.check.errors.total, 0)

    def test_mismatched_missing_and_duplicate_summary(self):
        self.rows[0][1]['value_num'] = '80'
        self.check.validate_summary(self.rows)
        self.assertIn('summary_mismatch', self.check.errors.by_code)
        for rows in ([r for r in self.rows if r[1]['section'] != 'dataset'], self.rows + [self.rows[0]]):
            check = v.Validator()
            check.counts.update(foods=67)
            check.validate_summary(rows)
            self.assertEqual(check.errors.by_code['summary_metric_missing_or_duplicate'], 1)

    def test_source_audit_block_is_not_a_new_validator_error(self):
        self.check.validate_audit([(2, dict(domain='nutrition', severity='block', issue_code='negative_core_nutrient'))])
        self.assertEqual(self.check.errors.total, 0)
        self.assertEqual(self.check.counts['source_audit']['severity'], {'block': 1})


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp, self.root = fixture_directory(self)
        self.csv_root = self.root / 'sources'
        self.csv_root.mkdir()
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps(dict(config_version=1, csv_root='sources', vision_root=None)))
        self.baseline = self.root / 'baseline.json'
        self.report = self.root / 'report.json'
        entries = []
        for name in v.FILES:
            cols = sorted(v.REQUIRED.get(name, {'id'}))
            path = self.csv_root / name
            with path.open('w', encoding='utf-8', newline='') as stream:
                csv.writer(stream).writerow(cols)
            entries.append(dict(name=name, columns=cols, data_rows=0,
                                bytes=path.stat().st_size, sha256=v.file_digest(path)))
        self.baseline.write_text(json.dumps(dict(baseline_version='synthetic-small-test', files=entries)))
        self.args = ['--config', str(self.config), '--baseline', str(self.baseline), '--report', str(self.report)]

    def run_cli(self, args=None):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return v.main(self.args if args is None else args)

    def test_empty_synthetic_snapshot_fails_with_report_exit_1(self):
        self.assertEqual(self.run_cli(), 1)
        report = json.loads(self.report.read_text(encoding='utf-8'))
        self.assertEqual(report['overall_status'], 'failed')
        self.assertIn('snapshot_count_mismatch', report['errors']['by_code'])
        self.assertEqual(report['scope'], 'backend_csv')
        self.assertTrue(report['not_checked'])

    def test_invalid_config_exit_2_without_output(self):
        for content in ('{}', '{', 'null', '{"config_version":true,"csv_root":"sources"}'):
            self.config.write_text(content)
            self.assertEqual(self.run_cli(), 2)
            self.assertFalse(self.report.exists())

    def test_invalid_baseline_exit_1_and_report(self):
        self.baseline.write_text('{"files":[]}')
        self.assertEqual(self.run_cli(), 1)
        self.assertIn('invalid_baseline', json.loads(self.report.read_text())['errors']['by_code'])

    def test_csv_root_override_resolves_from_cwd(self):
        config = dict(config_version=1, csv_root='does-not-exist', vision_root='missing-is-okay')
        self.config.write_text(json.dumps(config))
        args = self.args + ['--csv-root', os.path.relpath(self.csv_root)]
        self.assertEqual(self.run_cli(args), 1)  # Data failure, not config failure.
        self.assertTrue(self.report.exists())

    def test_source_output_alias_and_input_alias_are_blocked(self):
        source = self.csv_root / v.CLASSES
        before = source.read_bytes()
        for destination in (source, self.config, self.baseline, self.csv_root / 'new.json'):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                v.protect_paths(self.config, self.baseline, destination, self.csv_root)
        args = self.args[:-1] + [str(source)]
        self.assertEqual(self.run_cli(args), 2)
        self.assertEqual(source.read_bytes(), before)

    def test_filesystem_identity_alias_is_rejected(self):
        source = self.csv_root / v.CLASSES
        alias = self.root / 'alias.json'
        alias.write_text('{}')
        # Hard-link creation is denied in the sandbox; exercise samefile identity
        # deterministically without requiring Windows link privileges.
        def same_identity(a, b):
            return {a.resolve(), b.resolve()} == {alias.resolve(), source.resolve()}
        with patch.object(Path, 'samefile', same_identity):
            with self.assertRaises(ValueError):
                v.protect_paths(self.config, self.baseline, alias, self.csv_root)
            with self.assertRaises(ValueError):
                v.protect_paths(alias, self.baseline, self.report, self.csv_root)

    def test_report_failure_is_nonzero(self):
        with patch.object(v, 'write_report', side_effect=OSError('disk full')):
            self.assertEqual(self.run_cli(), 1)

    def test_atomic_report_failure_preserves_existing_report(self):
        self.report.write_text('previous')
        with patch.object(v.os, 'replace', side_effect=OSError('locked')):
            with self.assertRaises(OSError):
                v.write_report(self.report, {'new': True})
        self.assertEqual(self.report.read_text(), 'previous')
        self.assertEqual(list(self.root.glob('.foodlens-report-*')), [])

    def test_repeated_run_is_deterministic_except_timestamp(self):
        self.run_cli()
        first = json.loads(self.report.read_text(encoding='utf-8'))
        self.run_cli()
        second = json.loads(self.report.read_text(encoding='utf-8'))
        first.pop('generated_at')
        second.pop('generated_at')
        self.assertEqual(first, second)

    def test_import_has_no_side_effects_and_cli_usage_is_2(self):
        script = PROJECT / 'scripts/validate_dataset.py'
        code = ('import importlib.util; '
                f's=importlib.util.spec_from_file_location("validator",{str(script)!r}); '
                'm=importlib.util.module_from_spec(s); s.loader.exec_module(m)')
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=self.root,
                                capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        result = subprocess.run([sys.executable, str(script)], cwd=self.root, capture_output=True)
        self.assertEqual(result.returncode, 2)

    def test_baseline_rejects_traversal_duplicate_and_wrong_types(self):
        original = json.loads(self.baseline.read_text())
        for key, value in [('name', '../outside.csv'), ('bytes', True),
                           ('data_rows', -1), ('sha256', 'wrong'), ('columns', ['id', 'id'])]:
            with self.subTest(key=key):
                changed = copy.deepcopy(original)
                changed['files'][0][key] = value
                with self.assertRaises(ValueError):
                    v.validate_baseline(changed)


if __name__ == '__main__':
    unittest.main()
