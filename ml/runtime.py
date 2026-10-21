"""Local ML paths/settings. Import before torch/Ultralytics; no cloud tracking."""
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PROCESSED=ROOT/'data/processed'


def configure():
    config=PROCESSED/'ultralytics-settings'
    (config/'Ultralytics').mkdir(parents=True,exist_ok=True)
    os.environ['YOLO_CONFIG_DIR']=str(config)
    os.environ['YOLO_AUTOINSTALL']='false'
    os.environ['YOLO_OFFLINE']='true'
    os.environ['YOLO_VERBOSE']='false'
    os.environ['OMP_NUM_THREADS']='4'
    os.environ['MKL_NUM_THREADS']='4'
    os.environ['MPLCONFIGDIR']=str(PROCESSED/'matplotlib-cache')
    from ultralytics import settings
    settings.update({'sync':False,'datasets_dir':str(PROCESSED),'runs_dir':str(PROCESSED/'ml-runs'),
                     'weights_dir':str(ROOT/'ml/models/pretrained')})
    import torch
    torch.set_num_threads(4)
    return torch


def write_json(path,value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    temporary.replace(path)
