"""Synthetic adapter unit fixtures; real model acceptance uses held-out bytes."""
import asyncio
from io import BytesIO
import hashlib
import json
from pathlib import Path
import threading

import pytest
from PIL import Image

from backend.app.detector import UltralyticsPredictor,verify_bundle
from backend.app.errors import ApiError
from backend.app.images import CanonicalImage,canonical_image
from backend.app.predictor import ClassMap,PredictorInfo
from ml.train_budget import clean,durable_copy


@pytest.fixture
def bundle(tmp_path):
    mapping=ClassMap()
    source=Path(__file__).resolve().parents[2]/'docs/dataset/food-identities-v1.json'
    (tmp_path/'food-identities-v1.json').write_bytes(source.read_bytes())
    (tmp_path/'weights.pt').write_bytes(b'SYNTHETIC TEST ONLY - NOT MODEL WEIGHTS')
    evaluation={'status':'completed','splits':{'val':{},'test':{}},'synthetic_unit_fixture':True}
    (tmp_path/'evaluation.json').write_text(json.dumps(evaluation),encoding='utf-8')
    manifest=dict(bundle_version=1,stage='evaluated',inference_compatible=True,task='detect',class_count=67,
                  model_version='SYNTHETIC-UNIT-FIXTURE',class_map_version=mapping.version,class_map_sha256=mapping.digest,
                  input_contract='canonical_static_RGB_JPEG_EXIF_applied',bbox_output='xyxy_norm_canonical',imgsz=512,
                  confidence=.25,nms_iou=.7,max_detections=100,weights_file='weights.pt',class_map_file='food-identities-v1.json',
                  evaluation_file='evaluation.json',weights_sha256=hashlib.sha256((tmp_path/'weights.pt').read_bytes()).hexdigest(),
                  evaluation_sha256=hashlib.sha256((tmp_path/'evaluation.json').read_bytes()).hexdigest())
    (tmp_path/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    return tmp_path


class Tensor:
    def __init__(self,value):self.value=value
    def detach(self):return self
    def cpu(self):return self
    def tolist(self):return self.value


class Boxes:
    def __init__(self,coords=None,classes=None,scores=None):
        self.xyxy=Tensor(coords if coords is not None else [[10.,5.,90.,45.]])
        self.cls=Tensor(classes if classes is not None else [27.])
        self.conf=Tensor(scores if scores is not None else [.8])


class Engine:
    def __init__(self):
        self.names={t:f['name_vi'] for t,f in ClassMap().foods.items()};self.boxes=Boxes();self.options=None
    def predict(self,image,**kwargs):
        self.options=kwargs
        return [type('Result',(),dict(orig_shape=(image.height,image.width),boxes=self.boxes))()]


def image():
    data=BytesIO();Image.new('RGB',(100,50),'white').save(data,format='JPEG')
    return CanonicalImage(data.getvalue(),100,50)


@pytest.mark.parametrize('file',['weights.pt','food-identities-v1.json','evaluation.json'])
def test_tampered_bundle_artifact_is_rejected_before_loading(bundle,file):
    (bundle/file).write_bytes(b'tampered')
    with pytest.raises(ValueError):verify_bundle(bundle)


@pytest.mark.parametrize('change',[{'class_count':80},{'stage':'training'},{'weights_file':'../weights.pt'},
                                   {'confidence':float('nan')},{'imgsz':513},{'max_detections':101},{'bundle_version':True}])
def test_unsupported_bundle_contract_cannot_become_ready(bundle,change):
    p=bundle/'manifest.json';m=json.loads(p.read_text());p.write_text(json.dumps(m|change))
    with pytest.raises(ValueError):verify_bundle(bundle)


def test_coco_or_wrong_name_order_is_not_a_foodlens_model(bundle):
    e=Engine();e.names={i:str(i) for i in range(80)}
    with pytest.raises(ValueError):UltralyticsPredictor(bundle,loader=lambda _:e)


def test_pixel_xyxy_is_normalized_to_canonical_dimensions(bundle):
    e=Engine();p=UltralyticsPredictor(bundle,loader=lambda _:e)
    rows=asyncio.run(p.predict(image(),p.status()))
    assert rows[0].training_class_id==27 and rows[0].bbox==[.1,.1,.9,.9]
    detections=ClassMap().detections(rows)
    assert detections[0]['original_class_id']==28 and 'alternatives' not in detections[0]
    assert e.options['max_det']==100 and e.options['imgsz']==512


def test_empty_real_result_stays_empty(bundle):
    e=Engine();e.boxes=Boxes([],[],[]);p=UltralyticsPredictor(bundle,loader=lambda _:e)
    assert asyncio.run(p.predict(image(),p.status()))==[]


@pytest.mark.parametrize('boxes',[Boxes(classes=[27.5]),Boxes(scores=[float('inf')]),Boxes(coords=[[0.,0.,101.,50.]]),Boxes(coords=[[90.,5.,10.,45.]])])
def test_invalid_detector_outputs_fail_without_fabricating_detections(bundle,boxes):
    e=Engine();e.boxes=boxes;p=UltralyticsPredictor(bundle,loader=lambda _:e)
    with pytest.raises(ApiError) as caught:asyncio.run(p.predict(image(),p.status()))
    assert caught.value.code=='PREDICTION_FAILED'


def test_expected_model_version_is_enforced(bundle):
    p=UltralyticsPredictor(bundle,loader=lambda _:Engine())
    bad=PredictorInfo('different',p.info.class_map_version,p.info.class_map_sha256)
    with pytest.raises(ApiError) as caught:asyncio.run(p.predict(image(),bad))
    assert caught.value.code=='MODEL_NOT_READY'


def test_cancelled_request_keeps_model_exclusive_until_worker_finishes(bundle):
    entered,release=threading.Event(),threading.Event()
    e=Engine();original=e.predict;calls=[]
    def blocked(*args,**kwargs):
        calls.append(1);entered.set();release.wait(3)
        return original(*args,**kwargs)
    e.predict=blocked;p=UltralyticsPredictor(bundle,loader=lambda _:e)
    async def scenario():
        first=asyncio.create_task(p.predict(image(),p.status()))
        while not entered.is_set():await asyncio.sleep(.005)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):await first
        assert p.lock.locked()
        second=asyncio.create_task(p.predict(image(),p.status()))
        await asyncio.sleep(.02)
        assert len(calls)==1
        second.cancel()
        with pytest.raises(asyncio.CancelledError):await second
        release.set()
        for _ in range(100):
            if not p.lock.locked():break
            await asyncio.sleep(.005)
        assert not p.lock.locked()
    try:asyncio.run(scenario())
    finally:release.set()


def test_optimizer_resume_copy_is_distinct_and_nonfinite_status_is_explicit(tmp_path):
    source=tmp_path/'last.pt';target=tmp_path/'last-resume.pt';source.write_bytes(b'epoch one optimizer')
    durable_copy(source,target);source.write_bytes(b'stripped inference checkpoint')
    assert target.read_bytes()==b'epoch one optimizer'
    assert clean({'loss':float('nan'),'score':float('inf'),'zero':0})=={'loss':None,'score':None,'zero':0}
    assert clean({'box':Tensor([.2,.4]),'class':Tensor(.5)})=={'box':[.2,.4],'class':.5}


def test_optional_library_image_open_patch_cannot_bypass_upload_errors(monkeypatch):
    from tests.backend.test_scans import settings
    def codec_fallback(*args,**kwargs):raise ModuleNotFoundError('unsupported codec fixture')
    monkeypatch.setattr(Image,'open',codec_fallback)
    with pytest.raises(ApiError) as caught:canonical_image(b'not image','image/jpeg',settings())
    assert caught.value.status==422 and caught.value.code=='INVALID_IMAGE'
    valid=image()
    assert canonical_image(valid.data,'image/jpeg',settings()).width==100
