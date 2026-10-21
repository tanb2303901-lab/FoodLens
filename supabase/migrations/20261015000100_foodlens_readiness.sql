-- Minimal anonymous probe: fixed reads, boolean result, no user/catalog data.
create function public.core_readiness() returns boolean
language plpgsql stable security definer set search_path='' as $$
begin
 perform 1 from public.foods limit 1;
 perform 1 from public.food_nutrition limit 1;
 perform 1 from public.food_portions limit 1;
 perform 1 from public.meals limit 1;
 return true;
end $$;
revoke all on function public.core_readiness() from public, anon, authenticated;
grant execute on function public.core_readiness() to anon, authenticated;
notify pgrst, 'reload schema';
