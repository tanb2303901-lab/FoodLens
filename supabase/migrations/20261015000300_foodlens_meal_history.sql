-- One read transaction for keyset pagination + snapshots, under user JWT/RLS.
create function public.list_meals(p_limit integer default 20,p_from timestamptz default null,p_to timestamptz default null,
 p_cursor_at timestamptz default null,p_cursor_id uuid default null) returns jsonb
language plpgsql stable security invoker set search_path='' as $$
declare uid uuid:=foodlens_private.owner(); items jsonb;
begin
 if p_limit is null or p_limit not between 1 and 100 then perform foodlens_private.fail('INVALID_LIMIT'); end if;
 if p_from is not null and p_to is not null and p_from>=p_to then perform foodlens_private.fail('INVALID_TIME_RANGE'); end if;
 if (p_cursor_at is null)<>(p_cursor_id is null) then perform foodlens_private.fail('INVALID_CURSOR'); end if;
 select coalesce(jsonb_agg(foodlens_private.meal_json(id) order by eaten_at desc,id desc),'[]'::jsonb) into items
 from (select m.id,m.eaten_at from public.meals m where m.user_id=uid
  and (p_from is null or m.eaten_at>=p_from) and (p_to is null or m.eaten_at<p_to)
  and (p_cursor_at is null or (m.eaten_at,m.id)<(p_cursor_at,p_cursor_id))
  order by m.eaten_at desc,m.id desc limit p_limit+1) page;
 return items;
end $$;
revoke all on function public.list_meals(integer,timestamptz,timestamptz,timestamptz,uuid) from public,anon,authenticated;
grant execute on function public.list_meals(integer,timestamptz,timestamptz,timestamptz,uuid) to authenticated;
notify pgrst, 'reload schema';
