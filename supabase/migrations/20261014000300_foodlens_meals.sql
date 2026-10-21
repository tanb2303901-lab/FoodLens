create function foodlens_private.build_item(uid uuid,mid uuid,pos integer,input jsonb,previous jsonb) returns public.meal_items
language plpgsql set search_path='' as $$
declare result public.meal_items; old_item public.meal_items; f public.foods; prof public.food_nutrition;
 portion public.food_portions; det jsonb; preserve boolean:=false;
begin
 if previous is not null then old_item:=jsonb_populate_record(null::public.meal_items,previous); result:=old_item; end if;
 result.id:=coalesce(old_item.id,gen_random_uuid()); result.meal_id:=mid; result.user_id:=uid; result.position:=pos;
 result.food_id:=(input->>'food_id')::uuid; result.grams:=(input->>'grams')::numeric;
 select * into f from public.foods where id=result.food_id and active;
 if not found then perform foodlens_private.fail('INVALID_FOOD'); end if;
 result.food_name_snapshot:=case when old_item.food_id=result.food_id then old_item.food_name_snapshot else f.name_vi end;
 preserve:=old_item.id is not null and old_item.food_id=result.food_id and not input?'profile_id';
 if not preserve then
  if input?'profile_id' then
   select * into prof from public.food_nutrition where id=(input->>'profile_id')::uuid and food_id=result.food_id
    and status in ('approved','retired') and (is_current or (old_item.food_id=result.food_id and old_item.nutrition_profile_id=id));
   if not found then perform foodlens_private.fail('INVALID_OR_STALE_PROFILE'); end if;
  elsif f.scope_kind<>'broad_food_category' then
   select * into prof from public.food_nutrition where food_id=result.food_id and variant_key='default' and status='approved' and is_current;
  end if;
  if prof.id is not null then
   result.nutrition_profile_id:=prof.id; result.nutrition_status:='available'; result.unavailable_reason:=null;
   result.profile_version_snapshot:=prof.version; result.variant_key_snapshot:=prof.variant_key;
   result.source_snapshot:=prof.source_snapshot;
   result.per_100g_snapshot:=jsonb_build_object('energy_kcal',prof.energy_kcal_per_100g,'protein_g',prof.protein_g_per_100g,'carbs_g',prof.carbs_g_per_100g,'fat_g',prof.fat_g_per_100g);
  else
   result.nutrition_profile_id:=null; result.nutrition_status:='nutrition_unavailable';
   result.unavailable_reason:=case when exists(select 1 from public.food_nutrition where food_id=result.food_id and status='approved' and is_current)
    then 'variant_confirmation_required' else 'no_approved_profile' end;
   result.profile_version_snapshot:=null; result.variant_key_snapshot:=null; result.source_snapshot:=null; result.per_100g_snapshot:=null;
  end if;
 end if;
 if result.nutrition_status='available' then
  result.energy_kcal:=round((result.per_100g_snapshot->>'energy_kcal')::numeric*result.grams/100,6);
  result.protein_g:=round((result.per_100g_snapshot->>'protein_g')::numeric*result.grams/100,6);
  result.carbs_g:=round((result.per_100g_snapshot->>'carbs_g')::numeric*result.grams/100,6);
  result.fat_g:=round((result.per_100g_snapshot->>'fat_g')::numeric*result.grams/100,6);
 else result.energy_kcal:=null; result.protein_g:=null; result.carbs_g:=null; result.fat_g:=null; end if;
 if input?'portion_id' then
  result.portion_id:=null; result.portion_snapshot:=null;
  if input->'portion_id'<>'null'::jsonb then
   select * into portion from public.food_portions where id=(input->>'portion_id')::uuid and food_id=result.food_id and verified and active;
   if not found or portion.grams<>result.grams or portion.variant_key is distinct from result.variant_key_snapshot then perform foodlens_private.fail('INVALID_PORTION'); end if;
   result.portion_id:=portion.id; result.portion_snapshot:=jsonb_build_object('id',portion.id,'version',portion.version,'label',portion.label,'grams',portion.grams);
  end if;
 elsif old_item.id is null or old_item.food_id<>result.food_id or old_item.grams<>result.grams
  or old_item.variant_key_snapshot is distinct from result.variant_key_snapshot then result.portion_id:=null; result.portion_snapshot:=null;
 end if;
 if input?'scan_ref' then
  result.scan_id:=(input->'scan_ref'->>'scan_id')::uuid; result.detection_id:=(input->'scan_ref'->>'detection_id')::uuid;
  select d into det from public.scans s,lateral jsonb_array_elements(s.detections) d
   where s.id=result.scan_id and s.user_id=uid and s.status='completed' and (d->>'detection_id')::uuid=result.detection_id;
  if not found then perform foodlens_private.fail('INVALID_SCAN_REFERENCE'); end if;
  result.predicted_food_id:=(det->>'predicted_food_id')::uuid;
 end if;
 result.created_at:=coalesce(old_item.created_at,now()); result.updated_at:=coalesce(old_item.updated_at,now());
 if old_item.id is not null and to_jsonb(result) is distinct from to_jsonb(old_item) then result.updated_at:=now(); end if;
 return result;
