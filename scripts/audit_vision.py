"""ML-01 read-only VietFood image/label/manifest audit; no training or export.

Only config/reports under ignored data/processed are written. Images are sampled
for decode/SHA/CRC; every physical label is hashed and each preferred label parsed.
"""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from itertools import islice
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import sys
import warnings
import zlib

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / 'data/processed'
BASELINE = ROOT / 'docs/dataset/source-baseline.json'
IDENTITY = ROOT / 'docs/dataset/food-identities-v1.json'
ORIGINAL_SPLITS = {'train', 'valid', 'test'}
SPLITS = ORIGINAL_SPLITS | {'review', 'excluded'}
MODULUS = 1 << 256


def integer(value, minimum=0):
    if not isinstance(value, str) or not re.fullmatch(r'0|[1-9][0-9]*', value):
        raise ValueError('Expected a nonnegative integer')
    n = int(value)
    if n < minimum:
        raise ValueError('Integer is below minimum')
    return n


def boolean(value):
    if value not in ('true', 'false'):
        raise ValueError('Expected true or false')
    return value == 'true'


def box(values):
    if len(values) != 4:
        raise ValueError('Expected four normalized coordinates')
    x, y, w, h = (float(v) for v in values)
    if not all(math.isfinite(v) for v in (x, y, w, h)) or not (0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1):
        raise ValueError('Invalid normalized box values')
    if min(x-w/2, y-h/2) < -1e-6 or max(x+w/2, y+h/2) > 1+1e-6:
        raise ValueError('Box exceeds image bounds')
    return x, y, w, h


def training_id(original):
    if type(original) is not int or not 0 <= original <= 67 or original == 27:
        raise ValueError('Expected an original food class, excluding face 27')
    return original if original < 27 else original-1


def image_identity(value):
    if not isinstance(value, str) or '\\' in value or ':' in value or '\x00' in value:
        raise ValueError('Unsafe image ID')
    parts = value.split('/')
    if len(parts) != 2 or parts[0] not in ORIGINAL_SPLITS or parts[1] in ('', '.', '..'):
        raise ValueError('Expected original_split/image_stem')
    return parts


def relocated_path(value, kind, image_id):
    """Map an old root to this root by its unique images/labels anchor."""
    original, stem = image_identity(image_id)
    if not isinstance(value, str) or not value or '\x00' in value:
        raise ValueError('Invalid source path')
    normalized = value.replace('\\', '/')
    parts = normalized.split('/')
    if normalized.startswith('//') or any(p in ('.', '..') for p in parts):
        raise ValueError('Network/traversal path rejected')
    if parts.count(kind) != 1:
        raise ValueError('Source path needs one images/labels anchor')
    suffix = parts[parts.index(kind):]
    if len(suffix) < 3 or suffix[1] != original or any(not p or ':' in p for p in suffix):
        raise ValueError('Invalid source suffix/split')
    expected_ext = '.jpg' if kind == 'images' else '.txt'
    if suffix[-1].casefold() != (stem + expected_ext).casefold() or (kind == 'images' and len(suffix) != 3):
        raise ValueError('Path does not match image identity')
    return '/'.join(suffix)


def fingerprint(line, original, coordinates):
    # Order-independent multiset fingerprint; duplicate physical lines are checked
    # separately. Floats normalize equivalent lexical forms such as 0.5 and .500.
    normalized = tuple(0.0 if v == 0 else v for v in coordinates)
    return int.from_bytes(hashlib.sha256(struct.pack('>IHdddd', line, original, *normalized)).digest(), 'big')


def parse_label(content):
    digest, foods, faces, objects = 0, 0, 0, 0
    classes = Counter()
    if len(content) > 16*1024*1024:
        raise ValueError('Label exceeds audit read limit')
    for line, text in enumerate(content.decode('utf-8-sig').splitlines(), 1):
        if not text.strip():
            continue
        cells = text.split()
        if len(cells) != 5:
            raise ValueError(f'Invalid YOLO field count at line {line}')
        original = integer(cells[0])
        if original > 67:
            raise ValueError('Original class outside 0..67')
        coordinates = box(cells[1:])
        objects += 1
        if original == 27:
            faces += 1
        else:
            t = training_id(original)
            foods += 1
            classes[t] += 1
            digest = (digest + fingerprint(line, original, coordinates)) % MODULUS
    return dict(fingerprint=digest, foods=foods, faces=faces, objects=objects, classes=classes)


