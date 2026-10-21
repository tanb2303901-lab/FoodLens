"""Build a separate ML-05 export from reviewed regions and legacy replay.

New-class holdout uses object/food-region crops, not exhaustive full-scene
annotations. Metrics on these crops must never be described as phone/full-scene
acceptance. No source file is modified, including the legacy derived export.
"""
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/processed/food-extension-v2'
SLUGS = {'grilled_chicken_breast': 69, 'grilled_salmon': 70, 'sweet_potato': 71, 'coffee': 73, 'soft_drink': 74}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def phash(image):
    import cv2
    import numpy as np
    values = cv2.dct(np.asarray(image.convert('L').resize((32, 32)), dtype=np.float32))[:8, :8].reshape(-1)
    median = np.median(values[1:])
    return sum(int(v > median) << i for i, v in enumerate(values))


def xyxy(box):
    x, y, w, h = box
    return [max(0., x-w/2), max(0., y-h/2), min(1., x+w/2), min(1., y+h/2)]


def crop_region(image, box, context=.08):
    """Faithfully transform a reviewed box to a bounded crop, no guessed box."""
    if len(box) != 4 or not all(math.isfinite(v) and 0 <= v <= 1 for v in box) or not (box[0] < box[2] and box[1] < box[3]):
        raise ValueError('Invalid normalized reviewed region')
    w, h = image.size
    l, t, r, b = [box[0]*w, box[1]*h, box[2]*w, box[3]*h]
    bounds = (max(0, math.floor(l-(r-l)*context)), max(0, math.floor(t-(b-t)*context)),
              min(w, math.ceil(r+(r-l)*context)), min(h, math.ceil(b+(b-t)*context)))
    if min(bounds[2]-bounds[0], bounds[3]-bounds[1]) < 12:
        raise ValueError('Region too small for this export')
    out = image.crop(bounds)
    new = [(l-bounds[0])/out.width, (t-bounds[1])/out.height, (r-bounds[0])/out.width, (b-bounds[1])/out.height]
    return out, new, bounds


def yolo_line(c, box):
    l, t, r, b = box
    return f'{c} {(l+r)/2:.9f} {(t+b)/2:.9f} {r-l:.9f} {b-t:.9f}\n'


