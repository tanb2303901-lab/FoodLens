-- FOOD-02: owner decision 2026-10-19 — remove nutrition, manual meals and stats from the product.
-- Claude Code implementation. Earlier migrations stay as history; this forward migration drops
-- their objects. A schema+data backup was taken first (ignored data/processed/FOOD-02-backup).
-- Kept: profiles, foods, scans/confirmation, private Storage, food descriptions.
begin;

drop function if exists public.create_meal(text,jsonb);
drop function if exists public.patch_meal(uuid,integer,text,jsonb);
drop function if exists public.delete_meal(uuid,integer,text);
drop function if exists public.get_meal(uuid);
drop function if exists public.list_meals(integer,timestamptz,timestamptz,timestamptz,uuid);
drop function if exists public.daily_stats(date,text);
drop function if exists public.weekly_stats(date,text);

drop function if exists foodlens_private.mutate_meal(text,uuid,integer,text,jsonb);
drop function if exists foodlens_private.normalize_meal(jsonb,boolean);
drop function if exists foodlens_private.build_item(uuid,uuid,integer,jsonb,jsonb);
drop function if exists foodlens_private.meal_json(uuid);
drop function if exists foodlens_private.daily_stats(date,text);
drop function if exists foodlens_private.weekly_stats(date,text);

drop table if exists public.meal_items;
drop table if exists public.meals;
drop table if exists foodlens_private.mutation_receipts;
drop table if exists public.food_portions;
drop table if exists public.food_nutrition;
drop table if exists public.food_nutrition_links;
drop table if exists public.nutrition_references;

-- Trigger and validation helpers can go once their tables are gone.
drop function if exists foodlens_private.guard_item();
drop function if exists foodlens_private.nonempty_meal();
drop function if exists foodlens_private.positive_grams(jsonb);
drop function if exists foodlens_private.public_source_evidence(jsonb,timestamptz);
drop function if exists foodlens_private.valid_source_evidence(jsonb);
drop function if exists foodlens_private.immutable_approved();
drop function if exists foodlens_private.immutable_portion();

-- Profiles are the only remaining user of this trigger; meals branch removed.
create or replace function foodlens_private.lock_owner() returns trigger language plpgsql set search_path='' as $$ begin
 if new.id is distinct from old.id or new.created_at is distinct from old.created_at then perform foodlens_private.fail('OWNER_IMMUTABLE'); end if;
 return new;
end $$;

-- Same anonymous boolean probe, now reading only the remaining core tables.
create or replace function public.core_readiness() returns boolean
language plpgsql stable security definer set search_path='' as $$
begin
 perform 1 from public.foods limit 1;
 perform 1 from public.scans limit 1;
 perform 1 from public.food_descriptions limit 1;
 return true;
end $$;
revoke all on function public.core_readiness() from public, anon, authenticated;
grant execute on function public.core_readiness() to anon, authenticated;

do $$ begin
 if exists(select 1 from pg_tables where schemaname in ('public','foodlens_private')
   and tablename in ('meals','meal_items','mutation_receipts','food_nutrition','food_portions','food_nutrition_links','nutrition_references'))
 then perform foodlens_private.fail('NUTRITION_OBJECTS_REMAIN'); end if;
end $$;
notify pgrst,'reload schema';
commit;
