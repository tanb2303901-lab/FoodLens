-- Core access/RLS checks after FOOD-02 (nutrition, meals and stats removed).
-- Synthetic users only, rolled back. Safe with the imported catalog and existing users/scans.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path=public,extensions;
select no_plan();
insert into auth.users(id,email) values
 ('f0020000-0000-4000-8000-000000000001','food02-sql-a@example.invalid'),
 ('f0020000-0000-4000-8000-000000000002','food02-sql-b@example.invalid');

select ok(not exists(select 1 from pg_tables where schemaname in ('public','foodlens_private') and tablename in
 ('meals','meal_items','mutation_receipts','food_nutrition','food_portions','food_nutrition_links','nutrition_references')),
 'nutrition and meal tables are removed');
select ok(not exists(select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname in ('public','foodlens_private')
 and p.proname in ('create_meal','patch_meal','delete_meal','get_meal','list_meals','daily_stats','weekly_stats','mutate_meal')),
 'meal and stats functions are removed');
select ok((select bool_and(relrowsecurity) from pg_class where oid in ('public.profiles'::regclass,'public.foods'::regclass,
 'public.scans'::regclass,'public.food_descriptions'::regclass,'public.content_sources'::regclass,'public.food_description_sources'::regclass,
 'foodlens_private.import_runs'::regclass)),'RLS enabled on remaining app tables');
select ok(not has_table_privilege('authenticated','public.scans','INSERT'),'ordinary scan INSERT revoked');
select ok(not has_table_privilege('authenticated','public.foods','UPDATE'),'ordinary catalog UPDATE revoked');
select ok(not has_function_privilege('authenticated','public.start_scan(uuid,uuid,text,text)','EXECUTE'),'user cannot forge detector writes');
select ok(not pg_has_role('authenticated','foodlens_rpc','MEMBER'),'authenticated cannot assume writer role');
select ok((select not rolbypassrls and not rolsuper and not rolcanlogin from pg_roles where rolname='foodlens_rpc'),'writer cannot bypass RLS/login');
select ok((select bool_and(p.prosecdef and r.rolname='foodlens_rpc' and array_to_string(p.proconfig,',') like '%search_path%')
 from pg_proc p join pg_roles r on r.oid=p.proowner where p.oid in
 ('foodlens_private.patch_profile(jsonb)'::regprocedure,'foodlens_private.confirm_scan(uuid,integer,jsonb)'::regprocedure)),
 'private writers owned by limited role and pin search_path');
select ok((select bool_and(not prosecdef) from pg_proc where oid in
 ('public.patch_profile(jsonb)'::regprocedure,'public.confirm_scan(uuid,integer,jsonb)'::regprocedure)),'public wrappers are invoker');
select ok((select not prosecdef and prosqlbody is not null from pg_proc where oid='foodlens_private.jwt_uid()'::regprocedure),
 'Auth bridge is pre-parsed invoker, not privileged definer');
select is((select count(*)::integer from public.profiles where id in ('f0020000-0000-4000-8000-000000000001','f0020000-0000-4000-8000-000000000002')),2,
 'Auth users receive profiles');
select ok((select not public from storage.buckets where id='food-scans'),'scan image bucket stays private');

select set_config('request.jwt.claims','{"sub":"f0020000-0000-4000-8000-000000000001","role":"authenticated"}',true);
set local role authenticated;
select is((select count(*)::integer from public.profiles),1,'A sees only A profile');
select is((select training_class_id from public.foods where slug='cu_kieu')::integer,27,'training ID 27 remains food');
select is((select count(*)::integer from public.foods),75,'authenticated reads the active catalog');
select throws_ok($$select source_mapping_metadata from public.foods$$,'42501',null,'raw mapping metadata access denied');
select throws_ok($$update public.profiles set display_name='direct write'$$,'42501',null,'direct profile writes denied');
select lives_ok($$select public.patch_profile('{"timezone":"Asia/Ho_Chi_Minh","display_name":"FOOD02 SQL"}')$$,'owner patches own profile');
select is((select timezone from public.profiles),'Asia/Ho_Chi_Minh','profile timezone persisted');
select throws_ok($$select public.patch_profile('{"timezone":"Not/AZone"}')$$,'P0001',null,'invalid timezone rejected');
select set_config('request.jwt.claims','{"sub":"f0020000-0000-4000-8000-000000000002","role":"authenticated"}',true);
select is((select display_name from public.profiles),'','B cannot see or inherit A profile changes');
reset role;
set local role anon;
select throws_ok($$select id from public.foods$$,'42501',null,'anon cannot read catalog');
select throws_ok($$select id from public.profiles$$,'42501',null,'anon cannot read profiles');
select throws_ok($$select id from public.scans$$,'42501',null,'anon cannot read scans');
select is(public.core_readiness(),true,'anonymous readiness probe still works');
reset role;
select * from finish();
rollback;