def public_regions():
    decisions = json.loads((OUT/'source-review-decisions.json').read_text(encoding='utf-8'))
    sources = json.loads((OUT/'commons-candidates.json').read_text(encoding='utf-8')) + json.loads((OUT/'ffml-candidates.json').read_text(encoding='utf-8'))
    lookup = {(r['candidate_class'], str(r['source_id'])): r for r in sources}
    regions = []
    for directory in ('review-sheets', 'review-sheets-v2'):
        for r in json.loads((OUT/directory/'review-candidates.json').read_text(encoding='utf-8')):
            review = decisions.get(r['proposal_file'])
            if not review or review['decision'] != 'accepted_boxes':
                continue
            snapshot = hashlib.sha256(json.dumps(r, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if snapshot != review['proposal_snapshot_sha256'] or digest(OUT/directory/f"review-{review['review_sheet']:03d}.jpg") != review['review_sheet_sha256']:
                raise ValueError('Visual review snapshot changed')
            source = lookup[(r['candidate_class'], r['source_id'])]
            path = OUT/r['source_path']
            if digest(path) != r['source_sha256']:
                raise ValueError('Public source hash changed')
            day = re.search(r'\d{4}-\d\d-\d\d', source.get('datetime_original') or '')
            # Missing capture date: group all photos from this creator, avoiding
            # optimistic split independence for an unrecorded photo session.
            group = source.get('source_group') or 'commons:' + str(source.get('artist')) + ':' + (day.group() if day else 'unknown-session')
            regions.append(dict(source_id=source['source']+'-'+r['source_id'], path=str(path), image_sha256=r['source_sha256'],
                source_group=group, forced_split=source.get('forced_split'), source='public_reviewed',
                boxes=[dict(training_class_id=SLUGS[r['candidate_class']], bbox_xyxy_norm=r['boxes'][i]['bbox_xyxy_norm']) for i in review['selected_box_indices']],
                review_file=r['proposal_file'], review_directory=directory, provenance=source,
                annotation_unit='visually_reviewed_food_region_not_independent_human_annotation'))
    for r in json.loads((OUT/'native-regions/candidates.json').read_text(encoding='utf-8')):
        boxes = [b for b in r['boxes'] if b['training_class_id'] in {67,68,72}]
        if not boxes:
            continue
        regions.append(dict(source_id=r['source_id'], path=str(OUT/r['image_path']), image_sha256=r['image_sha256'],
            source_group=r['source_image_sha256'], forced_split=r['native_split'], source='foodseg103', boxes=boxes,
            provenance=r, annotation_unit='source_human_semantic_mask_connected_region_geometry_validated_sample_visual_qa'))
    return regions


def assign_splits(records):
    """One partition per source/session and near-duplicate connected component."""
    from PIL import Image, ImageOps
    parent = list(range(len(records)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    def union(i,j):
        parent[find(j)] = find(i)
    seen_group, seen_sha = {}, {}
    for i,r in enumerate(records):
        with Image.open(r['path']) as raw:
            image = ImageOps.exif_transpose(raw).convert('RGB'); image.load()
        if digest(Path(r['path'])) != r['image_sha256']:
            raise ValueError('Candidate image changed')
        r['phash'] = phash(image); r['aspect'] = image.width/image.height
        for key,lookup in ((r['source_group'],seen_group),(r['image_sha256'],seen_sha)):
            if key in lookup: union(i,lookup[key])
            else: lookup[key]=i
        for j,s in enumerate(records[:i]):
            if abs(math.log(r['aspect']/s['aspect'])) < .12 and (r['phash']^s['phash']).bit_count() <= 6:
                union(i,j)
    groups = defaultdict(list)
    for i,r in enumerate(records): groups[find(i)].append(r)
    partitions = {}
    ordered = sorted(groups.values(), key=lambda rs: hashlib.sha256('|'.join(sorted(r['source_id'] for r in rs)).encode()).hexdigest())
    # Respect the upstream original train/holdout boundary. Shared source groups
    # touching both are withheld in their entirety, never trained.
    holdout_index = 0
    flexible = []
    for rs in ordered:
        flags = {r['forced_split'] for r in rs if r.get('forced_split')}
        if 'holdout' in flags:
            split = 'valid' if holdout_index % 2 == 0 else 'test';holdout_index+=1
        elif 'train' in flags:
            split = 'train'
        else:
            flexible.append(rs);continue
        for r in rs: partitions[r['source_id']] = split
    # Deterministically reserve independent creator/session groups for each new
    # public-source class, with no holdout selection based on model scores.
    group_partition = {}
    for c in (69,70,71,73,74):
        eligible=[i for i,rs in enumerate(flexible) if any(b['training_class_id']==c for r in rs for b in r['boxes'])]
        if len(eligible)<5: raise ValueError(f'Too few independent source groups for class {c}: {len(eligible)}')
        n=max(1,round(len(eligible)*.15))
        for split, indices in (('test',eligible[:n]),('valid',eligible[n:2*n])):
            for i in indices:
                if i in group_partition and group_partition[i]!=split:
                    raise ValueError('Multiclass group split conflict requires explicit review')
                group_partition[i]=split
    for i,rs in enumerate(flexible):
        for r in rs: partitions[r['source_id']]=group_partition.get(i,'train')
    for r in records: r['split']=partitions[r['source_id']]
    return records


def main():
    from PIL import Image, ImageOps
    import yaml
    destination = OUT/'yolo-75-v3'
    if destination.exists(): raise ValueError('Preserve existing export; use a new explicitly versioned export for changes')
    records = assign_splits(public_regions())
    legacy = ROOT/'data/processed/vision-yolo-v1'
    parent_review=OUT/'legacy-replay-review-v2'
    native_qa=OUT/'native-regions/review-sheets'
    qa=json.loads((native_qa/'index.json').read_text())
    if len({r['source_id'] for r in qa})!=43: raise ValueError('Expected the actual reviewed native-mask QA sample')
    # Compare all selected source images/replay to legacy holdout. Existing
    # upstream split quality is reported separately, never silently fixed here.
    holdouts=[]; legacy_stems=set()
    for split in ('valid','test'):
        for path in sorted((legacy/'images'/('val' if split=='valid' else split)).glob('*.jpg')):
            with Image.open(path) as raw: im=raw.convert('RGB'); im.load()
            holdouts.append((digest(path),phash(im),im.width/im.height))
            legacy_stems.add(path.stem.split('__',1)[-1].split('.rf.')[0])
    excluded=[]
    def collides(path, known_sha=None):
        with Image.open(path) as raw: im=ImageOps.exif_transpose(raw).convert('RGB');im.load()
        h=phash(im);ratio=im.width/im.height;sha=known_sha or digest(path)
        return any(sha==s or abs(math.log(ratio/a))<.12 and (h^p).bit_count()<=6 for s,p,a in holdouts)
    for split in ('train','valid','test'):
        for kind in ('images','labels'): (destination/kind/split).mkdir(parents=True)
    lists=defaultdict(list);manifest=[];counts=Counter();sources_by_split=defaultdict(set)
    def save_crop(image, box, c, split, key, source):
        try: cropped,transformed,bounds=crop_region(image,box)
        except ValueError as exc:
            excluded.append(dict(source_id=source['source_id'],reason=str(exc)));return
        name=key+'.jpg';target=destination/'images'/split/name
        cropped.save(target,quality=95)
        label=destination/'labels'/split/(key+'.txt');label.write_text(yolo_line(c,transformed))
        lists[split].append(str(target));lists['extension_'+split].append(str(target));counts[(split,c)]+=1
        sources_by_split[split].add(source['source_id'])
        manifest.append(dict(source_id=source['source_id'],source_group=source['source_group'],split=split,
            training_class_id=c,image_path=str(target.relative_to(destination)),image_sha256=digest(target),label_sha256=digest(label),
            source_crop_bounds_xyxy_pixels=bounds,source_bbox_xyxy_norm=box,export_bbox_xyxy_norm=transformed,
            annotation_unit=source['annotation_unit']))
    for index,r in enumerate(records):
        if collides(Path(r['path']),r['image_sha256']):
            excluded.append(dict(source_id=r['source_id'],reason='near_duplicate_of_legacy_holdout'));continue
        with Image.open(r['path']) as raw: image=ImageOps.exif_transpose(raw).convert('RGB');image.load()
        for k,b in enumerate(r['boxes']):
            # Semantic regions smaller than this are not useful detector targets.
            save_crop(image,b['bbox_xyxy_norm'],b['training_class_id'],r['split'],f'extension-{index:05d}-{k:03d}',r)
    # Parent food crop review keeps only explicit non-overlapping legacy foods.
    candidates=json.loads((parent_review/'parent-candidates.json').read_text())
    decisions=json.loads((parent_review/'decisions.json').read_text())
    for decision in decisions:
        if not decision['accepted']: continue
        r=candidates[decision['index']];path=Path(r['image_path'])
        if decision['review_sheet_sha256']!=digest(parent_review/f"parents-{r['index']//16:03d}.jpg"):
            raise ValueError('Parent review evidence changed')
        if collides(path): continue
        with Image.open(path) as raw: image=raw.convert('RGB');image.load()
        source=dict(source_id='legacy-parent-'+r['source_group'],source_group=r['source_group'],
            annotation_unit='legacy_native_box_visually_reviewed_nonoverlapping_parent')
        before=len(lists['train'])
        save_crop(image,xyxy(r['bbox_xywh_norm']),r['training_class_id'],'train',f'legacy-parent-{r["index"]:03d}',source)
        if len(lists['train'])>before:
            lists['extension_train'].pop()  # Legacy crop belongs to replay, not extension oversampling.
    replay=json.loads((parent_review/'selected-nonparent.json').read_text())['images']
    replay_counts=Counter();replay_used=0
    for index,r in enumerate(replay):
        path=Path(r['image_path']);stem=path.stem.split('__',1)[-1].split('.rf.')[0]
        if stem in legacy_stems or collides(path):
            excluded.append(dict(source_id=path.name,reason='legacy_replay_near_duplicate_of_legacy_holdout'));continue
        if not path.resolve().is_relative_to((legacy/'images/train').resolve()): raise ValueError('Replay outside original train')
        target=destination/'images/train'/f'legacy-{index:05d}.jpg';shutil.copyfile(path,target)
        label=destination/'labels/train'/f'legacy-{index:05d}.txt'
        label.write_text(''.join(yolo_line(b['training_class_id'],xyxy(b['bbox_xywh_norm'])) for b in r['boxes']))
        lists['train'].append(str(target));replay_used+=1
        for c in {b['training_class_id'] for b in r['boxes']}:replay_counts[c]+=1
        manifest.append(dict(source_id=path.name,source_group=stem,split='train',image_path=str(target.relative_to(destination)),
            image_sha256=digest(target),label_sha256=digest(label),annotation_unit='legacy_native_training_box_replay'))
    # Preserve every old validation/test example and its native class labels.
    for split in ('valid','test'):
        legacy_split='val' if split=='valid' else split
        for path in sorted((legacy/'images'/legacy_split).glob('*.jpg')):
            target=destination/'images'/split/('legacy-'+path.name);shutil.copyfile(path,target)
            label=destination/'labels'/split/('legacy-'+path.stem+'.txt')
            shutil.copyfile(legacy/'labels'/legacy_split/(path.stem+'.txt'),label)
            lists[split].append(str(target));lists['legacy_'+split].append(str(target))
    mapping=ROOT/'docs/dataset/food-identities-v2.json';data=json.loads(mapping.read_text(encoding='utf-8'))
    if {s:len(lists['legacy_'+s]) for s in ('valid','test')}!={'valid':787,'test':404}:
        raise ValueError('Both complete legacy holdout splits are required')
    if data['foods'][69]['slug']!='ga_nuong':raise ValueError('Latest owner chicken scope is required')
    # Oversampling changes training frequency only. No copied/repeated view is
    # counted as an additional source photograph or independent holdout.
    byclass=defaultdict(list)
    for row in manifest:
        if row.get('training_class_id',-1)>=67 and row['split']=='train':
            byclass[row['training_class_id']].append(str(destination/row['image_path']))
    for c in range(67,75):
        if not byclass[c] or not counts[('valid',c)] or not counts[('test',c)]:
            raise ValueError(f'Class {c} requires actual train, valid and test crops')
        paths=byclass[c]
        lists['train'].extend(paths[k%len(paths)] for k in range(max(0,400-len(paths))))
    training_classes=set(replay_counts)|{c for split,c in counts if split=='train'}
    if training_classes!=set(range(75)):raise ValueError('Replay coverage missing: '+str(set(range(75))-training_classes))
    for key,paths in lists.items(): (destination/(key+'.txt')).write_text('\n'.join(paths)+'\n',encoding='utf-8')
    base=dict(path=str(destination),train=str(destination/'train.txt'),val=str(destination/'valid.txt'),test=str(destination/'test.txt'),
        nc=75,names={f['training_class_id']:f['name_vi'] for f in data['foods']})
    (destination/'dataset.yaml').write_text(yaml.safe_dump(base,allow_unicode=True),encoding='utf-8')
    for scope in ('legacy','extension'):
        cfg=dict(base,val=str(destination/(scope+'_valid.txt')),test=str(destination/(scope+'_test.txt')))
        (destination/(scope+'-eval.yaml')).write_text(yaml.safe_dump(cfg,allow_unicode=True),encoding='utf-8')
    (destination/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (destination/'sources.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    (destination/'excluded.json').write_text(json.dumps(excluded,ensure_ascii=False,indent=2),encoding='utf-8')
    export=dict(status='completed',training_scope='owner_extension_75_mixed_replay',class_map_sha256=digest(mapping),
        class_map_version=data['class_map_version'],all_training_labels_accepted=True,source_mutated=False,
        training_classes=list(range(75)),new_classes=list(range(67,75)),legacy_replay_full_images=replay_used,
        extension_region_counts={str(c):{s:counts[(s,c)] for s in ('train','valid','test')} for c in range(67,75)},
        unique_train_images=len(set(lists['train'])),train_sampling_entries=len(lists['train']),
        extension_unique_source_photos={s:len({r['source_id'] for r in manifest if r['split']==s and r.get('training_class_id',-1)>=67}) for s in ('train','valid','test')},
        legacy_holdout_images={s:len(lists['legacy_'+s]) for s in ('valid','test')},
        annotation_review='Codex visual self-review for public-source boxes; native semantic-mask boxes geometry checked with 43-photo sample QA; no independent human annotation audit',
        evaluation_scope='Legacy full scenes unchanged; new classes object/food-region crops with 8% context. Not phone/full-scene acceptance.',
        near_duplicate_policy='Full-source pHash Hamming<=6 with aspect log-difference<0.12; creator/capture-day grouping; original FoodSeg holdout never trained; selected replay/new photos excluded if similar to legacy holdout.',
        manifest_sha256=digest(destination/'manifest.json'),source_manifest_sha256=digest(destination/'sources.json'),
        not_checked=['Exhaustive semantic audit of legacy replay','Duplicates missed by pHash','Independent human annotation review','Full 75-class independent full-scene holdout','Phone/LAN acceptance','Nutrition approval'])
    (destination/'export.json').write_text(json.dumps(export,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(export,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
