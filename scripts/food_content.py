"""FOOD-01 food-description content: validate, report coverage, record human review, sync locally.

The JSON file in docs/content is the reviewable source of truth. AI-assisted drafts stay
`draft`; only a named human reviewer may mark an exact content hash `reviewed`, and only a
named publisher may make reviewed content `published` (user-visible). `apply` defaults to a
rolled-back dry-run against the dedicated local stack; `--apply` commits. No reset, no
deletion of database rows, no catalog/profile/scan writes.

  python scripts/food_content.py validate
  python scripts/food_content.py status [--write-coverage]
  python scripts/food_content.py review --slug pho --reviewer "Họ tên người duyệt" [--notes "..."]
  python scripts/food_content.py publish --slug pho --publisher "Họ tên người phát hành"
  python scripts/food_content.py apply [--apply]
"""
import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from uuid import UUID, uuid5

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / 'docs/content/food-descriptions-vi-v1.json'
IDENTITIES = ROOT / 'docs/dataset/food-identities-v2.json'
COVERAGE = ROOT / 'docs/content/food-descriptions-coverage.md'
PROCESSED = ROOT / 'data/processed'
NAMESPACE = UUID('6ba7b811-9dad-11d1-80b4-00c04fd430c8')
FIELDS = ('short_intro', 'origin_text', 'ingredients_summary', 'characteristics', 'scope_note')
REQUIRED = ('short_intro', 'ingredients_summary', 'characteristics')
LIMITS = {'short_intro': (20, 700), 'origin_text': (10, 700), 'ingredients_summary': (10, 700),
          'characteristics': (10, 900), 'scope_note': (10, 500)}
STATUSES = ('draft', 'reviewed', 'published', 'retired')
SOURCE_KINDS = ('government_tourism', 'government', 'university', 'museum', 'book', 'open_license_encyclopedia', 'other')
# Introductory content only: no health advice, nutrition values or medical claims.
OUT_OF_SCOPE = re.compile(r'(chữa|điều trị|phòng bệnh|phòng ngừa|giảm cân|tăng cân|tốt cho sức khỏe|có lợi cho sức khỏe|'
                          r'bổ dưỡng|dinh dưỡng|calo|kcal|vitamin|protein|chất xơ|chất béo|khẩu phần|liều)', re.IGNORECASE)
# Review/publication records a human decision; development tools are not reviewers.
NOT_A_PERSON = re.compile(r'\b(claude|codex|chatgpt|gpt|gemini|antigravity|copilot|ai|bot|llm)\b', re.IGNORECASE)


class ContentError(ValueError):
    pass


def load(path=CONTENT):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(document, path=CONTENT):
    Path(path).write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def source_id(key):
    return str(uuid5(NAMESPACE, 'urn:foodlens:content-source:' + key))


def description_id(entry):
    return str(uuid5(NAMESPACE, f"urn:foodlens:food-description:{entry['slug']}:vi:{entry['version']}"))


def content_hash(entry, sources):
    """Hash of exactly what a reviewer approves: text, citations and cited source metadata."""
    cited = []
    for ref in sorted(entry['sources'], key=lambda r: r['source_key']):
        s = sources[ref['source_key']]
        cited.append({'source_key': ref['source_key'], 'supports': sorted(ref['supports']), 'locator': ref.get('locator'),
                      **{k: s.get(k) for k in ('title', 'publisher', 'url', 'revision_ref', 'accessed_on')}})
    payload = {'food_id': entry['food_id'], 'locale': 'vi', 'version': entry['version'],
               **{f: entry.get(f) for f in FIELDS}, 'sources': cited}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def aware(value, label):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (AttributeError, ValueError):
        raise ContentError(label + ' must be an ISO timestamp') from None
    if parsed.tzinfo is None:
        raise ContentError(label + ' must include a timezone')
    return parsed


