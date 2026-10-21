"""Evaluate a trained 75-class candidate; never activate the local backend.

Evaluation is separate from the owner's reduced training budget.
New-class region-crop metrics and legacy full-scene metrics remain separate.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

from .runtime import ROOT, configure, write_json
from .train_budget import clean


def select_extension_checkpoint(dataset,job,initial,expected):
    """Choose new8 weights on validation only; legacy inference stays frozen."""
    import gc
    import torch
    from .dual75 import load_yolo,validator_class
    paths=sorted((job/'weights').glob('epoch*.pt'),key=lambda p:int(p.stem[5:]))+[initial,job/'weights/last.pt']
    seen=set();candidates=[];best=None;best_score=-1.
    for index,path in enumerate(paths):
        if datetime.now(timezone.utc)>=datetime.fromisoformat('2026-10-16T07:20:00+00:00'):
            raise RuntimeError('Evaluation cutoff reached; no untested candidate activation')
        if not path.is_file():continue
        sha=hashlib.sha256(path.read_bytes()).hexdigest()
        if sha in seen:continue
        seen.add(sha)
        state=json.loads((job/'status.json').read_text());state.update(stage='selecting_extension_checkpoint',
            checkpoint_selection_index=index+1,checkpoint_selection_total=len(paths),updated_at=datetime.now(timezone.utc).isoformat());write_json(job/'status.json',state)
        model=load_yolo(path)
        if model.names!=expected:raise ValueError('Candidate checkpoint identities changed')
        metric=model.val(validator=validator_class(),data=str(dataset/'extension-eval.yaml'),split='val',imgsz=512,batch=16,
            device=0,workers=0,plots=False,save_json=False,verbose=False,conf=.001,iou=.7,max_det=100,
            project=str(job/'checkpoint-validation'),name=path.stem,exist_ok=True)
        if sorted(int(c) for c in metric.box.ap_class_index)!=list(range(67,75)):
            raise ValueError('Checkpoint selection requires actual validation for all new8 classes')
        score=float(metric.box.map)
        candidates.append(dict(checkpoint=path.name,sha256=sha,extension_validation=clean(metric.results_dict)))
        if score>best_score:best_score=score;best=path
        write_json(job/'checkpoint-selection.json',dict(status='running',scope='extension8_validation_only_never_test',
            candidates=candidates,selected_checkpoint=best.name,selection_metric='extension mAP50-95',legacy_component='frozen original67'))
        del metric,model;gc.collect();torch.cuda.empty_cache()
    if best is None:raise ValueError('No evaluated extension checkpoint')
    result=dict(status='completed',scope='extension8_validation_only_never_test',candidates=candidates,
        selected_checkpoint=best.name,selection_metric='extension mAP50-95',legacy_component='frozen original67')
    write_json(job/'checkpoint-selection.json',result)
    return best,result


def evaluate(dataset, job):
    from .train_extension import accepted_export
    export=accepted_export(dataset)
    state=json.loads((job/'status.json').read_text(encoding='utf-8'))
    if state['stage']!='trained_pending_evaluation':raise ValueError('Finished training and a reviewed checkpoint required')
    weights=Path(state['best_checkpoint'])
    if not weights.resolve().is_relative_to((job/'weights').resolve()) or not weights.is_file():raise ValueError('Own best checkpoint required')
    if state['dataset_export_sha256']!=hashlib.sha256((dataset/'export.json').read_bytes()).hexdigest():raise ValueError('Training export changed')
    torch=configure()
    from ultralytics import __version__ as ultralytics_version
    from .dual75 import load_yolo,validator_class
    identity=ROOT/'docs/dataset/food-identities-v2.json'
    mapping=json.loads(identity.read_text(encoding='utf-8'))
    expected={f['training_class_id']:f['name_vi'] for f in mapping['foods']}
    from backend.app.detector import verify_bundle
    legacy_manifest,_,legacy_weights=verify_bundle(ROOT/'ml/models/foodlens-yolo11n-20261015-budget8h-v1')
    weights,selection=select_extension_checkpoint(dataset,job,weights,expected)
    model=load_yolo(weights,legacy_weights)
    if model.names!=expected:raise ValueError('Checkpoint identities do not match owner-approved scope75')
    state.update(stage='evaluating_candidate',updated_at=datetime.now(timezone.utc).isoformat());write_json(job/'status.json',state)
    observed={}
    def started(validator):
        boxes=Counter();images=Counter()
        for row in validator.dataloader.dataset.labels:
            ids=[int(c) for c in row['cls'].reshape(-1)]
            if any(c not in expected for c in ids):raise ValueError('Evaluation class ID outside map75')
            boxes.update(ids);images.update(set(ids))
        observed.update(boxes=boxes,images=images,count=len(validator.dataloader.dataset.labels))
    model.add_callback('on_val_start',started)
    report=dict(status='running',model_version=job.name+'-dual75',class_map_version=mapping['class_map_version'],
        training_budget_hours=state['budget_hours'],training_elapsed_seconds=state['training_job_elapsed_seconds'],
        checkpoint_selection='new8 validation mAP50-95; legacy67 model frozen; no test selection',
        selected_checkpoint=selection['selected_checkpoint'],inference_policy='frozen67_plus_new8_with_parent_precedence',
        quality_accepted=False,full_75_class_holdout=False,independent_human_annotation_review=False,
        active_model_unchanged=True,evaluation_export_sha256=hashlib.sha256((dataset/'export.json').read_bytes()).hexdigest(),splits={})
    for scope in ('legacy','extension'):
        for split in ('val','test'):
            if datetime.now(timezone.utc)>=datetime.fromisoformat('2026-10-16T07:20:00+00:00'):
                raise RuntimeError('Evaluation cutoff reached; no untested candidate activation')
            observed.clear();key=scope+'_'+('valid' if split=='val' else split)
            metric=model.val(validator=validator_class(),data=str(dataset/(scope+'-eval.yaml')),split=split,imgsz=512,batch=16,device=0,workers=0,
                plots=False,save_json=False,verbose=False,conf=.001,iou=.7,max_det=100,
                project=str(job/'evaluation'),name=key,exist_ok=True)
            paths=(dataset/(key+'.txt')).read_text(encoding='utf-8').splitlines()
            if observed['count']!=len(paths):raise ValueError('Native validation discarded an evaluation image')
            indices={int(c):i for i,c in enumerate(metric.box.ap_class_index)}
            rows=[]
            for c in range(75):
                i=indices.get(c);values=None
                if i is not None and observed['boxes'][c]>0:
                    values=dict(precision=float(metric.box.p[i]),recall=float(metric.box.r[i]),ap50=float(metric.box.ap50[i]),ap50_95=float(metric.box.ap[i]))
                rows.append(dict(training_class_id=c,name_vi=expected[c],ground_truth_images=observed['images'][c],
                    ground_truth_boxes=observed['boxes'][c],metrics=values))
            report['splits'][key]=dict(aggregate=clean(metric.results_dict),speed_ms=clean(metric.speed),
                images=observed['count'],ground_truth_boxes=sum(observed['boxes'].values()),present_classes=sorted(observed['boxes']),
                missing_classes=sorted(set(range(75))-set(observed['boxes'])),per_class=rows,
                scope='unchanged original full scenes; strict legacy taxonomy' if scope=='legacy' else 'held-out food-region crops, 8% context; AI-assisted visual review or source semantic masks; not full-scene phone acceptance')
            write_json(job/'evaluation.json',report)
    old=json.loads((ROOT/'docs/dataset/model-evaluation-v1.json').read_text(encoding='utf-8'))
    report.update(status='completed',completed_at=datetime.now(timezone.utc).isoformat(),
        legacy_comparison_reference='docs/dataset/model-evaluation-v1.json; same 787 validation and 404 test images, old class coverage35/29',
        extension_source_photo_counts=export['extension_unique_source_photos'],extension_region_counts=export['extension_region_counts'],
        limitations=export['not_checked'])
    # Evaluated technical bundle for isolated API testing. Activation remains a
    # separate gate requiring real model/Auth/Storage/ownership evidence.
    bundle=ROOT/'ml/models'/job.name
    bundle.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(weights,bundle/'weights.pt');shutil.copyfile(identity,bundle/'food-identities-v2.json')
    shutil.copyfile(legacy_weights,bundle/'legacy-weights.pt')
    write_json(bundle/'evaluation.json',report)
    manifest=dict(bundle_version=2,stage='evaluated',model_version=job.name+'-dual75',task='detect',
        architecture='yolo11n-frozen67-plus8',class_count=75,class_map_version=mapping['class_map_version'],
        legacy_weights_file='legacy-weights.pt',legacy_weights_sha256=legacy_manifest['weights_sha256'],
        class_map_file='food-identities-v2.json',class_map_sha256=hashlib.sha256(identity.read_bytes()).hexdigest(),
        weights_file='weights.pt',weights_sha256=hashlib.sha256((bundle/'weights.pt').read_bytes()).hexdigest(),
        evaluation_file='evaluation.json',evaluation_sha256=hashlib.sha256((bundle/'evaluation.json').read_bytes()).hexdigest(),
        imgsz=512,confidence=.25,nms_iou=.7,max_detections=100,input_contract='canonical_static_RGB_JPEG_EXIF_applied',
        bbox_output='xyxy_norm_canonical',ultralytics_version=ultralytics_version,torch_version=torch.__version__,
        training=dict(budget_hours=state['budget_hours'],elapsed_seconds=state['training_job_elapsed_seconds'],completed_epochs=state['completed_epochs'],
            epochs_with_updates=state['epochs_with_updates'],partial_final_epoch=state['partial_final_epoch'],
            source_model_version=state['source_model_version'],source_weights_sha256=state['source_weights_sha256'],
            dataset_export_sha256=state['dataset_export_sha256'],scope=state['training_scope']),
        inference_compatible=True,quality_status='experimental_extension_pending_owner_quality_acceptance',
        source_pretrained=dict(license='https://github.com/ultralytics/ultralytics/blob/main/LICENSE'))
    write_json(bundle/'manifest.json',manifest)
    (bundle/'model-card.md').write_text('# FoodLens75 candidate\n\nEight owner-selected broad additions, including Gà nướng of any cut and khoai lang across preparation styles.\n\n'
        'Training is capped at three cumulative hours with an earlier owner cutoff. Inference combines the unchanged67-class baseline with only8 new class outputs from the validation-selected extension checkpoint. Overlapping grilled chicken/salmon take precedence over credible matching parent boxes. This candidate is not activated in the backend. See evaluation.json for separate legacy full-scene and new region-crop metrics, actual per-class coverage, missing classes and limitations. No nutrition approval or phone/full-scene acceptance.\n',encoding='utf-8')
    write_json(job/'evaluation.json',report)
    state.update(stage='evaluated_candidate_pending_api_integration',bundle=str(bundle),updated_at=datetime.now(timezone.utc).isoformat(),
        quality_accepted=False,active_model_unchanged=True);write_json(job/'status.json',state)
    print('Candidate75 evaluated separately on legacy full scenes and new region crops; active model67 unchanged.',flush=True)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,required=True);p.add_argument('--job',type=Path,required=True)
    a=p.parse_args();evaluate(a.dataset.resolve(),a.job.resolve())
