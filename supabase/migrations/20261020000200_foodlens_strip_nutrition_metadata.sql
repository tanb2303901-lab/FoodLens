-- FOOD-02 follow-up: the 67 legacy foods carried their nutrition-mapping CSV row in
-- source_mapping_metadata. Remove those nutrition keys; keep identity/provenance keys.
-- Backup of the original metadata: ignored data/processed/FOOD-02-backup/foods-metadata-before.json.
begin;
update public.foods
 set source_mapping_metadata = source_mapping_metadata - array['matching_rule','review_reason','mapping_status','candidate_count',
  'candidate_names','candidate_details','candidate_record_ids','candidate_source_codes','nutrition_approved','selected_record_id',
  'basis_review_required','variant_review_required','use_for_portion_calculation']
 where source_mapping_metadata ?| array['matching_rule','review_reason','mapping_status','candidate_count','candidate_names',
  'candidate_details','candidate_record_ids','candidate_source_codes','nutrition_approved','selected_record_id',
  'basis_review_required','variant_review_required','use_for_portion_calculation'];
do $$ begin
 if exists(select 1 from public.foods where source_mapping_metadata ?| array['candidate_details','nutrition_approved',
   'use_for_portion_calculation','selected_record_id','mapping_status'])
 then perform foodlens_private.fail('NUTRITION_METADATA_REMAINS'); end if;
end $$;
commit;
