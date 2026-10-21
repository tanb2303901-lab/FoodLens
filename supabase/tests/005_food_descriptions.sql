-- FOOD-01 synthetic content fixtures, isolated and rolled back. Safe with imported
-- catalog/history and with real draft/published descriptions already present.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path=public,extensions;
select no_plan();
create temp table content_state(name text primary key,value uuid);
grant all on content_state to authenticated,anon;
insert into content_state values
 ('food',(select id from public.foods where slug='pho')),
 ('broad',(select id from public.foods where slug='ca_phe')),
 ('source','f1010000-0000-4000-8000-000000000001'),
 ('v1','f1010000-0000-4000-8000-000000000011'),
 ('v2','f1010000-0000-4000-8000-000000000012'),
 ('broad_v','f1010000-0000-4000-8000-000000000013');
-- Retiring any real current row is an allowed transition and lets this test publish.
update public.food_descriptions set content_status='retired',is_current=false
 where food_id in (select value from content_state where name in ('food','broad')) and is_current;

select ok((select bool_and(relrowsecurity) from pg_class where oid in
 ('public.content_sources'::regclass,'public.food_descriptions'::regclass,'public.food_description_sources'::regclass)),'RLS enabled on content tables');
select ok(not has_table_privilege('anon','public.food_descriptions','SELECT'),'anon cannot read descriptions');
select ok(not has_table_privilege('anon','public.content_sources','SELECT'),'anon cannot read sources');
select ok(not has_column_privilege('authenticated','public.food_descriptions','reviewed_by','SELECT'),'reviewer identity is not user-readable');
select ok(not has_column_privilege('authenticated','public.food_descriptions','review_notes','SELECT'),'review notes are not user-readable');
select ok(not has_table_privilege('authenticated','public.food_descriptions','INSERT'),'users cannot write descriptions');

insert into public.content_sources(id,source_key,title,publisher,url,language,source_kind,accessed_on,license_note)
 values((select value from content_state where name='source'),'synthetic-test-source','SYNTHETIC TEST SOURCE','SYNTHETIC',
  'https://example.invalid/synthetic','en','other','2026-10-19','SYNTHETIC TEST ONLY');
select throws_ok($$insert into public.food_descriptions(id,food_id,version,content_status,is_current,short_intro,ingredients_summary,characteristics,
 authoring_method,drafted_by,content_sha256,reviewed_by,reviewed_at) values('f1010000-0000-4000-8000-000000000019',
 (select value from content_state where name='food'),899,'reviewed',false,'SYNTHETIC TEST INTRO TEXT ONLY','SYNTHETIC TEST','SYNTHETIC TEST',
 'manual','SYNTHETIC',repeat('a',64),'SYNTHETIC',now())$$,'P0001','DESCRIPTION_STARTS_AS_DRAFT','content cannot be inserted already reviewed');
select throws_ok($$insert into public.food_descriptions(id,food_id,version,short_intro,ingredients_summary,characteristics,authoring_method,drafted_by,content_sha256)
 values('f1010000-0000-4000-8000-000000000018','f1010000-0000-4000-8000-0000000000ff',1,'SYNTHETIC TEST INTRO TEXT ONLY','SYNTHETIC TEST','SYNTHETIC TEST',
 'manual','SYNTHETIC',repeat('a',64))$$,'23503',null,'description must reference a canonical food');
insert into public.food_descriptions(id,food_id,version,short_intro,origin_text,ingredients_summary,characteristics,authoring_method,drafted_by,content_sha256)
 values((select value from content_state where name='v1'),(select value from content_state where name='food'),900,
  'SYNTHETIC TEST INTRO TEXT ONLY','SYNTHETIC ORIGIN','SYNTHETIC INGREDIENTS','SYNTHETIC TRAITS','ai_assisted_draft','SYNTHETIC',repeat('a',64));
insert into public.food_description_sources values((select value from content_state where name='v1'),(select value from content_state where name='source'),'{short_intro}',null);
select throws_ok($$update public.food_descriptions set content_status='reviewed',reviewed_by='SYNTHETIC',reviewed_at=now()
 where id=(select value from content_state where name='v1')$$,'P0001','DESCRIPTION_SOURCES_REQUIRED','every non-empty field needs a cited source');
update public.food_description_sources set supports='{short_intro,origin_text,ingredients_summary,characteristics}'
 where description_id=(select value from content_state where name='v1');
select lives_ok($$update public.food_descriptions set content_status='reviewed',reviewed_by='SYNTHETIC',reviewed_at=now()
 where id=(select value from content_state where name='v1')$$,'draft with full source coverage can be reviewed');
select throws_ok($$update public.food_descriptions set short_intro='SYNTHETIC CHANGED AFTER REVIEW' where id=(select value from content_state where name='v1')$$,
 'P0001','DESCRIPTION_IMMUTABLE','reviewed text is frozen');
select throws_ok($$update public.food_descriptions set reviewed_by='SOMEONE ELSE' where id=(select value from content_state where name='v1')$$,
 'P0001','DESCRIPTION_IMMUTABLE','review evidence is frozen');
select throws_ok($$delete from public.food_description_sources where description_id=(select value from content_state where name='v1')$$,
 'P0001','DESCRIPTION_IMMUTABLE','reviewed source links are frozen');
select throws_ok($$delete from public.food_descriptions where id=(select value from content_state where name='v1')$$,
 'P0001','DESCRIPTION_IMMUTABLE','reviewed content cannot be deleted');
