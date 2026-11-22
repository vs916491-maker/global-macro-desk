-- Global Macro Desk: run once in Supabase -> SQL Editor -> New query -> Run.
-- Uses the same Supabase project as F&O Desk: the `docs` table (keys gm_*) and the
-- dispatch_repo_workflow() function already exist there (fno-desk supabase/008).

-- ------------------------------------------------------------ Track record
create table if not exists public.gm_ideas (
  id bigserial primary key,
  key text unique not null,
  tab text not null check (tab in ('crypto', 'commodities', 'us')),
  view text not null check (view in ('swing', 'positional')),
  symbol text not null, name text,
  side text not null check (side in ('Long', 'Short')),
  setup text, score integer, tf text,
  signal_ts timestamptz, entry_after timestamptz,
  planned_entry double precision, stop double precision, target double precision,
  status text not null default 'pending' check (status in ('pending', 'open', 'closed')),
  entry double precision, entry_ts timestamptz,
  exit double precision, exit_ts timestamptz, result text,
  net_pct double precision, r_mult double precision,
  last_price double precision, last_ts timestamptz, last_pct double precision,
  max_days integer, info jsonb,
  created_at timestamptz not null default now()
);
create index if not exists gm_ideas_open on public.gm_ideas (tab, status);
create index if not exists gm_ideas_signal on public.gm_ideas (signal_ts desc);

-- only vs916491@gmail.com (signed in on the website) can read it; the jobs use the service key
alter table public.gm_ideas enable row level security;
drop policy if exists "owner reads gm ideas" on public.gm_ideas;
create policy "owner reads gm ideas" on public.gm_ideas for select to authenticated
  using ((auth.jwt() ->> 'email') = 'vs916491@gmail.com');

-- ------------------------------------------------------------ schedules (pg_cron, UTC)
do $$
declare j record;
begin
  for j in select jobname from cron.job where jobname like 'gm-%' loop
    perform cron.unschedule(j.jobname);
  end loop;
end $$;
-- every hour at :07 (all days: crypto trades 24/7)
select cron.schedule('gm-hourly', '7 * * * *',
  $$select public.dispatch_repo_workflow('global-macro-desk', 'hourly.yml')$$);
-- US equity scan 21:40 UTC Mon-Fri = 03:10 IST Tue-Sat (after the 4 pm New York close, summer and winter)
select cron.schedule('gm-us-equity', '40 21 * * 1-5',
  $$select public.dispatch_repo_workflow('global-macro-desk', 'us-equity.yml')$$);

-- one test call now. Then: select status_code, content from net._http_response order by id desc limit 3;
-- 204 = OK; 403/404 = the GitHub token in Vault cannot reach this repo yet (add the repo to the token, see README)
select public.dispatch_repo_workflow('global-macro-desk', 'hourly.yml') as test_request_id;
