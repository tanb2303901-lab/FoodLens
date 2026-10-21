"""Optional real Ultralytics adapter. Only verified, evaluated local bundles load."""
import asyncio
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import re

from PIL import Image

from .errors import ApiError
from .images import CanonicalImage
from .predictor import ClassMap,PredictorInfo,RawDetection,UnavailablePredictor,model_not_ready


def verify_bundle(path):
    path=Path(path).resolve()
    if not path.is_dir():raise ValueError('Model bundle missing')
    data=json.loads((path/'manifest.json').read_text(encoding='utf-8'))
    mapping=ClassMap(data.get('class_map_version'))
    expected_bundle_version=1 if len(mapping.foods)==67 else 2
    if (type(data.get('bundle_version')) is not int or data['bundle_version']!=expected_bundle_version or data.get('stage')!='evaluated' or data.get('inference_compatible') is not True
        or data.get('task')!='detect' or type(data.get('class_count')) is not int or data['class_count']!=len(mapping.foods)
        or data.get('class_map_version')!=mapping.version or data.get('class_map_sha256')!=mapping.digest
        or data.get('input_contract')!='canonical_static_RGB_JPEG_EXIF_applied' or data.get('bbox_output')!='xyxy_norm_canonical'):
        raise ValueError('Unsupported model bundle contract')
    if not isinstance(data.get('model_version'),str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,128}',data['model_version']):
        raise ValueError('Invalid model version')
    if type(data.get('imgsz')) is not int or not 32<=data['imgsz']<=2048 or data['imgsz']%32:
        raise ValueError('Invalid input image size')
    if type(data.get('max_detections')) is not int or not 1<=data['max_detections']<=100:
        raise ValueError('Invalid detection limit')
    for key in ('confidence','nms_iou'):
        if type(data.get(key)) not in (int,float) or not math.isfinite(data[key]) or not 0<data[key]<=1:
            raise ValueError('Invalid inference threshold')
    for filename,digest in [('weights.pt',data.get('weights_sha256')),
                            (mapping.filename,mapping.digest),('evaluation.json',data.get('evaluation_sha256'))]:
        f=path/filename
        if not f.is_file() or f.is_symlink() or f.resolve().parent!=path or not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):
            raise ValueError('Unsafe/missing bundle artifact')
        if hashlib.sha256(f.read_bytes()).hexdigest()!=digest:raise ValueError('Model artifact checksum mismatch')
    if data.get('weights_file')!='weights.pt' or data.get('class_map_file')!=mapping.filename or data.get('evaluation_file')!='evaluation.json':
        raise ValueError('Unsupported artifact filenames')
    evaluation=json.loads((path/'evaluation.json').read_text(encoding='utf-8'))
    expected_splits={'val','test'} if expected_bundle_version==1 else {'legacy_valid','legacy_test','extension_valid','extension_test'}
    if evaluation.get('status')!='completed' or set(evaluation.get('splits',{}))!=expected_splits:
        raise ValueError('Real validation/test evaluation missing')
    if expected_bundle_version==2:
        if evaluation.get('evaluation_export_sha256')!=data.get('training',{}).get('dataset_export_sha256'):
            raise ValueError('Extension training/evaluation export mismatch')
        for split in ('extension_valid','extension_test'):
            if evaluation['splits'][split].get('present_classes')!=list(range(67,75)):
                raise ValueError('All eight new classes require actual held-out evaluation')
        if data.get('architecture')=='yolo11n-frozen67-plus8':
            legacy=path/'legacy-weights.pt'
            expected=data.get('legacy_weights_sha256')
            if (data.get('legacy_weights_file')!='legacy-weights.pt' or not isinstance(expected,str)
                or expected!=data.get('training',{}).get('source_weights_sha256')
                or not legacy.is_file() or legacy.is_symlink() or legacy.resolve().parent!=path
                or hashlib.sha256(legacy.read_bytes()).hexdigest()!=expected
                or evaluation.get('inference_policy')!='frozen67_plus_new8_with_parent_precedence'):
                raise ValueError('Frozen legacy component/policy verification failed')
    return data,mapping,path/'weights.pt'


