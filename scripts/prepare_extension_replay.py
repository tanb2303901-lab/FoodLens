"""Select legacy replay without silently relabeling coarse chicken/fish/meat.

Uses the trusted, locally generated Ultralytics cache, never an untrusted pickle.
Potentially overlapping parent classes are isolated for explicit visual review.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/processed/food-extension-v2'
PARENTS = {17, 50, 53}  # Cá, Thịt gà, Thịt nướng; 51 is Thịt heo.


def main():
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    source = ROOT / 'data/processed/vision-yolo-v1'
    export = json.loads((source / 'export.json').read_text())
    if export['status'] != 'completed' or export['images']['train'] != 161247 or export['source_mutated']:
        raise ValueError('Trusted legacy training export required')
    cache = np.load(source / 'labels/train.cache', allow_pickle=True).item()
    labels = cache['labels']
    if len(labels) != 161247:
        raise ValueError('Unexpected legacy cache size')
    ordered = sorted(enumerate(labels), key=lambda pair: hashlib.sha256(Path(pair[1]['im_file']).name.encode()).digest())
    chosen, counts = {}, {i: 0 for i in range(67)}
    for index, row in ordered:
        classes = {int(c) for c in row['cls'].reshape(-1)}
        if classes & PARENTS or not classes or not any(counts[c] < 100 for c in classes):
            continue
        if not Path(row['im_file']).resolve().is_relative_to((source / 'images/train').resolve()):
            raise ValueError('Replay must come only from original train')
        chosen[index] = dict(image_path=row['im_file'], boxes=[dict(training_class_id=int(c), bbox_xywh_norm=b.tolist())
            for c, b in zip(row['cls'].reshape(-1), row['bboxes'])])
        for c in classes:
            counts[c] += 1
    candidates = []
    for c in sorted(PARENTS):
        groups = set()
        for index, row in ordered:
            if c not in set(row['cls'].reshape(-1).astype(int)):
                continue
            # Roboflow augmented siblings share the source stem; avoid selecting
            # all variants of a single photo for this small review sample.
            stem = Path(row['im_file']).stem.split('.rf.')[0]
            if stem in groups:
                continue
            k = next(k for k, v in enumerate(row['cls'].reshape(-1)) if int(v) == c)
            groups.add(stem)
            candidates.append(dict(index=len(candidates), cache_index=index, image_path=row['im_file'],
                training_class_id=c, bbox_xywh_norm=row['bboxes'][k].tolist(), source_group=stem))
            if len(groups) == 32:
                break
    destination = OUT / 'legacy-replay-review-v2'
    destination.mkdir(exist_ok=False)
    (destination / 'selected-nonparent.json').write_text(json.dumps(dict(counts=counts, images=list(chosen.values())), indent=2))
    (destination / 'parent-candidates.json').write_text(json.dumps(candidates, indent=2))
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 14)
    for offset in range(0, len(candidates), 16):
        canvas = Image.new('RGB', (1120, 1280), 'white'); draw = ImageDraw.Draw(canvas)
        for j, row in enumerate(candidates[offset:offset + 16]):
            with Image.open(row['image_path']) as raw:
                image = raw.convert('RGB')
            x, y, w, h = row['bbox_xywh_norm']
            crop = image.crop((max(0, int((x - w / 2) * image.width)), max(0, int((y - h / 2) * image.height)),
                min(image.width, int((x + w / 2) * image.width) + 1), min(image.height, int((y + h / 2) * image.height) + 1)))
            crop.thumbnail((270, 250)); left, top = j % 4 * 280, j // 4 * 320
            canvas.paste(crop, (left, top + 42))
            draw.text((left + 3, top + 3), str(row['index']) + ' legacy class ' + str(row['training_class_id']), fill='black', font=font)
        canvas.save(destination / ('parents-' + str(offset // 16).zfill(3) + '.jpg'), quality=92)
    print('Nonparent replay images:', len(chosen), '; overlapping-parent crop candidates:', len(candidates))


if __name__ == '__main__':
    main()
