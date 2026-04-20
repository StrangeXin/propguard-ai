-- Force PostgREST to reload its schema cache after the order_attributions
-- table appeared via a collided earlier migration (20260424000000). Without
-- this reload PostgREST keeps returning PGRST205 "table not found in schema
-- cache" for every select/insert against order_attributions even though the
-- table exists.
notify pgrst, 'reload schema';
