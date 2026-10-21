"""FOOD-01 content workflow tests: provenance, review gates and sync payload. No DB or network."""
from copy import deepcopy
from datetime import date
import json

import pytest

from scripts import food_content as fc

DOC = fc.load()
TODAY = date(2026, 10, 19)


def doc():
    """Workflow fixture: the real content reset to unreviewed drafts."""
    d = deepcopy(DOC)
    for e in d['descriptions']:
        e.update(content_status='draft', review=None, publication=None)
    return d


def entry(document, slug):
    return next(e for e in document['descriptions'] if e['slug'] == slug)


def test_repository_content_is_valid_and_only_human_decisions_change_status():
    fc.validate(deepcopy(DOC), TODAY)
    sources = {s['source_key']: s for s in DOC['sources']}
    for e in DOC['descriptions']:
        assert e['authoring_method'] == 'ai_assisted_draft'
        if e['content_status'] == 'draft':
            assert e['review'] is None and e['publication'] is None
        else:
            assert not fc.NOT_A_PERSON.search(e['review']['reviewed_by']) and e['review']['notes']
            assert e['review']['content_sha256'] == fc.content_hash(e, sources)
            assert not fc.NOT_A_PERSON.search(e['publication']['published_by'])
    rows, counts = fc.coverage(DOC)
    assert len(rows) == 75 and sum(counts.values()) == 75
    published = {e['slug'] for e in DOC['descriptions'] if e['content_status'] == 'published'}
    assert {r['slug'] for r in rows if r['api_status'] == 'available'} == published


def test_extension_classes_and_broad_scopes_are_covered():
    slugs = {e['slug'] for e in DOC['descriptions']}
    assert {'chuoi', 'tao', 'ga_nuong', 'ca_hoi_nuong', 'khoai_lang', 'khom', 'ca_phe', 'nuoc_ngot'} <= slugs
    for e in DOC['descriptions']:
        if e['slug'] in ('ca_phe', 'nuoc_ngot', 'ga_nuong', 'ca_hoi_nuong', 'khoai_lang', 'xoi', 'lau'):
            assert e['scope_note'] and 'ảnh không cho biết' in e['scope_note']


def test_wikipedia_citations_pin_revisions_and_urls_are_https():
    for s in DOC['sources']:
        assert s['url'].startswith('https://')
        if s['source_kind'] == 'open_license_encyclopedia':
            assert 'oldid=' in s['url'] and s['revision_ref'].startswith('oldid=') and 'CC BY-SA' in s['license_note']


def test_review_requires_a_named_person_and_freezes_exact_content():
    d = doc()
    for tool in ['Claude Code', 'codex', 'ChatGPT', 'AI reviewer', 'Gemini', ' ']:
        with pytest.raises(fc.ContentError):
            fc.review(deepcopy(d), 'pho', tool)
    reviewed = fc.review(d, 'pho', 'Nguyễn Văn Kiểm Thử', at='2026-10-19T10:00:00+07:00')
    assert reviewed['content_status'] == 'reviewed'
    assert reviewed['review']['content_sha256'] == fc.content_hash(reviewed, {s['source_key']: s for s in d['sources']})
    fc.validate(d, TODAY)
    changed = deepcopy(d)
    entry(changed, 'pho')['short_intro'] += ' Thêm câu.'
    with pytest.raises(fc.ContentError, match='content changed after review'):
        fc.validate(changed, TODAY)
    retitled = deepcopy(d)
    next(s for s in retitled['sources'] if s['source_key'] == 'wiki-vi-pho')['title'] = 'Changed'
    with pytest.raises(fc.ContentError, match='content changed after review'):
        fc.validate(retitled, TODAY)


