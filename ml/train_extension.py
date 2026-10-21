"""ML-05 training, reduced by the owner to a three-hour cumulative ceiling.

Launch --supervise as an independent local process. The supervisor enforces the
wall budget even during initialization/checkpointing. Data acceptance is required;
candidate/pseudo labels alone cannot start this run.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from .runtime import ROOT, PROCESSED, configure, write_json


def remaining_seconds(hours, consumed):
    import math
    if not math.isfinite(hours) or not 0 < hours <= 3 or not math.isfinite(consumed) or consumed < 0:
        raise ValueError('Owner reduced ML-05 to a maximum three-hour run; resume requires an explicit owner instruction')
    return hours * 3600 - consumed


def progress_epoch(trainer):
    # Ultralytics dispatches on_train_start before defining trainer.epoch.
    return int(getattr(trainer,'epoch',trainer.start_epoch))


def resume_consumed(previous, control, pause, ledger, now, checkpoint_sha256):
    """Exclude only the explicit, verified pause; unknown downtime is consumed."""
    if previous['stage']=='paused_by_owner' and not ledger.get('pause_resume_dispatch_at'):
        if (pause.get('status')!='paused_by_owner' or pause.get('first_started_at')!=previous['created_at']
            or pause.get('paused_at')!=previous.get('paused_at') or pause.get('paused_at')!=ledger.get('paused_at')
            or pause.get('resume_checkpoint_sha256')!=checkpoint_sha256
            or previous.get('resume_checkpoint_sha256')!=checkpoint_sha256
            or pause.get('training_elapsed_seconds')!=previous.get('training_job_elapsed_seconds')
            or pause.get('training_elapsed_seconds')!=ledger.get('training_elapsed_seconds_at_verified_pause')):
            raise ValueError('Pause evidence or optimizer checkpoint changed; no budget exclusion allowed')
        excluded=(now-datetime.fromisoformat(pause['paused_at'])).total_seconds()
        if excluded<0:raise ValueError('Resume precedes the verified pause')
        consumed=pause['training_elapsed_seconds']
        remaining_seconds(ledger['training_budget_hours'],consumed)
        return consumed,excluded
    consumed=max(previous['training_job_elapsed_seconds'],control['consumed_before_child_seconds']+
        (now-datetime.fromisoformat(control['child_dispatch_at'])).total_seconds())
    return consumed,0.


def available_seconds(hours, consumed, deadline_utc, now):
    deadline=datetime.fromisoformat(deadline_utc)
    if deadline.tzinfo is None:raise ValueError('A timezone-aware training cutoff is required')
    return min(remaining_seconds(hours,consumed),(deadline-now).total_seconds())


def accepted_export(dataset):
    if not dataset.resolve().is_relative_to((PROCESSED / 'food-extension-v2').resolve()):
        raise ValueError('Expected an isolated ML-05 dataset')
    export = json.loads((dataset / 'export.json').read_text(encoding='utf-8'))
    mapping = ROOT / 'docs/dataset/food-identities-v2.json'
    if (export.get('status') != 'completed' or export.get('training_scope') != 'owner_extension_75_mixed_replay'
        or export.get('class_map_sha256') != hashlib.sha256(mapping.read_bytes()).hexdigest()
        or export.get('all_training_labels_accepted') is not True or export.get('source_mutated') is not False
        or export.get('legacy_holdout_images') != {'valid':787,'test':404}
        or export.get('training_classes') != list(range(75)) or export.get('new_classes') != list(range(67, 75))):
        raise ValueError('Audited 75-class export and accepted labels required; proposals are not ground truth')
    for name,key in (('manifest.json','manifest_sha256'),('sources.json','source_manifest_sha256')):
        if hashlib.sha256((dataset/name).read_bytes()).hexdigest()!=export.get(key):
            raise ValueError('Dataset manifest changed after export acceptance')
    return export


def train(dataset, job, hours, resume):
    accepted_export(dataset)
    control = json.loads((job / 'control.json').read_text())
    consumed = control['consumed_before_child_seconds'] + (datetime.now(timezone.utc) - datetime.fromisoformat(control['child_dispatch_at'])).total_seconds()
    if available_seconds(hours,consumed,control['training_deadline_utc'],datetime.now(timezone.utc)) < 300:
        raise ValueError('Training budget/cutoff exhausted or insufficient for a safe checkpoint')
    started = time.monotonic()
    torch = configure()
    if not torch.cuda.is_available():
        raise ValueError('CUDA required for this owner-authorized local run')
    from ultralytics import YOLO
    from .extension_model import extension_trainer_class
    from .train_budget import clean
    source = ROOT / 'ml/models/foodlens-yolo11n-20261015-budget8h-v1'
    from backend.app.detector import verify_bundle
    manifest, mapping, weights = verify_bundle(source)
    checkpoint = job / 'weights/last-resume.pt'
    resume_optimizer=resume and checkpoint.exists()
    if resume:
        if not checkpoint.exists() and control.get('resume_without_updates') is not True:
            raise ValueError('Optimizer-preserving extension checkpoint required')
        if resume_optimizer: weights = checkpoint
    model = YOLO(str(weights))
    if not resume_optimizer and model.names != {i: f['name_vi'] for i, f in mapping.foods.items()}:
        raise ValueError('Source model class identities do not match the trusted 67-class baseline')
    status = dict(task='ML-05', stage='initializing', created_at=control['first_started_at'], updated_at=datetime.now(timezone.utc).isoformat(),
        budget_hours=hours, training_job_elapsed_seconds=consumed, training_scope='owner_extension_75_mixed_replay',
        source_model_version=manifest['model_version'], source_weights_sha256=manifest['weights_sha256'],
        class_map_version='foodlens-75-2026-10-16-v2', class_count=75, resume=resume,
        latest_expected_deadline_utc=control['training_deadline_utc'],
        verified_pause_excluded_seconds=control.get('verified_pause_excluded_seconds',0),
        dataset_export_sha256=hashlib.sha256((dataset / 'export.json').read_bytes()).hexdigest())
    write_json(job / 'status.json', status)
    batches = {}
    last_update = [0.]
    def elapsed():
        return consumed + time.monotonic() - started
    def report(trainer, force=False):
        epoch = progress_epoch(trainer)
        if not force:
            batches[epoch] = batches.get(epoch, 0) + 1
        status.update(stage='training', updated_at=datetime.now(timezone.utc).isoformat(), training_job_elapsed_seconds=elapsed(),
            epoch_index=epoch, completed_epochs=epoch, batches_seen_in_epoch=batches.get(epoch, 0),
            batches_per_epoch=len(trainer.train_loader), batch_size=int(trainer.batch_size),
            cuda_allocated_gib=torch.cuda.memory_allocated() / 2**30)
        if getattr(trainer,'loss_items',None) is not None:
            status['last_loss'] = clean(trainer.loss_items)
        if force or time.monotonic() - last_update[0] > 20:
            write_json(job / 'status.json', status)
            last_update[0] = time.monotonic()
        if available_seconds(hours,elapsed(),control['training_deadline_utc'],datetime.now(timezone.utc)) < 180:
            trainer.stop = True
    def epoch_start(trainer):
        batches[int(trainer.epoch)] = 0
    def epoch_end(trainer):
        if int(trainer.epoch) in batches:
            report(trainer, True)
            full=batches[int(trainer.epoch)]>=len(trainer.train_loader)
            status.update(completed_epochs=int(trainer.epoch)+int(full),epochs_with_updates=int(trainer.epoch)+1,
                partial_final_epoch=not full,best_checkpoint=str(trainer.best),resume_checkpoint=str(trainer.wdir/'last-resume.pt'),
                validation_metrics=clean(dict(trainer.metrics)))
            write_json(job/'status.json',clean(status))
    model.add_callback('on_train_epoch_start', epoch_start)
    model.add_callback('on_train_batch_end', report)
    model.add_callback('on_fit_epoch_end', epoch_end)
    model.add_callback('on_train_start', lambda trainer: report(trainer, True))
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    try:
        result = model.train(trainer=extension_trainer_class(), data=str(dataset / 'dataset.yaml'),
            project=str(job.parent), name=job.name, exist_ok=True, epochs=10000,
            time=max(.01, (available_seconds(hours,elapsed(),control['training_deadline_utc'],datetime.now(timezone.utc)) - 180) / 3600),
            imgsz=512, batch=32, workers=0, device=0, amp=True, cache=False,
            optimizer='AdamW', lr0=.001, lrf=.1, cos_lr=True, patience=50,
            seed=16, deterministic=True, plots=False, val=True, save=True, save_period=1,
            close_mosaic=10, verbose=False, resume=str(checkpoint) if resume_optimizer else False)
        status.update(stage='trained_pending_evaluation', updated_at=datetime.now(timezone.utc).isoformat(),
            training_job_elapsed_seconds=elapsed(), epochs_with_updates=max(batches)+1 if batches else 0,
            partial_final_epoch=bool(batches) and batches[max(batches)] < status.get('batches_per_epoch', 0),
            final_training_metrics=clean(result.results_dict) if result else None,
            quality_accepted=False, active_model_unchanged=True)
        status.update(best_checkpoint=str(model.trainer.best),resume_checkpoint=str(model.trainer.wdir/'last-resume.pt'))
        write_json(job / 'status.json', clean(status))
    except BaseException:
        status.update(stage='training_failed', updated_at=datetime.now(timezone.utc).isoformat(), training_job_elapsed_seconds=elapsed())
        write_json(job / 'status.json', clean(status))
        raise
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


def supervise(dataset, job, hours, resume, cutoff_utc):
    accepted_export(dataset)
    preflight=json.loads((dataset/'preflight.json').read_text(encoding='utf-8'))
    if preflight.get('status')!='passed' or preflight.get('export_sha256')!=hashlib.sha256((dataset/'export.json').read_bytes()).hexdigest():
        raise ValueError('Concrete export preflight required before spending the training budget')
    if not job.resolve().is_relative_to((PROCESSED / 'ml-runs').resolve()):
        raise ValueError('Extension job must stay in ignored ml-runs')
    now = datetime.now(timezone.utc)
    consumed = 0.
    excluded_pause = 0.
    first = now.isoformat()
    ledger_path=PROCESSED/'ML-05-budget.json'
    if resume:
        previous = json.loads((job / 'status.json').read_text())
        if previous['stage'] in ('trained_pending_evaluation','evaluating_candidate','evaluated_candidate_pending_api_integration'):
            raise ValueError('Completed runs require evaluation, not additional unrequested training')
        first = previous['created_at']
        ledger=json.loads(ledger_path.read_text(encoding='utf-8'))
        if ledger['job']!=str(job) or ledger['first_started_at']!=first or hours>ledger['training_budget_hours']:
            raise ValueError('Resume must preserve the authorized job and reduced budget')
        # Reject concurrent launchers/workers for this exact job before mutation.
        import psutil,os
        ancestors={p.pid for p in psutil.Process().parents()}
        for proc in psutil.process_iter(['pid','cmdline']):
            if proc.pid==os.getpid() or proc.pid in ancestors:continue
            try:
                args=proc.info['cmdline'] or []
                if 'ml.train_extension' in args and '--job' in args and Path(args[args.index('--job')+1]).resolve()==job:
                    raise ValueError('An extension trainer/supervisor is already running')
            except (psutil.NoSuchProcess,psutil.AccessDenied):pass
        pause=json.loads((job/'pause.json').read_text(encoding='utf-8')) if (job/'pause.json').exists() else {}
        old_control=json.loads((job/'control.json').read_text(encoding='utf-8'))
        checkpoint=job/'weights/last-resume.pt'
        checkpoint_sha=hashlib.sha256(checkpoint.read_bytes()).hexdigest() if checkpoint.exists() else None
        consumed,excluded_pause=resume_consumed(previous,old_control,pause,ledger,now,checkpoint_sha)
    else:
        job.mkdir(parents=True, exist_ok=False)
    remaining = available_seconds(hours,consumed,cutoff_utc,now)
    if remaining < 300:
        raise ValueError('Extension budget/cutoff exhausted')
    if resume:
        if excluded_pause:
            ledger.update(pause_resume_dispatch_at=now.isoformat(),verified_pause_excluded_seconds=excluded_pause,
                resume_authorized_by_owner_at=now.isoformat(),training_cutoff_utc=cutoff_utc)
            write_json(ledger_path,ledger)
    else:
        # Exclusive creation prevents another job name from resetting the same
        # owner authorization to a second four-hour budget.
        with ledger_path.open('x',encoding='utf-8') as ledger:
            json.dump(dict(task='ML-05',job=str(job),first_started_at=first,training_budget_hours=hours,
                owner_authorization='2026-10-16 one additional run, maximum four hours'),ledger,indent=2)
    resume_without_updates=resume and previous.get('epochs_with_updates',0)==0 and previous.get('batches_seen_in_epoch',0)==0 and not (job/'weights/last-resume.pt').exists()
    write_json(job / 'control.json', dict(first_started_at=first, child_dispatch_at=now.isoformat(),
        consumed_before_child_seconds=consumed, training_budget_hours=hours,resume_without_updates=bool(resume_without_updates),
        training_deadline_utc=(now+timedelta(seconds=remaining)).isoformat(),verified_pause_excluded_seconds=excluded_pause))
    command = [sys.executable, '-m', 'ml.train_extension', '--dataset', str(dataset), '--job', str(job), '--hours', str(hours)]
    if resume:
        command.append('--resume')
    with (job / 'stdout.log').open('a', encoding='utf-8') as stdout, (job / 'stderr.log').open('a', encoding='utf-8') as stderr:
        child = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        state = dict(task='ML-05', stage='training', training_budget_hours=hours, first_started_at=first,
            train_pid=child.pid, job=str(job), dataset=str(dataset), active_model_unchanged=True,
            restart_authorized=True,verified_pause_excluded_seconds=excluded_pause,
            latest_expected_deadline_utc=(now+timedelta(seconds=remaining)).isoformat())
        write_json(PROCESSED / 'ML-05-job.json', state)
        deadline = time.monotonic() + remaining
        while child.poll() is None:
            if time.monotonic() >= deadline:
                from .processes import stop_child
                stop_child(child)
                state.update(stage='training_budget_terminated_pending_checkpoint_review', updated_at=datetime.now(timezone.utc).isoformat())
                write_json(PROCESSED / 'ML-05-job.json', state)
                raise RuntimeError('Four-hour guard stopped only its own training child')
            time.sleep(1)
        state.update(stage='trained_pending_evaluation' if child.returncode == 0 else 'training_failed',
            updated_at=datetime.now(timezone.utc).isoformat(), exit_code=child.returncode)
        write_json(PROCESSED / 'ML-05-job.json', state)
        if child.returncode:
            raise RuntimeError('Extension training failed; active model67 is unchanged')
    state.update(stage='evaluating_candidate',updated_at=datetime.now(timezone.utc).isoformat())
    write_json(PROCESSED/'ML-05-job.json',state)
    command=[sys.executable,'-m','ml.evaluate_extension','--dataset',str(dataset),'--job',str(job)]
    with (job/'evaluation.stdout.log').open('w',encoding='utf-8') as stdout, (job/'evaluation.stderr.log').open('w',encoding='utf-8') as stderr:
        result=subprocess.run(command,cwd=ROOT,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
    state.update(stage='evaluated_candidate_pending_api_integration' if result.returncode==0 else 'evaluation_failed',
        updated_at=datetime.now(timezone.utc).isoformat(),evaluation_exit_code=result.returncode)
    write_json(PROCESSED/'ML-05-job.json',state)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--hours', type=float, default=3)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--supervise', action='store_true')
    parser.add_argument('--cutoff-utc',help='Required supervisor cutoff, including timezone; owner target 13:00 UTC+7')
    args = parser.parse_args()
    if args.supervise:
        if not args.cutoff_utc:parser.error('--cutoff-utc is required when supervising')
        supervise(args.dataset.resolve(),args.job.resolve(),args.hours,args.resume,args.cutoff_utc)
    else:
        train(args.dataset.resolve(),args.job.resolve(),args.hours,args.resume)
