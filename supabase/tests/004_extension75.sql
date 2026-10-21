-- ML-05 synthetic ownership fixtures, isolated and rolled back (meal checks removed by FOOD-02). Safe with an
-- imported catalog and existing users/meals; no empty-state assumption.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path=public,extensions;
select no_plan();
create temp table extension_state(name text primary key,value jsonb);
grant all on extension_state to authenticated,service_role;
insert into auth.users(id,email) values
 ('f1050000-0000-4000-8000-000000000001','ml05-sql-a@example.invalid'),
 ('f1050000-0000-4000-8000-000000000002','ml05-sql-b@example.invalid');
insert into extension_state values ('food',to_jsonb((select id from public.foods where training_class_id=69 and class_map_version='foodlens-75-2026-10-16-v2')));
select is((select count(*)::integer from public.foods where training_class_id>=67),8,'eight extension foods only');
select is((select count(*)::integer from public.foods where original_class_id is null),8,'only extension originals are null');
select is((select original_class_id::integer from public.foods where training_class_id=27),28,'training27 remains food, never face');
select throws_ok($$insert into public.foods(id,slug,name_vi,scope_kind,training_class_id,original_class_id,class_map_version)
 values('f1050000-0000-4000-8000-000000000010','ml05_bad_legacy','TEST','prepared_food',26,null,'vietfood-67-2026-10-12-v1')$$,
 '23514',null,'legacy catalog original may not become null');
select throws_ok($$insert into public.foods(id,slug,name_vi,scope_kind,training_class_id,original_class_id,class_map_version)
 values('f1050000-0000-4000-8000-000000000010','ml05_bad_new','TEST','prepared_food',69,null,'foodlens-75-2026-10-16-v2')$$,
 '23514',null,'new catalog requires source namespace and source ID');
select throws_ok($$update public.foods set source_mapping_metadata=jsonb_set(source_mapping_metadata,'{source_class_id}','7') where training_class_id=69$$,
 'P0001','FOOD_IDENTITY_IMMUTABLE','new provenance identity is immutable');
select set_config('request.jwt.claims','{"role":"service_role"}',true);
set local role service_role;
insert into extension_state select 'scan',public.start_scan('f1050000-0000-4000-8000-000000000001','f1050000-0000-4000-8000-000000000020',
 'f1050000-0000-4000-8000-000000000001/f1050000-0000-4000-8000-000000000020/fixture.jpg','gallery');
insert into extension_state select 'detection',jsonb_build_array(jsonb_build_object(
 'detection_id','f1050000-0000-4000-8000-000000000030','predicted_food_id',value,
 'training_class_id',69,'original_class_id',null,'bbox',jsonb_build_array(.1,.1,.9,.9),'confidence',.8)) from extension_state where name='food';
select throws_ok($$select public.finish_scan('f1050000-0000-4000-8000-000000000001','f1050000-0000-4000-8000-000000000020','SYNTHETIC-ML05-ONLY','foodlens-75-2026-10-16-v2',
 (select jsonb_set(value,'{0,original_class_id}','69') from extension_state where name='detection'))$$,
 'P0001','INVALID_CLASS_MAP','invented original69 does not pass null-safe matching');
select throws_ok($$select public.finish_scan('f1050000-0000-4000-8000-000000000001','f1050000-0000-4000-8000-000000000020','SYNTHETIC-ML05-ONLY','vietfood-67-2026-10-12-v1',
 (select value from extension_state where name='detection'))$$,
 'P0001','INVALID_CLASS_MAP','legacy map cannot save new prediction');
select throws_ok($$select public.finish_scan('f1050000-0000-4000-8000-000000000001','f1050000-0000-4000-8000-000000000020','SYNTHETIC-ML05-ONLY','foodlens-75-2026-10-16-v2',
 (select jsonb_build_array((value->0)-'original_class_id') from extension_state where name='detection'))$$,
 'P0001','INVALID_DETECTIONS','missing original key differs from explicit null');
select throws_ok($$select public.finish_scan('f1050000-0000-4000-8000-000000000001','f1050000-0000-4000-8000-000000000020','SYNTHETIC-ML05-ONLY',null,'[]')$$,
 '23514',null,'completed empty scan still requires a nonnull known map');
insert into extension_state select 'complete',public.finish_scan('f1050000-0000-4000-8000-000000000001','f1050000-0000-4000-8000-000000000020',
 'SYNTHETIC-ML05-ONLY','foodlens-75-2026-10-16-v2',(select value from extension_state where name='detection'));
select is((select value->'detections'->0->'original_class_id' from extension_state where name='complete'),'null'::jsonb,'new original stored as JSON null');
reset role;
select set_config('request.jwt.claims','{"role":"authenticated","sub":"f1050000-0000-4000-8000-000000000002"}',true);
set local role authenticated;
select is((select count(*)::integer from public.scans where id='f1050000-0000-4000-8000-000000000020'),0,'other owner cannot read extension scan');
select throws_ok($$select public.confirm_scan('f1050000-0000-4000-8000-000000000020',2,'{"confirmations":[]}')$$,
 'P0001','NOT_FOUND','other owner cannot confirm extension scan');
select throws_ok($$select public.start_scan('f1050000-0000-4000-8000-000000000002',gen_random_uuid(),null,'gallery')$$,
 '42501',null,'ordinary user cannot invoke privileged scan writer');
select set_config('request.jwt.claims','{"role":"authenticated","sub":"f1050000-0000-4000-8000-000000000001"}',true);
select is((select count(*)::integer from public.scans where id='f1050000-0000-4000-8000-000000000020'),1,'owner reads extension scan');
insert into extension_state select 'confirmed',public.confirm_scan('f1050000-0000-4000-8000-000000000020',2,
 jsonb_build_object('confirmations',jsonb_build_array(jsonb_build_object('detection_id','f1050000-0000-4000-8000-000000000030','food_id',value)))) from extension_state where name='food';
select is((select value->'detections' from extension_state where name='confirmed'),(select value from extension_state where name='detection'),'confirm preserves original nullable prediction');
reset role;
select * from finish();
rollback;