@dataclass(frozen=True, slots=True)
class FileInfo:
    path: Path
    rel: str
    size: int
    mtime: int


class Issues:
    def __init__(self, stream):
        self.stream = stream
        self.counts = Counter()
        self.examples = []

    def add(self, severity, code, **details):
        item = dict(severity=severity, code=code, **details)
        self.counts[severity + ':' + code] += 1
        if len(self.examples) < 30:
            self.examples.append(item)
        self.stream.write(json.dumps(item, ensure_ascii=False) + '\n')

    @property
    def errors(self):
        return sum(n for k, n in self.counts.items() if k.startswith('error:'))


def inventory(root, kind, issues):
    found = {}
    stack = [root / kind]
    while stack:
        parent = stack.pop()
        if parent.is_symlink() or parent.is_junction():
            issues.add('error', 'reparse_path_rejected', path=str(parent))
            continue
        try:
            with os.scandir(parent) as entries:
                for entry in entries:
                    metadata = entry.stat(follow_symlinks=False)
                    relative = Path(entry.path).relative_to(root).as_posix()
                    if entry.is_symlink() or getattr(metadata, 'st_file_attributes', 0) & 0x400:
                        issues.add('error', 'reparse_path_rejected', path=relative)
                    elif stat.S_ISDIR(metadata.st_mode):
                        stack.append(Path(entry.path))
                    elif stat.S_ISREG(metadata.st_mode):
                        key = relative.casefold()
                        if key in found:
                            issues.add('error', 'case_colliding_files', path=relative)
                        found[key] = FileInfo(Path(entry.path), relative, metadata.st_size, metadata.st_mtime_ns)
        except OSError:
            issues.add('error', 'inventory_read_failed', path=str(parent))
    return found


def read_stable(info):
    if info.path.is_symlink() or info.path.is_junction():
        raise ValueError('Reparse file rejected')
    before = info.path.stat()
    if (before.st_size, before.st_mtime_ns) != (info.size, info.mtime):
        raise ValueError('Source changed since inventory')
    # Resolve before reading, so a replaced symlink/junction cannot escape root.
    root = info.path.parents[len(PurePosixPath(info.rel).parts)-1]
    if not info.path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Resolved source escapes vision root')
    content = info.path.read_bytes()
    after = info.path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('Source changed while reading')
    return content


@dataclass(slots=True)
class ImageRow:
    id: str
    split: str
    included: bool
    status: str
    reason: str
    groups: tuple
    image_rel: str
    label_rel: str
    image_bytes: int
    label_bytes: int
    label_sha: str
    copies: int
    food_boxes: int
    face_boxes: int
    objects: int
    background: bool
    crc: int
    rank: bytes
    annotations: int = 0
    fingerprint: int = 0
    lines: int = 0
    classes: int = 0


def csv_rows(path, expected):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream, strict=True)
        if reader.fieldnames != expected:
            raise ValueError('Manifest header differs from baseline')
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError('Manifest row width differs from header')
            yield reader.line_num, row


def load_images(csv_root, columns, issues):
    rows = {}
    for line, row in csv_rows(csv_root / 'foodlens_images.csv', columns):
        try:
            key = row['image_id']
            original, _ = image_identity(key)
            if key in rows or row['original_split'] != original or row['split'] not in SPLITS:
                raise ValueError('Duplicate identity or invalid split')
            included, train, evaluate = [boolean(row[n]) for n in ('include_in_dataset', 'use_for_training', 'use_for_evaluation')]
            if included != (row['split'] != 'excluded') or train != (row['split'] == 'train') or evaluate != (row['split'] in ('valid', 'test')):
                raise ValueError('Inconsistent inclusion/train/evaluation flags')
            review = json.loads(row['eval_review_reasons'])
            if not isinstance(review, list) or not all(isinstance(v, str) for v in review):
                raise ValueError('Invalid review reasons')
            if row['split'] == 'review' and not review:
                raise ValueError('Review split needs provenance reason')
            item = ImageRow(key, row['split'], included, row['record_status'], row['exclusion_reason'],
                            tuple(row[n] for n in ('source_video_family', 'source_video_key', 'source_name_prefix')),
                            relocated_path(row['image_path'], 'images', key), relocated_path(row['raw_label_path'], 'labels', key),
                            integer(row['image_bytes'], 1), integer(row['label_bytes']), row['label_sha256'], integer(row['label_copy_count'], 1),
                            integer(row['food_box_count']), integer(row['removed_face_box_count']), integer(row['original_object_count']),
                            boolean(row['is_background']), integer(row['archive_image_crc32']), hashlib.sha256(key.encode()).digest())
            if not re.fullmatch('[0-9a-f]{64}', item.label_sha) or item.crc > 0xffffffff:
                raise ValueError('Invalid label checksum/image CRC')
            if item.objects != item.food_boxes + item.face_boxes or item.background != (item.objects == 0):
                raise ValueError('Inconsistent box/background counts')
            if not included and item.reason not in ('face_only_image', 'identical_image_conflicting_annotations'):
                raise ValueError('Excluded record needs a known reason')
            rows[key] = item
        except (ValueError, KeyError, TypeError) as exc:
            issues.add('error', 'invalid_image_manifest_row', line=line, reason=str(exc))
    return rows


