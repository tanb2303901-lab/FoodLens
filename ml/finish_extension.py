"""Finish the already-authorized ML-05 run after evaluation; never train.

Waits for the existing supervisor, checks predeclared experimental quality
minima, runs real model/API integration, then activates only the tested bundle.
Failure preserves the old local model/config. All accounts in tests are owned
fixtures, not the owner's diagnostic account. No cloud, database reset or mail.
"""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .runtime import ROOT,PROCESSED,write_json


def quality_check(bundle):
    from backend.app.detector import verify_bundle
    manifest,_,_=verify_bundle(bundle)
    evaluation=json.loads((bundle/'evaluation.json').read_text(encoding='utf-8'))
    baseline=json.loads((ROOT/'docs/dataset/model-evaluation-v1.json').read_text(encoding='utf-8'))
    gates=json.loads((ROOT/'docs/dataset/extension-quality-gates-v2.json').read_text(encoding='utf-8'))
    # Baseline portable metadata wraps the original complete native report.
    old=baseline.get('evaluation',baseline)
    checks=[]
    def check(name,valid,observed):checks.append(dict(name=name,passed=bool(valid),observed=observed))
    for metric,suffix in [('metrics/mAP50(B)','map50'),('metrics/mAP50-95(B)','map50_95')]:
        old_value=old['splits']['val']['aggregate'][metric]
        new_value=evaluation['splits']['legacy_valid']['aggregate'][metric]
        check('legacy_validation_'+suffix,new_value>=old_value*(1-gates['legacy_validation_max_relative_'+suffix+'_drop']),
              dict(baseline=old_value,candidate=new_value))
    for split in ('extension_valid','extension_test'):
        rows={r['training_class_id']:r for r in evaluation['splits'][split]['per_class']}
        threshold=gates['extension_min_per_class_'+('validation' if split.endswith('valid') else 'test')+'_ap50']
        for c in range(67,75):
            metrics=rows[c]['metrics'];value=metrics['ap50'] if metrics else None
            check(split+'_class_'+str(c),value is not None and value>=threshold,dict(ap50=value,minimum=threshold))
    result=dict(status='passed' if all(c['passed'] for c in checks) else 'failed',checks=checks,
        evaluation_sha256=manifest['evaluation_sha256'],weights_sha256=manifest['weights_sha256'],
        gates_version=gates['version'],gates_sha256=hashlib.sha256((ROOT/'docs/dataset/extension-quality-gates-v2.json').read_bytes()).hexdigest(),
        scope=gates['scope'],limitations=gates['limitations'],recorded_at=datetime.now(timezone.utc).isoformat())
    write_json(PROCESSED/'ML-05-quality-gates.json',result)
    if result['status']!='passed':raise ValueError('Experimental local quality minima did not pass; old model retained')
    return result


