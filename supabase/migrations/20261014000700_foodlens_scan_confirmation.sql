-- Keep the JSON alias distinct from the PL/pgSQL detection variable.
do $$
declare definition text;
begin
 select pg_get_functiondef('foodlens_private.guard_scan()'::regprocedure) into definition;
 definition:=replace(definition,
  'jsonb_array_elements(new.detections) d where (d->>''detection_id'')::uuid=cid',
  'jsonb_array_elements(new.detections) detection_row where (detection_row->>''detection_id'')::uuid=cid');
 execute definition;
end $$;
notify pgrst, 'reload schema';
