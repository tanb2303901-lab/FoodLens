-- ML-05: append the eight owner-approved classes; preserve all legacy rows/history.
-- Codex implementation/self-review. No nutrition/portion seed or model activation.
begin;
alter table public.foods alter column original_class_id drop not null;
alter table public.foods drop constraint if exists foods_training_class_id_check;
alter table public.foods drop constraint if exists foods_class_map_version_check;
alter table public.foods drop constraint if exists foods_identity_map_v2_check;
alter table public.foods add constraint foods_identity_map_v2_check check (
 (class_map_version='vietfood-67-2026-10-12-v1' and training_class_id between 0 and 66
  and original_class_id is not null and original_class_id<>27
  and training_class_id=case when original_class_id<27 then original_class_id else original_class_id-1 end)
 or
 (class_map_version='foodlens-75-2026-10-16-v2' and training_class_id between 67 and 74
  and original_class_id is null
  and source_mapping_metadata ?& array['source_namespace','source_class_id']
  and jsonb_typeof(source_mapping_metadata->'source_namespace')='string'
  and jsonb_typeof(source_mapping_metadata->'source_class_id')='number'
  and source_mapping_metadata->>'source_namespace'='foodlens-owner-extension-2026-10-16'
  and source_mapping_metadata->'source_class_id'=to_jsonb((training_class_id-67)::integer))
);
create or replace function foodlens_private.food_identity() returns trigger language plpgsql set search_path='' as $$ begin
 if (new.id,new.slug,new.training_class_id,new.original_class_id,new.class_map_version,
     new.source_mapping_metadata->'source_namespace',new.source_mapping_metadata->'source_class_id') is distinct from
    (old.id,old.slug,old.training_class_id,old.original_class_id,old.class_map_version,
     old.source_mapping_metadata->'source_namespace',old.source_mapping_metadata->'source_class_id') then
   perform foodlens_private.fail('FOOD_IDENTITY_IMMUTABLE'); end if; return new;
end $$;
-- The old remap/face checks remain; SQL NULL in the remap is allowed only for
-- the explicit new-class branch above. Legacy originals remain required.
alter table public.scans drop constraint if exists scans_check2;
alter table public.scans drop constraint if exists scans_model_map_v2_check;
alter table public.scans add constraint scans_model_map_v2_check check (
 status<>'completed' or (model_version is not null and class_map_version is not null
 and class_map_version in ('vietfood-67-2026-10-12-v1','foodlens-75-2026-10-16-v2'))
);
create or replace function foodlens_private.guard_scan() returns trigger language plpgsql set search_path='' as $$
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
 if jsonb_array_length(new.detections)>0 and (new.class_map_version is null or new.class_map_version not in ('vietfood-67-2026-10-12-v1','foodlens-75-2026-10-16-v2')) then perform foodlens_private.fail('INVALID_CLASS_MAP'); end if;
 for d in select value from jsonb_array_elements(new.detections) loop
  perform foodlens_private.object_keys(d,array['detection_id','predicted_food_id','training_class_id','original_class_id','bbox','confidence','alternatives']);
  if not d ?& array['detection_id','predicted_food_id','training_class_id','original_class_id','bbox','confidence']
   or jsonb_typeof(d->'detection_id')<>'string' or jsonb_typeof(d->'predicted_food_id')<>'string'
   or jsonb_typeof(d->'confidence')<>'number' or jsonb_typeof(d->'training_class_id')<>'number' or jsonb_typeof(d->'original_class_id') not in ('number','null')
  then perform foodlens_private.fail('INVALID_DETECTIONS'); end if;
  cid:=(d->>'detection_id')::uuid; if cid=any(ids) then perform foodlens_private.fail('DUPLICATE_DETECTION'); end if; ids:=array_append(ids,cid);
  select * into f from public.foods where id=(d->>'predicted_food_id')::uuid;
  if not found or (d->>'training_class_id') is distinct from f.training_class_id::text
   or (d->>'original_class_id') is distinct from f.original_class_id::text
   or (new.class_map_version='vietfood-67-2026-10-12-v1' and f.class_map_version<>'vietfood-67-2026-10-12-v1')
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
  if cid=any(ids) or not exists(select 1 from jsonb_array_elements(new.detections) detection_row where (detection_row->>'detection_id')::uuid=cid)
   or not exists(select 1 from public.foods where id=(c->>'confirmed_food_id')::uuid and active)
  then perform foodlens_private.fail('INVALID_CONFIRMATION'); end if; ids:=array_append(ids,cid);
 end loop;
 return new;
exception when invalid_text_representation or numeric_value_out_of_range then perform foodlens_private.fail('INVALID_DETECTIONS'); return null;
end $$;