def load_annotations(csv_root, columns, rows, issues):
    counts, coverage = Counter(), defaultdict(Counter)
    for line, row in csv_rows(csv_root / 'foodlens_dataset.csv', columns):
        try:
            item = rows[row['image_id']]
            original, train_id = integer(row['original_class_id']), integer(row['training_class_id'])
            label_line = integer(row['original_label_line'], 1)
            if label_line > 1000000:
                raise ValueError('Label line exceeds audit bound')
            if not item.included or training_id(original) != train_id or row['split'] != item.split or row['original_split'] != item.id.split('/')[0]:
                raise ValueError('Annotation identity/remap/split mismatch')
            if row['annotation_id'] != f'{item.id}:{label_line}' or item.lines & (1 << label_line):
                raise ValueError('Duplicate or invalid annotation line')
            if boolean(row['use_for_training']) != (item.split == 'train') or boolean(row['use_for_evaluation']) != (item.split in ('valid', 'test')):
                raise ValueError('Annotation flags mismatch')
            coords = box([row[k] for k in ('x_center_norm', 'y_center_norm', 'width_norm', 'height_norm')])
            item.lines |= 1 << label_line
            item.classes |= 1 << train_id
            item.annotations += 1
            item.fingerprint = (item.fingerprint + fingerprint(label_line, original, coords)) % MODULUS
            counts[item.split] += 1
            coverage[item.split][train_id] += 1
        except (ValueError, KeyError, TypeError) as exc:
            issues.add('error', 'invalid_annotation_manifest_row', line=line, reason=str(exc))
    for item in rows.values():
        expected = item.food_boxes if item.included else 0
        if item.annotations != expected:
            issues.add('error', 'annotation_count_mismatch', image_id=item.id, expected=expected, actual=item.annotations)
    return counts, coverage


def label_check(item, copies):
    problems = []
    preferred = next((f for f in copies if f.rel.casefold() == item.label_rel.casefold()), None)
    if preferred is None:
        return dict(problems=[('preferred_label_missing', {})], files_hashed=0, files_parsed=0)
    if len(copies) != item.copies:
        problems.append(('label_copy_count_mismatch', dict(expected=item.copies, actual=len(copies))))
    parsed = None
    hashed = 0
    for info in copies:
        try:
            content = read_stable(info)
            hashed += 1
            if len(content) != item.label_bytes or hashlib.sha256(content).hexdigest() != item.label_sha:
                problems.append(('label_size_or_sha_mismatch', dict(path=info.rel)))
            if info is preferred:
                parsed = parse_label(content)
        except (OSError, ValueError, UnicodeError, struct.error):
            problems.append(('label_read_or_parse_failed', dict(path=info.rel)))
    if parsed:
        if (parsed['foods'], parsed['faces'], parsed['objects']) != (item.food_boxes, item.face_boxes, item.objects):
            problems.append(('raw_label_count_mismatch', {}))
        if item.included and parsed['fingerprint'] != item.fingerprint:
            problems.append(('bbox_manifest_mismatch', {}))
        if not item.included and item.reason == 'face_only_image' and not (parsed['foods'] == 0 and parsed['faces'] > 0):
            problems.append(('face_only_exclusion_mismatch', {}))
    return dict(problems=problems, files_hashed=hashed, files_parsed=int(parsed is not None))


