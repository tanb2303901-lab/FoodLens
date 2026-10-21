-- FoodLens DB-02: application schema, no production nutrition or serving seed.
create schema if not exists foodlens_private;
revoke all on schema foodlens_private from public, anon, authenticated;
do $$ begin
  if not exists (select 1 from pg_roles where rolname='foodlens_rpc') then
    create role foodlens_rpc nologin nosuperuser nocreatedb nocreaterole noinherit nobypassrls;
  end if;
end $$;

create function foodlens_private.finite(n numeric) returns boolean
language sql immutable set search_path='' as $$
  select n is not null and n not in ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)
$$;
create function foodlens_private.fail(code text) returns void
language plpgsql set search_path='' as $$ begin raise exception using errcode='P0001',message=code; end $$;
create function foodlens_private.touch() returns trigger
language plpgsql set search_path='' as $$ begin new.updated_at=now(); return new; end $$;
create function foodlens_private.check_timezone() returns trigger
language plpgsql set search_path='' as $$ begin
  if not (new.timezone='UTC' or position('/' in new.timezone)>0) or not exists
    (select 1 from pg_catalog.pg_timezone_names where name=new.timezone) then
    perform foodlens_private.fail('INVALID_TIMEZONE');
  end if;
  return new;
end $$;

create table public.profiles (
 id uuid primary key references auth.users(id) on delete cascade,
 display_name text not null default '' check(length(display_name)<=100),
 timezone text not null default 'UTC',
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create trigger profiles_timezone before insert or update on public.profiles
 for each row execute function foodlens_private.check_timezone();
create trigger profiles_touch before update on public.profiles
 for each row execute function foodlens_private.touch();
create function foodlens_private.new_auth_user() returns trigger
language plpgsql security definer set search_path='' as $$ begin
 insert into public.profiles(id) values(new.id); return new;
end $$;
create trigger foodlens_auth_profile after insert on auth.users
 for each row execute function foodlens_private.new_auth_user();

create table public.foods (
 id uuid primary key, slug text unique not null check(slug ~ '^[a-z0-9]+(_[a-z0-9]+)*$'),
 name_vi text not null check(length(name_vi)>0), name_en text,
 scope_kind text not null check(scope_kind in ('prepared_food','ingredient_or_component','broad_food_category')),
 original_class_id smallint not null check(original_class_id between 0 and 67 and original_class_id<>27),
 training_class_id smallint not null check(training_class_id between 0 and 66),
 class_map_version text not null check(class_map_version='vietfood-67-2026-10-12-v1'),
 source_mapping_metadata jsonb not null default '{}'::jsonb check(jsonb_typeof(source_mapping_metadata)='object'),
 active boolean not null default true,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 unique(class_map_version,training_class_id), unique(class_map_version,original_class_id),
 check(training_class_id=case when original_class_id<27 then original_class_id else original_class_id-1 end)
);
create trigger foods_touch before update on public.foods for each row execute function foodlens_private.touch();
create function foodlens_private.food_identity() returns trigger language plpgsql set search_path='' as $$ begin
 if (new.id,new.slug,new.training_class_id,new.original_class_id,new.class_map_version) is distinct from
    (old.id,old.slug,old.training_class_id,old.original_class_id,old.class_map_version) then
   perform foodlens_private.fail('FOOD_IDENTITY_IMMUTABLE'); end if; return new;
end $$;
create trigger foods_identity before update on public.foods for each row execute function foodlens_private.food_identity();

create table public.nutrition_references (
 record_id text not null, source_data_version text not null,
 source_type text not null check(source_type in ('vn_kaggle','usda_foundation','usda_sr_legacy')),
 source_id text not null, source_code text, name_vi text, name_en text,
 source_url text, source_file text, publication_date date, source_release_version text,
 basis_g numeric, energy_kcal_per_100g numeric, protein_g_per_100g numeric,
 carbs_g_per_100g numeric, fat_g_per_100g numeric,
 basis_status text, energy_unit text, energy_nutrient_id text, energy_selection_rule text,
 quality_status text not null, quality_flags text not null default '',
 core_complete boolean not null, reference_usable boolean not null,
 raw_record jsonb not null check(jsonb_typeof(raw_record)='object'), imported_at timestamptz not null default now(),
 primary key(record_id,source_data_version), check(coalesce(name_vi,name_en) is not null)
);
create index references_quality on public.nutrition_references(source_type,quality_status);
create table public.food_nutrition_links (
 food_id uuid not null references public.foods(id) on delete restrict,
 record_id text not null, source_data_version text not null,
 source_candidate_details jsonb not null, source_matching_rule text, source_review_reason text,
 review_status text not null default 'candidate' check(review_status in ('candidate','approved','rejected')),
 reviewed_by text, reviewed_at timestamptz, review_notes text,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 primary key(food_id,record_id,source_data_version),
 foreign key(record_id,source_data_version) references public.nutrition_references(record_id,source_data_version) on delete restrict,
 check(review_status='candidate' or (reviewed_by is not null and reviewed_at is not null))
);
create trigger links_touch before update on public.food_nutrition_links for each row execute function foodlens_private.touch();

create table public.food_nutrition (
 id uuid primary key default gen_random_uuid(), food_id uuid not null references public.foods(id) on delete restrict,
 variant_key text not null check(length(variant_key)>0), variant_name_vi text not null,
 version integer not null check(version>0), status text not null default 'draft' check(status in ('draft','approved','retired')),
 is_current boolean not null default false, basis_g numeric, energy_unit text, mass_unit text,
 energy_kcal_per_100g numeric(18,6), protein_g_per_100g numeric(18,6), carbs_g_per_100g numeric(18,6), fat_g_per_100g numeric(18,6),
 source_snapshot jsonb, approved_by text, approved_at timestamptz, created_at timestamptz not null default now(),
 unique(id,food_id), unique(food_id,variant_key,version), check(not is_current or status='approved'),
 check(status='draft' or (basis_g is not null and basis_g=100 and energy_unit is not null and energy_unit='kcal'
  and mass_unit is not null and mass_unit='g' and foodlens_private.finite(energy_kcal_per_100g) and energy_kcal_per_100g>=0
  and foodlens_private.finite(protein_g_per_100g) and protein_g_per_100g between 0 and 100
  and foodlens_private.finite(carbs_g_per_100g) and carbs_g_per_100g between 0 and 100
  and foodlens_private.finite(fat_g_per_100g) and fat_g_per_100g between 0 and 100
  and approved_by is not null and length(approved_by)>0 and approved_at is not null
  and source_snapshot is not null and jsonb_typeof(source_snapshot)='object'
  and coalesce(length(source_snapshot->>'basis_verification'),0)>0
  and jsonb_typeof(source_snapshot->'records')='array'))
);
create unique index one_current_nutrition on public.food_nutrition(food_id,variant_key) where is_current;
create function foodlens_private.immutable_approved() returns trigger language plpgsql set search_path='' as $$ begin
 if old.status in ('approved','retired') then
  if tg_op='DELETE' then perform foodlens_private.fail('PROFILE_IMMUTABLE'); end if;
  if (to_jsonb(new)-array['status','is_current']) is distinct from (to_jsonb(old)-array['status','is_current'])
    or new.status not in ('approved','retired') then perform foodlens_private.fail('PROFILE_IMMUTABLE'); end if;
 end if; return new;
end $$;
create trigger nutrition_immutable before update or delete on public.food_nutrition for each row execute function foodlens_private.immutable_approved();

create table public.food_portions (
 id uuid primary key default gen_random_uuid(), food_id uuid not null references public.foods(id) on delete restrict,
 variant_key text not null, label text not null, version integer not null check(version>0),
 grams numeric(12,3) not null check(foodlens_private.finite(grams) and grams>0),
 verified boolean not null default false, source_snapshot jsonb, verified_by text, verified_at timestamptz,
 active boolean not null default true, created_at timestamptz not null default now(),
 unique(id,food_id,variant_key), unique(food_id,variant_key,label,version),
 check(not verified or (source_snapshot is not null and jsonb_typeof(source_snapshot)='object' and verified_by is not null and verified_at is not null))
);
create index portions_lookup on public.food_portions(food_id,variant_key,active,verified);
create function foodlens_private.immutable_portion() returns trigger language plpgsql set search_path='' as $$ begin
 if old.verified then
  if tg_op='DELETE' or not new.verified or (to_jsonb(new)-'active') is distinct from (to_jsonb(old)-'active')
   then perform foodlens_private.fail('PORTION_IMMUTABLE'); end if;
 end if; return new;
end $$;
create trigger portions_immutable before update or delete on public.food_portions for each row execute function foodlens_private.immutable_portion();

create table public.scans (
 id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
 image_path text unique, status text not null check(status in ('processing','completed','failed')),
 input_source text not null check(input_source in ('camera','gallery','share')),
 model_version text, class_map_version text, detections jsonb not null default '[]', confirmations jsonb not null default '[]',
 revision integer not null default 1 check(revision>0), error_code text,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(id,user_id),
 check(jsonb_typeof(detections)='array' and jsonb_typeof(confirmations)='array'),
 check(image_path is null or (split_part(image_path,'/',1)=user_id::text and split_part(image_path,'/',2)=id::text and image_path !~ '(^|/)\.\.(/|$)')),
 check(status<>'completed' or (model_version is not null and class_map_version='vietfood-67-2026-10-12-v1'))
);
create index scans_owner_time on public.scans(user_id,created_at desc,id desc);
create trigger scans_touch before update on public.scans for each row execute function foodlens_private.touch();

create table public.meals (
 id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
 meal_type text not null check(meal_type in ('breakfast','lunch','dinner','snack','other')),
 eaten_at timestamptz not null, timezone text not null,
 create_idempotency_key text not null, revision integer not null default 1 check(revision>0),
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 unique(id,user_id), unique(user_id,create_idempotency_key)
);
create index meals_owner_time on public.meals(user_id,eaten_at desc,id desc);
create trigger meals_timezone before insert or update on public.meals for each row execute function foodlens_private.check_timezone();
create trigger meals_touch before update on public.meals for each row execute function foodlens_private.touch();
create table public.meal_items (
 id uuid primary key default gen_random_uuid(), meal_id uuid not null, user_id uuid not null,
 position smallint not null check(position between 0 and 99),
 food_id uuid not null references public.foods(id) on delete restrict, food_name_snapshot text not null,
 grams numeric(12,3) not null check(foodlens_private.finite(grams) and grams>0),
 nutrition_profile_id uuid, nutrition_status text not null check(nutrition_status in ('available','nutrition_unavailable')),
 unavailable_reason text, profile_version_snapshot integer, variant_key_snapshot text,
 per_100g_snapshot jsonb, source_snapshot jsonb,
 energy_kcal numeric(18,6), protein_g numeric(18,6), carbs_g numeric(18,6), fat_g numeric(18,6),
 scan_id uuid, detection_id uuid, predicted_food_id uuid references public.foods(id),
 portion_id uuid references public.food_portions(id) on delete restrict, portion_snapshot jsonb,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 foreign key(meal_id,user_id) references public.meals(id,user_id) on delete cascade,
 foreign key(scan_id,user_id) references public.scans(id,user_id) on delete no action deferrable initially deferred,
 foreign key(nutrition_profile_id,food_id) references public.food_nutrition(id,food_id) on delete restrict,
 unique(meal_id,position) deferrable initially deferred,
 check((scan_id is null and detection_id is null and predicted_food_id is null) or
       (scan_id is not null and detection_id is not null and predicted_food_id is not null)),
 check((portion_id is null)=(portion_snapshot is null)),
 check((nutrition_status='nutrition_unavailable' and nutrition_profile_id is null and unavailable_reason is not null
   and profile_version_snapshot is null and variant_key_snapshot is null and per_100g_snapshot is null and source_snapshot is null
   and energy_kcal is null and protein_g is null and carbs_g is null and fat_g is null) or
  (nutrition_status='available' and nutrition_profile_id is not null and unavailable_reason is null
   and profile_version_snapshot is not null and variant_key_snapshot is not null and per_100g_snapshot is not null and source_snapshot is not null
   and foodlens_private.finite(energy_kcal) and energy_kcal>=0 and foodlens_private.finite(protein_g) and protein_g>=0
   and foodlens_private.finite(carbs_g) and carbs_g>=0 and foodlens_private.finite(fat_g) and fat_g>=0))
);
create unique index meal_detection_once on public.meal_items(meal_id,scan_id,detection_id) where scan_id is not null;
create index items_meal on public.meal_items(meal_id);
create index items_owner on public.meal_items(user_id);
create index items_scan on public.meal_items(scan_id);
create trigger items_touch before update on public.meal_items for each row execute function foodlens_private.touch();
create function foodlens_private.nonempty_meal() returns trigger language plpgsql set search_path='' as $$
declare mid uuid; begin
 if tg_table_name='meals' then mid:=new.id; else mid:=old.meal_id; end if;
 if exists(select 1 from public.meals where id=mid) and not exists(select 1 from public.meal_items where meal_id=mid)
 then perform foodlens_private.fail('EMPTY_MEAL'); end if; return null;
end $$;
create constraint trigger meals_nonempty after insert or update on public.meals
 deferrable initially deferred for each row execute function foodlens_private.nonempty_meal();
create constraint trigger items_nonempty after delete or update on public.meal_items
 deferrable initially deferred for each row execute function foodlens_private.nonempty_meal();

create table foodlens_private.mutation_receipts (
 user_id uuid not null references auth.users(id) on delete cascade, idempotency_key text not null,
 operation text not null, resource_id uuid, request_hash text not null,
 response_status integer not null, response_body jsonb, response_revision integer,
 created_at timestamptz not null default now(), primary key(user_id,idempotency_key)
);
create table foodlens_private.import_runs (
 id uuid primary key default gen_random_uuid(), dataset_version text not null, file_checksums jsonb not null,
 class_map_version text not null, status text not null check(status in ('completed','failed')),
 observed_counts jsonb, operator text not null, started_at timestamptz not null default now(),
 finished_at timestamptz, error_summary text
);
