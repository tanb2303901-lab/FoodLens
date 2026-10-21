-- FOOD-01: canonical food introduction content with source provenance and review states.
-- Claude Code implementation 2026-10-19. Additive only: foods, nutrition, portions,
-- scans, meals and history are not modified. No content rows are seeded here; the
-- versioned JSON importer (scripts/food_content.py) owns data and review transitions.
begin;

create table public.content_sources (
 id uuid primary key,
 source_key text not null unique check(source_key ~ '^[a-z0-9]+(-[a-z0-9]+)*$' and length(source_key)<=100),
 title text not null check(length(btrim(title)) between 1 and 300),
 publisher text not null check(length(btrim(publisher)) between 1 and 200),
 url text not null check(url ~ '^https://[^[:space:]]+$' and length(url)<=1000),
 language text not null check(language in ('vi','en')),
 source_kind text not null check(source_kind in ('government_tourism','government','university','museum','book','open_license_encyclopedia','other')),
 revision_ref text check(revision_ref is null or length(btrim(revision_ref)) between 1 and 200),
 accessed_on date not null,
 license_note text not null check(length(btrim(license_note)) between 1 and 500),
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table public.food_descriptions (
 id uuid primary key,
 food_id uuid not null references public.foods(id) on delete restrict,
 locale text not null default 'vi' check(locale='vi'),
 version integer not null check(version>0),
 content_status text not null default 'draft' check(content_status in ('draft','reviewed','published','retired')),
 is_current boolean not null default false,
 short_intro text not null check(length(btrim(short_intro)) between 20 and 700),
 origin_text text check(origin_text is null or length(btrim(origin_text)) between 10 and 700),
 ingredients_summary text not null check(length(btrim(ingredients_summary)) between 10 and 700),
 characteristics text not null check(length(btrim(characteristics)) between 10 and 900),
 scope_note text check(scope_note is null or length(btrim(scope_note)) between 10 and 500),
 authoring_method text not null check(authoring_method in ('manual','ai_assisted_draft')),
 drafted_by text not null check(length(btrim(drafted_by)) between 1 and 200),
 source_check jsonb not null default '{}'::jsonb check(jsonb_typeof(source_check)='object'),
 content_sha256 text not null check(content_sha256 ~ '^[0-9a-f]{64}$'),
 reviewed_by text, reviewed_at timestamptz, review_notes text,
 published_by text, published_at timestamptz,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 unique(food_id,locale,version),
 -- Exactly the published version is current; retired keeps its history.
 check(is_current=(content_status='published')),
 check(content_status='draft' or (length(btrim(coalesce(reviewed_by,'')))>0 and reviewed_at is not null)),
 check(content_status in ('draft','reviewed') or (length(btrim(coalesce(published_by,'')))>0 and published_at is not null)),
 check(content_status<>'draft' or (reviewed_by is null and reviewed_at is null and published_by is null and published_at is null)),
 check(content_status<>'reviewed' or (published_by is null and published_at is null))
);
create unique index one_current_description on public.food_descriptions(food_id,locale) where is_current;

create table public.food_description_sources (
 description_id uuid not null references public.food_descriptions(id) on delete cascade,
 source_id uuid not null references public.content_sources(id) on delete restrict,
 supports text[] not null check(cardinality(supports) between 1 and 5
  and supports <@ array['short_intro','origin_text','ingredients_summary','characteristics','scope_note']::text[]),
 locator text check(locator is null or length(btrim(locator)) between 1 and 300),
 primary key(description_id,source_id)
);
create index description_sources_source on public.food_description_sources(source_id);

create trigger content_sources_touch before update on public.content_sources for each row execute function foodlens_private.touch();
create trigger descriptions_touch before update on public.food_descriptions for each row execute function foodlens_private.touch();

-- Reviewed text is what gets published: content and review evidence are frozen after
-- draft, and review requires every non-empty field to cite at least one source.
create function foodlens_private.description_guard() returns trigger language plpgsql set search_path='' as $$
declare
 content text[]:=array['id','food_id','locale','version','short_intro','origin_text','ingredients_summary','characteristics',
  'scope_note','authoring_method','drafted_by','source_check','content_sha256','created_at'];
 frozen_old jsonb; frozen_new jsonb;
begin
 if tg_op='INSERT' then
  if new.content_status<>'draft' or new.is_current then perform foodlens_private.fail('DESCRIPTION_STARTS_AS_DRAFT'); end if;
  return new;
 end if;
 if tg_op='DELETE' then
  if old.content_status<>'draft' then perform foodlens_private.fail('DESCRIPTION_IMMUTABLE'); end if;
  return old;
 end if;
 if (new.id,new.food_id,new.locale,new.version,new.created_at) is distinct from (old.id,old.food_id,old.locale,old.version,old.created_at)
 then perform foodlens_private.fail('DESCRIPTION_IDENTITY_IMMUTABLE'); end if;
 if (old.content_status,new.content_status) not in (('draft','draft'),('draft','reviewed'),('reviewed','reviewed'),
   ('reviewed','published'),('published','published'),('published','retired'),('retired','retired'))
 then perform foodlens_private.fail('INVALID_DESCRIPTION_TRANSITION'); end if;
 if old.content_status<>'draft' then
  select jsonb_object_agg(k,to_jsonb(old)->k),jsonb_object_agg(k,to_jsonb(new)->k) into frozen_old,frozen_new from unnest(content) k;
  if frozen_old is distinct from frozen_new or (new.reviewed_by,new.reviewed_at,new.review_notes) is distinct from
     (old.reviewed_by,old.reviewed_at,old.review_notes) then perform foodlens_private.fail('DESCRIPTION_IMMUTABLE'); end if;
  if old.content_status in ('published','retired') and (new.published_by,new.published_at) is distinct from (old.published_by,old.published_at)
  then perform foodlens_private.fail('DESCRIPTION_IMMUTABLE'); end if;
 end if;
 if old.content_status='draft' and new.content_status='reviewed' then
  if exists(select 1 from unnest(array['short_intro','origin_text','ingredients_summary','characteristics','scope_note']) f(name)
    where to_jsonb(new)->>f.name is not null and not exists(select 1 from public.food_description_sources l
     where l.description_id=new.id and f.name=any(l.supports)))
  then perform foodlens_private.fail('DESCRIPTION_SOURCES_REQUIRED'); end if;
  if new.scope_note is null and exists(select 1 from public.foods where id=new.food_id and scope_kind='broad_food_category')
  then perform foodlens_private.fail('DESCRIPTION_SCOPE_NOTE_REQUIRED'); end if;
 end if;
 return new;
end $$;
create trigger descriptions_guard before insert or update or delete on public.food_descriptions
 for each row execute function foodlens_private.description_guard();

create function foodlens_private.description_source_guard() returns trigger language plpgsql set search_path='' as $$ begin
 -- A cascaded delete of a draft finds no parent row and is allowed.
 if tg_op in ('UPDATE','DELETE') and exists(select 1 from public.food_descriptions where id=old.description_id and content_status<>'draft')
 then perform foodlens_private.fail('DESCRIPTION_IMMUTABLE'); end if;
 if tg_op in ('INSERT','UPDATE') and exists(select 1 from public.food_descriptions where id=new.description_id and content_status<>'draft')
 then perform foodlens_private.fail('DESCRIPTION_IMMUTABLE'); end if;
 if tg_op='DELETE' then return old; end if;
 return new;
end $$;
create trigger description_sources_guard before insert or update or delete on public.food_description_sources
 for each row execute function foodlens_private.description_source_guard();

create function foodlens_private.content_source_guard() returns trigger language plpgsql set search_path='' as $$ begin
 if (to_jsonb(new)-'updated_at') is distinct from (to_jsonb(old)-'updated_at') and exists(select 1 from public.food_description_sources l
   join public.food_descriptions d on d.id=l.description_id where l.source_id=old.id and d.content_status<>'draft')
 then perform foodlens_private.fail('SOURCE_IMMUTABLE'); end if;
 return new;
end $$;
create trigger content_sources_guard before update on public.content_sources
 for each row execute function foodlens_private.content_source_guard();

-- Catalog-style access: users read only published current content and the sources it cites.
-- Reviewer/drafter names, drafts and review notes stay server/admin side.
alter table public.content_sources enable row level security;
alter table public.food_descriptions enable row level security;
alter table public.food_description_sources enable row level security;
revoke all on public.content_sources,public.food_descriptions,public.food_description_sources from public,anon,authenticated;
grant select(id,source_key,title,publisher,url,language,source_kind,revision_ref,accessed_on,license_note) on public.content_sources to authenticated;
grant select(id,food_id,locale,version,content_status,is_current,short_intro,origin_text,ingredients_summary,characteristics,
 scope_note,authoring_method,reviewed_at,published_at,updated_at) on public.food_descriptions to authenticated;
grant select(description_id,source_id,supports,locator) on public.food_description_sources to authenticated;
grant all on public.content_sources,public.food_descriptions,public.food_description_sources to service_role;
create policy descriptions_read on public.food_descriptions for select to authenticated
 using(content_status='published' and is_current);
create policy description_sources_read on public.food_description_sources for select to authenticated
 using(exists(select 1 from public.food_descriptions d where d.id=description_id and d.content_status='published' and d.is_current));
create policy content_sources_read on public.content_sources for select to authenticated
 using(exists(select 1 from public.food_description_sources l join public.food_descriptions d on d.id=l.description_id
  where l.source_id=content_sources.id and d.content_status='published' and d.is_current));
revoke execute on function foodlens_private.description_guard(),foodlens_private.description_source_guard(),
 foodlens_private.content_source_guard() from public,anon,authenticated;

notify pgrst,'reload schema';
commit;