end $$;

create function foodlens_private.meal_json(mid uuid) returns jsonb language sql stable set search_path='' as $$
 select jsonb_build_object('id',m.id,'meal_type',m.meal_type,'eaten_at',m.eaten_at,'timezone',m.timezone,
 'revision',m.revision,'created_at',m.created_at,'updated_at',m.updated_at,
 'items',(select jsonb_agg(jsonb_build_object('id',i.id,'position',i.position,'food_id',i.food_id,'food_name',i.food_name_snapshot,
  'grams',i.grams,'nutrition_status',i.nutrition_status,'unavailable_reason',i.unavailable_reason,
  'nutrition_snapshot',case when i.nutrition_status='available' then jsonb_build_object('profile_id',i.nutrition_profile_id,
   'profile_version',i.profile_version_snapshot,'variant_key',i.variant_key_snapshot,'basis_g',100,'mass_unit','g','energy_unit','kcal',
   'per_100g',i.per_100g_snapshot,'source',i.source_snapshot) else null end,
  'nutrients',jsonb_build_object('energy_kcal',i.energy_kcal,'protein_g',i.protein_g,'carbs_g',i.carbs_g,'fat_g',i.fat_g),
  'portion_snapshot',i.portion_snapshot,'scan_ref',case when i.scan_id is null then null else jsonb_build_object(
   'scan_id',i.scan_id,'detection_id',i.detection_id,'predicted_food_id',i.predicted_food_id) end) order by i.position)
  from public.meal_items i where i.meal_id=m.id and i.user_id=auth.uid()),
 'known_totals',jsonb_build_object('energy_kcal',a.energy,'protein_g',a.protein,'carbs_g',a.carbs,'fat_g',a.fat),
 'known_nutrition_count',a.known,'missing_nutrition_count',a.missing,
 'nutrition_completeness',case when a.known=0 then 'unavailable' when a.missing=0 then 'complete' else 'partial' end)
 from public.meals m cross join lateral (select count(*) filter(where nutrition_status='available') known,
  count(*) filter(where nutrition_status='nutrition_unavailable') missing,
  sum(energy_kcal) energy,sum(protein_g) protein,sum(carbs_g) carbs,sum(fat_g) fat
  from public.meal_items where meal_id=m.id and user_id=auth.uid()) a where m.id=mid and m.user_id=auth.uid()
$$;

