"""Evaluate real trained weights, record missing-class coverage and build a bundle."""
from collections import Counter
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import time

from .runtime import ROOT,PROCESSED,configure,write_json
from .train_budget import clean,durable_copy
from .model_card import render as model_card


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def label_coverage(dataset,split):
    boxes,images=Counter(),Counter()
    max_objects=0
    for path in (dataset/'labels'/split).glob('*.txt'):
        seen=set();count=0
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.strip():continue
            c=int(line.split()[0])
            if not 0<=c<67:raise ValueError('Invalid derived class')
            boxes[c]+=1;seen.add(c);count+=1
        images.update(seen);max_objects=max(max_objects,count)
    return boxes,images,max_objects


def native_coverage(labels):
    """Count the labels actually retained by the library after its verification."""
    boxes,images=Counter(),Counter();maximum=0;background=0
    for row in labels:
        ids=[int(c) for c in row['cls'].reshape(-1)]
        if any(not 0<=c<67 for c in ids):raise ValueError('Native class map mismatch')
        boxes.update(ids);images.update(set(ids));maximum=max(maximum,len(ids));background+=not ids
    return boxes,images,maximum,dict(images=len(labels),boxes=sum(boxes.values()),class_count=len(boxes),background_images=background)


def evaluate(dataset,job,bundle):
    torch=configure()
    from ultralytics import YOLO,__version__ as ultralytics_version
    state=json.loads((job/'status.json').read_text(encoding='utf-8'))
    if state['stage'] not in ('trained_pending_evaluation','evaluating'):
        raise ValueError('A finished real training job is required')
    if not bundle.resolve().is_relative_to((ROOT/'ml/models').resolve()) or bundle.exists():
        raise ValueError('New bundle must be inside ignored ml/models')
    weights=Path(state['best_checkpoint'])
    export_path=dataset/'export.json'
    export=json.loads(export_path.read_text(encoding='utf-8'))
    if export.get('status')!='completed':raise ValueError('Completed evaluation dataset required')
    fixture=state.get('training_scope')=='checkpoint_smoke_fixture'
    if not fixture and state['dataset_export_sha256']!=sha(export_path):
        raise ValueError('Evaluation export does not match the audited training export')
    if not weights.is_file():raise ValueError('Best checkpoint missing')
    identity_path=ROOT/'docs/dataset/food-identities-v1.json'
    identity=json.loads(identity_path.read_text(encoding='utf-8'))
    expected=[r['name_vi'] for r in sorted(identity['foods'],key=lambda r:r['training_class_id'])]
    model=YOLO(str(weights))
    if [model.names[i] for i in range(67)]!=expected or len(model.names)!=67:
        raise ValueError('Checkpoint names do not match the 67-class map')
    state['stage']='evaluating';write_json(job/'status.json',state)
    evaluations={}
    observed={}
    def validation_start(validator):
        observed['coverage']=native_coverage(validator.dataloader.dataset.labels)
    model.add_callback('on_val_start',validation_start)
    for split in ('val','test'):
        raw_counts,_,_=label_coverage(dataset,split)
        observed.clear()
        metric=model.val(data=str(dataset/'dataset.yaml'),split=split,imgsz=state['imgsz'],batch=state['batch'],
                         device=0,workers=0,plots=False,save_json=False,verbose=False,conf=.001,iou=.7,max_det=100,
                         project=str(job/'evaluation'),name=split,exist_ok=True)
        counts,images,max_objects,native=observed['coverage']
        if native['images']!=sum(1 for _ in (dataset/'images'/split).glob('*.jpg')):
            raise ValueError('Native evaluation discarded images; review before bundling')
        per_class={int(c):i for i,c in enumerate(metric.box.ap_class_index)}
        rows=[]
        for c in range(67):
            index=per_class.get(c)
            values=None
            if index is not None and counts[c]>0:
                values=dict(precision=float(metric.box.p[index]),recall=float(metric.box.r[index]),
                            ap50=float(metric.box.ap50[index]),ap50_95=float(metric.box.ap[index]))
            rows.append(dict(training_class_id=c,name_vi=expected[c],ground_truth_images=images[c],
                             ground_truth_boxes=counts[c],metrics=values))
        evaluations[split]=dict(aggregate=clean(dict(metric.results_dict)),speed_ms=clean(dict(metric.speed)),
                               present_classes=sorted(counts),missing_classes=sorted(set(range(67))-set(counts)),
                               class_count=len(counts),ground_truth_boxes=sum(counts.values()),maximum_objects_per_image=max_objects,
                               native_dataset=native,raw_export_ground_truth_boxes=sum(raw_counts.values()),
                               removed_duplicate_labels=sum(raw_counts.values())-sum(counts.values()),
                               per_class=rows,conf_for_ap=.001,nms_iou=.7,max_detections=100,
                               interpretation='Metrics apply only to classes present in this received split; absent classes are unmeasured, not assigned average AP.')
        write_json(job/'evaluation.json',dict(status='running',splits=evaluations))
    # Batch-one latency on actual held-out bytes, independent of val batching.
    from PIL import Image
    samples=sorted((dataset/'images/test').glob('*.jpg'))[:10]
    times=[];sample_detections=[]
    for index,path in enumerate(samples):
        with Image.open(path) as im:
            image=im.convert('RGB')
            start=time.perf_counter()
            result=model.predict(image,imgsz=state['imgsz'],conf=.25,iou=.7,max_det=100,device=0,verbose=False)[0]
            torch.cuda.synchronize()
            elapsed=(time.perf_counter()-start)*1000
            if index>0:times.append(elapsed)
            sample_detections.append(dict(sample_name=path.name,detections=len(result.boxes)))
    bundle.mkdir(parents=True)
    durable_copy(weights,bundle/'weights.pt')
    durable_copy(identity_path,bundle/'food-identities-v1.json')
    evaluation=dict(status='completed',splits=evaluations,
                    batch_one_latency_ms=dict(samples=len(times),mean=sum(times)/len(times) if times else None,
                                              min=min(times) if times else None,max=max(times) if times else None,
                                              hardware=torch.cuda.get_device_name(0)),sample_detection_counts=sample_detections,
                    quality_accepted=False,full_67_class_holdout=False,
                    evidence_scope='train_subset_preflight_only' if fixture else 'effective_validation_and_test',
                    evaluation_export_sha256=sha(export_path))
    write_json(bundle/'evaluation.json',evaluation)
    native_train=None
    if not fixture:
        import numpy as np
        # This is this job's trusted, locally generated cache, never an upload.
        cached=np.load(dataset/'labels/train.cache',allow_pickle=True).item()
        *_,native_train=native_coverage(cached['labels'])
        if native_train['images']!=export['images']['train'] or native_train['class_count']!=67:
            raise ValueError('Native training coverage differs from the full audited export')
        del cached
    manifest=dict(bundle_version=1,stage='evaluated',model_version=job.name,
                  architecture=state['selected_model'][:-3],task='detect',class_count=67,
                  class_map_version=identity['class_map_version'],class_map_sha256=sha(identity_path),
                  class_map_file='food-identities-v1.json',weights_file='weights.pt',weights_sha256=sha(bundle/'weights.pt'),
                  imgsz=state['imgsz'],confidence=.25,nms_iou=.7,max_detections=100,
                  input_contract='canonical_static_RGB_JPEG_EXIF_applied',bbox_output='xyxy_norm_canonical',
                  ultralytics_version=ultralytics_version,torch_version=torch.__version__,
                  created_at=datetime.now(timezone.utc).isoformat(),inference_compatible=True,
                  training=dict(budget_hours=state['budget_hours'],elapsed_seconds=state['training_job_elapsed_seconds'],
                                scope=state.get('training_scope','unknown_do_not_activate'),
                                source_dataset_images=export.get('images'),raw_export_boxes=export.get('boxes'),native_train=native_train,
                                completed_epochs=state['completed_epochs'],dataset_export_sha256=state['dataset_export_sha256'],
                                epochs_with_updates=state.get('epochs_with_updates'),partial_final_epoch=state.get('partial_final_epoch'),
                                source_baseline_version=identity['source_data_version']),
                  evaluation_file='evaluation.json',evaluation_sha256=sha(bundle/'evaluation.json'),
                  quality_status='checkpoint_smoke_only_do_not_activate' if fixture else 'experimental_budgeted_baseline_not_full_67_class_acceptance',
                  source_pretrained=dict(file=state['selected_model'],sha256=sha(ROOT/'ml/models/pretrained'/state['selected_model']),
                                         release='https://github.com/ultralytics/assets/releases/tag/v8.4.0',
                                         license='https://github.com/ultralytics/ultralytics/blob/main/LICENSE'))
    (bundle/'model-card.md').write_text(model_card(manifest,evaluation),encoding='utf-8')
    manifest.update(model_card_file='model-card.md',model_card_sha256=sha(bundle/'model-card.md'))
    write_json(bundle/'manifest.json',manifest)
    write_json(job/'evaluation.json',evaluation)
    state.update(stage='evaluated_bundle_ready_for_api_test',bundle=str(bundle),evaluation_summary={s:v['aggregate'] for s,v in evaluations.items()},
                 quality_status=manifest['quality_status'],updated_at=datetime.now(timezone.utc).isoformat())
    write_json(job/'status.json',state)
    print('Real validation/test evaluation and verified 67-class model bundle completed.',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True);p.add_argument('--job',type=Path,required=True);p.add_argument('--bundle',type=Path,required=True)
    a=p.parse_args();evaluate(a.dataset.resolve(),a.job.resolve(),a.bundle.resolve())
