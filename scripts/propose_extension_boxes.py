"""Assist ML-05 annotation; outputs are unreviewed proposals, never ground truth."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/processed/food-extension-v2'
MODEL = OUT / 'annotation-model'


def review_boxes(boxes):
    selected = []
    def area(box):
        return max(0, box[2] - box[0]) * max(0, box[3] - box[1])
    for index, item in sorted(enumerate(boxes), key=lambda pair: -pair[1]['proposal_score']):
        box = item['bbox_xyxy_norm']
        if area(box) < .004:
            continue
        duplicate = False
        for other in selected:
            b = other['bbox_xyxy_norm']
            intersection = max(0, min(box[2], b[2]) - max(box[0], b[0])) * max(0, min(box[3], b[3]) - max(box[1], b[1]))
            union = area(box) + area(b) - intersection
            if intersection / max(union, 1e-12) > .7 or intersection / max(min(area(box), area(b)), 1e-12) > .92:
                duplicate = True
                break
        if not duplicate:
            selected.append(dict(item, original_proposal_index=index))
    return selected


def prepare_model():
    sys.path.insert(0, str(ROOT / 'scripts'))
    from collect_extension_sources import fetch, write_json, UA
    info_url = 'https://huggingface.co/api/models/IDEA-Research/grounding-dino-tiny'
    with urlopen(Request(info_url, headers={'User-Agent': UA}), timeout=35) as response:
        info = json.load(response)
    revision = info['sha']
    tree_url = 'https://huggingface.co/api/models/IDEA-Research/grounding-dino-tiny/tree/' + revision + '?recursive=true'
    with urlopen(Request(tree_url, headers={'User-Agent': UA}), timeout=35) as response:
        tree = json.load(response)
    names = {'config.json', 'preprocessor_config.json', 'processor_config.json', 'tokenizer_config.json',
             'tokenizer.json', 'vocab.txt', 'special_tokens_map.json', 'model.safetensors', 'README.md'}
    source = []
    for entry in tree:
        name = entry.get('path')
        if name not in names or entry.get('type') != 'file':
            continue
        expected = entry.get('lfs', {}).get('oid')
        if name == 'model.safetensors' and not expected:
            raise ValueError('Official safe weights SHA required')
        fetch('https://huggingface.co/IDEA-Research/grounding-dino-tiny/resolve/' + revision + '/' + name,
              MODEL / name, expected, entry.get('size'))
        source.append(dict(file=name, sha256=hashlib.sha256((MODEL / name).read_bytes()).hexdigest()))
        print('Annotation model artifact ready: ' + name, flush=True)
    if not (MODEL / 'model.safetensors').exists():
        raise ValueError('No safe annotation model downloaded')
    write_json(MODEL / 'source.json', dict(model='IDEA-Research/grounding-dino-tiny', revision=revision,
        purpose='local bbox proposals only; not application model or accepted labels', files=source))


def propose():
    from PIL import Image, ImageOps
    import torch
    from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection, AutoConfig
    torch.set_num_threads(4)
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    processor = AutoProcessor.from_pretrained(str(MODEL), local_files_only=True, trust_remote_code=False, use_fast=False)
    config = AutoConfig.from_pretrained(str(MODEL), local_files_only=True, trust_remote_code=False)
    config.disable_custom_kernels = True
    model = AutoModelForZeroShotObjectDetection.from_pretrained(str(MODEL), config=config,
        local_files_only=True, trust_remote_code=False, use_safetensors=True).to('cuda').eval()
    prompts = {'grilled_chicken_breast': 'grilled chicken. roasted chicken.', 'grilled_salmon': 'cooked salmon fillet.',
               'soft_drink': 'soda bottle. soda can. glass of soda.', 'sweet_potato': 'sweet potato.',
               'coffee': 'cup of coffee. glass of coffee.'}
    records = json.loads((OUT / 'commons-candidates.json').read_text(encoding='utf-8'))
    if (OUT / 'ffml-candidates.json').exists():
        records.extend(json.loads((OUT / 'ffml-candidates.json').read_text(encoding='utf-8')))
    destination = OUT / 'box-proposals'
    destination.mkdir(exist_ok=True)
    for index, record in enumerate(records):
        if record.get('download_status') != 'downloaded':
            continue
        slug, sid = record['candidate_class'], record['source_id']
        target = destination / (slug + '-' + sid + '.json')
        if target.exists():
            continue
        path = OUT / record['local_path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
            raise ValueError('Downloaded source changed')
        try:
            with Image.open(path) as raw:
                if raw.width * raw.height > 20_000_000:
                    raise ValueError('Source image exceeds safe limits')
                image = ImageOps.exif_transpose(raw).convert('RGB')
        except (OSError, ValueError):
            target.write_text(json.dumps(dict(source_id=sid, candidate_class=slug,
                source_path=record['local_path'], source_sha256=record['sha256'], boxes=[],
                annotation_status='rejected_source_decode_failed'), indent=2) + '\n')
            continue
        inputs = processor(images=image, text=prompts[slug], return_tensors='pt').to('cuda')
        with torch.inference_mode():
            outputs = model(**inputs)
        detections = processor.post_process_grounded_object_detection(outputs, inputs.input_ids, threshold=.25,
            text_threshold=.25, target_sizes=[(image.height, image.width)])[0]
        boxes = []
        labels = detections.get('text_labels', detections.get('labels', []))
        for coords, score, label in zip(detections['boxes'].tolist(), detections['scores'].tolist(), labels):
            x1, y1, x2, y2 = coords
            box = [max(0, min(1, x1 / image.width)), max(0, min(1, y1 / image.height)),
                   max(0, min(1, x2 / image.width)), max(0, min(1, y2 / image.height))]
            if box[0] < box[2] and box[1] < box[3]:
                boxes.append(dict(bbox_xyxy_norm=box, proposal_score=score, proposal_text=str(label)))
        value = dict(source_id=sid, candidate_class=slug, source_sha256=record['sha256'], source_path=record['local_path'],
            source_title=record['title'], canonical_size=[image.width, image.height], boxes=boxes,
            annotation_status='unreviewed_model_proposals_not_ground_truth', annotation_model='IDEA-Research/grounding-dino-tiny',
            created_at=datetime.now(timezone.utc).isoformat())
        target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        if index % 20 == 0:
            print('Annotation proposals written: ' + str(len(list(destination.glob('*.json')))), flush=True)


def sheets(directory_name='review-sheets', only_unreviewed=False):
    from PIL import Image, ImageOps, ImageDraw, ImageFont
    records = []
    decisions_path = OUT / 'source-review-decisions.json'
    decisions = json.loads(decisions_path.read_text(encoding='utf-8')) if decisions_path.exists() else {}
    for path in sorted((OUT / 'box-proposals').glob('*.json')):
        if only_unreviewed and path.name in decisions:
            continue
        item = json.loads(path.read_text(encoding='utf-8'))
        if item.get('annotation_status', '').startswith('rejected_'):
            continue
        item['boxes'] = review_boxes(item['boxes'])
        item['proposal_file'] = path.name
        records.append(item)
    sheet_dir = OUT / directory_name
    if sheet_dir.resolve().parent != OUT.resolve() or sheet_dir.exists():
        raise ValueError('Use a new review sheet directory; preserve existing visual-review evidence')
    sheet_dir.mkdir(exist_ok=True)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 14)
    manifest = []
    for start in range(0, len(records), 16):
        sheet = Image.new('RGB', (1120, 1280), 'white')
        draw = ImageDraw.Draw(sheet)
        items = []
        for position, item in enumerate(records[start:start + 16]):
            with Image.open(OUT / item['source_path']) as raw:
                image = ImageOps.exif_transpose(raw).convert('RGB')
            image.thumbnail((270, 250))
            x, y = (position % 4) * 280, (position // 4) * 320
            sheet.paste(image, (x, y + 42))
            draw.text((x + 3, y + 3), str(start + position) + ' ' + item['candidate_class'][:24], fill='black', font=font)
            draw.text((x + 3, y + 21), item['source_id'] + ' | proposals=' + str(len(item['boxes'])), fill='black', font=font)
            for k, b in enumerate(item['boxes']):
                l, t, r, bottom = b['bbox_xyxy_norm']
                coords = (x + l * image.width, y + 42 + t * image.height, x + r * image.width, y + 42 + bottom * image.height)
                draw.rectangle(coords, outline=['red', 'blue', 'green', 'orange'][k % 4], width=2)
                draw.text((coords[0], coords[1]), str(k), fill='red', font=font)
            items.append(dict(index=start + position, proposal_file=item['proposal_file'], source_id=item['source_id'], candidate_class=item['candidate_class']))
        name = 'review-' + str(start // 16).zfill(3) + '.jpg'
        sheet.save(sheet_dir / name, quality=92)
        manifest.append(dict(sheet=name, items=items))
    (sheet_dir / 'index.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (sheet_dir / 'review-candidates.json').write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Review sheets prepared: ' + str(len(manifest)) + '; no labels approved automatically.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['download', 'propose', 'sheets'])
    parser.add_argument('--review-directory', default='review-sheets')
    parser.add_argument('--only-unreviewed', action='store_true')
    args = parser.parse_args()
    if args.stage == 'sheets':
        sheets(args.review_directory, args.only_unreviewed)
    else:
        {'download': prepare_model, 'propose': propose}[args.stage]()