def test_publish_only_after_review_and_retires_previous_version():
    d = doc()
    with pytest.raises(fc.ContentError, match='Only reviewed'):
        fc.publish(deepcopy(d), 'pho', 'Người Phát Hành')
    fc.review(d, 'pho', 'Người Kiểm Thử', at='2026-10-19T10:00:00+07:00')
    fc.publish(d, 'pho', 'Người Phát Hành', at='2026-10-19T11:00:00+07:00')
    rows, counts = fc.coverage(d)
    assert counts['published'] == 1 and next(r for r in rows if r['slug'] == 'pho')['api_status'] == 'available'
    v2 = deepcopy(entry(d, 'pho'))
    v2.update(version=2, content_status='draft', review=None, publication=None, short_intro=v2['short_intro'] + ' Bản 2.')
    d['descriptions'].append(v2)
    fc.review(d, 'pho', 'Người Kiểm Thử', version=2, at='2026-10-20T10:00:00+07:00')
    fc.publish(d, 'pho', 'Người Phát Hành', version=2, at='2026-10-20T11:00:00+07:00')
    assert [(e['version'], e['content_status']) for e in d['descriptions'] if e['slug'] == 'pho'] == [(1, 'retired'), (2, 'published')]
    early = deepcopy(d)
    entry(early, 'banh_mi')  # untouched
    v = [e for e in early['descriptions'] if e['slug'] == 'pho'][-1]
    v['publication']['published_at'] = '2026-10-20T09:00:00+07:00'
    with pytest.raises(fc.ContentError, match='precede review'):
        fc.validate(early, TODAY)


@pytest.mark.parametrize('field,value,message', [
    ('short_intro', 'Món này giúp giảm cân và tốt cho sức khỏe mỗi ngày.', 'health/nutrition'),
    ('characteristics', 'Một bát chứa khoảng 400 kcal năng lượng.', 'health/nutrition'),
    ('short_intro', ' leading space is not trimmed text here ', 'trimmed'),
    ('ingredients_summary', None, 'required'),
])
def test_text_rules(field, value, message):
    d = doc()
    entry(d, 'pho')[field] = value
    with pytest.raises(fc.ContentError, match=message):
        fc.validate(d, TODAY)


def test_every_field_needs_a_citation_and_citations_need_content():
    d = doc()
    e = entry(d, 'banh_khot')
    e['sources'] = [r for r in e['sources'] if r['source_key'] != 'wiki-vi-banh-khot']
    e['sources'][1]['supports'] = ['ingredients_summary', 'characteristics']
    with pytest.raises(fc.ContentError, match='uncited fields origin_text'):
        fc.validate(d, TODAY)
    d = doc()
    entry(d, 'xoi')['sources'][0]['supports'].append('origin_text')
    with pytest.raises(fc.ContentError, match='empty field'):
        fc.validate(d, TODAY)


def test_identity_scope_and_source_rules():
    d = doc()
    entry(d, 'pho')['name_vi'] = 'Pho'
    with pytest.raises(fc.ContentError, match='map75'):
        fc.validate(d, TODAY)
    d = doc()
    entry(d, 'ca_phe')['scope_note'] = None
    for r in entry(d, 'ca_phe')['sources']:
        r['supports'] = [f for f in r['supports'] if f != 'scope_note']
    with pytest.raises(fc.ContentError, match='broad classes'):
        fc.validate(d, TODAY)
    d = doc()
    next(s for s in d['sources'] if s['source_key'] == 'wiki-vi-pho')['revision_ref'] = None
    with pytest.raises(fc.ContentError, match='pin a revision'):
        fc.validate(d, TODAY)
    d = doc()
    d['sources'][0]['accessed_on'] = '2026-12-01'
    with pytest.raises(fc.ContentError, match='future'):
        fc.validate(d, TODAY)
    d = doc()
    d['sources'].append({**d['sources'][0], 'source_key': 'unused-source'})
    with pytest.raises(fc.ContentError, match='Unused sources'):
        fc.validate(d, TODAY)
    d = doc()
    d['sources'][0]['url'] = 'http://vietnam.travel/'
    with pytest.raises(fc.ContentError, match='HTTPS'):
        fc.validate(d, TODAY)


def test_sync_payload_is_deterministic_and_carries_no_review_for_drafts():
    first, second = fc.sync_payload(doc()), fc.sync_payload(doc())
    assert first == second
    assert len({d['id'] for d in first['descriptions']}) == len(first['descriptions'])
    assert fc.source_id('vnat-21-must-try-dishes') == fc.source_id('vnat-21-must-try-dishes') != fc.source_id('wiki-vi-pho')
    for d in first['descriptions']:
        assert d['content_status'] == 'draft' and d['reviewed_by'] is None and d['published_by'] is None
    real = fc.sync_payload(deepcopy(DOC))
    for d in real['descriptions']:
        assert (d['reviewed_by'] is None) == (d['content_status'] == 'draft')
        assert {f for link in d['links'] for f in link['supports']} == {f for f in fc.FIELDS if d[f] is not None}
    assert '$foodlens_content$' not in json.dumps(first, ensure_ascii=False)