def finish():
    deadline=datetime.fromisoformat('2026-10-16T07:25:00+00:00') #14:25 local, reserve five minutes.
    report=dict(task='ML-05',stage='waiting_for_existing_training_and_evaluation',status='running',
        started_at=datetime.now(timezone.utc).isoformat(),no_additional_training=True,active_model_unchanged=True)
    output=PROCESSED/'ML-05-finish.json';write_json(output,report)
    while datetime.now(timezone.utc)<deadline:
        state=json.loads((PROCESSED/'ML-05-job.json').read_text(encoding='utf-8'))
        if state['stage']=='evaluated_candidate_pending_api_integration':break
        if state['stage'] in ('training_failed','evaluation_failed','training_budget_terminated_pending_checkpoint_review','paused_by_owner'):
            raise RuntimeError('Existing supervisor requires review: '+state['stage'])
        time.sleep(5)
    else:raise RuntimeError('Owner deadline reached before an evaluated candidate; old model retained')
    job=Path(state['job']).resolve();dataset=Path(state['dataset']).resolve()
    if not job.is_relative_to(PROCESSED/'ml-runs') or not dataset.is_relative_to(PROCESSED/'food-extension-v2'):
        raise ValueError('Only the recorded ML-05 local job/export is allowed')
    bundle=ROOT/'ml/models'/job.name
    report.update(stage='checking_quality_minima',updated_at=datetime.now(timezone.utc).isoformat());write_json(output,report)
    quality=quality_check(bundle)
    report.update(stage='real_model_api_integration',quality_minima='passed');write_json(output,report)
    with (PROCESSED/'ML-05-finish-api.log').open('w',encoding='utf-8') as log:
        child=subprocess.Popen([sys.executable,str(ROOT/'scripts/test_model_local.py'),'--bundle',str(bundle),'--dataset',str(dataset),
                                '--deadline-utc','2026-10-16T07:23:00+00:00'],
            cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:code=child.wait(timeout=max(1,(deadline-datetime.now(timezone.utc)).total_seconds()))
        except subprocess.TimeoutExpired:
            from .processes import stop_child
            stop_child(child)
            raise RuntimeError('API check deadline reached; inspect own fixture cleanup; old model retained') from None
    if code:raise RuntimeError('Real extension API checks failed; old model retained')
    report.update(stage='activating_tested_local_model');write_json(output,report)
    from .activate_local import activate
    activate(bundle)
    report.update(stage='recording_results',active_model_unchanged=False);write_json(output,report)
    manifest=json.loads((bundle/'manifest.json').read_text(encoding='utf-8'))
    evaluation=json.loads((bundle/'evaluation.json').read_text(encoding='utf-8'))
    api=json.loads((PROCESSED/'ML-05-model-integration.json').read_text(encoding='utf-8'))
    portable=dict(artifact_version=2,technical_status='ready_for_owner_test',model_version=manifest['model_version'],
        architecture=manifest['architecture'],class_count=75,class_map_version=manifest['class_map_version'],
        class_map_sha256=manifest['class_map_sha256'],weights_sha256=manifest['weights_sha256'],
        legacy_weights_sha256=manifest['legacy_weights_sha256'],evaluation_sha256=manifest['evaluation_sha256'],
        training=manifest['training'],evaluation=evaluation,local_api_checks=api['checks_passed'],
        correct_new_classes=api['correct_new_classes'],quality_minima=quality,
        scope='Experimental local75 detector; crop holdouts for new8, strict legacy full scenes; no phone/nutrition acceptance')
    write_json(ROOT/'docs/dataset/model-evaluation-v2.json',portable)
    summary='# ML-05 — Kết quả local sau train\n\n'
    summary+=f"Model `{manifest['model_version']}` đã đạt tối thiểu thực nghiệm và{api['checks_passed']} real model/API checks, đủ8 lớp mới có detection đúng với IoU≥0,5 qua API. Model67 nguồn giữ nguyên SHA. Không có extra training. Thời gian train tích lũy{manifest['training']['elapsed_seconds']:.3f} giây trong cap3 giờ;{manifest['training']['completed_epochs']} full epochs. Codex tự triển khai/review, không có reviewer độc lập.\n\n"
    summary+='| Split | Ảnh | mAP50 | mAP50-95 | Lớp có ground truth |\n| --- | ---: | ---: | ---: | ---: |\n'
    for key,value in evaluation['splits'].items():
        summary+=f"|{key}|{value['images']}|{value['aggregate']['metrics/mAP50(B)']:.4f}|{value['aggregate']['metrics/mAP50-95(B)']:.4f}|{len(value['present_classes'])}|\n"
    summary+='\nLớp mới đánh giá trên crop vùng thực phẩm; không phải ảnh toàn cảnh/iPhone. Legacy full-scene giữ35/29 lớp có GT, không full75. Nutrition vẫn chưa có approved profiles/portions, không tính thiếu thành0. Frontend/LAN/thiết bị thật và independent human annotation audit chưa nghiệm thu. Xem model-evaluation-v2.json cho đủ per-class metrics và trường thiếuNULL.\n'
    (ROOT/'docs/reviews/ML-05-local-result.md').write_text(summary,encoding='utf-8')
    status_path=ROOT/'docs/tasks/status.md';status_text=status_path.read_text(encoding='utf-8')
    lines=status_text.splitlines()
    lines=[f"| ML-05 | Bổ sung8 lớp, cap3 giờ, cutoff13:00 | DONE_LOCAL_EXPERIMENTAL |{api['checks_passed']} real API checks,8/8 mới có correct detections; live model ready. Xem ML-05-local-result. Crop holdouts; phone/nutrition acceptance còn mở |" if line.startswith('| ML-05 |') else line for line in lines]
    status_path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    for relative in ('AGENTS.md','docs/ml-local.md','docs/handoff/backend75-extension.md','docs/reviews/ML-05-extension.md'):
        path=ROOT/relative;original=path.read_text(encoding='utf-8');head,tail=original.split('\n',1)
        note='\nCurrent ML-05 result: local experimental75 model activated after real evaluation/API gates. See docs/reviews/ML-05-local-result.md and docs/dataset/model-evaluation-v2.json (paths relative to repository). Earlier training/pending/67-active notes below are historical. Full-scene new8/iPhone/LAN/nutrition remain unaccepted.\n'
        path.write_text(head+'\n'+note+tail,encoding='utf-8')
    report.update(status='passed',stage='ready_for_owner_test',active_model_unchanged=False,
        model_version=manifest['model_version'],api_checks=api['checks_passed'],correct_new_classes=api['correct_new_classes'],
        training_seconds=manifest['training']['elapsed_seconds'],completed_at=datetime.now(timezone.utc).isoformat(),
        not_accepted=['Full75-class independent quality','New8 full-scene/iPhone/LAN acceptance','Nutrition profiles'])
    write_json(output,report)
    print('ML-05 technical local model/API acceptance passed; full-scene phone and nutrition acceptance remain open.',flush=True)


if __name__=='__main__':
    import ctypes
    if os.name=='nt':ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    try:finish()
    except BaseException as exc:
        path=PROCESSED/'ML-05-finish.json'
        report=json.loads(path.read_text()) if path.exists() else {'task':'ML-05'}
        report.update(status='failed',stage='needs_review',error_type=type(exc).__name__,reason=str(exc),
            updated_at=datetime.now(timezone.utc).isoformat())
        write_json(path,report)
        print('ML-05 finalization requires review; see private status. No extra training was started.',file=sys.stderr,flush=True)
        raise SystemExit(1)
    finally:
        if os.name=='nt':ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
