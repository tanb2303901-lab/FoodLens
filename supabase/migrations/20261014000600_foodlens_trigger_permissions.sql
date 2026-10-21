create or replace function foodlens_private.lock_owner() returns trigger language plpgsql set search_path='' as $$ begin
 if new.id is distinct from old.id or new.created_at is distinct from old.created_at then perform foodlens_private.fail('OWNER_IMMUTABLE'); end if;
 -- Separate branches: the profiles row has no user_id/create_idempotency_key fields.
 if tg_table_name='meals' then
  if (new.user_id,new.create_idempotency_key) is distinct from (old.user_id,old.create_idempotency_key)
  then perform foodlens_private.fail('OWNER_IMMUTABLE'); end if;
 end if; return new;
end $$;
-- Invoker read RPCs need this error-only helper to reject invalid dates/timezones.
grant execute on function foodlens_private.fail(text) to authenticated;
notify pgrst,'reload schema';
