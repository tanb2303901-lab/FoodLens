"""Identity/nullable ID/bundle gates; synthetic fixtures are not ML accuracy."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from backend.app.predictor import ClassMap,PredictorInfo
from backend.app.models import Detection,Food,Scan
from backend.app.errors import ApiError
from backend.app.detector import verify_bundle

V2='foodlens-75-2026-10-16-v2'


def detection(c=69,original=None):
    return dict(detection_id=str(uuid4()),predicted_food_id=ClassMap(V2).foods[c]['id'],
        training_class_id=c,original_class_id=original,bbox=[.1,.1,.9,.9],confidence=.8)


def test_extension_keeps_all_legacy_identities_and_face_exclusion():
    old,new=ClassMap(),ClassMap(V2)
    assert {i:new.foods[i] for i in range(67)}==old.foods
    assert all(new.foods[i]['original_class_id'] is None for i in range(67,75))
    assert new.foods[27]['original_class_id']==28
    assert new.foods[69]['name_vi']=='Gà nướng'


@pytest.mark.parametrize('c',range(67,75))
def test_new_prediction_maps_to_uuid_and_null_original_without_fake_alternatives(c):
    mapped=ClassMap(V2).detections([dict(training_class_id=c,bbox=[0.,0.,1.,1.],confidence=.9)])[0]
    assert mapped['predicted_food_id']==ClassMap(V2).foods[c]['id']
    assert mapped['original_class_id'] is None and 'alternatives' not in mapped
    assert Detection.model_validate(mapped).training_class_id==c


def test_legacy_predictor_cannot_emit_new_class_or_accept_new_digest():
    old,new=ClassMap(),ClassMap(V2)
    assert not old.compatible(PredictorInfo('TEST',new.version,new.digest))
    with pytest.raises(ApiError):old.detections([dict(training_class_id=67,bbox=[0.,0.,1.,1.],confidence=.9)])
    with pytest.raises(ValueError):ClassMap('untrusted75-map')


@pytest.mark.parametrize('c,original',[(0,None),(27,27),(69,69),(69,0),(74,67)])
def test_null_or_invented_original_id_is_rejected_outside_its_taxonomy(c,original):
    with pytest.raises(ValidationError):Detection.model_validate(detection(c,original))


def test_catalog_extension_and_legacy_are_validated_separately():
    food={k:v for k,v in ClassMap(V2).foods[69].items() if k in Food.model_fields}
    food.update(class_map_version=V2)
    assert Food.model_validate(food).original_class_id is None
    with pytest.raises(ValidationError):Food.model_validate(food|{'class_map_version':ClassMap().version})


@pytest.fixture
def extension_bundle(tmp_path):
    root=Path(__file__).resolve().parents[2];mapping=ClassMap(V2)
    (tmp_path/mapping.filename).write_bytes((root/'docs/dataset'/mapping.filename).read_bytes())
    (tmp_path/'weights.pt').write_bytes(b'SYNTHETIC UNIT FIXTURE ONLY')
    evaluation=dict(status='completed',evaluation_export_sha256='a'*64,synthetic_unit_fixture=True,splits={
        'legacy_valid':{},'legacy_test':{},'extension_valid':{'present_classes':list(range(67,75))},
        'extension_test':{'present_classes':list(range(67,75))}})
    (tmp_path/'evaluation.json').write_text(json.dumps(evaluation))
    manifest=dict(bundle_version=2,stage='evaluated',inference_compatible=True,task='detect',class_count=75,
        model_version='SYNTHETIC-UNIT-FIXTURE75',class_map_version=V2,class_map_sha256=mapping.digest,
        input_contract='canonical_static_RGB_JPEG_EXIF_applied',bbox_output='xyxy_norm_canonical',imgsz=512,
        confidence=.25,nms_iou=.7,max_detections=100,weights_file='weights.pt',class_map_file=mapping.filename,
        evaluation_file='evaluation.json',training={'dataset_export_sha256':'a'*64},
        weights_sha256=hashlib.sha256((tmp_path/'weights.pt').read_bytes()).hexdigest(),
        evaluation_sha256=hashlib.sha256((tmp_path/'evaluation.json').read_bytes()).hexdigest())
    (tmp_path/'manifest.json').write_text(json.dumps(manifest));return tmp_path


def test_verified_extension_bundle_and_unchanged_legacy_bundle_both_load_contract(extension_bundle):
    _,mapping,_=verify_bundle(extension_bundle)
    assert len(mapping.foods)==75


@pytest.mark.parametrize('change',[{'stage':'evaluated_candidate_pending_api_integration'}, {'inference_compatible':False},
    {'class_count':67},{'bundle_version':1},{'class_map_file':'../food-identities-v2.json'}])
def test_unapproved_or_mismatched_candidate_cannot_become_ready(extension_bundle,change):
    path=extension_bundle/'manifest.json';manifest=json.loads(path.read_text());path.write_text(json.dumps(manifest|change))
    with pytest.raises(ValueError):verify_bundle(extension_bundle)


def test_extension_bundle_needs_all_eight_held_out_classes(extension_bundle):
    p=extension_bundle/'evaluation.json';data=json.loads(p.read_text());data['splits']['extension_test']['present_classes']=[67]
    p.write_text(json.dumps(data));m=extension_bundle/'manifest.json';manifest=json.loads(m.read_text());manifest['evaluation_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();m.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='eight new classes'):verify_bundle(extension_bundle)


@pytest.mark.parametrize('damage',['none','missing','changed','source_mismatch','policy'])
def test_frozen_legacy_component_and_policy_are_verified(extension_bundle,damage):
    legacy=extension_bundle/'legacy-weights.pt';legacy.write_bytes(b'SYNTHETIC FROZEN LEGACY FIXTURE')
    sha=hashlib.sha256(legacy.read_bytes()).hexdigest()
    p=extension_bundle/'evaluation.json';evaluation=json.loads(p.read_text())
    evaluation['inference_policy']='frozen67_plus_new8_with_parent_precedence'
    if damage=='policy':evaluation['inference_policy']='unverified_policy'
    p.write_text(json.dumps(evaluation))
    m=extension_bundle/'manifest.json';manifest=json.loads(m.read_text())
    manifest.update(architecture='yolo11n-frozen67-plus8',legacy_weights_file='legacy-weights.pt',legacy_weights_sha256=sha,
        evaluation_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    manifest['training']['source_weights_sha256']='f'*64 if damage=='source_mismatch' else sha
    m.write_text(json.dumps(manifest))
    if damage=='missing':legacy.unlink()
    if damage=='changed':legacy.write_bytes(b'TAMPERED SYNTHETIC FIXTURE')
    if damage=='none':assert verify_bundle(extension_bundle)[0]['legacy_weights_sha256']==sha
    else:
        with pytest.raises(ValueError,match='Frozen legacy'):verify_bundle(extension_bundle)


def test_extension_preflight_keeps_active_config_unchanged(extension_bundle,tmp_path,monkeypatch):
    import ml.activate_local as activation
    private=tmp_path/'private';private.mkdir()
    (private/'backend-local.json').write_text(json.dumps({'supabase_url':'http://127.0.0.1:54321'}))
    active=private/'backend-ml.json';active.write_text('UNCHANGED ACTIVE CONFIG SENTINEL')
    monkeypatch.setattr(activation,'PROCESSED',private)
    result=activation.prepare(extension_bundle)
    assert result.name=='backend-ml75-preflight.json'
    assert active.read_text()=='UNCHANGED ACTIVE CONFIG SENTINEL'
    assert json.loads(result.read_text())['model_bundle_path']==str(extension_bundle.resolve())


@pytest.mark.parametrize('damage',['none','legacy_drop','weak_new_class'])
def test_quality_minima_reject_regression_or_a_weak_added_class(extension_bundle,tmp_path,monkeypatch,damage):
    import ml.finish_extension as finish
    old=json.loads((finish.ROOT/'docs/dataset/model-evaluation-v1.json').read_text(encoding='utf-8'))
    p=extension_bundle/'evaluation.json';evaluation=json.loads(p.read_text())
    evaluation['splits']['legacy_valid']['aggregate']=dict(old['splits']['val']['aggregate'])
    if damage=='legacy_drop':evaluation['splits']['legacy_valid']['aggregate']['metrics/mAP50(B)']*=.5
    for split in ('extension_valid','extension_test'):
        evaluation['splits'][split]['per_class']=[dict(training_class_id=c,metrics={'ap50':.7}) for c in range(67,75)]
    if damage=='weak_new_class':evaluation['splits']['extension_test']['per_class'][0]['metrics']['ap50']=.1
    p.write_text(json.dumps(evaluation));m=extension_bundle/'manifest.json';manifest=json.loads(m.read_text())
    manifest['evaluation_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();m.write_text(json.dumps(manifest))
    monkeypatch.setattr(finish,'PROCESSED',tmp_path/'private')
    if damage=='none':assert finish.quality_check(extension_bundle)['status']=='passed'
    else:
        with pytest.raises(ValueError,match='quality minima'):finish.quality_check(extension_bundle)