insert into public.foods(id,slug,name_vi,name_en,scope_kind,original_class_id,training_class_id,class_map_version,source_mapping_metadata) values
('94d34795-c510-530a-ba47-576ea9c3dc09'::uuid,'chuoi','Chuối','Banana','ingredient_or_component',null,67,'foodlens-75-2026-10-16-v2','{"source_namespace": "foodlens-owner-extension-2026-10-16", "source_class_id": 0, "aliases": ["banana"], "class_map_sha256": "588c35ed6184c182918bdd5e77fa02f7d1b8845ad8387a4a6e2f497218ae3e56", "owner_approved_scope": true, "nutrition_approved": false}'::jsonb),
('44e7a64e-2c43-5c0c-89e6-9253d1e59298'::uuid,'tao','Táo','Apple','ingredient_or_component',null,68,'foodlens-75-2026-10-16-v2','{"source_namespace": "foodlens-owner-extension-2026-10-16", "source_class_id": 1, "aliases": ["apple"], "class_map_sha256": "588c35ed6184c182918bdd5e77fa02f7d1b8845ad8387a4a6e2f497218ae3e56", "owner_approved_scope": true, "nutrition_approved": false}'::jsonb),
('60d0fad3-3d72-5c98-800b-7582f784b37b'::uuid,'ga_nuong','Gà nướng','Grilled chicken','prepared_food',null,69,'foodlens-75-2026-10-16-v2','{"source_namespace": "foodlens-owner-extension-2026-10-16", "source_class_id": 2, "aliases": ["grilled_chicken", "roasted chicken", "grilled_chicken_breast"], "class_map_sha256": "588c35ed6184c182918bdd5e77fa02f7d1b8845ad8387a4a6e2f497218ae3e56", "owner_approved_scope": true, "nutrition_approved": false}'::jsonb),
('d56ba32e-e39d-5708-96d0-9fcccbfc6060'::uuid,'ca_hoi_nuong','Cá hồi nướng','Grilled salmon','prepared_food',null,70,'foodlens-75-2026-10-16-v2','{"source_namespace": "foodlens-owner-extension-2026-10-16", "source_class_id": 3, "aliases": ["grilled_salmon"], "class_map_sha256": "588c35ed6184c182918bdd5e77fa02f7d1b8845ad8387a4a6e2f497218ae3e56", "owner_approved_scope": true, "nutrition_approved": false}'::jsonb),
('c0053ada-1a8b-5194-b89d-455f5193601c'::uuid,'khoai_lang','Khoai lang','Sweet potato','ingredient_or_component',null,71,'foodlens-75-2026-10-16-v2','{"source_namespace": "foodlens-owner-extension-2026-10-16", "source_class_id": 4, "aliases": ["sweet_potato"], "class_map_sha256": "588c35ed6184c182918bdd5e77fa02f7d1b8845ad8387a4a6e2f497218ae3e56", "owner_approved_scope": true, "nutrition_approved": false}'::jsonb),
('f502f80e-12a1-563b-9b46-354360d31011'::uuid,'khom','Khóm','Pineapple','ingredient_or_component',null,72,'foodlens-75-2026-10-16-v2','{"source_namespace": "foodlens-owner-extension-2026-10-16", "source_class_id": 5, "aliases": ["pineapple", "dứa", "thơm"], "class_map_sha256": "588c35ed6184c182918bdd5e77fa02f7d1b8845ad8387a4a6e2f497218ae3e56", "owner_approved_scope": true, "nutrition_approved": false}'::jsonb),
('254cea80-105c-5827-85c3-3e0775a2c923'::uuid,'ca_phe','Cà phê','Coffee','broad_food_category',null,73,'foodlens-75-2026-10-16-v2','{"source_namespace": "foodlens-owner-extension-2026-10-16", "source_class_id": 6, "aliases": ["coffee"], "class_map_sha256": "588c35ed6184c182918bdd5e77fa02f7d1b8845ad8387a4a6e2f497218ae3e56", "owner_approved_scope": true, "nutrition_approved": false}'::jsonb),
('12df07be-30ad-5d7d-901c-ac8c76a88ce7'::uuid,'nuoc_ngot','Nước ngọt','Soft drink','broad_food_category',null,74,'foodlens-75-2026-10-16-v2','{"source_namespace": "foodlens-owner-extension-2026-10-16", "source_class_id": 7, "aliases": ["soft_drink"], "class_map_sha256": "588c35ed6184c182918bdd5e77fa02f7d1b8845ad8387a4a6e2f497218ae3e56", "owner_approved_scope": true, "nutrition_approved": false}'::jsonb)
on conflict do nothing;
do $$ begin
 if (select count(*) from public.foods where class_map_version='foodlens-75-2026-10-16-v2')<>8
 then perform foodlens_private.fail('EXTENSION_CATALOG_CONFLICT'); end if;
end $$;
notify pgrst,'reload schema';
commit;
