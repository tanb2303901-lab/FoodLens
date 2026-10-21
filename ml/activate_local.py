"""Prepare private model config; optionally restart only this project's server."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .runtime import ROOT,PROCESSED,write_json


def prepare(bundle):
    from backend.app.detector import verify_bundle
    manifest,_,_=verify_bundle(bundle)
    source=PROCESSED/'backend-local.json'
    base=json.loads(source.read_text(encoding='utf-8-sig'))
    if base['supabase_url']!='http://127.0.0.1:54321':raise ValueError('Local stack only')
    filename=('backend-ml75-preflight.json' if manifest['class_count']==75 else
              'backend-ml-preflight.json' if manifest.get('training',{}).get('scope')=='checkpoint_smoke_fixture' else 'backend-ml.json')
    result=PROCESSED/filename
    write_json(result,base|{'model_bundle_path':str(bundle.resolve()),'model_device':'cuda:0'})
    return result


def owner_preview_matches(manifest,quality,decision):
    """A human may preview one exact candidate without rewriting its quality result."""
    failed=[c.get('name') for c in quality.get('checks',[]) if c.get('passed') is not True]
    return (decision.get('authorized_by_owner') is True and decision.get('scope')=='local_owner_preview_only'
        and decision.get('model_version')==manifest.get('model_version')
        and all(isinstance(manifest.get(k),str) and decision.get(k)==manifest[k]
                for k in ('weights_sha256','legacy_weights_sha256','evaluation_sha256','class_map_sha256'))
        and quality.get('status')=='failed' and failed==['extension_test_class_71']
        and quality.get('evaluation_sha256')==manifest.get('evaluation_sha256')
        and quality.get('weights_sha256')==manifest.get('weights_sha256'))


def activate(bundle,owner_preview=False):
    import httpx
    import psutil
    from .processes import stop_child,stop_tree
    from backend.app.detector import verify_bundle
    manifest,_,_=verify_bundle(bundle)
    extension=manifest['class_count']==75
    if owner_preview and not extension:raise ValueError('This owner preview decision applies only to the exact75-class candidate')
    prefix='ML-05' if extension else 'ML-03'
    test=PROCESSED/(prefix+'-model-integration.json')
    evidence=json.loads(test.read_text(encoding='utf-8'))
    if evidence['status']!='passed' or evidence['model_bundle']!=str(bundle.resolve()):
        raise ValueError('Passing real model/API integration evidence required')
    if extension:
        quality=json.loads((PROCESSED/'ML-05-quality-gates.json').read_text(encoding='utf-8'))
        quality_allowed=quality.get('status')=='passed'
        if owner_preview:
            decision=json.loads((PROCESSED/'ML-05-owner-preview.json').read_text(encoding='utf-8'))
            if not owner_preview_matches(manifest,quality,decision):
                raise ValueError('Owner preview authorization must match this exact tested candidate and known quality exception')
            quality_allowed=True
        if (manifest['training'].get('scope')!='owner_extension_75_mixed_replay'
            or manifest['architecture']!='yolo11n-frozen67-plus8'
            or evidence.get('weights_sha256')!=manifest['weights_sha256']
            or evidence.get('legacy_weights_sha256')!=manifest['legacy_weights_sha256']
            or evidence.get('evaluation_sha256')!=manifest['evaluation_sha256']
            or evidence.get('correct_new_classes')!=list(range(67,75))
            or not quality_allowed
            or quality.get('evaluation_sha256')!=manifest['evaluation_sha256']
            or not 0<manifest['training']['elapsed_seconds']<=3*3600
            or manifest['training']['budget_hours']!=3):
            raise ValueError('Extension requires matching real eight-class API and bounded training evidence')
    elif manifest['training'].get('scope')!='full_audited_effective_train':
        raise ValueError('Smoke/partial-fixture models cannot activate the owner backend')
    prepared=prepare(bundle)
    config=PROCESSED/'backend-ml75.json' if extension else prepared
    previous_config_bytes=config.read_bytes() if extension and config.exists() else None
    state=PROCESSED/'backend-server.json'
    old_config=PROCESSED/'backend-ml.json' if extension else PROCESSED/'backend-local.json'
    if state.exists():
        old=json.loads(state.read_text(encoding='utf-8-sig'))
        candidate=Path(old.get('config_path',old_config)).resolve()
        if candidate not in {(PROCESSED/name).resolve() for name in ('backend-local.json','backend-ml.json','backend-ml75-preflight.json','backend-ml75.json')}:
            raise ValueError('Existing backend configuration is not owned by this local stack')
        old_config=candidate
        try:
            proc=psutil.Process(old['pid'])
            if 'create_time' in old and abs(old['create_time']-proc.create_time())>.01:
                # PID was reused after shutdown: this is stale state, never kill it.
                raise psutil.NoSuchProcess(old['pid'])
            allowed={(ROOT/'.venv/Scripts/python.exe').resolve(),(PROCESSED/'ml-venv/Scripts/python.exe').resolve(),
                     Path(getattr(sys,'_base_executable',sys.executable)).resolve()}
            args=proc.cmdline()
            if (Path(proc.exe()).resolve() not in allowed or proc.cwd()!=str(ROOT)
                or 'uvicorn' not in args or 'backend.app.main:app' not in args
                ):
                raise ValueError('Existing PID is not an owned FoodLens backend')
            stop_tree(proc)
        except psutil.NoSuchProcess:pass
    def launch(path,model_bundle=None):
        with (PROCESSED/'backend-server.stdout.log').open('a',encoding='utf-8') as stdout, (PROCESSED/'backend-server.stderr.log').open('a',encoding='utf-8') as stderr:
            process=subprocess.Popen([sys.executable,'-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port','8000','--no-access-log'],
                                     cwd=ROOT,env=dict(os.environ,FOODLENS_CONFIG_PATH=str(path)),stdout=stdout,stderr=stderr,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        write_json(state,dict(pid=process.pid,create_time=psutil.Process(process.pid).create_time(),host='127.0.0.1',port=8000,
                              config_path=str(path),model_bundle=model_bundle))
        return process
    def ready(process,require_model):
        with httpx.Client(timeout=5,trust_env=False) as client:
            for _ in range(120):
                if process.poll() is not None:raise RuntimeError('Owned backend exited during startup')
                try:
                    r=client.get('http://127.0.0.1:8000/health/ready')
                    if r.status_code==200 and (not require_model or r.json()['capabilities']['scan']):
                        if client.get('http://127.0.0.1:8000/docs').status_code!=200:raise RuntimeError('Swagger unavailable')
                        return r.json()
                except httpx.HTTPError:pass
                time.sleep(.5)
        raise RuntimeError('Owned backend did not become ready')
    if extension:write_json(config,json.loads(prepared.read_text(encoding='utf-8')))
    process=None
    try:
        process=launch(config,str(bundle.resolve()))
        readiness=ready(process,True)
        write_json(PROCESSED/(prefix+'-live-smoke.json'),dict(status='passed',readiness=readiness,swagger_status=200,model_bundle=str(bundle.resolve()),
            acceptance_mode='owner_authorized_local_preview' if owner_preview else 'normal_tested_activation'))
    except BaseException:
        if process is not None:stop_child(process)
        if extension and previous_config_bytes is not None:config.write_bytes(previous_config_bytes)
        # Restore the previously selected local model/core, not an untested candidate.
        rollback=launch(old_config)
        core_ready=ready(rollback,False)
        write_json(PROCESSED/(prefix+'-activation-rollback.json'),dict(status='previous_config_restored',readiness=core_ready))
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--activate',action='store_true')
    p.add_argument('--owner-preview',action='store_true',help='Requires exact recorded owner decision; does not mark failed quality as passed')
    a=p.parse_args()
    if a.owner_preview and not a.activate:p.error('--owner-preview requires --activate')
    if a.activate:activate(a.bundle.resolve(),a.owner_preview);print('Local backend now uses the tested real FoodLens model.',flush=True)
    else:prepare(a.bundle.resolve());print('Private local model config prepared; no keys printed.',flush=True)
