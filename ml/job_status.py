"""Print only safe local ML progress; no credentials or private image URLs."""
import json
from datetime import datetime,timezone,timedelta
from pathlib import Path
from .runtime import PROCESSED


def main():
    path=PROCESSED/'ML-job.json'
    if not path.exists():print('ML pipeline has not been started.');return
    state=json.loads(path.read_text(encoding='utf-8'))
    print('Pipeline:',state['stage'])
    print('Last stage update (UTC):',state['updated_at'])
    if 'export_progress' in state and state['stage']=='waiting_for_data':
        data=state['export_progress'];print('Images copied:',data['completed'],'/',data['total'])
    status_path=Path(state['job'])/'status.json'
    if status_path.exists():
        train=json.loads(status_path.read_text(encoding='utf-8'))
        elapsed=train['training_job_elapsed_seconds']
        deadline=train.get('latest_expected_deadline_utc')
        if state['stage']=='training' and train['stage'] in ('initializing','training') and deadline:
            remaining=train['budget_hours']*3600-train.get('prior_elapsed_seconds',0)
            session_start=datetime.fromisoformat(deadline)-timedelta(seconds=remaining)
            elapsed=max(elapsed,train.get('prior_elapsed_seconds',0)+(datetime.now(timezone.utc)-session_start).total_seconds())
        print('Train:',train['stage'],'| elapsed hours:',round(elapsed/3600,2),
              '/',train['budget_hours'],'| completed epochs:',train.get('completed_epochs',0))
        print('Latest deadline (UTC):',deadline or 'not set')
        if deadline:print('Latest deadline (local):',datetime.fromisoformat(deadline).astimezone().isoformat())
        if train['stage']=='training':print('Current epoch batches:',train.get('batches_seen_in_epoch',0),'/',train.get('batches_per_epoch','unknown'))
        print('Config:',train['selected_model'],'batch',train['batch'],'image',train['imgsz'])
    if state['stage']=='failed':print('Stopped at:',state.get('failed_stage'),'| error:',state.get('error_type'))


if __name__=='__main__':main()