def select_decode(rows, per_split):
    selected = set()
    buckets = defaultdict(list)
    representatives = {}
    for item in rows.values():
        buckets[item.split].append(item)
        bits = item.classes
        for t in range(67):
            if bits & (1 << t):
                key = item.split, 'class', t
                if key not in representatives or item.rank < representatives[key].rank:
                    representatives[key] = item
        for key in [(item.split, 'status', item.status), (item.split, 'reason', item.reason)]:
            if key not in representatives or item.rank < representatives[key].rank:
                representatives[key] = item
    for items in buckets.values():
        selected.update(v.id for v in sorted(items, key=lambda v: v.rank)[:per_split])
    selected.update(v.id for v in representatives.values())
    return sorted(selected)


def source_overlap(rows):
    result = {}
    for index, name in enumerate(('source_video_family', 'source_video_key', 'source_name_prefix')):
        grouped = defaultdict(lambda: defaultdict(list))
        for item in rows.values():
            if item.included and item.groups[index]:
                grouped[item.split][item.groups[index]].append(item.id)
        overlap = {}
        for split in ('valid', 'test', 'review'):
            shared = sorted(set(grouped['train']) & set(grouped[split]))
            overlap[split] = dict(shared_group_count=len(shared),
                                  affected_images=sum(len(grouped[split][g]) for g in shared), groups=shared)
        result[name] = overlap
    return result


def checked_output(path, config, csv_root, vision_root):
    path = path.resolve()
    if path.suffix != '.json' or not path.is_relative_to(PROCESSED.resolve()) or path == config.resolve():
        raise ValueError('JSON report must be in ignored data/processed and distinct from config')
    if path.is_relative_to(csv_root) or path.is_relative_to(vision_root):
        raise ValueError('Output must be outside both source roots')
    issues_path = path.with_suffix('.issues.jsonl')
    if not issues_path.resolve().is_relative_to(PROCESSED.resolve()):
        raise ValueError('Issue output must stay in ignored data/processed')
    inputs = [config, BASELINE, IDENTITY, *csv_root.glob('*.csv')]
    for output in (path, issues_path):
        for source in inputs:
            if output == source.resolve() or (output.exists() and source.exists() and output.samefile(source)):
                raise ValueError('Output aliases a source/config file')
    return path, issues_path


def source_checks(csv_root, baseline):
    checks = {}
    for entry in baseline['files']:
        path = csv_root / entry['name']
        before = path.stat()
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(8*1024*1024), b''):
                digest.update(chunk)
        after = path.stat()
        checks[entry['name']] = dict(bytes=after.st_size, sha256=digest.hexdigest(),
                                    matches_baseline=after.st_size == entry['bytes'] and digest.hexdigest() == entry['sha256'],
                                    stable=(before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns))
    return checks


