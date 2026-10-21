"""Independent local training job with an eight-hour ceiling and durable status.

All dataset/checkpoints/logs stay in ignored project directories. No Codex/OpenAI
API is involved. A completed training job preserves an optimizer resume checkpoint
before Ultralytics strips inference weights during final validation.
"""
import argparse
from datetime import datetime,timedelta,timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import time
import traceback

from .runtime import ROOT,PROCESSED,configure,write_json


def now():return datetime.now(timezone.utc).isoformat()


def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [clean(v) for v in value]
    if hasattr(value,'detach'):return clean(value.detach().cpu().tolist())
    if hasattr(value,'item'):return clean(value.item())
    if isinstance(value,float) and not math.isfinite(value):return None
    return value


def durable_copy(source,target):
    target=Path(target)
    temporary=target.with_suffix(target.suffix+'.tmp')
    shutil.copyfile(source,temporary)
    temporary.replace(target)


def atomic_trainer_class():
    from ultralytics.models.yolo.detect import DetectionTrainer
    class AtomicTrainer(DetectionTrainer):
        def check_resume(self,overrides):
            super().check_resume(overrides)
            if self.resume:
                # Timed runs rewrite epochs to an estimate; an optimizer-bearing
                # checkpoint can continue under its remaining explicit budget.
                self.args.epochs=max(self.args.epochs,int(overrides.get('epochs',self.args.epochs)))
        def save_model(self):
            last,best=self.last,self.best
            pending_last=last.with_name('last.pending.pt')
            pending_best=best.with_name('best.pending.pt')
            self.last,self.best=pending_last,pending_best
            try:
                result=super().save_model()
            finally:
                self.last,self.best=last,best
            if pending_last.exists():pending_last.replace(last)
            if pending_best.exists():pending_best.replace(best)
            if last.exists():durable_copy(last,last.with_name('last-resume.pt'))
            return result
    return AtomicTrainer


