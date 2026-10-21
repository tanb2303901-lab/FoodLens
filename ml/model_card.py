"""Readable evidence card from measured bundle data, with explicit missing coverage."""


def number(value):
    return 'unmeasured' if value is None else f'{value:.4f}'


def render(manifest,evaluation):
    train=manifest['training']
    lines=[f"# FoodLens model: {manifest['model_version']}",'',
           f"Status: {manifest['quality_status']}. Quality acceptance: pending.",
           f"Training scope: {train['scope']}. Evaluation scope: {evaluation['evidence_scope']}.",'',
           'This bundle supports the 67 received VietFood classes. Original face ID 27 is excluded; training ID 27 is food original ID 28.',
           'Training time does not establish accuracy. Present-class metrics below do not measure absent classes or complete product acceptance.','',
           f"Detector: {manifest['architecture']}; input {manifest['imgsz']} px; runtime confidence {manifest['confidence']}; NMS IoU {manifest['nms_iou']}; max detections {manifest['max_detections']}.",
           f"Training budget: {train['budget_hours']} hours; measured job time: {train['elapsed_seconds']/3600:.3f} hours; complete epochs: {train['completed_epochs']}; partial final epoch: {train['partial_final_epoch']}.",
           f"Torch {manifest['torch_version']}; Ultralytics {manifest['ultralytics_version']}; class map {manifest['class_map_version']}.",'',
           '## Measured evaluation','',
           'Ultralytics native dataset evaluation, confidence 0.001 for AP; values are fractions from 0 to 1. This differs from the runtime display threshold of 0.25.','',
           '| Split | Classes measured / 67 | GT boxes | Precision | Recall | mAP50 | mAP50-95 |',
           '| --- | --- | --- | --- | --- | --- | --- |']
    for split,data in evaluation['splits'].items():
        a=data['aggregate']
        values=[number(a.get(k)) for k in ('metrics/precision(B)','metrics/recall(B)','metrics/mAP50(B)','metrics/mAP50-95(B)')]
        lines.append(f"| {split} | {data['class_count']} / 67 | {data['ground_truth_boxes']} | "+' | '.join(values)+' |')
    if train.get('native_train'):
        n=train['native_train']
        lines+=['',f"Native training loader retained {n['images']} images and {n['boxes']} boxes across {n['class_count']} classes. Library duplicate-label removal affects the cache; original files remain preserved."]
    lines+=['','## Per-class coverage and AP50','',
            'Unmeasured cells remain unmeasured; they are never filled using average AP. Class names follow the exact training map.','',
            '| Training ID | Food | Val GT boxes | Val AP50 | Test GT boxes | Test AP50 |',
            '| --- | --- | --- | --- | --- | --- |']
    for v,t in zip(evaluation['splits']['val']['per_class'],evaluation['splits']['test']['per_class']):
        if v['training_class_id']!=t['training_class_id']:raise ValueError('Evaluation class order mismatch')
        ap=lambda r:number(r['metrics']['ap50'] if r['metrics'] is not None else None)
        lines.append(f"| {v['training_class_id']} | {v['name_vi']} | {v['ground_truth_boxes']} | {ap(v)} | {t['ground_truth_boxes']} | {ap(t)} |")
    latency=evaluation['batch_one_latency_ms']
    lines+=['','## Runtime interpretation','',
            f"Batch-one local prediction latency: mean {number(latency['mean'])} ms over {latency['samples']} warmed samples on {latency['hardware']}. This excludes HTTP/Auth/Storage; the real API report records those separately.",
            'Input is a static supported image canonicalized to oriented RGB JPEG by the backend. Boxes are normalized xyxy relative to that canonical image. Confidence is a detector score, not a guarantee of correct identification.',
            'Grams require user confirmation. Approved nutrition data is separate; this bundle supplies no grams, calorie estimates or nutrient approval.',
            'Mobile/device integration, full independent 67-class holdout and production quality acceptance remain separate. A technical readiness check is not product acceptance.','',
            '## Provenance','',
            f"Weights SHA-256: {manifest['weights_sha256']}",
            f"Class-map SHA-256: {manifest['class_map_sha256']}",
            f"Evaluation SHA-256: {manifest['evaluation_sha256']}",
            f"Pretrained source: {manifest['source_pretrained']['release']}",
            f"Source license: {manifest['source_pretrained']['license']}",'']
    return '\n'.join(lines)