def run(config_path, report_path, per_split=128, workers=4, candidate_limit=2048):
    config = json.loads(config_path.read_text(encoding='utf-8-sig'))
    if type(config.get('config_version')) is not int or config['config_version'] != 1:
        raise ValueError('Unsupported config version')
    csv_root, vision_root = (Path(config[k]).resolve() for k in ('csv_root', 'vision_root'))
    if not csv_root.is_dir() or not vision_root.is_dir():
        raise ValueError('Source roots must exist')
    report_path, issue_path = checked_output(report_path, config_path, csv_root, vision_root)
    baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
    columns = {e['name']: e['columns'] for e in baseline['files']}
    before = source_checks(csv_root, baseline)
    if not all(v['matches_baseline'] and v['stable'] for v in before.values()):
        raise ValueError('Source CSV baseline mismatch; no audit performed')
    identity = json.loads(IDENTITY.read_text(encoding='utf-8'))
    # The immutable identity artifact is verified against the source class table.
    class_rows = list(csv_rows(csv_root/'foodlens_classes.csv', columns['foodlens_classes.csv']))
    source_classes = {(integer(r['training_class_id']), integer(r['original_class_id']), r['slug']) for _, r in class_rows}
    artifact_classes = {(r['training_class_id'], r['original_class_id'], r['slug']) for r in identity['foods']}
    if len(source_classes) != 67 or source_classes != artifact_classes or any(training_id(o) != t for t, o, _ in source_classes):
        raise ValueError('Source classes differ from immutable 67-food identities')
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with issue_path.open('w', encoding='utf-8') as issue_stream:
        issues = Issues(issue_stream)
        print('ML-01: inventory images/labels (metadata only)', flush=True)
        image_files = inventory(vision_root, 'images', issues)
        label_files = inventory(vision_root, 'labels', issues)
        print(f'ML-01: inventory {len(image_files)} images-tree files / {len(label_files)} labels-tree files', flush=True)
        rows = load_images(csv_root, columns['foodlens_images.csv'], issues)
        annotation_counts, coverage = load_annotations(csv_root, columns['foodlens_dataset.csv'], rows, issues)
        label_index = defaultdict(list)
        for info in label_files.values():
            parts = PurePosixPath(info.rel).parts
            if len(parts) >= 3 and parts[1] in ORIGINAL_SPLITS and info.path.suffix.lower() == '.txt':
                label_index[(parts[1]+'/'+info.path.stem).casefold()].append(info)
            else:
                issues.add('review', 'unrecognized_label_tree_file', path=info.rel)
        expected_images = set()
        original_counts, split_counts, backgrounds = Counter(), Counter(), Counter()
        for item in rows.values():
            expected_images.add(item.image_rel.casefold())
            info = image_files.get(item.image_rel.casefold())
            if info is None:
                issues.add('error', 'image_missing', image_id=item.id)
            elif info.size != item.image_bytes:
                issues.add('error', 'image_size_mismatch', image_id=item.id, expected=item.image_bytes, actual=info.size)
            original_counts[item.id.split('/')[0]] += 1
            split_counts[item.split] += 1
            if item.background:
                backgrounds[item.split] += 1
        for key in image_files.keys() - expected_images:
            issues.add('review', 'unmanifested_image_tree_file', path=image_files[key].rel)
        for key in label_index.keys() - rows.keys():
            issues.add('review', 'unmanifested_label_identity', image_id=key)
        totals = Counter()
        ids = iter(sorted(rows))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            done = 0
            while batch := list(islice(ids, 512)):
                results = pool.map(lambda key: label_check(rows[key], label_index.get(key, [])), batch)
                for key, result in zip(batch, results):
                    totals.update({k: result[k] for k in ('files_hashed', 'files_parsed')})
                    for code, details in result['problems']:
                        issues.add('error', code, image_id=key, **details)
                done += len(batch)
                if done % 10240 == 0 or done == len(rows):
                    print(f'ML-01: labels {done}/{len(rows)} identities checked', flush=True)
        overlap = source_overlap(rows)
        for field_name, splits in overlap.items():
            for split, detail in splits.items():
                if detail['shared_group_count']:
                    issues.add('review', 'source_group_overlap', field=field_name, split=split,
                               shared_groups=detail['shared_group_count'], affected_images=detail['affected_images'])
        selected = select_decode(rows, per_split)
        crc_groups = defaultdict(list)
        for item in rows.values():
            crc_groups[item.image_bytes, item.crc].append(item.id)
        candidates = [sorted(v) for v in crc_groups.values() if len(v) > 1]
        candidate_ids = sorted({key for group in candidates for key in group})
        targeted = set(candidate_ids[:candidate_limit])
        decoded, hashed = {}, {}
        from io import BytesIO
        for key in sorted(set(selected) | targeted):
            item = rows[key]
            info = image_files.get(item.image_rel.casefold())
            if info is None:
                continue
            try:
                content = read_stable(info)
                hashed[key] = hashlib.sha256(content).hexdigest()
                if zlib.crc32(content) & 0xffffffff != item.crc:
                    issues.add('error', 'image_archive_crc_mismatch', image_id=key)
                if key in selected:
                    with warnings.catch_warnings():
                        warnings.simplefilter('error', Image.DecompressionBombWarning)
                        with Image.open(BytesIO(content)) as image:
                            image.load()
                            decoded[key] = dict(width=image.width, height=image.height, format=image.format,
                                                orientation=image.getexif().get(274, 1), frames=getattr(image, 'n_frames', 1))
                    if decoded[key]['orientation'] != 1:
                        issues.add('review', 'exif_orientation_needs_label_alignment', image_id=key)
            except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
                issues.add('error', 'sample_image_read_or_decode_failed', image_id=key)
        duplicate_groups = []
        sha_groups = defaultdict(list)
        for key, sha in hashed.items():
            sha_groups[sha].append(key)
        for group in sha_groups.values():
            if len(group) > 1:
                duplicate_groups.append(dict(image_ids=sorted(group), splits=sorted({rows[k].split for k in group}),
                                             included_images=sum(rows[k].included for k in group)))
        if len(candidate_ids) > candidate_limit:
            issues.add('review', 'duplicate_candidate_hash_limit', candidate_images=len(candidate_ids), hashed_limit=candidate_limit)
        for detail in duplicate_groups:
            if len({rows[k].split for k in detail['image_ids'] if rows[k].included}) > 1:
                issues.add('error', 'confirmed_cross_effective_split_duplicate', **detail)
        after = source_checks(csv_root, baseline)
        if before != after:
            issues.add('error', 'source_csv_changed_during_audit')
        class_images = defaultdict(Counter)
        sample_class_images = defaultdict(Counter)
        for item in rows.values():
            if item.included:
                for t in range(67):
                    if item.classes & (1 << t):
                        class_images[item.split][t] += 1
                        if item.id in decoded:
                            sample_class_images[item.split][t] += 1
        expected_counts = dict(train=161247, valid=787, test=404, review=8493, excluded=688)
        if dict(split_counts) != expected_counts or sum(annotation_counts.values()) != 838716:
            issues.add('error', 'baseline_manifest_count_mismatch')
        report = dict(task='ML-01', report_version=1, generated_at=datetime.now(timezone.utc).isoformat(),
                      status='failed' if issues.errors else 'passed_with_review',
                      csv_root=str(csv_root), vision_root=str(vision_root), baseline_version=baseline['baseline_version'],
                      class_map_sha256=hashlib.sha256(IDENTITY.read_bytes()).hexdigest(), source_integrity=after,
                      inventory=dict(image_tree_files=len(image_files), label_tree_files=len(label_files), image_bytes=sum(f.size for f in image_files.values())),
                      manifests=dict(images=len(rows), included_images=sum(r.included for r in rows.values()), original_splits=dict(original_counts),
                                     effective_splits=dict(split_counts), background_images=dict(backgrounds), food_boxes=dict(annotation_counts),
                                     removed_face_boxes=sum(r.face_boxes for r in rows.values()), exclusion_reasons=dict(Counter(r.reason for r in rows.values() if r.reason))),
                      labels=dict(preferred_labels_parsed=totals['files_parsed'], physical_label_copies_hashed=totals['files_hashed']),
                      per_class=[dict(training_class_id=t, original_class_id=o, slug=s,
                                      images={split:class_images[split][t] for split in ('train','valid','test','review')},
                                      boxes={split:coverage[split][t] for split in ('train','valid','test','review')}) for t,o,s in sorted(source_classes)],
                      source_group_overlap=overlap,
                      decode=dict(selection='lowest SHA256(image_id), per effective split plus class/status/reason representatives',
                                  base_per_split=per_split, selected=len(selected), completed=len(decoded),
                                  by_split=dict(Counter(rows[k].split for k in decoded)), classes_covered={s:sorted(v) for s,v in sample_class_images.items()},
                                  images=[dict(image_id=k, **decoded[k]) for k in sorted(decoded)]),
                      image_hashing=dict(sha256_images=len(hashed), crc32_images=len(hashed), candidate_groups=len(candidates), candidate_images=len(candidate_ids),
                                         candidate_limit=candidate_limit, candidate_images_hashed=len(targeted & hashed.keys()),
                                         verified_duplicate_groups=duplicate_groups),
                      issues=dict(errors=issues.errors, counts=dict(issues.counts), examples=issues.examples, detail_file=str(issue_path)),
                      not_checked=['Full image decode/SHA256/pixel-duplicate or perceptual hashing', 'Visual semantic label accuracy and provenance proof',
                                   'Independent holdout coverage for all 67 classes', 'Training/model weights/inference/accuracy/latency', 'Nutrition approval/mobile/cloud'])
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(f"ML-01: {report['status']}; {issues.errors} errors; decoded {len(decoded)}/{len(rows)} images. Report saved locally.", flush=True)
        return 1 if issues.errors else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--decode-per-split', type=int, default=128)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--hash-candidate-limit', type=int, default=2048)
    args = parser.parse_args(argv)
    if not 1 <= args.decode_per_split <= 10000 or not 1 <= args.workers <= 8 or not 0 <= args.hash_candidate_limit <= 100000:
        parser.error('Invalid audit sample/worker/hash limits')
    try:
        return run(args.config, args.report, args.decode_per_split, args.workers, args.hash_candidate_limit)
    except (OSError, ValueError, KeyError, TypeError, csv.Error):
        print('ML-01 audit could not complete; check input paths/baseline/config. No sources changed.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
