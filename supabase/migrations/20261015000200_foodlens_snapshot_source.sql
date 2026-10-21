-- Approved source metadata must serialize into the public API before a meal commits.
create function foodlens_private.valid_source_evidence(s jsonb) returns boolean
language plpgsql immutable set search_path='' as $$
declare entry jsonb;
begin
 if jsonb_typeof(s) is distinct from 'object'
  or coalesce(s->>'source_type','') not in ('vn_kaggle','usda_foundation','usda_sr_legacy','recipe','multiple')
  or jsonb_typeof(s->'basis_verification') is distinct from 'string' or length(s->>'basis_verification')=0
  or jsonb_typeof(s->'records') is distinct from 'array' or jsonb_typeof(s->'urls') is distinct from 'array'
 then return false; end if;
 for entry in select value from jsonb_array_elements(s->'records') loop
  if jsonb_typeof(entry) is distinct from 'object' or jsonb_typeof(entry->'record_id') is distinct from 'string'
   or jsonb_typeof(entry->'source_data_version') is distinct from 'string'
   or length(entry->>'record_id')=0 or length(entry->>'source_data_version')=0 then return false; end if;
 end loop;
 for entry in select value from jsonb_array_elements(s->'urls') loop
  if jsonb_typeof(entry) is distinct from 'string' or (entry#>>'{}') !~ '^[A-Za-z][A-Za-z0-9+.-]*:'
   or (entry#>>'{}') ~ '[[:cntrl:][:space:]]' then return false; end if;
 end loop;
 return true;
end $$;
revoke all on function foodlens_private.valid_source_evidence(jsonb) from public,anon;
grant execute on function foodlens_private.valid_source_evidence(jsonb) to authenticated,foodlens_rpc,service_role;
alter table public.food_nutrition add constraint approved_public_source_shape
 check(status='draft' or foodlens_private.valid_source_evidence(source_snapshot));

create function foodlens_private.public_source_evidence(s jsonb,approved timestamptz) returns jsonb
language sql immutable set search_path='' as $$
 select jsonb_build_object('source_type',s->'source_type','basis_verification',s->'basis_verification',
  'records',(select coalesce(jsonb_agg(jsonb_build_object('record_id',r->'record_id','source_data_version',r->'source_data_version')),'[]'::jsonb)
   from jsonb_array_elements(s->'records') r),'urls',s->'urls','approved_at',approved)
$$;
revoke all on function foodlens_private.public_source_evidence(jsonb,timestamptz) from public,anon;
grant execute on function foodlens_private.public_source_evidence(jsonb,timestamptz) to authenticated,foodlens_rpc,service_role;

-- Keep raw stored snapshots unchanged. Approval date comes from the immutable FK version.
do $$ declare definition text; needle text:='''source'',i.source_snapshot'; begin
 select pg_get_functiondef('foodlens_private.meal_json(uuid)'::regprocedure) into definition;
 if position(needle in definition)=0 then raise exception 'SNAPSHOT_SOURCE_MIGRATION_MISMATCH'; end if;
 definition:=replace(definition,needle,
  '''source'',foodlens_private.public_source_evidence(i.source_snapshot,(select approved_at from public.food_nutrition p where p.id=i.nutrition_profile_id and p.food_id=i.food_id))');
 execute definition;
end $$;
notify pgrst, 'reload schema';
