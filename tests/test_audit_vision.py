from dataclasses import replace
import hashlib
from io import StringIO
from pathlib import Path

import pytest

from scripts import audit_vision as a
from scripts import export_detector_dataset as e


def item(**changes):
    values=dict(id='train/example',split='train',included=True,status='food',reason='',groups=('family','video','prefix'),
                image_rel='images/train/example.jpg',label_rel='labels/train/train/example.txt',image_bytes=3,label_bytes=0,
                label_sha='',copies=1,food_boxes=1,face_boxes=0,objects=1,background=False,crc=0,rank=b'a')
    return a.ImageRow(**(values|changes))


@pytest.mark.parametrize('original,expected',[(0,0),(26,26),(28,27),(67,66)])
def test_original_training_remap_preserves_food_training_27(original,expected):
    assert a.training_id(original)==expected


@pytest.mark.parametrize('value',[27,-1,68,True,'28'])
def test_nonfood_or_invalid_original_class_rejected(value):
    with pytest.raises(ValueError):a.training_id(value)


@pytest.mark.parametrize('value',['train/../other','../example','train/example/extra','train\\example','train/C:example','train/','review/example'])
def test_unsafe_or_effective_image_identity_cannot_select_source(value):
    with pytest.raises(ValueError):a.image_identity(value)


def test_root_relocation_nested_labels_and_filename_case_are_supported():
    assert a.relocated_path('E:/old/labels/train/train/Example.txt','labels','train/example')=='labels/train/train/Example.txt'
    assert a.relocated_path('D:\\new\\images\\train\\EXAMPLE.jpg','images','train/example')=='images/train/EXAMPLE.jpg'


@pytest.mark.parametrize('value',['E:/old/images/../train/example.jpg','//server/images/train/example.jpg','E:/images/other/images/train/example.jpg','E:/images/test/example.jpg','E:/images/train/different.jpg'])
def test_invalid_source_path_cannot_be_relocated(value):
    with pytest.raises(ValueError):a.relocated_path(value,'images','train/example')


def test_raw_labels_face_removed_and_physical_line_ids_preserved():
    parsed=a.parse_label(b'27 .5 .5 .2 .2\n\n28 .5 .5 1 1\n')
    assert (parsed['foods'],parsed['faces'],parsed['objects'])==(1,1,2)
    assert parsed['classes']=={27:1}
    assert parsed['fingerprint']==a.fingerprint(3,28,(.5,.5,1.,1.))
    assert a.parse_label(b'')['objects']==0


@pytest.mark.parametrize('label',[b'28 .5 .5 0 1',b'68 .5 .5 1 1',b'28 nan .5 1 1',b'28 .1 .5 .9 1',b'28 .5 .5 1',b'28 .5 .5 1 1 extra',b'28.0 .5 .5 1 1'])
def test_invalid_yolo_geometry_class_or_row_is_rejected(label):
    with pytest.raises(ValueError):a.parse_label(label)


def test_equivalent_numeric_label_forms_have_equal_fingerprints():
    assert a.parse_label(b'28 0.5 .500 1 1')['fingerprint']==a.parse_label(b'28 .5 0.5 1.0 1.00')['fingerprint']


def test_all_label_copies_hashed_and_conflicting_copy_is_reported(tmp_path):
    content=b'28 .5 .5 1 1\n'
    files=[]
    for rel in ['labels/train/train/example.txt','labels/train/example.txt']:
        p=tmp_path/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(content)
        s=p.stat();files.append(a.FileInfo(p,rel,s.st_size,s.st_mtime_ns))
    r=item(label_bytes=len(content),label_sha=hashlib.sha256(content).hexdigest(),copies=2,
           fingerprint=a.parse_label(content)['fingerprint'])
    result=a.label_check(r,files)
    assert result['problems']==[] and result['files_hashed']==2 and result['files_parsed']==1
    bad=b'29 .5 .5 1 1\n';files[1].path.write_bytes(bad);s=files[1].path.stat()
    files[1]=a.FileInfo(files[1].path,files[1].rel,s.st_size,s.st_mtime_ns)
    assert any(code=='label_size_or_sha_mismatch' for code,_ in a.label_check(r,files)['problems'])


def test_changed_file_since_inventory_is_rejected(tmp_path):
    p=tmp_path/'images/train/example.jpg';p.parent.mkdir(parents=True);p.write_bytes(b'old')
    s=p.stat();info=a.FileInfo(p,'images/train/example.jpg',s.st_size,s.st_mtime_ns)
    p.write_bytes(b'changed')
    with pytest.raises(ValueError):a.read_stable(info)


def test_sampling_is_order_independent_and_includes_class_background_exclusion():
    rows={f'train/{n}':replace(item(),id=f'train/{n}',rank=bytes([n]),classes=1<<n) for n in range(3)}
    rows['test/bg']=item(id='test/bg',split='test',status='background',background=True,objects=0,food_boxes=0,rank=b'z')
    rows['test/excluded']=item(id='test/excluded',split='excluded',included=False,reason='face_only_image',rank=b'q')
    selected=a.select_decode(rows,1)
    assert selected==a.select_decode(dict(reversed(list(rows.items()))),1)
    assert set(selected)==set(rows)


def test_family_heuristic_does_not_become_exact_video_overlap():
    rows={'a':item(),'b':item(id='valid/another',split='valid',groups=('family','different_video','different_prefix'))}
    overlap=a.source_overlap(rows)
    assert overlap['source_video_family']['valid']['shared_group_count']==1
    assert overlap['source_video_key']['valid']['shared_group_count']==0


def test_output_cannot_alias_config_or_source_hardlink(tmp_path,monkeypatch):
    processed=tmp_path/'processed';processed.mkdir()
    source=tmp_path/'source';source.mkdir()
    config=processed/'config.json';config.write_text('{}')
    csv=source/'data.csv';csv.write_text('immutable')
    monkeypatch.setattr(a,'PROCESSED',processed)
    report=processed/'report.json';report.hardlink_to(csv)
    with pytest.raises(ValueError):a.checked_output(report,config,source,tmp_path/'vision')
    with pytest.raises(ValueError):a.checked_output(config,config,source,tmp_path/'vision')
    assert csv.read_text()=='immutable'


def test_export_label_uses_training_id_and_rejects_face_or_wrong_split():
    r=dict(image_id='train/example',split='train',original_class_id='28',training_class_id='27',
           x_center_norm='.5',y_center_norm='.5',width_norm='1',height_norm='1')
    assert e.export_label(r,item()).startswith('27 ')
    for changed in [r|{'original_class_id':'27'},r|{'training_class_id':'28'},r|{'split':'test'}]:
        with pytest.raises(ValueError):e.export_label(changed,item())


def test_export_never_reuses_existing_or_source_directory(tmp_path,monkeypatch):
    processed=tmp_path/'processed';processed.mkdir()
    monkeypatch.setattr(e,'PROCESSED',processed)
    old=processed/'old';old.mkdir()
    with pytest.raises(ValueError):e.safe_output(old,(tmp_path/'source',))
    with pytest.raises(ValueError):e.safe_output(processed/'source'/'derived',(processed/'source',))
