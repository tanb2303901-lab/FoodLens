-- Grants and policies are both required. No ordinary direct business-table DML.
revoke all on all tables in schema public from anon,authenticated;
revoke execute on all functions in schema foodlens_private from public,anon,authenticated;
revoke execute on function public.patch_profile(jsonb), public.start_scan(uuid,uuid,text,text),
 public.finish_scan(uuid,uuid,text,text,jsonb,text), public.confirm_scan(uuid,integer,jsonb),
 public.create_meal(text,jsonb), public.patch_meal(uuid,integer,text,jsonb),public.delete_meal(uuid,integer,text),
 public.get_meal(uuid),public.daily_stats(date,text),public.weekly_stats(date,text) from public,anon,authenticated;
alter default privileges for role postgres in schema public revoke execute on functions from public;
alter default privileges for role postgres in schema foodlens_private revoke execute on functions from public;

grant usage on schema public,foodlens_private,auth to foodlens_rpc;
grant execute on function auth.uid(),auth.role() to foodlens_rpc;
grant execute on all functions in schema foodlens_private to foodlens_rpc;
grant select on public.profiles,public.foods,public.food_nutrition,public.food_portions,public.scans,public.meals,public.meal_items to foodlens_rpc;
grant update(display_name,timezone) on public.profiles to foodlens_rpc;
grant update(confirmations,revision) on public.scans to foodlens_rpc;
grant insert,update,delete on public.meals,public.meal_items to foodlens_rpc;
grant select,insert on foodlens_private.mutation_receipts to foodlens_rpc;
grant foodlens_rpc to postgres;
grant create on schema foodlens_private to foodlens_rpc;
alter function foodlens_private.patch_profile(jsonb) owner to foodlens_rpc;
alter function foodlens_private.confirm_scan(uuid,integer,jsonb) owner to foodlens_rpc;
alter function foodlens_private.mutate_meal(text,uuid,integer,text,jsonb) owner to foodlens_rpc;
revoke create on schema foodlens_private from foodlens_rpc;

grant usage on schema public,foodlens_private to authenticated;
grant select on public.profiles,public.food_nutrition,public.food_portions,public.scans,public.meals,public.meal_items to authenticated;
grant select(id,slug,name_vi,name_en,scope_kind,original_class_id,training_class_id,class_map_version,active,created_at,updated_at) on public.foods to authenticated;
grant execute on function foodlens_private.owner(),foodlens_private.valid_timezone(text),foodlens_private.meal_json(uuid),
 foodlens_private.daily_stats(date,text),foodlens_private.weekly_stats(date,text),foodlens_private.patch_profile(jsonb),
 foodlens_private.confirm_scan(uuid,integer,jsonb),foodlens_private.mutate_meal(text,uuid,integer,text,jsonb) to authenticated;
grant execute on function public.patch_profile(jsonb),public.confirm_scan(uuid,integer,jsonb),public.create_meal(text,jsonb),
 public.patch_meal(uuid,integer,text,jsonb),public.delete_meal(uuid,integer,text),public.get_meal(uuid),public.daily_stats(date,text),public.weekly_stats(date,text) to authenticated;
grant usage on schema public,foodlens_private to service_role;
grant all on all tables in schema public,foodlens_private to service_role;
grant execute on all functions in schema foodlens_private to service_role;
grant execute on function public.start_scan(uuid,uuid,text,text),public.finish_scan(uuid,uuid,text,text,jsonb,text) to service_role;

do $$ declare tab text; begin
 foreach tab in array array['profiles','foods','nutrition_references','food_nutrition_links','food_nutrition','food_portions','scans','meals','meal_items'] loop
 execute format('alter table public.%I enable row level security',tab);
 end loop;
 foreach tab in array array['mutation_receipts','import_runs'] loop
 execute format('alter table foodlens_private.%I enable row level security',tab);
 end loop;
end $$;
create policy profiles_read on public.profiles for select to authenticated,foodlens_rpc using(id=(select auth.uid()));
create policy profiles_write on public.profiles for update to foodlens_rpc using(id=(select auth.uid())) with check(id=(select auth.uid()));
create policy foods_read on public.foods for select to authenticated using(active);
create policy foods_writer_read on public.foods for select to foodlens_rpc using(true);
create policy nutrition_read on public.food_nutrition for select to authenticated,foodlens_rpc using(status in ('approved','retired'));
create policy portions_read on public.food_portions for select to authenticated using(verified and active);
create policy portions_writer_read on public.food_portions for select to foodlens_rpc using(verified);
do $$ declare tab text; begin
 foreach tab in array array['scans','meals','meal_items'] loop
 execute format('create policy owner_read on public.%I for select to authenticated using(user_id=(select auth.uid()))',tab);
 execute format('create policy owner_writer on public.%I for all to foodlens_rpc using(user_id=(select auth.uid())) with check(user_id=(select auth.uid()))',tab);
 end loop;
end $$;
create policy receipts_writer on foodlens_private.mutation_receipts for all to foodlens_rpc
 using(user_id=(select auth.uid())) with check(user_id=(select auth.uid()));

insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
 values('food-scans','food-scans',false,10485760,array['image/jpeg','image/png','image/webp']);
revoke all on storage.objects from anon,authenticated;
grant select on storage.objects to authenticated;
create policy foodlens_image_owner on storage.objects for select to authenticated using(
 bucket_id='food-scans' and (storage.foldername(name))[1]=(select auth.uid())::text
 and exists(select 1 from public.scans s where s.user_id=(select auth.uid())
  and s.id::text=(storage.foldername(name))[2] and s.image_path=name));

notify pgrst,'reload schema';