def train(dataset,job,hours,benchmark,resume=False):
    if not 0<hours<=8:raise ValueError('Training budget must be positive and at most eight hours')
    if not dataset.resolve().is_relative_to(PROCESSED.resolve()) or not (dataset/'export.json').exists():
        raise ValueError('Completed isolated dataset export required')
    if not job.resolve().is_relative_to((PROCESSED/'ml-runs').resolve()):
        raise ValueError('Job must stay inside ignored ml-runs')
    if job.exists() and not resume:raise ValueError('Existing run is preserved; use explicit resume')
    export=json.loads((dataset/'export.json').read_text(encoding='utf-8'))
    bench=json.loads(benchmark.read_text(encoding='utf-8'))
    if export['status']!='completed' or bench['status']!='completed':raise ValueError('Export/benchmark incomplete')
    chosen=bench['selected']
    fixture=export.get('not_production_dataset') is True
    if not fixture:
        if (export.get('images')!={'train':161247,'valid':787,'test':404}
            or export.get('source_mutated') is not False
            or export.get('class_map_sha256')!=hashlib.sha256((ROOT/'docs/dataset/food-identities-v1.json').read_bytes()).hexdigest()
            or export.get('classes',{}).get('train')!=list(range(67))):
            raise ValueError('Full training requires the exact audited effective split export')
    if chosen['model'] not in ('yolo11n.pt','yolo26n.pt'):raise ValueError('Unexpected pretrained model')
    torch=configure()
    if not torch.cuda.is_available():raise ValueError('CUDA is required for this local budgeted job')
    from ultralytics import YOLO
    job.mkdir(parents=True,exist_ok=resume)
    status_file=job/'status.json'
    previous=json.loads(status_file.read_text(encoding='utf-8')) if resume and status_file.exists() else {}
    consumed=previous.get('training_job_elapsed_seconds',0.)
    remaining=hours*3600-consumed
    if remaining<300:raise ValueError('Budget exhausted; an additional budget needs an explicit new run/decision')
    started=time.monotonic()
    status=dict(stage='initializing',created_at=previous.get('created_at',now()),updated_at=now(),
                budget_hours=hours,prior_elapsed_seconds=consumed,training_job_elapsed_seconds=consumed,
                latest_expected_deadline_utc=(datetime.now(timezone.utc)+timedelta(seconds=remaining)).isoformat(),
                dataset_yaml=str(dataset/'dataset.yaml'),dataset_export_sha256=hashlib.sha256((dataset/'export.json').read_bytes()).hexdigest(),
                selected_model=chosen['model'],batch=chosen['batch'],imgsz=chosen['imgsz'],workers=0,
                gpu=torch.cuda.get_device_name(0),resume=resume,not_accuracy_accepted=True,
                training_scope='checkpoint_smoke_fixture' if fixture else 'full_audited_effective_train')
    write_json(status_file,status)
    last_update=[0.]
    training_started=[None]
    epoch_batches={}
    def epoch_start(trainer):
        # An OOM retry restarts this epoch; earlier batches are not a full pass.
        epoch_batches[int(trainer.epoch)]=0
    def report(trainer,force=False):
        elapsed=consumed+time.monotonic()-started
        epoch=int(getattr(trainer,'epoch',trainer.start_epoch))
        if not force:epoch_batches[epoch]=epoch_batches.get(epoch,0)+1
        status.update(stage='training',updated_at=now(),training_job_elapsed_seconds=elapsed,
                      epoch_index=epoch,completed_epochs=epoch,
                      batch_size=int(trainer.batch_size),batches_per_epoch=len(trainer.train_loader),
                      cuda_allocated_gib=torch.cuda.memory_allocated()/2**30)
        status['batches_seen_in_epoch']=epoch_batches.get(epoch,0)
        if training_started[0] is not None:
            status['training_loop_elapsed_seconds']=time.monotonic()-training_started[0]
        if hasattr(trainer,'loss_items') and trainer.loss_items is not None:
            status['last_loss']=clean(trainer.loss_items)
        if force or time.monotonic()-last_update[0]>=30:
            write_json(status_file,clean(status));last_update[0]=time.monotonic()
        # Reserve time for validation/checkpoint serialization inside the 8h ceiling.
        if elapsed>hours*3600-180:trainer.stop=True
    def train_start(trainer):
        training_started[0]=time.monotonic();report(trainer,True)
    def epoch_end(trainer):
        # Ultralytics final_eval emits this callback once more at epoch+1.
        # It contains validation only and must never add a training epoch.
        if int(trainer.epoch) not in epoch_batches:return
        report(trainer,True)
        full=epoch_batches.get(int(trainer.epoch),0)>=len(trainer.train_loader)
        status['completed_epochs']=int(trainer.epoch)+int(full)
        status['epochs_with_updates']=int(trainer.epoch)+1
        status['partial_final_epoch']=not full
        status['validation_metrics']=clean(dict(trainer.metrics))
        status['resume_checkpoint']=str(trainer.wdir/'last-resume.pt')
        status['best_checkpoint']=str(trainer.best)
        write_json(status_file,clean(status))
    weights=job/'weights/last-resume.pt' if resume else ROOT/'ml/models/pretrained'/chosen['model']
    model=YOLO(str(weights))
    model.add_callback('on_train_start',train_start)
    model.add_callback('on_train_epoch_start',epoch_start)
    model.add_callback('on_train_batch_end',report)
    model.add_callback('on_fit_epoch_end',epoch_end)
    keep_awake=False
    try:
        import ctypes
        if hasattr(ctypes,'windll'):
            keep_awake=bool(ctypes.windll.kernel32.SetThreadExecutionState(0x80000001))
        args=dict(data=str(dataset/'dataset.yaml'),time=max(.001,(remaining-300)/3600),epochs=1000,
                  imgsz=chosen['imgsz'],batch=chosen['batch'],device=0,workers=0,cache=False,amp=True,
                  plots=False,save=True,save_period=-1,verbose=False,project=str(job.parent),name=job.name,exist_ok=True,
                  optimizer='AdamW',lr0=.001,lrf=.01,weight_decay=.0005,momentum=.9,seed=20261015,deterministic=False,
                  mosaic=.5,close_mosaic=0,patience=30,val=True,compile=False)
        model.train(trainer=atomic_trainer_class(),resume=resume,**args)
        status.update(stage='trained_pending_evaluation',updated_at=now(),training_job_elapsed_seconds=consumed+time.monotonic()-started,
                      best_checkpoint=str(model.trainer.best),
                      resume_checkpoint=str(model.trainer.wdir/'last-resume.pt'),validation_metrics=clean(dict(model.trainer.metrics)))
        write_json(status_file,clean(status))
    except BaseException as exc:
        status.update(stage='interrupted' if isinstance(exc,(KeyboardInterrupt,SystemExit)) else 'failed',updated_at=now(),
                      training_job_elapsed_seconds=consumed+time.monotonic()-started,error_type=type(exc).__name__)
        write_json(status_file,clean(status))
        raise
    finally:
        if keep_awake:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
    print('Training complete; checkpoint saved. Real held-out evaluation follows separately.',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--job',type=Path,required=True)
    p.add_argument('--benchmark',type=Path,required=True)
    p.add_argument('--hours',type=float,default=8.)
    p.add_argument('--resume',action='store_true')
    a=p.parse_args()
    train(a.dataset.resolve(),a.job.resolve(),a.hours,a.benchmark.resolve(),a.resume)
