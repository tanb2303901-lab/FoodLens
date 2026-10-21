"""Derive candidate detection regions from verified FoodSeg semantic masks.

Connected regions are not native instance annotations. Sources stay unchanged;
these candidates require visual QA and a documented annotation policy before
becoming part of the ML-05 training export.
"""
from collections import Counter
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/processed/food-extension-v2'
TARGET = {13: 73, 25: 68, 29: 67, 40: 72}
# Exact ingredient/category matches only. Ambiguous meat/cheese/pepper labels
# must not silently become FoodLens fine-grained labels.
OTHER = {3: 37, 24: 55, 37: 24, 53: 28, 56: 54, 60: 33, 66: 25, 68: 29,
         73: 18, 80: 47, 82: 31, 84: 20, 87: 10, 89: 47, 91: 47,
         97: 42, 98: 42, 99: 42, 100: 42, 101: 42, 102: 48}
AMBIGUOUS = {9, 46, 47, 48, 50, 51, 54, 55, 65, 94}


def main():
    if not (OUT / 'foodseg-source-download.json').is_file():
        raise ValueError('All source parquet hashes must be verified before extraction')
    meta = json.loads((OUT / 'source-metadata/hf-foodseg-tree.json').read_text())
    expected = {Path(e['path']).name: e['lfs']['oid'] for e in meta if e.get('path', '').endswith('.parquet')}
    records, excluded = [], []
    directory = OUT / 'native-regions'
    (directory / 'images').mkdir(parents=True, exist_ok=True)
    for name, digest in expected.items():
        path = OUT / 'sources/foodseg103' / name
        if sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Source parquet checksum changed')
        native_split = 'holdout' if name.startswith('validation') else 'train'
        selected = pl.scan_parquet(path).filter(pl.any_horizontal([
            pl.col('classes_on_image').list.contains(c) for c in TARGET])).collect()
        for row in selected.iter_rows(named=True):
            key = 'foodseg103-' + native_split + '-' + str(row['id'])
            classes = set(row['classes_on_image'])
            if classes & AMBIGUOUS:
                excluded.append(dict(source_id=key, reason='ambiguous_existing_food_labels', source_classes=sorted(classes & AMBIGUOUS)))
                continue
            image_bytes, mask_bytes = row['image']['bytes'], row['label']['bytes']
            with Image.open(BytesIO(image_bytes)) as raw:
                if raw.getexif().get(274, 1) != 1:
                    excluded.append(dict(source_id=key, reason='orientation_needs_mask_review'))
                    continue
                rgb = raw.convert('RGB')
            with Image.open(BytesIO(mask_bytes)) as raw_mask:
                mask = np.array(raw_mask)
            if mask.ndim != 2 or mask.shape != (rgb.height, rgb.width) or int(mask.max()) > 103:
                raise ValueError('Mask dimensions/label IDs do not match source image')
            boxes = []
            for source_class in sorted(set(np.unique(mask)) & set(TARGET | OTHER)):
                label = (TARGET | OTHER)[source_class]
                binary = np.ascontiguousarray(mask == source_class, dtype=np.uint8)
                count, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
                for x, y, width, height, area in stats[1:]:
                    if area < max(32, rgb.width * rgb.height * .0005) or min(width, height) < 4:
                        continue
                    boxes.append(dict(training_class_id=label,
                        bbox_xyxy_norm=[x / rgb.width, y / rgb.height, (x + width) / rgb.width, (y + height) / rgb.height],
                        source_mask_class_id=int(source_class), source_mask_region_area_pixels=int(area)))
            present = sorted({b['training_class_id'] for b in boxes if b['training_class_id'] >= 67})
            if not present:
                excluded.append(dict(source_id=key, reason='no_target_region_above_minimum_size'))
                continue
            destination = directory / 'images' / (key + '.jpg')
            if not destination.exists():
                rgb.save(destination, format='JPEG', quality=95)
            records.append(dict(source_id=key, source='foodseg103', native_split=native_split,
                source_parquet=name, source_parquet_sha256=digest, source_original_id=row['id'],
                source_image_sha256=sha256(image_bytes).hexdigest(), source_mask_sha256=sha256(mask_bytes).hexdigest(),
                image_path=str(destination.relative_to(OUT)), image_sha256=sha256(destination.read_bytes()).hexdigest(),
                image_size=[rgb.width, rgb.height], target_classes=present, boxes=boxes,
                annotation_status='semantic_mask_regions_geometry_checked_pending_visual_qa',
                annotation_unit='connected_semantic_region_not_native_instance_box'))
        print('Mask-derived candidate regions extracted: ' + name, flush=True)
    (directory / 'candidates.json').write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (directory / 'excluded.json').write_text(json.dumps(excluded, indent=2) + '\n', encoding='utf-8')
    summary = Counter((r['native_split'], c) for r in records for c in r['target_classes'])
    print('Candidate image counts: ' + json.dumps({str(k): v for k, v in sorted(summary.items())}), flush=True)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 14)
    sheets = directory / 'review-sheets'
    sheets.mkdir(exist_ok=True)
    index = []
    # Deterministic QA examples from each target/split, independent of model scores.
    chosen = {}
    for split in ('train', 'holdout'):
        for c in TARGET.values():
            subset = sorted((r for r in records if r['native_split'] == split and c in r['target_classes']),
                            key=lambda r: r['source_image_sha256'])
            for r in subset[:6]:
                chosen[r['source_id']] = r
    examples = list(chosen.values())
    for offset in range(0, len(examples), 16):
        canvas = Image.new('RGB', (1120, 1280), 'white')
        draw = ImageDraw.Draw(canvas)
        for j, row in enumerate(examples[offset:offset + 16]):
            image = Image.open(OUT / row['image_path']).convert('RGB')
            image.thumbnail((270, 250))
            x, y = (j % 4) * 280, (j // 4) * 320
            canvas.paste(image, (x, y + 42))
            draw.text((x + 3, y + 3), row['source_id'][:34], font=font, fill='black')
            draw.text((x + 3, y + 20), str(row['target_classes']) + ' regions=' + str(len(row['boxes'])), font=font, fill='black')
            for b in row['boxes']:
                l, t, r, bottom = b['bbox_xyxy_norm']
                draw.rectangle((x + l * image.width, y + 42 + t * image.height, x + r * image.width, y + 42 + bottom * image.height),
                               outline='red' if b['training_class_id'] >= 67 else 'green', width=2)
            index.append(dict(sheet=offset // 16, tile=j, source_id=row['source_id']))
        canvas.save(sheets / ('native-' + str(offset // 16).zfill(3) + '.jpg'), quality=92)
    (sheets / 'index.json').write_text(json.dumps(index, indent=2) + '\n')
    print('Native-mask visual QA sheets ready; no training export created.', flush=True)


if __name__ == '__main__':
    main()
