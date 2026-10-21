"""Copy an audited immutable source into an isolated 67-class YOLO dataset.

Copies, never links, images so detector-library caches/repairs cannot mutate the
source. Review/excluded images never enter train/val/test. JSON is valid YAML.
"""
from concurrent.futures import ThreadPoolExecutor
import argparse
from collections import Counter, defaultdict
import hashlib
from itertools import islice
import json
from pathlib import Path
import sys
import zlib

if __package__:
    from .audit_vision import BASELINE, IDENTITY, PROCESSED, Issues, box, csv_rows, load_images, source_checks, training_id
else:
    from audit_vision import BASELINE, IDENTITY, PROCESSED, Issues, box, csv_rows, load_images, source_checks, training_id


def safe_output(path, source_roots):
    path = path.resolve()
    if not path.is_relative_to(PROCESSED.resolve()) or path == PROCESSED.resolve():
        raise ValueError('Dataset output must be a child of ignored data/processed')
    if any(path.is_relative_to(root.resolve()) or root.resolve().is_relative_to(path) for root in source_roots):
        raise ValueError('Derived dataset must be disjoint from source roots')
    if path.exists():
        raise ValueError('Use a new output directory; existing data is preserved')
    return path


def export_label(row, image):
    original, t = int(row['original_class_id']), int(row['training_class_id'])
    if training_id(original) != t or row['split'] != image.split or row['image_id'] != image.id or not image.included:
        raise ValueError('Annotation identity/class/split mismatch')
    coords = box([row[k] for k in ('x_center_norm', 'y_center_norm', 'width_norm', 'height_norm')])
    return str(t) + ' ' + ' '.join(format(v, '.17g') for v in coords) + '\n'


def copy_image(item, source_root, target):
    source = source_root / item.image_rel
    if not source.resolve().is_relative_to(source_root.resolve()) or source.is_symlink():
        raise ValueError('Source escapes vision root')
    before = source.stat()
    if before.st_size != item.image_bytes:
        raise ValueError('Source image size changed')
    sha, crc, size = hashlib.sha256(), 0, 0
    temporary = target.with_suffix('.jpg.partial')
    with source.open('rb') as reader, temporary.open('xb') as writer:
        for content in iter(lambda: reader.read(1024*1024), b''):
            writer.write(content)
            sha.update(content)
            crc = zlib.crc32(content, crc)
            size += len(content)
    after = source.stat()
    if size != item.image_bytes or crc & 0xffffffff != item.crc or (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise ValueError('Copied source bytes/CRC/stability mismatch')
    temporary.replace(target)
    return dict(image_id=item.id, split=item.split, target=target.as_posix(), bytes=size, sha256=sha.hexdigest())


def export(config_path, audit_path, output, workers=4):
    config = json.loads(config_path.read_text(encoding='utf-8-sig'))
    csv_root, source_root = (Path(config[k]).resolve() for k in ('csv_root','vision_root'))
    output = safe_output(output, (csv_root,source_root))
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
    identity = json.loads(IDENTITY.read_text(encoding='utf-8'))
    checks = source_checks(csv_root, baseline)
    if audit['status'] != 'passed_with_review' or audit['issues']['errors'] or audit['source_integrity'] != checks:
        raise ValueError('Successful current audit is required')
    if Path(audit['vision_root']).resolve()!=source_root or audit['class_map_sha256']!=hashlib.sha256(IDENTITY.read_bytes()).hexdigest():
        raise ValueError('Audit root/class map mismatch')
    output.mkdir(parents=True)
    columns={e['name']:e['columns'] for e in baseline['files']}
    with (output/'issues.jsonl').open('w',encoding='utf-8') as stream:
        issues=Issues(stream)
        rows=load_images(csv_root,columns['foodlens_images.csv'],issues)
        if issues.errors: raise ValueError('Invalid image manifest')
    selected={key:item for key,item in rows.items() if item.split in ('train','valid','test')}
    labels=defaultdict(list)
    class_boxes=defaultdict(Counter)
    for _,row in csv_rows(csv_root/'foodlens_dataset.csv',columns['foodlens_dataset.csv']):
        key=row['image_id']
        if key in selected:
            labels[key].append(export_label(row,selected[key]))
            class_boxes[selected[key].split][int(row['training_class_id'])]+=1
    if set(class_boxes['train'])!=set(range(67)):
        raise ValueError('Training split does not cover all 67 classes')
    split_map={'train':'train','valid':'val','test':'test'}
    destinations={}
    for split in split_map.values():
        for kind in ('images','labels'):
            (output/kind/split).mkdir(parents=True)
    for key,item in selected.items():
        lines=labels.pop(key,[])
        if len(lines)!=item.food_boxes:
            raise ValueError('Export label count mismatch')
        name=key.replace('/','__')
        split=split_map[item.split]
        (output/'labels'/split/(name+'.txt')).write_text(''.join(lines),encoding='utf-8')
        destinations[key]=output/'images'/split/(name+'.jpg')
    del labels
    ids=iter(sorted(selected))
    counts=Counter()
    total_bytes=0
    digest=hashlib.sha256()
    with (output/'copied-images.jsonl').open('w',encoding='utf-8') as evidence, ThreadPoolExecutor(max_workers=workers) as pool:
        done=0
        while batch:=list(islice(ids,512)):
            results=pool.map(lambda key:copy_image(selected[key],source_root,destinations[key]),batch)
            for record in results:
                text=json.dumps(record,sort_keys=True)
                evidence.write(text+'\n');digest.update((text+'\n').encode())
                counts[record['split']]+=1;total_bytes+=record['bytes']
            done+=len(batch)
            if done%10240==0 or done==len(selected):
                print(f'ML-02: copied and CRC-verified {done}/{len(selected)} images',flush=True)
                (output/'progress.json').write_text(json.dumps(dict(stage='copying',completed=done,total=len(selected)))+'\n',encoding='utf-8')
    after=source_checks(csv_root,baseline)
    if checks!=after: raise ValueError('Source CSV changed during export')
    data=dict(path=output.as_posix(),train='images/train',val='images/val',test='images/test',
              names=[food['name_vi'] for food in sorted(identity['foods'],key=lambda r:r['training_class_id'])],nc=67)
    (output/'dataset.yaml').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'food-identities-v1.json').write_bytes(IDENTITY.read_bytes())
    report=dict(status='completed',images=dict(counts),image_bytes=total_bytes,source_integrity=after,
                source_vision_root=str(source_root),class_map_sha256=hashlib.sha256(IDENTITY.read_bytes()).hexdigest(),
                copied_images_evidence_sha256=digest.hexdigest(),source_mutated=False,method='byte copy + full CRC32/SHA256, remapped labels from validated CSV',
                boxes={s:sum(c.values()) for s,c in class_boxes.items()},classes={s:sorted(c) for s,c in class_boxes.items()},
                excluded_from_export=['review','excluded'],not_checked=['Full pixel decode/perceptual duplicates','Semantic annotation accuracy','Full 67-class independent holdout'])
    (output/'export.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('ML-02: dataset export completed; original images/labels preserved.',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--audit',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workers',type=int,default=4)
    args=p.parse_args()
    if not 1<=args.workers<=8:p.error('workers must be 1..8')
    try:export(args.config,args.audit,args.output,args.workers)
    except (ValueError,OSError,KeyError):
        print('ML-02 export failed; partial derived files retained for diagnosis; sources unchanged.',file=sys.stderr)
        raise SystemExit(1)