def person(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 200 or NOT_A_PERSON.search(value):
        raise ContentError(label + ' must name the human who took this decision, not a tool')


def validate(document, today=None):
    today = today or date.today()
    foods = {f['id']: f for f in load(IDENTITIES)['foods']}
    if document.get('locale') != 'vi' or document.get('class_map_version') != load(IDENTITIES)['class_map_version']:
        raise ContentError('Content must target locale vi and the current map75 identities')
    sources = {}
    for s in document['sources']:
        key = s.get('source_key', '')
        if not re.fullmatch(r'[a-z0-9]+(-[a-z0-9]+)*', key) or len(key) > 100 or key in sources:
            raise ContentError('Invalid or duplicate source_key: ' + str(key))
        if not re.fullmatch(r'https://\S+', s.get('url', '')) or s.get('language') not in ('vi', 'en') or s.get('source_kind') not in SOURCE_KINDS:
            raise ContentError(key + ': HTTPS URL, language vi/en and a known source_kind are required')
        if not all(isinstance(s.get(k), str) and s[k].strip() for k in ('title', 'publisher', 'license_note')):
            raise ContentError(key + ': title, publisher and license_note are required')
        if s['source_kind'] == 'open_license_encyclopedia' and not s.get('revision_ref'):
            raise ContentError(key + ': open-license encyclopedia citations must pin a revision')
        if date.fromisoformat(s['accessed_on']) > today:
            raise ContentError(key + ': accessed_on cannot be in the future')
        sources[key] = s
    used, seen, published = set(), set(), {}
    for e in document['descriptions']:
        label = f"{e.get('slug')} v{e.get('version')}"
        food = foods.get(e.get('food_id'))
        if not food or food['slug'] != e.get('slug') or food['name_vi'] != e.get('name_vi'):
            raise ContentError(label + ': food_id/slug/name_vi must match map75 exactly')
        if type(e.get('version')) is not int or e['version'] < 1 or (e['slug'], e['version']) in seen:
            raise ContentError(label + ': positive unique version required')
        seen.add((e['slug'], e['version']))
        if e.get('content_status') not in STATUSES or e.get('authoring_method') not in ('manual', 'ai_assisted_draft'):
            raise ContentError(label + ': unknown status or authoring method')
        if not isinstance(e.get('drafted_by'), str) or not e['drafted_by'].strip():
            raise ContentError(label + ': drafted_by is required')
        for f in FIELDS:
            value = e.get(f)
            if value is None:
                if f in REQUIRED:
                    raise ContentError(label + ': ' + f + ' is required')
                continue
            low, high = LIMITS[f]
            if not isinstance(value, str) or value != value.strip() or not low <= len(value) <= high:
                raise ContentError(f'{label}: {f} must be trimmed text of {low}..{high} characters')
            if OUT_OF_SCOPE.search(value):
                raise ContentError(f'{label}: {f} contains health/nutrition wording outside the introduction scope')
        if food['scope_kind'] == 'broad_food_category' and not e.get('scope_note'):
            raise ContentError(label + ': broad classes need a scope_note')
        keys = [r.get('source_key') for r in e.get('sources', [])]
        if not keys or len(set(keys)) != len(keys) or any(k not in sources for k in keys):
            raise ContentError(label + ': sources must be unique known source keys')
        for r in e['sources']:
            if not r.get('supports') or len(set(r['supports'])) != len(r['supports']) or not set(r['supports']) <= set(FIELDS):
                raise ContentError(label + ': each citation must list supported fields')
        cited = {f for r in e['sources'] for f in r['supports']}
        missing = [f for f in FIELDS if e.get(f) is not None and f not in cited]
        if missing:
            raise ContentError(label + ': uncited fields ' + ', '.join(missing))
        if [f for f in cited if e.get(f) is None]:
            raise ContentError(label + ': citation supports an empty field')
        used.update(keys)
        status, review, publication = e['content_status'], e.get('review'), e.get('publication')
        if status == 'draft':
            if review is not None or publication is not None:
                raise ContentError(label + ': drafts cannot carry review or publication records')
        else:
            if not isinstance(review, dict):
                raise ContentError(label + ': review record required')
            person(review.get('reviewed_by'), label + ' reviewed_by')
            aware(review.get('reviewed_at'), label + ' reviewed_at')
            if review.get('content_sha256') != content_hash(e, sources):
                raise ContentError(label + ': content changed after review; create a new draft version')
            if status == 'reviewed' and publication is not None:
                raise ContentError(label + ': reviewed content is not yet published')
            if status in ('published', 'retired'):
                if not isinstance(publication, dict):
                    raise ContentError(label + ': publication record required')
                person(publication.get('published_by'), label + ' published_by')
                if aware(publication.get('published_at'), label + ' published_at') < aware(review['reviewed_at'], 'reviewed_at'):
                    raise ContentError(label + ': publication cannot precede review')
            if status == 'published':
                if e['slug'] in published:
                    raise ContentError(label + ': only one published version per food')
                published[e['slug']] = e['version']
    unused = sorted(set(sources) - used)
    if unused:
        raise ContentError('Unused sources: ' + ', '.join(unused))
    return sources


def coverage(document):
    foods = load(IDENTITIES)['foods']
    by_slug = {}
    for e in document['descriptions']:
        by_slug.setdefault(e['slug'], []).append(e)
    rows = []
    for f in foods:
        entries = sorted(by_slug.get(f['slug'], []), key=lambda e: e['version'])
        live = next((e for e in entries if e['content_status'] == 'published'), None)
        latest = entries[-1] if entries else None
        state = 'published' if live else (latest['content_status'] if latest else 'missing')
        rows.append(dict(training_class_id=f['training_class_id'], slug=f['slug'], name_vi=f['name_vi'], scope_kind=f['scope_kind'],
                         state=state, latest_version=latest['version'] if latest else None,
                         api_status='available' if live else 'description_unavailable'))
    counts = {s: sum(r['state'] == s for r in rows) for s in ('published', 'reviewed', 'draft', 'retired', 'missing')}
    return rows, counts


def write_coverage(document, rows, counts):
    lines = ['# Độ phủ dữ liệu mô tả món — FOOD-01', '',
             'Tệp sinh tự động bởi `scripts/food_content.py status --write-coverage` từ '
             '[food-descriptions-vi-v1.json](food-descriptions-vi-v1.json); không sửa tay.', '',
             f"Tổng 75 lớp: published {counts['published']}, reviewed {counts['reviewed']}, draft {counts['draft']}, "
             f"missing {counts['missing']}. API chỉ trả nội dung khi trạng thái là `published`; mọi trạng thái khác trả "
             '`description_unavailable`.', '',
             '| Training ID | Slug | Món | Phạm vi | Trạng thái nội dung | Version mới nhất | API hiện trả |',
             '| --- | --- | --- | --- | --- | --- | --- |']
    for r in rows:
        lines.append(f"| {r['training_class_id']} | `{r['slug']}` | {r['name_vi']} | {r['scope_kind']} | {r['state']} | "
                     f"{r['latest_version'] or '—'} | {r['api_status']} |")
    COVERAGE.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def find(document, slug, version=None):
    entries = [e for e in document['descriptions'] if e['slug'] == slug and (version is None or e['version'] == version)]
    if not entries:
        raise ContentError('No description entry for ' + slug)
    return max(entries, key=lambda e: e['version'])


def review(document, slug, reviewer, notes=None, version=None, at=None):
    sources = validate(document)
    person(reviewer, 'reviewer')
    entry = find(document, slug, version)
    if entry['content_status'] != 'draft':
        raise ContentError('Only a draft can be reviewed')
    entry['content_status'] = 'reviewed'
    entry['review'] = {'reviewed_by': reviewer.strip(), 'reviewed_at': at or datetime.now(timezone.utc).isoformat(timespec='seconds'),
                       'content_sha256': content_hash(entry, sources), 'notes': notes}
    validate(document)
    return entry


def publish(document, slug, publisher, version=None, at=None):
    validate(document)
    person(publisher, 'publisher')
    entry = find(document, slug, version)
    if entry['content_status'] != 'reviewed':
        raise ContentError('Only reviewed content can be published')
    for other in document['descriptions']:
        if other['slug'] == slug and other['content_status'] == 'published':
            other['content_status'] = 'retired'
    entry['content_status'] = 'published'
    entry['publication'] = {'published_by': publisher.strip(), 'published_at': at or datetime.now(timezone.utc).isoformat(timespec='seconds')}
    validate(document)
    return entry


def sync_payload(document):
    sources = validate(document)
    payload_sources = [{'id': source_id(k), 'source_key': k, **{f: s.get(f) for f in (
        'title', 'publisher', 'url', 'language', 'source_kind', 'revision_ref', 'accessed_on', 'license_note')}} for k, s in sources.items()]
    descriptions = []
    for e in document['descriptions']:
        review_record, publication = e.get('review') or {}, e.get('publication') or {}
        descriptions.append({'id': description_id(e), 'food_id': e['food_id'], 'version': e['version'],
            'content_status': e['content_status'], 'authoring_method': e['authoring_method'], 'drafted_by': e['drafted_by'],
            'source_check': e.get('source_check') or {}, 'content_sha256': content_hash(e, sources),
            **{f: e.get(f) for f in FIELDS},
            'links': [{'source_id': source_id(r['source_key']), 'supports': sorted(r['supports']), 'locator': r.get('locator')}
                      for r in sorted(e['sources'], key=lambda r: r['source_key'])],
            'reviewed_by': review_record.get('reviewed_by'), 'reviewed_at': review_record.get('reviewed_at'),
            'review_notes': review_record.get('notes'), 'published_by': publication.get('published_by'),
            'published_at': publication.get('published_at')})
    return {'sources': payload_sources, 'descriptions': descriptions}


SYNC_SQL = r"""
do $foodlens_content$
declare doc jsonb:=%(payload)s::jsonb; s jsonb; d jsonb; cur public.food_descriptions; rank_cur int; rank_new int;
 ranks constant jsonb:='{"draft":0,"reviewed":1,"published":2,"retired":3}';
begin
 for s in select value from jsonb_array_elements(doc->'sources') loop
  insert into public.content_sources(id,source_key,title,publisher,url,language,source_kind,revision_ref,accessed_on,license_note)
  values((s->>'id')::uuid,s->>'source_key',s->>'title',s->>'publisher',s->>'url',s->>'language',s->>'source_kind',
   s->>'revision_ref',(s->>'accessed_on')::date,s->>'license_note')
  on conflict(id) do update set source_key=excluded.source_key,title=excluded.title,publisher=excluded.publisher,url=excluded.url,
   language=excluded.language,source_kind=excluded.source_kind,revision_ref=excluded.revision_ref,accessed_on=excluded.accessed_on,
   license_note=excluded.license_note
  where (content_sources.source_key,content_sources.title,content_sources.publisher,content_sources.url,content_sources.language,
   content_sources.source_kind,content_sources.revision_ref,content_sources.accessed_on,content_sources.license_note) is distinct from
   (excluded.source_key,excluded.title,excluded.publisher,excluded.url,excluded.language,excluded.source_kind,excluded.revision_ref,
   excluded.accessed_on,excluded.license_note);
 end loop;
 for d in select value from jsonb_array_elements(doc->'descriptions') loop
  select * into cur from public.food_descriptions where id=(d->>'id')::uuid;
  if not found then
   insert into public.food_descriptions(id,food_id,version,short_intro,origin_text,ingredients_summary,characteristics,scope_note,
    authoring_method,drafted_by,source_check,content_sha256)
   values((d->>'id')::uuid,(d->>'food_id')::uuid,(d->>'version')::int,d->>'short_intro',d->>'origin_text',d->>'ingredients_summary',
    d->>'characteristics',d->>'scope_note',d->>'authoring_method',d->>'drafted_by',d->'source_check',d->>'content_sha256');
   insert into public.food_description_sources(description_id,source_id,supports,locator)
   select (d->>'id')::uuid,(l->>'source_id')::uuid,array(select jsonb_array_elements_text(l->'supports')),l->>'locator'
   from jsonb_array_elements(d->'links') l;
   select * into cur from public.food_descriptions where id=(d->>'id')::uuid;
  elsif cur.content_status='draft' then
   if cur.food_id<>(d->>'food_id')::uuid or cur.version<>(d->>'version')::int then perform foodlens_private.fail('DESCRIPTION_IDENTITY_IMMUTABLE'); end if;
   update public.food_descriptions set short_intro=d->>'short_intro',origin_text=d->>'origin_text',ingredients_summary=d->>'ingredients_summary',
    characteristics=d->>'characteristics',scope_note=d->>'scope_note',authoring_method=d->>'authoring_method',drafted_by=d->>'drafted_by',
    source_check=d->'source_check',content_sha256=d->>'content_sha256'
   where id=cur.id and (short_intro,origin_text,ingredients_summary,characteristics,scope_note,authoring_method,drafted_by,source_check,content_sha256)
    is distinct from (d->>'short_intro',d->>'origin_text',d->>'ingredients_summary',d->>'characteristics',d->>'scope_note',
    d->>'authoring_method',d->>'drafted_by',d->'source_check',d->>'content_sha256');
   if (select coalesce(jsonb_agg(jsonb_build_object('source_id',source_id,'supports',to_jsonb(supports),'locator',locator) order by source_id),'[]')
       from public.food_description_sources where description_id=cur.id) is distinct from
      (select coalesce(jsonb_agg(l order by l->>'source_id'),'[]') from jsonb_array_elements(d->'links') l) then
    delete from public.food_description_sources where description_id=cur.id;
    insert into public.food_description_sources(description_id,source_id,supports,locator)
    select cur.id,(l->>'source_id')::uuid,array(select jsonb_array_elements_text(l->'supports')),l->>'locator'
    from jsonb_array_elements(d->'links') l;
   end if;
   select * into cur from public.food_descriptions where id=cur.id;
  elsif cur.content_sha256<>d->>'content_sha256' then perform foodlens_private.fail('REVIEWED_CONTENT_CHANGED');
  end if;
  rank_cur:=(ranks->>cur.content_status)::int; rank_new:=(ranks->>(d->>'content_status'))::int;
  if rank_new<rank_cur then perform foodlens_private.fail('DESCRIPTION_STATUS_REGRESSION'); end if;
  if rank_cur=0 and rank_new>=1 then
   update public.food_descriptions set content_status='reviewed',reviewed_by=d->>'reviewed_by',reviewed_at=(d->>'reviewed_at')::timestamptz,
    review_notes=d->>'review_notes' where id=cur.id;
  end if;
  if rank_cur<=1 and rank_new>=2 then
   update public.food_descriptions set content_status='retired',is_current=false
    where food_id=cur.food_id and locale='vi' and is_current and id<>cur.id;
   update public.food_descriptions set content_status='published',is_current=true,published_by=d->>'published_by',
    published_at=(d->>'published_at')::timestamptz where id=cur.id;
  end if;
  if rank_new=3 and rank_cur<3 then
   update public.food_descriptions set content_status='retired',is_current=false where id=cur.id;
  end if;
 end loop;
end $foodlens_content$;
select jsonb_build_object('sources',(select count(*) from public.content_sources),'descriptions',(select jsonb_object_agg(content_status,n)
 from (select content_status,count(*) n from public.food_descriptions group by 1) x),
 'links',(select count(*) from public.food_description_sources),
 'db_only',(select coalesce(jsonb_agg(id order by id),'[]') from public.food_descriptions where not (id::text = any(%(ids)s::text[]))));
"""


def apply_local(document, commit=False, report_name=None):
    sys.path.insert(0, str(ROOT / 'scripts'))
    from apply_food_content_schema import snapshot, execute
    from import_dataset import literal
    payload = sync_payload(document)
    text = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    if '$foodlens_content$' in text:
        raise ContentError('Content contains the reserved SQL delimiter')
    ids = 'array[' + ','.join(literal(d['id']) for d in payload['descriptions']) + ']' if payload['descriptions'] else "'{}'"
    before = snapshot()
    sql = ("begin; set local lock_timeout='15s';\n" + SYNC_SQL % {'payload': literal(text), 'ids': ids}
           + ('commit;' if commit else 'rollback;'))
    counts = json.loads(execute(sql).splitlines()[-1])
    after = snapshot()
    if before != after:
        raise RuntimeError('Catalog/profile/scan fingerprints changed during content sync')
    report = dict(task='FOOD-01', mode='apply' if commit else 'dry_run_rolled_back', content_file=str(CONTENT.relative_to(ROOT)),
                  content_sha256=hashlib.sha256(CONTENT.read_bytes()).hexdigest(), database_after=counts,
                  preserved_fingerprints_match=True, generated_at=datetime.now(timezone.utc).isoformat(timespec='seconds'))
    (PROCESSED / (report_name or ('FOOD-01-content-apply.json' if commit else 'FOOD-01-content-dry-run.json'))).write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return report


def main(argv=None):
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('validate')
    status = sub.add_parser('status')
    status.add_argument('--write-coverage', action='store_true')
    for name, who in (('review', '--reviewer'), ('publish', '--publisher')):
        p = sub.add_parser(name)
        p.add_argument('--slug', required=True)
        p.add_argument('--version', type=int)
        p.add_argument(who, required=True, dest='person')
        if name == 'review':
            p.add_argument('--notes')
    apply = sub.add_parser('apply')
    apply.add_argument('--apply', action='store_true', help='Commit to foodlens-local (default: rolled-back dry-run)')
    args = parser.parse_args(argv)
    try:
        document = load()
        if args.command == 'validate':
            validate(document)
            rows, counts = coverage(document)
            print(f"Valid: {len(document['descriptions'])} description entries, {len(document['sources'])} sources; " + json.dumps(counts))
        elif args.command == 'status':
            validate(document)
            rows, counts = coverage(document)
            for r in rows:
                print(f"{r['training_class_id']:>2} {r['slug']:<22} {r['state']:<10} {r['api_status']}")
            print(json.dumps(counts))
            if args.write_coverage:
                write_coverage(document, rows, counts)
        elif args.command == 'review':
            entry = review(document, args.slug, args.person, args.notes, args.version)
            save(document)
            print(f"Reviewed {entry['slug']} v{entry['version']} sha256={entry['review']['content_sha256']}")
        elif args.command == 'publish':
            entry = publish(document, args.slug, args.person, args.version)
            save(document)
            print(f"Published {entry['slug']} v{entry['version']}; run `apply --apply` to sync the local database")
        else:
            report = apply_local(document, args.apply)
            print(json.dumps(report['database_after'], ensure_ascii=False) + ' (' + report['mode'] + ')')
    except ContentError as exc:
        print('Content validation failed: ' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
