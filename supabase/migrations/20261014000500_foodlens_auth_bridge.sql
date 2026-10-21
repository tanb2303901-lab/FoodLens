-- Supabase's postgres role cannot delegate USAGE on the vendor-owned auth schema.
-- A SQL-standard, pre-parsed invoker bridge binds auth.uid at creation time;
-- it does not elevate privileges or reimplement/accept client identity claims.
create function foodlens_private.jwt_uid() returns uuid language sql stable security invoker
 set search_path='' return auth.uid();
revoke execute on function foodlens_private.jwt_uid() from public,anon;
grant execute on function foodlens_private.jwt_uid() to authenticated,foodlens_rpc,service_role;
do $$ declare definition text; f record; begin
 for f in select oid from pg_proc where pronamespace='foodlens_private'::regnamespace
  and proname in ('owner','meal_json','weekly_stats') loop
  definition:=pg_get_functiondef(f.oid);
  execute replace(definition,'auth.uid()','foodlens_private.jwt_uid()');
 end loop;
end $$;

create or replace function foodlens_private.nonempty_meal() returns trigger
language plpgsql security definer set search_path='' as $$ declare mid uuid; begin
 if tg_table_name='meals' then mid:=new.id; else mid:=old.meal_id; end if;
 if exists(select 1 from public.meals where id=mid) and not exists(select 1 from public.meal_items where meal_id=mid)
 then perform foodlens_private.fail('EMPTY_MEAL'); end if; return null;
end $$;
create or replace function foodlens_private.immutable_approved() returns trigger
language plpgsql set search_path='' as $$ begin
 if old.status in ('approved','retired') then
  if tg_op='DELETE' then perform foodlens_private.fail('PROFILE_IMMUTABLE'); end if;
  if (to_jsonb(new)-array['status','is_current']) is distinct from (to_jsonb(old)-array['status','is_current'])
   or new.status not in ('approved','retired') then perform foodlens_private.fail('PROFILE_IMMUTABLE'); end if;
 end if;
 if tg_op='DELETE' then return old; end if; return new;
end $$;
create or replace function foodlens_private.immutable_portion() returns trigger
language plpgsql set search_path='' as $$ begin
 if old.verified then
  if tg_op='DELETE' or not new.verified or (to_jsonb(new)-'active') is distinct from (to_jsonb(old)-'active')
   then perform foodlens_private.fail('PORTION_IMMUTABLE'); end if;
 end if;
 if tg_op='DELETE' then return old; end if; return new;
end $$;
alter table public.food_nutrition add constraint approved_source_evidence
 check(status='draft' or (source_snapshot is not null and coalesce(jsonb_typeof(source_snapshot->'records'),'')='array'
  and coalesce(length(source_snapshot->>'basis_verification'),0)>0));

create function foodlens_private.lock_owner() returns trigger language plpgsql set search_path='' as $$ begin
 if new.id is distinct from old.id or new.created_at is distinct from old.created_at then perform foodlens_private.fail('OWNER_IMMUTABLE'); end if;
 if tg_table_name='meals' and (new.user_id,new.create_idempotency_key) is distinct from (old.user_id,old.create_idempotency_key)
 then perform foodlens_private.fail('OWNER_IMMUTABLE'); end if; return new;
end $$;
create trigger profiles_identity before update on public.profiles for each row execute function foodlens_private.lock_owner();
create trigger meals_identity before update on public.meals for each row execute function foodlens_private.lock_owner();
revoke execute on function foodlens_private.lock_owner() from public,anon,authenticated;
grant execute on function foodlens_private.lock_owner() to foodlens_rpc,service_role;
notify pgrst,'reload schema';
