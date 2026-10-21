"""Independent local ML pipeline: wait for prepared data, train, evaluate, test API.

This process makes no Codex/OpenAI calls. A failure stops later stages and records
the phase; it never enables a fake detector or silently retries a failed train.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys
import time

from .runtime import ROOT,PROCESSED,write_json
from .processes import stop_child


def stamp():return datetime.now(timezone.utc).isoformat()


def main(dataset,job,bundle,hours):
    if not 0<hours<=8:raise ValueError('Budget must be positive and at most eight training hours')
    state_file=PROCESSED/'ML-job.json'
    state=dict(stage='waiting_for_data',created_at=stamp(),updated_at=stamp(),budget_hours=hours,
               dataset=str(dataset),job=str(job),bundle=str(bundle),pid=__import__('os').getpid(),
               script_scope='train/eval/real local API integration; mobile/nutrition approval separate')
    write_json(state_file,state)
    def update(stage,**kwargs):
        state.update(stage=stage,updated_at=stamp(),**kwargs);write_json(state_file,state)
        print('ML pipeline:',stage,flush=True)
    def step(stage,args,timeout):
        update(stage)
        child=subprocess.Popen([sys.executable,*args],cwd=ROOT)
        update(stage,child_pid=child.pid)
        started=time.monotonic()
        while child.poll() is None:
            if time.monotonic()-started>timeout:
                # This is an explicitly-owned child and its recorded checkpoint is
                # preserved; no other process or source data is touched.
                stop_child(child)
                raise TimeoutError('Owned ML stage exceeded its wall-clock guard')
            time.sleep(5)
        if child.returncode:raise RuntimeError(stage+' failed with exit '+str(child.returncode))
        state.pop('child_pid',None)
    awake=False
    try:
        import ctypes
        if hasattr(ctypes,'windll'):awake=bool(ctypes.windll.kernel32.SetThreadExecutionState(0x80000001))
        deadline=time.monotonic()+7200
        while not (dataset/'export.json').exists():
            progress=dataset/'progress.json'
            if progress.exists():
                try:update('waiting_for_data',export_progress=json.loads(progress.read_text(encoding='utf-8')))
                except json.JSONDecodeError:pass
            if time.monotonic()>deadline:raise TimeoutError('Dataset export wait exceeded two hours')
            time.sleep(30)
        benchmark=PROCESSED/'ml-benchmark/results.json'
        if json.loads(benchmark.read_text(encoding='utf-8'))['status']!='completed':raise RuntimeError('Benchmark incomplete')
        smoke=PROCESSED/'ml-runs/checkpoint-smoke-v3/status.json'
        smoke_deadline=time.monotonic()+600
        while True:
            status=json.loads(smoke.read_text(encoding='utf-8')) if smoke.exists() else {}
            if status.get('stage')=='trained_pending_evaluation':break
            if status.get('stage') in ('failed','interrupted'):raise RuntimeError('Checkpoint smoke did not pass')
            if time.monotonic()>smoke_deadline:raise TimeoutError('Checkpoint smoke wait timeout')
            time.sleep(5)
        if not Path(status['resume_checkpoint']).is_file():raise RuntimeError('Durable optimizer checkpoint missing')
        step('training',['-m','ml.train_budget','--dataset',str(dataset),'--job',str(job),
                          '--benchmark',str(benchmark),'--hours',str(hours)],hours*3600)
        step('evaluating',['-m','ml.evaluate_bundle','--dataset',str(dataset),'--job',str(job),'--bundle',str(bundle)],3600)
        step('real_api_test',[str(ROOT/'scripts/test_model_local.py'),'--bundle',str(bundle),'--dataset',str(dataset)],1800)
        step('activating_local',['-m','ml.activate_local','--bundle',str(bundle),'--activate'],180)
        update('ready_for_owner_test',completed_at=stamp(),quality_scope='experimental baseline; see real evaluation and incomplete holdout coverage')
    except BaseException as exc:
        state['failed_stage']=state['stage']
        update('failed',error_type=type(exc).__name__,action='Inspect local log/status; preserve checkpoints; core backend remains separately configured')
        raise
    finally:
        if awake:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True);p.add_argument('--job',type=Path,required=True)
    p.add_argument('--bundle',type=Path,required=True);p.add_argument('--hours',type=float,default=8.)
    a=p.parse_args();main(a.dataset.resolve(),a.job.resolve(),a.bundle.resolve(),a.hours)
