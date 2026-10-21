create function foodlens_private.object_keys(value jsonb, allowed text[]) returns void
language plpgsql set search_path='' as $$ begin
 if value is null or jsonb_typeof(value)<>'object' or exists
 (select 1 from jsonb_object_keys(value) k where not k=any(allowed))
 then perform foodlens_private.fail('INVALID_INPUT'); end if;
end $$;
create function foodlens_private.positive_grams(value jsonb) returns numeric
language plpgsql set search_path='' as $$ declare n numeric; begin
 if jsonb_typeof(value) is distinct from 'number' then perform foodlens_private.fail('INVALID_GRAMS'); end if;
 n:=(value#>>'{}')::numeric;
 if not foodlens_private.finite(n) or n<=0 or n>=1000000000 or n<>round(n,3)
 then perform foodlens_private.fail('INVALID_GRAMS'); end if; return trim_scale(n);
end $$;
create function foodlens_private.valid_timezone(t text) returns text
language plpgsql stable set search_path='' as $$ begin
 if t is null or not (t='UTC' or position('/' in t)>0) or not exists
 (select 1 from pg_catalog.pg_timezone_names where name=t) then perform foodlens_private.fail('INVALID_TIMEZONE'); end if;
 return t;
end $$;
create function foodlens_private.owner() returns uuid
language plpgsql stable set search_path='' as $$ declare uid uuid:=auth.uid(); begin
 if uid is null then perform foodlens_private.fail('UNAUTHENTICATED'); end if; return uid;
end $$;
create function foodlens_private.normalize_meal(request jsonb, is_create boolean) returns jsonb
language plpgsql set search_path='' as $$
declare result jsonb:=request; item jsonb; normalized jsonb; all_items jsonb:='[]'; stamp timestamptz;
begin
 perform foodlens_private.object_keys(request,array['meal_type','eaten_at','timezone','items']);
 if request='{}' or (is_create and not request ?& array['meal_type','eaten_at','items']) then perform foodlens_private.fail('INVALID_INPUT'); end if;
 if request?'meal_type' and (jsonb_typeof(request->'meal_type')<>'string' or request->>'meal_type' not in
 ('breakfast','lunch','dinner','snack','other')) then perform foodlens_private.fail('INVALID_MEAL_TYPE'); end if;
 if request?'timezone' then
  if jsonb_typeof(request->'timezone')<>'string' then perform foodlens_private.fail('INVALID_TIMEZONE'); end if;
  perform foodlens_private.valid_timezone(request->>'timezone');
 end if;
 if request?'eaten_at' then
  if jsonb_typeof(request->'eaten_at')<>'string' or (request->>'eaten_at') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T.*(Z|[+-][0-9]{2}:[0-9]{2})$'
  then perform foodlens_private.fail('INVALID_TIMESTAMP'); end if;
  stamp:=(request->>'eaten_at')::timestamptz;
  result:=jsonb_set(result,'{eaten_at}',to_jsonb(to_char(stamp at time zone 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')));
 end if;
 if request?'items' then
  if jsonb_typeof(request->'items')<>'array' or jsonb_array_length(request->'items') not between 1 and 100 then perform foodlens_private.fail('INVALID_ITEMS'); end if;
  for item in select value from jsonb_array_elements(request->'items') loop
   perform foodlens_private.object_keys(item,case when is_create then array['food_id','grams','profile_id','portion_id','scan_ref'] else array['id','food_id','grams','profile_id','portion_id','scan_ref'] end);
   if not item ?& array['food_id','grams'] or jsonb_typeof(item->'food_id')<>'string' then perform foodlens_private.fail('INVALID_ITEMS'); end if;
   normalized:=jsonb_set(item,'{food_id}',to_jsonb((item->>'food_id')::uuid::text));
   normalized:=jsonb_set(normalized,'{grams}',to_jsonb(foodlens_private.positive_grams(item->'grams')));
   if item?'id' then
    if jsonb_typeof(item->'id')<>'string' then perform foodlens_private.fail('INVALID_ITEM_ID'); end if;
    normalized:=jsonb_set(normalized,'{id}',to_jsonb((item->>'id')::uuid::text));
   end if;
   if item?'profile_id' then
    if jsonb_typeof(item->'profile_id')<>'string' then perform foodlens_private.fail('INVALID_PROFILE'); end if;
    normalized:=jsonb_set(normalized,'{profile_id}',to_jsonb((item->>'profile_id')::uuid::text));
   end if;
   if item?'portion_id' and item->'portion_id'<>'null'::jsonb then
    if jsonb_typeof(item->'portion_id')<>'string' then perform foodlens_private.fail('INVALID_PORTION'); end if;
    normalized:=jsonb_set(normalized,'{portion_id}',to_jsonb((item->>'portion_id')::uuid::text));
   end if;
   if item?'scan_ref' then
    perform foodlens_private.object_keys(item->'scan_ref',array['scan_id','detection_id']);
    if not (item->'scan_ref') ?& array['scan_id','detection_id'] or jsonb_typeof(item->'scan_ref'->'scan_id')<>'string'
    or jsonb_typeof(item->'scan_ref'->'detection_id')<>'string' then perform foodlens_private.fail('INVALID_SCAN_REFERENCE'); end if;
    normalized:=jsonb_set(normalized,'{scan_ref}',jsonb_build_object('scan_id',(item->'scan_ref'->>'scan_id')::uuid::text,'detection_id',(item->'scan_ref'->>'detection_id')::uuid::text));
   end if;
   all_items:=all_items||jsonb_build_array(normalized);
  end loop;
  result:=jsonb_set(result,'{items}',all_items);
 end if;
 return result;
exception when invalid_text_representation or datetime_field_overflow or numeric_value_out_of_range then
 perform foodlens_private.fail('INVALID_INPUT'); return null;
end $$;

create function foodlens_private.guard_scan() returns trigger language plpgsql set search_path='' as $$
declare d jsonb; c jsonb; alt jsonb; f public.foods; ids uuid[]:='{}'; cid uuid; b numeric[]; conf numeric;
begin
 if tg_op='UPDATE' then
  if (new.id,new.user_id,new.image_path,new.input_source,new.created_at) is distinct from
     (old.id,old.user_id,old.image_path,old.input_source,old.created_at) then perform foodlens_private.fail('SCAN_IDENTITY_IMMUTABLE'); end if;
  if old.status<>'processing' and (new.status,new.model_version,new.class_map_version,new.detections,new.error_code) is distinct from
     (old.status,old.model_version,old.class_map_version,old.detections,old.error_code) then perform foodlens_private.fail('SCAN_PREDICTION_IMMUTABLE'); end if;
 end if;
 if jsonb_typeof(new.detections)<>'array' or jsonb_array_length(new.detections)>100 or jsonb_typeof(new.confirmations)<>'array'
 then perform foodlens_private.fail('INVALID_DETECTIONS'); end if;
 for d in select value from jsonb_array_elements(new.detections) loop
  perform foodlens_private.object_keys(d,array['detection_id','predicted_food_id','training_class_id','original_class_id','bbox','confidence','alternatives']);
  if not d ?& array['detection_id','predicted_food_id','training_class_id','original_class_id','bbox','confidence']
   or jsonb_typeof(d->'detection_id')<>'string' or jsonb_typeof(d->'predicted_food_id')<>'string'
   or jsonb_typeof(d->'confidence')<>'number' or jsonb_typeof(d->'training_class_id')<>'number' or jsonb_typeof(d->'original_class_id')<>'number'
  then perform foodlens_private.fail('INVALID_DETECTIONS'); end if;
  cid:=(d->>'detection_id')::uuid; if cid=any(ids) then perform foodlens_private.fail('DUPLICATE_DETECTION'); end if; ids:=array_append(ids,cid);
  select * into f from public.foods where id=(d->>'predicted_food_id')::uuid;
  if not found or d->>'training_class_id'<>f.training_class_id::text or d->>'original_class_id'<>f.original_class_id::text
  then perform foodlens_private.fail('INVALID_CLASS_MAP'); end if;
  conf:=(d->>'confidence')::numeric;
  if not foodlens_private.finite(conf) or conf not between 0 and 1 or jsonb_typeof(d->'bbox')<>'array' or jsonb_array_length(d->'bbox')<>4
   or exists(select 1 from jsonb_array_elements(d->'bbox') x where jsonb_typeof(x)<>'number')
  then perform foodlens_private.fail('INVALID_DETECTIONS'); end if;
  select array_agg(value::numeric order by ord) into b from jsonb_array_elements_text(d->'bbox') with ordinality a(value,ord);
  if exists(select 1 from unnest(b) x where not foodlens_private.finite(x) or x not between 0 and 1) or b[1]>=b[3] or b[2]>=b[4]
  then perform foodlens_private.fail('INVALID_BBOX'); end if;
  if d?'alternatives' then
   if jsonb_typeof(d->'alternatives')<>'array' or jsonb_array_length(d->'alternatives')>3 then perform foodlens_private.fail('INVALID_ALTERNATIVES'); end if;
   for alt in select value from jsonb_array_elements(d->'alternatives') loop
    perform foodlens_private.object_keys(alt,array['food_id','confidence']);
    if not alt ?& array['food_id','confidence'] or jsonb_typeof(alt->'confidence')<>'number' then perform foodlens_private.fail('INVALID_ALTERNATIVES'); end if;
    conf:=(alt->>'confidence')::numeric;
    if not foodlens_private.finite(conf) or conf not between 0 and 1 or not exists(select 1 from public.foods where id=(alt->>'food_id')::uuid)
    then perform foodlens_private.fail('INVALID_ALTERNATIVES'); end if;
   end loop;
  end if;
 end loop;
 ids:='{}';
 for c in select value from jsonb_array_elements(new.confirmations) loop
  perform foodlens_private.object_keys(c,array['detection_id','confirmed_food_id']);
  if not c ?& array['detection_id','confirmed_food_id'] then perform foodlens_private.fail('INVALID_CONFIRMATION'); end if;
  cid:=(c->>'detection_id')::uuid;
  if cid=any(ids) or not exists(select 1 from jsonb_array_elements(new.detections) d where (d->>'detection_id')::uuid=cid)
   or not exists(select 1 from public.foods where id=(c->>'confirmed_food_id')::uuid and active)
  then perform foodlens_private.fail('INVALID_CONFIRMATION'); end if; ids:=array_append(ids,cid);
 end loop;
 return new;
exception when invalid_text_representation or numeric_value_out_of_range then perform foodlens_private.fail('INVALID_DETECTIONS'); return null;
end $$;
create trigger scans_guard before insert or update on public.scans for each row execute function foodlens_private.guard_scan();

create function foodlens_private.guard_item() returns trigger language plpgsql set search_path='' as $$
declare prof public.food_nutrition; portion public.food_portions; expected jsonb; det jsonb;
begin
 if tg_op='UPDATE' and (new.id,new.user_id,new.meal_id,new.created_at) is distinct from
 (old.id,old.user_id,old.meal_id,old.created_at) then perform foodlens_private.fail('ITEM_IDENTITY_IMMUTABLE'); end if;
 if new.nutrition_status='available' then
  select * into prof from public.food_nutrition where id=new.nutrition_profile_id and food_id=new.food_id and status in ('approved','retired');
  if not found then perform foodlens_private.fail('INVALID_PROFILE'); end if;
  expected:=jsonb_build_object('energy_kcal',prof.energy_kcal_per_100g,'protein_g',prof.protein_g_per_100g,'carbs_g',prof.carbs_g_per_100g,'fat_g',prof.fat_g_per_100g);
  if new.per_100g_snapshot is distinct from expected or new.source_snapshot is distinct from prof.source_snapshot
   or new.profile_version_snapshot<>prof.version or new.variant_key_snapshot<>prof.variant_key
   or (new.energy_kcal,new.protein_g,new.carbs_g,new.fat_g) is distinct from
   (round(prof.energy_kcal_per_100g*new.grams/100,6),round(prof.protein_g_per_100g*new.grams/100,6),round(prof.carbs_g_per_100g*new.grams/100,6),round(prof.fat_g_per_100g*new.grams/100,6))
  then perform foodlens_private.fail('INVALID_SNAPSHOT'); end if;
 end if;
 if new.portion_id is not null then
  select * into portion from public.food_portions where id=new.portion_id and food_id=new.food_id and verified;
  if not found or portion.grams<>new.grams or new.variant_key_snapshot is distinct from portion.variant_key
   or new.portion_snapshot is distinct from jsonb_build_object('id',portion.id,'version',portion.version,'label',portion.label,'grams',portion.grams)
  then perform foodlens_private.fail('INVALID_PORTION'); end if;
 end if;
 if new.scan_id is not null then
  select d into det from public.scans s, lateral jsonb_array_elements(s.detections) d
   where s.id=new.scan_id and s.user_id=new.user_id and s.status='completed' and (d->>'detection_id')::uuid=new.detection_id;
  if not found or (det->>'predicted_food_id')::uuid is distinct from new.predicted_food_id then perform foodlens_private.fail('INVALID_SCAN_REFERENCE'); end if;
 end if;
 return new;
end $$;
create trigger items_guard before insert or update on public.meal_items for each row execute function foodlens_private.guard_item();

create function foodlens_private.patch_profile(request jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$ declare uid uuid:=foodlens_private.owner(); result public.profiles; begin
 perform foodlens_private.object_keys(request,array['display_name','timezone']);
 if request='{}' or (request?'display_name' and jsonb_typeof(request->'display_name')<>'string')
 or (request?'timezone' and jsonb_typeof(request->'timezone')<>'string') then perform foodlens_private.fail('INVALID_INPUT'); end if;
 update public.profiles set display_name=case when request?'display_name' then request->>'display_name' else display_name end,
 timezone=case when request?'timezone' then request->>'timezone' else timezone end where id=uid returning * into result;
 if not found then perform foodlens_private.fail('NOT_FOUND'); end if; return to_jsonb(result);
end $$;
create function public.patch_profile(p_request jsonb) returns jsonb language sql security invoker set search_path='' as $$ select foodlens_private.patch_profile(p_request) $$;

create function public.start_scan(p_owner uuid,p_scan_id uuid,p_image_path text,p_input_source text) returns jsonb
language plpgsql security invoker set search_path='' as $$ declare result public.scans; begin
 if auth.role() is distinct from 'service_role' then perform foodlens_private.fail('FORBIDDEN'); end if;
 insert into public.scans(id,user_id,image_path,status,input_source) values(p_scan_id,p_owner,p_image_path,'processing',p_input_source) returning * into result;
 return to_jsonb(result);
end $$;
create function public.finish_scan(p_owner uuid,p_scan_id uuid,p_model_version text,p_class_map_version text,p_detections jsonb,p_error_code text default null) returns jsonb
language plpgsql security invoker set search_path='' as $$ declare result public.scans; begin
 if auth.role() is distinct from 'service_role' then perform foodlens_private.fail('FORBIDDEN'); end if;
 update public.scans set status=case when p_error_code is null then 'completed' else 'failed' end,
 model_version=p_model_version,class_map_version=p_class_map_version,detections=case when p_error_code is null then p_detections else '[]'::jsonb end,
 error_code=p_error_code,revision=revision+1 where id=p_scan_id and user_id=p_owner and status='processing' returning * into result;
 if not found then perform foodlens_private.fail('NOT_FOUND'); end if; return to_jsonb(result);
end $$;
create function foodlens_private.confirm_scan(scan_id uuid,expected_revision integer,request jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare uid uuid:=foodlens_private.owner(); current public.scans; changes jsonb:='[]'; item jsonb;
begin
 perform foodlens_private.object_keys(request,array['confirmations']);
 if jsonb_typeof(request->'confirmations') is distinct from 'array' then perform foodlens_private.fail('INVALID_INPUT'); end if;
 select * into current from public.scans where id=scan_id and user_id=uid for update;
 if not found then perform foodlens_private.fail('NOT_FOUND'); end if;
 if current.status<>'completed' then perform foodlens_private.fail('SCAN_NOT_COMPLETED'); end if;
 if expected_revision is null then perform foodlens_private.fail('IF_MATCH_REQUIRED'); end if;
 if current.revision<>expected_revision then perform foodlens_private.fail('VERSION_CONFLICT'); end if;
 for item in select value from jsonb_array_elements(request->'confirmations') loop
  perform foodlens_private.object_keys(item,array['detection_id','food_id']);
  if not item ?& array['detection_id','food_id'] then perform foodlens_private.fail('INVALID_CONFIRMATION'); end if;
  changes:=changes||jsonb_build_array(jsonb_build_object('detection_id',item->'detection_id','confirmed_food_id',item->'food_id'));
 end loop;
 update public.scans set confirmations=changes,revision=revision+1 where id=scan_id and user_id=uid returning * into current;
 return to_jsonb(current);
end $$;
create function public.confirm_scan(p_scan_id uuid,p_expected_revision integer,p_request jsonb) returns jsonb
language sql security invoker set search_path='' as $$ select foodlens_private.confirm_scan(p_scan_id,p_expected_revision,p_request) $$;