create function foodlens_private.mutate_meal(operation text,mid uuid,expected_revision integer,idem text,request jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare uid uuid:=foodlens_private.owner(); normalized jsonb; hashed text; receipt foodlens_private.mutation_receipts;
 meal public.meals; old_items jsonb; input jsonb; previous jsonb; item public.meal_items; seen uuid[]:='{}'; pos integer:=0;
 body jsonb; status_code integer; tz text;
begin
 if operation not in ('create','patch','delete') or idem is null or length(idem) not between 8 and 128 or idem !~ '^[A-Za-z0-9._:-]+$'
 then perform foodlens_private.fail('INVALID_IDEMPOTENCY_KEY'); end if;
 if operation='delete' then
  if request is distinct from '{}'::jsonb then perform foodlens_private.fail('INVALID_INPUT'); end if; normalized:='{}';
 else normalized:=foodlens_private.normalize_meal(request,operation='create'); end if;
 if operation='create' and (mid is not null or expected_revision is not null) then perform foodlens_private.fail('INVALID_INPUT'); end if;
 if operation<>'create' and mid is null then perform foodlens_private.fail('INVALID_INPUT'); end if;
 hashed:=encode(sha256(convert_to(jsonb_build_object('operation',operation,'resource',mid,'revision',expected_revision,'request',normalized)::text,'UTF8')),'hex');
 -- Hash collision only serializes unrelated requests; full keys/hashes are checked below.
 perform pg_advisory_xact_lock(hashtextextended(uid::text||':'||idem,0));
 select * into receipt from foodlens_private.mutation_receipts where user_id=uid and idempotency_key=idem;
 if found then
  if receipt.request_hash<>hashed then perform foodlens_private.fail('IDEMPOTENCY_KEY_REUSED'); end if;
  return jsonb_build_object('status_code',receipt.response_status,'body',receipt.response_body,'revision',receipt.response_revision,'replayed',true);
 end if;
 if operation='create' then
  tz:=coalesce(normalized->>'timezone',(select timezone from public.profiles where id=uid));
  insert into public.meals(user_id,meal_type,eaten_at,timezone,create_idempotency_key)
   values(uid,normalized->>'meal_type',(normalized->>'eaten_at')::timestamptz,tz,idem) returning * into meal;
  mid:=meal.id; old_items:='[]'; status_code:=201;
 else
  select * into meal from public.meals where id=mid and user_id=uid for update;
  if not found then perform foodlens_private.fail('NOT_FOUND'); end if;
  if expected_revision is null then perform foodlens_private.fail('IF_MATCH_REQUIRED'); end if;
  if expected_revision<=0 or expected_revision<>meal.revision then perform foodlens_private.fail('VERSION_CONFLICT'); end if;
  if operation='delete' then
   delete from public.meals where id=mid and user_id=uid; body:=null; status_code:=204;
  else
   select coalesce(jsonb_agg(to_jsonb(i)),'[]'::jsonb) into old_items from public.meal_items i where meal_id=mid and user_id=uid;
   update public.meals set meal_type=coalesce(normalized->>'meal_type',meal_type),
    eaten_at=coalesce((normalized->>'eaten_at')::timestamptz,eaten_at),timezone=coalesce(normalized->>'timezone',timezone),
    revision=revision+1 where id=mid and user_id=uid returning * into meal;
   status_code:=200;
  end if;
 end if;
 if operation<>'delete' then
  if normalized?'items' then
   delete from public.meal_items where meal_id=mid and user_id=uid;
   for input in select value from jsonb_array_elements(normalized->'items') loop
    previous:=null;
    if input?'id' then
     select x into previous from jsonb_array_elements(old_items) x where (x->>'id')::uuid=(input->>'id')::uuid;
     if previous is null or (input->>'id')::uuid=any(seen) then perform foodlens_private.fail('INVALID_ITEM_ID'); end if;
     seen:=array_append(seen,(input->>'id')::uuid);
    end if;
    item:=foodlens_private.build_item(uid,mid,pos,input,previous);
    insert into public.meal_items select (item).*;
    pos:=pos+1;
   end loop;
  end if;
  body:=foodlens_private.meal_json(mid);
 end if;
 insert into foodlens_private.mutation_receipts(user_id,idempotency_key,operation,resource_id,request_hash,response_status,response_body,response_revision)
  values(uid,idem,operation,mid,hashed,status_code,body,case when operation='delete' then null else meal.revision end) returning * into receipt;
 return jsonb_build_object('status_code',status_code,'body',body,'revision',receipt.response_revision,'replayed',false);
end $$;
create function public.create_meal(p_idempotency_key text,p_request jsonb) returns jsonb
language sql security invoker set search_path='' as $$ select foodlens_private.mutate_meal('create',null,null,p_idempotency_key,p_request) $$;
create function public.patch_meal(p_meal_id uuid,p_expected_revision integer,p_idempotency_key text,p_request jsonb) returns jsonb
language sql security invoker set search_path='' as $$ select foodlens_private.mutate_meal('patch',p_meal_id,p_expected_revision,p_idempotency_key,p_request) $$;
create function public.delete_meal(p_meal_id uuid,p_expected_revision integer,p_idempotency_key text) returns jsonb
language sql security invoker set search_path='' as $$ select foodlens_private.mutate_meal('delete',p_meal_id,p_expected_revision,p_idempotency_key,'{}') $$;
create function public.get_meal(p_meal_id uuid) returns jsonb language sql security invoker set search_path='' as $$ select foodlens_private.meal_json(p_meal_id) $$;

create function foodlens_private.daily_stats(day date,tz text) returns jsonb
language plpgsql stable set search_path='' as $$
declare uid uuid:=foodlens_private.owner(); start_at timestamptz; end_at timestamptz; result jsonb;
begin
 tz:=foodlens_private.valid_timezone(coalesce(tz,(select timezone from public.profiles where id=uid)));
 if day is null then perform foodlens_private.fail('INVALID_DATE'); end if;
 start_at:=day::timestamp at time zone tz; end_at:=(day+1)::timestamp at time zone tz;
 select jsonb_build_object('date',day,'timezone',tz,'meal_count',count(distinct m.id),'item_count',count(i.id),
  'known_nutrition_count',count(i.id) filter(where i.nutrition_status='available'),
  'missing_nutrition_count',count(i.id) filter(where i.nutrition_status='nutrition_unavailable'),
  'known_totals',jsonb_build_object('energy_kcal',case when count(i.id)=0 then 0 else sum(i.energy_kcal) end,
   'protein_g',case when count(i.id)=0 then 0 else sum(i.protein_g) end,
   'carbs_g',case when count(i.id)=0 then 0 else sum(i.carbs_g) end,'fat_g',case when count(i.id)=0 then 0 else sum(i.fat_g) end))
 into result from public.meals m join public.meal_items i on i.meal_id=m.id and i.user_id=uid
 where m.user_id=uid and m.eaten_at>=start_at and m.eaten_at<end_at;
 return result;
end $$;
create function public.daily_stats(p_date date,p_timezone text default null) returns jsonb
language sql security invoker set search_path='' as $$ select foodlens_private.daily_stats(p_date,p_timezone) $$;
create function foodlens_private.weekly_stats(first_day date,tz text) returns jsonb
language plpgsql stable set search_path='' as $$ declare days jsonb:='[]'; d jsonb; result jsonb; begin
 perform foodlens_private.owner();
 if first_day is null or extract(isodow from first_day)<>1 then perform foodlens_private.fail('INVALID_WEEK_START'); end if;
 tz:=foodlens_private.valid_timezone(coalesce(tz,(select timezone from public.profiles where id=auth.uid())));
 for n in 0..6 loop d:=foodlens_private.daily_stats(first_day+n,tz); days:=days||jsonb_build_array(d); end loop;
 select jsonb_build_object('week_start',first_day,'timezone',tz,'days',days,
  'meal_count',sum((x->>'meal_count')::integer),'item_count',sum((x->>'item_count')::integer),
  'known_nutrition_count',sum((x->>'known_nutrition_count')::integer),'missing_nutrition_count',sum((x->>'missing_nutrition_count')::integer),
  'known_totals',jsonb_build_object('energy_kcal',case when sum((x->>'item_count')::integer)>0 and sum((x->>'known_nutrition_count')::integer)=0 then null else sum((x->'known_totals'->>'energy_kcal')::numeric) end,
  'protein_g',case when sum((x->>'item_count')::integer)>0 and sum((x->>'known_nutrition_count')::integer)=0 then null else sum((x->'known_totals'->>'protein_g')::numeric) end,
  'carbs_g',case when sum((x->>'item_count')::integer)>0 and sum((x->>'known_nutrition_count')::integer)=0 then null else sum((x->'known_totals'->>'carbs_g')::numeric) end,
  'fat_g',case when sum((x->>'item_count')::integer)>0 and sum((x->>'known_nutrition_count')::integer)=0 then null else sum((x->'known_totals'->>'fat_g')::numeric) end))
 into result from jsonb_array_elements(days) x; return result;
end $$;
create function public.weekly_stats(p_week_start date,p_timezone text default null) returns jsonb
language sql security invoker set search_path='' as $$ select foodlens_private.weekly_stats(p_week_start,p_timezone) $$;
