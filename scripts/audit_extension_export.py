"""Verify the concrete ML-05 export before any training is dispatched."""
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def audit(dataset):
    from PIL import Image
    from ml.train_extension import accepted_export
    from ml.runtime import write_json
    export=accepted_export(dataset)
    manifest=json.loads((dataset/'manifest.json').read_text(encoding='utf-8'))
    listed={}
    classes={}
    for split in ('train','valid','test','legacy_valid','legacy_test','extension_valid','extension_test'):
        paths=[Path(line) for line in (dataset/(split+'.txt')).read_text(encoding='utf-8').splitlines() if line]
        if not paths or any(not p.resolve().is_relative_to(dataset.resolve()) for p in paths):raise ValueError('Dataset list escaped export or is empty')
        if split!='train' and len(set(paths))!=len(paths):raise ValueError('Repeated holdout path')
        listed[split]=set(paths);counts=Counter()
        for path in set(paths):
            label=path.parent.parent.parent/'labels'/path.parent.name/(path.stem+'.txt')
            with Image.open(path) as image:image.load()
            for line in label.read_text().splitlines():
                values=line.split()
                if len(values)!=5:raise ValueError('Invalid YOLO row')
                c=int(values[0]);x,y,w,h=map(float,values[1:])
                if not 0<=c<75 or not all(math.isfinite(v) for v in (x,y,w,h)) or min(w,h)<=0 or min(x-w/2,y-h/2)<-2e-7 or max(x+w/2,y+h/2)>1+2e-7:
                    raise ValueError('Invalid normalized label')
                counts[c]+=1
        classes[split]=sorted(counts)
    if any(listed[a]&listed[b] for a,b in (('train','valid'),('train','test'),('valid','test'))):raise ValueError('Export path leakage')
    if classes['train']!=list(range(75)) or classes['extension_valid']!=list(range(67,75)) or classes['extension_test']!=list(range(67,75)):
        raise ValueError('Missing training/new holdout class')
    if len(listed['legacy_valid'])!=787 or len(listed['legacy_test'])!=404 or len(classes['legacy_valid'])!=35 or len(classes['legacy_test'])!=29:
        raise ValueError('Legacy holdout coverage differs from accepted baseline')
    groups=defaultdict(set);sources=defaultdict(set)
    for row in manifest:
        groups[row['source_group']].add(row['split']);sources[row['source_id']].add(row['split'])
        path=dataset/row['image_path'];label=path.parent.parent.parent/'labels'/path.parent.name/(path.stem+'.txt')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=row['image_sha256'] or hashlib.sha256(label.read_bytes()).hexdigest()!=row['label_sha256']:
            raise ValueError('Image/label manifest checksum mismatch')
    if any(len(s)>1 for s in groups.values()) or any(len(s)>1 for s in sources.values()):raise ValueError('New source/group partition leakage')
    for split,oldsplit in (('valid','val'),('test','test')):
        for path in listed['legacy_'+split]:
            source=ROOT/'data/processed/vision-yolo-v1/images'/oldsplit/path.name.removeprefix('legacy-')
            source_label=source.parent.parent.parent/'labels'/oldsplit/(source.stem+'.txt')
            label=path.parent.parent.parent/'labels'/split/(path.stem+'.txt')
            if path.read_bytes()!=source.read_bytes() or label.read_bytes()!=source_label.read_bytes():raise ValueError('Legacy holdout copy differs')
    report=dict(status='passed',export_sha256=hashlib.sha256((dataset/'export.json').read_bytes()).hexdigest(),
        unique_images={s:len(listed[s]) for s in ('train','valid','test')},classes=classes,
        image_and_label_hashes_verified=len(manifest),legacy_holdout_copies_verified=1191,
        new_source_groups_disjoint=True,new_source_photos_disjoint=True,
        independent_human_annotation_review=False,full_scene_new_class_acceptance=False)
    write_json(dataset/'preflight.json',report)
    print(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    import argparse,sys
    sys.path.insert(0,str(ROOT))
    parser=argparse.ArgumentParser();parser.add_argument('--dataset',type=Path,required=True)
    audit(parser.parse_args().dataset.resolve())