select throws_ok($$update public.food_descriptions set content_status='draft',reviewed_by=null,reviewed_at=null where id=(select value from content_state where name='v1')$$,
 'P0001','INVALID_DESCRIPTION_TRANSITION','review cannot be silently undone');
select throws_ok($$update public.food_descriptions set content_status='published' where id=(select value from content_state where name='v1')$$,
 '23514',null,'publishing requires publisher evidence and current flag');

set local role authenticated;
select set_config('request.jwt.claims','{"role":"authenticated","sub":"f1010000-0000-4000-8000-0000000000a1"}',true);
select is((select count(*)::integer from public.food_descriptions where id=(select value from content_state where name='v1')),0,'reviewed but unpublished content is hidden');
reset role;

update public.food_descriptions set content_status='published',is_current=true,published_by='SYNTHETIC',published_at=now()
 where id=(select value from content_state where name='v1');
select throws_ok($$update public.content_sources set title='SYNTHETIC CHANGED' where id=(select value from content_state where name='source')$$,
 'P0001','SOURCE_IMMUTABLE','a cited source cannot be rewritten after review');
insert into public.food_descriptions(id,food_id,version,short_intro,ingredients_summary,characteristics,authoring_method,drafted_by,content_sha256)
 values((select value from content_state where name='v2'),(select value from content_state where name='food'),901,
  'SYNTHETIC TEST INTRO TEXT V2','SYNTHETIC INGREDIENTS','SYNTHETIC TRAITS','manual','SYNTHETIC',repeat('b',64));
insert into public.food_description_sources values((select value from content_state where name='v2'),(select value from content_state where name='source'),
 '{short_intro,ingredients_summary,characteristics}','SYNTHETIC LOCATOR');

set local role authenticated;
select set_config('request.jwt.claims','{"role":"authenticated","sub":"f1010000-0000-4000-8000-0000000000a1"}',true);
select is((select count(*)::integer from public.food_descriptions where food_id=(select value from content_state where name='food')),1,'user sees only the current published version');
select is((select version from public.food_descriptions where food_id=(select value from content_state where name='food')),900,'draft v2 is hidden');
select is((select count(*)::integer from public.food_description_sources where description_id=(select value from content_state where name='v1')),1,'published citations visible');
select is((select count(*)::integer from public.food_description_sources where description_id=(select value from content_state where name='v2')),0,'draft citations hidden');
select is((select title from public.content_sources where id=(select value from content_state where name='source')),'SYNTHETIC TEST SOURCE','cited source visible');
select throws_ok($$select reviewed_by from public.food_descriptions$$,'42501',null,'reviewer column denied to users');
select throws_ok($$update public.food_descriptions set short_intro='USER WRITE' where id=(select value from content_state where name='v1')$$,'42501',null,'users cannot edit content');
reset role;

update public.food_descriptions set content_status='reviewed',reviewed_by='SYNTHETIC',reviewed_at=now() where id=(select value from content_state where name='v2');
select throws_ok($$update public.food_descriptions set content_status='published',is_current=true,published_by='SYNTHETIC',published_at=now()
 where id=(select value from content_state where name='v2')$$,'23505',null,'only one current version per food');
update public.food_descriptions set content_status='retired',is_current=false where id=(select value from content_state where name='v1');
update public.food_descriptions set content_status='published',is_current=true,published_by='SYNTHETIC',published_at=now()
 where id=(select value from content_state where name='v2');
select throws_ok($$update public.food_descriptions set content_status='published',is_current=true where id=(select value from content_state where name='v1')$$,
 'P0001','INVALID_DESCRIPTION_TRANSITION','retired versions stay retired');

set local role authenticated;
select set_config('request.jwt.claims','{"role":"authenticated","sub":"f1010000-0000-4000-8000-0000000000a1"}',true);
select is((select version from public.food_descriptions where food_id=(select value from content_state where name='food')),901,'new published version replaces old');
select is((select count(*)::integer from public.food_descriptions where id=(select value from content_state where name='v1')),0,'retired version hidden');
reset role;
set local role anon;
select throws_ok($$select id from public.food_descriptions$$,'42501',null,'anonymous read denied');
reset role;

insert into public.food_descriptions(id,food_id,version,short_intro,ingredients_summary,characteristics,authoring_method,drafted_by,content_sha256)
 values((select value from content_state where name='broad_v'),(select value from content_state where name='broad'),900,
  'SYNTHETIC BROAD CLASS INTRO','SYNTHETIC INGREDIENTS','SYNTHETIC TRAITS','manual','SYNTHETIC',repeat('c',64));
insert into public.food_description_sources values((select value from content_state where name='broad_v'),(select value from content_state where name='source'),
 '{short_intro,ingredients_summary,characteristics}',null);
select throws_ok($$update public.food_descriptions set content_status='reviewed',reviewed_by='SYNTHETIC',reviewed_at=now()
 where id=(select value from content_state where name='broad_v')$$,'P0001','DESCRIPTION_SCOPE_NOTE_REQUIRED','broad classes must state their scope');
select lives_ok($$delete from public.food_descriptions where id=(select value from content_state where name='broad_v')$$,'drafts can be deleted');
select is((select count(*)::integer from public.food_description_sources where description_id=(select value from content_state where name='broad_v')),0,'draft links cascade');
select * from finish();
rollback;
