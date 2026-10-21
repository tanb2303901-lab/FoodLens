"""Diagnostic UI readiness/security logic only; no detections or accuracy claims."""
import json

import httpx
import pytest

import scripts.local_scan_test as tool


@pytest.mark.parametrize('classes,accepted,version_match,expected',[
    (67,True,True,False),(75,False,True,False),(75,True,False,False),(75,True,True,True)])
def test_only_the_accepted_active75_model_can_enable_the_new_tool(tmp_path,monkeypatch,classes,accepted,version_match,expected):
    monkeypatch.setattr(tool,'PROCESSED',tmp_path)
    version='SYNTHETIC-READINESS-FIXTURE'
    identity=dict(model_version=version,class_count=classes,class_map_version=tool.MAP75 if classes==75 else 'vietfood-67-2026-10-12-v1')
    monkeypatch.setattr(tool,'active_model',lambda:identity)
    (tmp_path/'ML-05-finish.json').write_text(json.dumps(dict(status='passed' if accepted else 'running',
        model_version=version if version_match else 'OTHER-SYNTHETIC-FIXTURE')))
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'capabilities':{'scan':True}}))) as client:
        assert tool.test_status(client)['ready'] is expected


@pytest.mark.parametrize('health',[[],{'capabilities':{'scan':False}}])
def test_missing_or_invalid_live_readiness_does_not_use_metadata_alone(tmp_path,monkeypatch,health):
    monkeypatch.setattr(tool,'PROCESSED',tmp_path)
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=health))) as client:
        assert tool.test_status(client)['ready'] is False


def test_training_progress_returns_only_public_fields(tmp_path,monkeypatch):
    monkeypatch.setattr(tool,'PROCESSED',tmp_path)
    job=tmp_path/'ml-runs/fixture';job.mkdir(parents=True)
    (tmp_path/'ML-05-job.json').write_text(json.dumps(dict(job=str(job),private_key='SYNTHETIC SECRET')))
    (job/'status.json').write_text(json.dumps(dict(stage='training',completed_epochs=12,checkpoint='/PRIVATE/WEIGHTS',secret='SYNTHETIC SECRET')))
    assert tool.preparation()==dict(stage='training',completed_epochs=12,training_cutoff_local='13:00')


@pytest.mark.parametrize('api,decision,expected',[('passed','authorized',True),('failed','authorized',False),('passed','pending',False)])
def test_owner_preview_ui_requires_real_api_and_explicit_decision(tmp_path,monkeypatch,api,decision,expected):
    monkeypatch.setattr(tool,'PROCESSED',tmp_path)
    identity=dict(model_version='SYNTHETIC-PREVIEW-READINESS',class_count=75,class_map_version=tool.MAP75)
    monkeypatch.setattr(tool,'active_model',lambda:identity)
    (tmp_path/'ML-05-finish.json').write_text(json.dumps(dict(status='owner_preview_ready',model_version=identity['model_version'],
        api_status=api,owner_preview_decision=decision)))
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'capabilities':{'scan':True}}))) as client:
        assert tool.test_status(client)['ready'] is expected


def test_draft_preview_reads_latest_version_and_only_https_sources(tmp_path,monkeypatch):
    doc={'sources':[{'source_key':'ok','title':'T','publisher':'P','url':'https://example.invalid/a'},
                    {'source_key':'bad','title':'X','publisher':'Y','url':'javascript:alert(1)'}],
         'descriptions':[{'food_id':'F','version':1,'content_status':'draft','authoring_method':'ai_assisted_draft','short_intro':'OLD',
                          'sources':[{'source_key':'ok','supports':['short_intro']}]},
                         {'food_id':'F','version':2,'content_status':'draft','authoring_method':'ai_assisted_draft','short_intro':'NEW',
                          'sources':[{'source_key':'ok','supports':['short_intro']},{'source_key':'bad','supports':['short_intro']}]}]}
    path=tmp_path/'content.json';path.write_text(json.dumps(doc),encoding='utf-8')
    monkeypatch.setattr(tool,'CONTENT',path)
    draft=tool.draft_preview('F')
    assert draft['version']==2 and draft['short_intro']=='NEW' and draft['content_status']=='draft'
    assert [s['url'] for s in draft['sources']]==['https://example.invalid/a']
    assert tool.draft_preview('UNKNOWN') is None
    monkeypatch.setattr(tool,'CONTENT',tmp_path/'missing.json')
    assert tool.draft_preview('F') is None


def test_describe_calls_api_once_per_food_and_isolates_failures(monkeypatch):
    monkeypatch.setattr(tool,'draft_preview',lambda food_id:None)
    calls=[]
    class Session:
        def request(self,method,path):
            calls.append((method,path))
            if path.endswith('/BAD/description'):raise httpx.ConnectError('SYNTHETIC')
            return httpx.Response(200,json={'status':'description_unavailable'})
    cards=tool.describe(Session(),['A','BAD'])
    assert calls==[('GET','/v1/foods/A/description'),('GET','/v1/foods/BAD/description')]
    assert cards['A']['api']['status']=='description_unavailable' and cards['BAD']['api']['status']=='error'


@pytest.mark.parametrize('origins,host,origin,mutation,expected',[
    ({'http://127.0.0.1:8765'},'127.0.0.1:8765','http://127.0.0.1:8765',True,True),
    ({'http://127.0.0.1:8765'},'192.168.1.20:8765','http://192.168.1.20:8765',True,False),  # LAN not opted in
    ({'http://127.0.0.1:8765','http://192.168.1.20:8765'},'192.168.1.20:8765','http://192.168.1.20:8765',True,True),
    ({'http://127.0.0.1:8765','http://192.168.1.20:8765'},'192.168.1.20:8765','http://127.0.0.1:8765',True,False),  # cross-origin post
    ({'http://127.0.0.1:8765','http://192.168.1.20:8765'},'192.168.1.20:8765','http://evil.example',False,False),
    ({'http://127.0.0.1:8765','http://192.168.1.20:8765'},'evil.example:8765',None,False,False)])
def test_lan_mode_accepts_only_its_own_origins(origins,host,origin,mutation,expected):
    sent=[]
    class Fake:
        server=type('S',(),{'origins':origins})()
        headers={'Host':host,**({'Origin':origin} if origin else {})}
        send=lambda self,status,payload:sent.append(status)
    assert tool.Handler.local_request(Fake(),mutation=mutation) is expected
    assert sent==([] if expected else [403])
