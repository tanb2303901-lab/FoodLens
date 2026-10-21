"""Read-only validation of the FoodLens backend CSV handoff (standard library)."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile


CLASSES = "foodlens_classes.csv"
SUMMARY = "dataset_summary.csv"
ISSUES = "dataset_issues.csv"
FILES = (CLASSES, "foodlens_images.csv", "foodlens_dataset.csv", SUMMARY, ISSUES)
SMALL_FILES = {CLASSES, SUMMARY, ISSUES}
# Received in the original package and recorded in the baseline, but out of scope since
# FOOD-02 removed nutrition: never read, validated or imported. Source files stay untouched.
REMOVED_FILES = ("nutrition_reference.csv", "food_nutrition_mapping.csv")
REQUIRED = {
    CLASSES: {"training_class_id", "original_class_id", "slug", "food_name_vi", "scope_kind"},
    SUMMARY: {"section", "entity_id", "metric", "value_num", "value_text"},
    ISSUES: {"domain", "severity", "issue_code"},
}
NOT_CHECKED = [
    "Supabase migrations, Auth, RLS and Storage",
    "Actual image/label presence, image decoding/hashing and label semantics",
    "Full vision manifest joins, bbox semantics and leakage evaluation",
    "Model training/inference and application endpoints",
    "Nutrition CSVs (out of scope since FOOD-02; not read)",
]


def parse_bool(value: str) -> bool:
    if value not in ("true", "false"):
        raise ValueError("Expected exactly true or false")
    return value == "true"


def parse_integer(value: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+", value):
        raise ValueError("Expected a nonnegative integer")
    return int(value)


def reject_constant(value: str):
    raise ValueError(f"Nonstandard JSON numeric constant: {value}")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(text: str):
    return json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique_object)


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class Findings:
    """Bounded examples, with complete totals even when samples are truncated."""

    def __init__(self):
        self.total = 0
        self.by_code = Counter()
        self.samples = []
        self.sample_counts = Counter()

    def add(self, code, file, message, row=None, field=None):
        self.total += 1
        self.by_code[code] += 1
        if self.sample_counts[code] < 5 and len(self.samples) < 100:
            self.samples.append(dict(code=code, file=file, row=row, field=field,
                                     message=message))
            self.sample_counts[code] += 1

    def as_dict(self):
        return dict(total=self.total, by_code=dict(sorted(self.by_code.items())),
                    samples=self.samples, samples_truncated=self.total > len(self.samples))


class Validator:
    def __init__(self):
        self.errors = Findings()
        self.review = Findings()
        self.files = {}
        self.counts = {}
        self.checks = []
        self.classes = {}

    def value(self, row, field, parser, file, line):
        try:
            return parser(row[field])
        except (ValueError, TypeError, KeyError) as exc:
            self.errors.add("invalid_value", file, str(exc), line, field)
            return None

    def require(self, valid, code, file, message, row=None, field=None):
        if not valid:
            self.errors.add(code, file, message, row, field)

    def phase(self, name, action):
        before = self.errors.total
        action()
        self.checks.append(dict(name=name, status="passed" if self.errors.total == before
                                else "failed", errors_added=self.errors.total - before))

    def read_csv(self, path: Path, expected: dict):
        """Retain only small backend/audit tables; stream both vision manifests."""
        name = path.name
        saved = []
        metadata = dict(path=str(path), status="failed", data_rows=0)
        self.files[name] = metadata
        before_errors = self.errors.total
        try:
            before_stat = path.stat()
            metadata.update(bytes=before_stat.st_size, sha256=file_digest(path))
            for key in ("bytes", "sha256"):
                self.require(metadata[key] == expected[key], "baseline_drift", name,
                             f"{key} differs from baseline", field=key)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.reader(stream, strict=True)
                header = next(reader, [])
                metadata["columns"] = header
                good_header = header == expected["columns"] and len(set(header)) == len(header)
                self.require(good_header, "invalid_header", name,
                             "Header must match baseline exactly without duplicate columns", row=1)
                for fields in reader:
                    metadata["data_rows"] += 1
                    if len(fields) != len(header):
                        self.errors.add("invalid_row_width", name,
                                        "Number of cells differs from header", reader.line_num)
                    elif good_header and name in SMALL_FILES:
                        saved.append((reader.line_num, dict(zip(header, fields))))
                self.require(metadata["data_rows"] == expected["data_rows"], "baseline_drift",
                             name, "Data row count differs from baseline", field="data_rows")
            after_stat = path.stat()
            self.require((before_stat.st_size, before_stat.st_mtime_ns) ==
                         (after_stat.st_size, after_stat.st_mtime_ns), "source_changed",
                         name, "Source changed while being read")
            if self.errors.total == before_errors:
                metadata["status"] = "passed"
        except (OSError, UnicodeError, csv.Error) as exc:
            self.errors.add("csv_read_error", name, str(exc),
                            getattr(locals().get("reader"), "line_num", None))
        return saved

    def validate_classes(self, rows):
        slugs, originals = set(), set()
        for line, r in rows:
            t = self.value(r, "training_class_id", parse_integer, CLASSES, line)
            o = self.value(r, "original_class_id", parse_integer, CLASSES, line)
            self.require(t is not None and o is not None and 0 <= t <= 66 and
                         0 <= o <= 67 and o != 27 and t == (o if o < 27 else o - 1),
                         "invalid_class_remap", CLASSES, "Invalid original/training ID pair", line)
            self.require(t not in self.classes and o not in originals and r["slug"] not in slugs,
                         "duplicate_class_key", CLASSES, "Class ID or slug is duplicated", line)
            self.require(bool(re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", r["slug"])) and
                         bool(r["food_name_vi"].strip()) and r["scope_kind"] in
                         {"prepared_food", "ingredient_or_component", "broad_food_category"},
                         "invalid_class_identity", CLASSES, "Invalid food name, slug or scope", line)
            if t is not None:
                self.classes[t] = r
            slugs.add(r["slug"])
            originals.add(o)
        self.counts["foods"] = len(rows)

    def validate_summary(self, rows):
        # Only dataset-level metrics are in scope; nutrition summary rows are ignored (FOOD-02).
        seen = 0
        for line, r in rows:
            if r["entity_id"] or (r["section"], r["metric"]) != ("dataset", "food_classes"):
                continue
            seen += 1
            value = self.value(r, "value_num", parse_integer, SUMMARY, line)
            self.require(value == self.counts["foods"], "summary_mismatch", SUMMARY,
                         "food_classes disagrees with source records", line, "value_num")
        self.require(seen == 1, "summary_metric_missing_or_duplicate", SUMMARY,
                     "Expected exactly one dataset food_classes summary row")

    def validate_audit(self, rows):
        severity, codes, domains = Counter(), Counter(), Counter()
        for line, r in rows:
            severity[r["severity"]] += 1
            codes[r["issue_code"]] += 1
            domains[r["domain"]] += 1
            self.require(r["severity"] in {"info", "review", "block", "quarantine"} and
                         r["domain"] in {"vision", "nutrition"} and bool(r["issue_code"]),
                         "invalid_audit_metadata", ISSUES, "Invalid audit severity/domain/code", line)
        self.counts["source_audit"] = dict(rows=len(rows), severity=dict(sorted(severity.items())),
                                          codes=dict(sorted(codes.items())), domains=dict(sorted(domains.items())))
        self.review.add("source_audit_retained", ISSUES,
                        "Source audit includes handled exclusions and unresolved reviews; counts do not imply open errors")

    def validate_snapshot(self):
        self.require(self.counts["foods"] == 67, "snapshot_count_mismatch", None,
                     f"foods: expected 67, found {self.counts['foods']}", field="foods")
        self.require(set(self.classes) == set(range(67)), "class_coverage_mismatch", CLASSES,
                     "Training IDs must cover exactly 0..66")

    def report(self, baseline_version=None, status=None):
        if status is None:
            status = "failed" if self.errors.total else ("passed_with_review" if self.review.total else "passed")
        return dict(report_version=1, generated_at=datetime.now(timezone.utc).isoformat(),
                    scope="backend_csv", baseline_version=baseline_version, overall_status=status,
                    counts=self.counts, files=self.files, checks=self.checks,
                    errors=self.errors.as_dict(), review_findings=self.review.as_dict(),
                    not_checked=NOT_CHECKED)


def validate_baseline(baseline):
    if not isinstance(baseline, dict) or not isinstance(baseline.get("baseline_version"), str) or not baseline["baseline_version"]:
        raise ValueError("Baseline requires a nonempty baseline_version")
    entries = baseline.get("files")
    if not isinstance(entries, list):
        raise ValueError("Baseline must contain a file list")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("name") not in (*FILES, *REMOVED_FILES) or entry["name"] in seen:
            raise ValueError("Baseline file names must be unique supported names")
        seen.add(entry["name"])
    if not set(FILES) <= seen:
        raise ValueError("Baseline must describe every in-scope file")
    entries = [e for e in entries if e["name"] in FILES]
    for entry in entries:
        name = entry["name"]
        if any(type(entry.get(k)) is not int or entry[k] < 0 for k in ("bytes", "data_rows")):
            raise ValueError(f"{name}: invalid bytes/data_rows")
        if not isinstance(entry.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise ValueError(f"{name}: invalid SHA-256")
        cols = entry.get("columns")
        if (not isinstance(cols, list) or not cols or any(not isinstance(c, str) or not c for c in cols)
                or len(set(cols)) != len(cols) or not REQUIRED.get(name, set()).issubset(cols)):
            raise ValueError(f"{name}: invalid or missing baseline columns")
    return entries


def aliases(a: Path, b: Path) -> bool:
    return a.resolve() == b.resolve() or (a.exists() and b.exists() and a.samefile(b))


def protect_paths(config: Path, baseline: Path, report: Path, root: Path):
    sources = [root / name for name in FILES]
    for input_path in (config, baseline):
        if any(aliases(input_path, source) for source in sources):
            raise ValueError("Config/baseline must not alias a source CSV")
    if (report.suffix.lower() != ".json" or report.is_dir() or
            report.resolve().is_relative_to(root.resolve()) or
            any(aliases(report, p) for p in (*sources, config, baseline))):
        raise ValueError("Report must be a JSON file outside csv_root and must not alias any input")


def write_report(path: Path, report: dict):
    """Atomic replace prevents truncated reports if serialization or IO fails."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, prefix=".foodlens-report-", suffix=".tmp", delete=False) as f:
            temporary = Path(f.name)
            json.dump(report, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--csv-root", type=Path)
    args = parser.parse_args(argv)
    validator = Validator()
    try:
        config = load_json(args.config.read_text(encoding="utf-8-sig"))
        if not isinstance(config, dict) or type(config.get("config_version")) is not int or config["config_version"] != 1:
            raise ValueError("config_version must be integer 1")
        if args.csv_root is not None:
            root = args.csv_root.resolve()
        else:
            if not isinstance(config.get("csv_root"), str) or not config["csv_root"].strip():
                raise ValueError("csv_root must be a nonempty path string")
            root = Path(config["csv_root"])
            if not root.is_absolute():
                root = args.config.resolve().parent / root
            root = root.resolve()
        if config.get("vision_root") is not None and not isinstance(config["vision_root"], str):
            raise ValueError("vision_root must be a path string or null")
        if not root.is_dir():
            raise ValueError("csv_root is not an accessible directory")
        protect_paths(args.config, args.baseline, args.report, root)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"CONFIG_ERROR: {exc}", file=sys.stderr)
        return 2  # Without verified paths, writing an error report is unsafe.

    version = None
    try:
        baseline = load_json(args.baseline.read_text(encoding="utf-8-sig"))
        entries = validate_baseline(baseline)
        version = baseline["baseline_version"]
    except (OSError, UnicodeError, ValueError) as exc:
        validator.errors.add("invalid_baseline", str(args.baseline), str(exc))
    else:
        tables = {}
        for entry in entries:
            name = entry["name"]
            validator.phase(f"file:{name}", lambda e=entry, n=name:
                            tables.update({n: validator.read_csv(root / n, e)}))
        actions = [(CLASSES, "classes", validator.validate_classes),
                   (SUMMARY, "summary", validator.validate_summary),
                   (ISSUES, "source_audit", validator.validate_audit)]
        # Do not label semantic checks as passed when their inputs could not be parsed.
        complete = all(validator.files[n]["status"] == "passed" for n in SMALL_FILES)
        if complete:
            for name, label, action in actions:
                validator.phase(label, lambda n=name, a=action: a(tables[n]))
            validator.phase("snapshot", validator.validate_snapshot)
        else:
            validator.checks.append(dict(name="backend_semantics", status="not_run",
                                         reason="Backend/audit file metadata or CSV structure failed"))
        validator.review.add("holdout_coverage_incomplete", "foodlens_images.csv",
                             "Received baseline valid/test cover 35/29 classes; vision evaluation remains outside this task")
    result = validator.report(version)
    try:
        protect_paths(args.config, args.baseline, args.report, root)
        write_report(args.report, result)
    except (OSError, ValueError) as exc:
        print(f"REPORT_WRITE_ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"{result['overall_status']}: {validator.errors.total} errors; "
          f"{validator.review.total} review findings. Report: {args.report}")
    return 1 if validator.errors.total else 0


if __name__ == "__main__":
    raise SystemExit(main())