class UltralyticsPredictor:
    def __init__(self,path,device='cpu',loader=None):
        self.bundle,self.map,weights=verify_bundle(path)
        if device not in ('cpu','cuda:0'):raise ValueError('Unsupported inference device')
        self.device=device
        real_loader=loader is None
        if real_loader:
            # ML dependencies are optional in the core backend environment.
            from ml.runtime import configure
            configure()
            from ultralytics import YOLO
            if self.bundle.get('architecture')=='yolo11n-frozen67-plus8':
                from ml.dual75 import load_yolo
                loader=lambda path:load_yolo(path,Path(path).parent/'legacy-weights.pt')
            else:loader=YOLO
        self.model=loader(str(weights))
        names=self.model.names
        expected={t:f['name_vi'] for t,f in self.map.foods.items()}
        if not isinstance(names,dict) or names!=expected:
            raise ValueError('Loaded model is not the exact versioned FoodLens detector')
        self.info=PredictorInfo(self.bundle['model_version'],self.map.version,self.map.digest)
        self.lock=asyncio.Lock()
        if real_loader:
            # Technical warmup only, never persisted or presented as a detection.
            warmup=BytesIO();Image.new('RGB',(64,64),'white').save(warmup,format='JPEG')
            self.infer(CanonicalImage(warmup.getvalue(),64,64))

    def status(self):return self.info

    def infer(self,image):
        with Image.open(BytesIO(image.data)) as opened:
            rgb=opened.convert('RGB')
            if rgb.size!=(image.width,image.height):raise ValueError('Canonical dimensions mismatch')
            outputs=self.model.predict(rgb,imgsz=self.bundle['imgsz'],conf=self.bundle['confidence'],
                                       iou=self.bundle['nms_iou'],max_det=self.bundle['max_detections'],
                                       device=self.device,verbose=False)
        if len(outputs)!=1 or tuple(outputs[0].orig_shape)!=(image.height,image.width):
            raise ValueError('Detector coordinates do not match canonical image')
        boxes=outputs[0].boxes
        if boxes is None:return []
        coords=boxes.xyxy.detach().cpu().tolist()
        classes=boxes.cls.detach().cpu().tolist()
        scores=boxes.conf.detach().cpu().tolist()
        if not len(coords)==len(classes)==len(scores) or len(coords)>self.bundle['max_detections']:
            raise ValueError('Invalid detector result lengths')
        from .taxonomy import keep_specific_foods
        keep=keep_specific_foods(coords,classes,scores) if self.bundle.get('architecture')=='yolo11n-frozen67-plus8' else range(len(coords))
        rows=[]
        for index in keep:
            xyxy,c,score=coords[index],classes[index],scores[index]
            if not math.isfinite(c) or int(c)!=c:raise ValueError('Noninteger predicted class')
            row=RawDetection(training_class_id=int(c),bbox=[xyxy[0]/image.width,xyxy[1]/image.height,xyxy[2]/image.width,xyxy[3]/image.height],
                             confidence=float(score))
            if row.bbox[0]>=row.bbox[2] or row.bbox[1]>=row.bbox[3]:raise ValueError('Invalid box geometry')
            rows.append(row)
        return rows

    async def predict(self,image,info):
        if info!=self.info:raise model_not_ready()
        await self.lock.acquire()
        task=asyncio.create_task(asyncio.to_thread(self.infer,image))
        def finished(done):
            # A canceled HTTP request must not release the non-thread-safe GPU model
            # while its worker is still running. shield keeps this task alive.
            self.lock.release()
            if not done.cancelled():done.exception()
        task.add_done_callback(finished)
        try:return await asyncio.shield(task)
        except asyncio.CancelledError:raise
        except Exception:raise ApiError(503,'PREDICTION_FAILED','Detector inference failed.') from None


def configured_predictor(settings):
    if settings.model_bundle_path is None:return UnavailablePredictor()
    try:return UltralyticsPredictor(settings.model_bundle_path,settings.model_device)
    except Exception:
        # Invalid config/artifact/optional dependency never takes core APIs down.
        import logging
        logging.getLogger(__name__).warning('Real detector is unavailable; verify local model bundle and ML runtime.')
        return UnavailablePredictor()
