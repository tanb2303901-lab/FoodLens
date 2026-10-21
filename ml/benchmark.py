"""Train-time benchmark on a small TRAIN-only derived subset, not accuracy eval."""
import argparse
import gc
import json
from pathlib import Path
import time

from .runtime import ROOT,PROCESSED,configure,write_json


def main(dataset):
    torch=configure()
    from ultralytics import YOLO
    identity=json.loads((ROOT/'docs/dataset/food-identities-v1.json').read_text(encoding='utf-8'))
    # Wait only for enough verified derived copies, while the full export continues.
    deadline=time.monotonic()+1800
    while True:
        files=sorted((dataset/'images/train').glob('*.jpg'))[:384]
        if len(files)>=384:break
        if time.monotonic()>deadline:raise RuntimeError('Derived benchmark image wait timed out')
        time.sleep(5)
    folder=PROCESSED/'ml-benchmark'
    folder.mkdir(exist_ok=True)
    for split,items in [('train',files[:320]),('val',files[320:])]:
        (folder/(split+'.txt')).write_text('\n'.join(p.as_posix() for p in items)+'\n',encoding='utf-8')
    data=folder/'dataset.yaml'
    write_json(data,dict(path=str(folder),train=str(folder/'train.txt'),val=str(folder/'val.txt'),
                         names=[r['name_vi'] for r in sorted(identity['foods'],key=lambda r:r['training_class_id'])],nc=67))
    previous=folder/'results.json'
    results=json.loads(previous.read_text(encoding='utf-8'))['results'] if previous.exists() else []
    finished={(r['model'],r['batch']) for r in results}
    for name,batch in [('yolo26n.pt',16),('yolo11n.pt',16),('yolo26n.pt',32),('yolo11n.pt',32),('yolo11n.pt',64)]:
        if (name,batch) in finished:continue
        torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats()
        started=time.monotonic();batch_times=[]
        model=YOLO(str(ROOT/'ml/models/pretrained'/name))
        def begin(trainer):trainer._bench_step_started=time.monotonic()
        def end(trainer):
            torch.cuda.synchronize()
            batch_times.append(time.monotonic()-trainer._bench_step_started)
        model.add_callback('on_train_batch_start',begin)
        model.add_callback('on_train_batch_end',end)
        try:
            model.train(data=str(data),epochs=1,imgsz=512,batch=batch,device=0,workers=0,cache=False,
                        amp=True,plots=False,save=False,verbose=False,project=str(folder/'runs'),name=name[:-3]+'-b'+str(batch),
                        exist_ok=False,optimizer='AdamW',lr0=.001,seed=20261015,deterministic=False,
                        mosaic=.5,close_mosaic=0,val=False,compile=False)
            steady=batch_times[3:]
            result=dict(model=name,batch=batch,imgsz=512,workers=0,training_steps=len(batch_times),
                        training_images_per_second=(batch*len(steady)/sum(steady)) if steady else None,
                        elapsed_seconds=time.monotonic()-started,peak_allocated_gib=torch.cuda.max_memory_allocated()/2**30,
                        status='passed',not_accuracy_evaluation=True)
        except torch.cuda.OutOfMemoryError:
            result=dict(model=name,batch=batch,status='cuda_oom',not_accuracy_evaluation=True)
        results.append(result)
        write_json(folder/'results.json',dict(status='running',results=results))
        del model;gc.collect();torch.cuda.empty_cache()
    candidates=[r for r in results if r['status']=='passed' and r['training_images_per_second']]
    if not candidates:raise RuntimeError('No successful training benchmark')
    best=max(candidates,key=lambda r:r['training_images_per_second'])
    write_json(folder/'results.json',dict(status='completed',gpu=torch.cuda.get_device_name(0),results=results,
                                        selected=best,selection_basis='observed steady batch throughput; not validation/test accuracy'))
    print('Benchmark completed; selected',best['model'],'batch',best['batch'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,required=True)
    main(p.parse_args().dataset.resolve())
