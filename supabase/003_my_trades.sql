-- Global Macro Desk: "My Trades" (his request, 26 Nov 2026; same as F&O Desk's My Stock Trades).
-- Run once in Supabase -> SQL Editor -> New query -> Run. Safe to run again.
-- Needs trade_fix_until() and trade_set_closed_at() from fno-desk supabase/011_fix_closed_trades.sql
-- (already in the shared project).
--
-- His choices: P&L in net % (after a round-trip cost per asset class), US $ and rupees (USD/INR on
-- the closing day); open trades close automatically at the stop only (target by hand); a trade
-- closed by hand can be edited or reopened until the next weekday 19:40 IST, auto-closed trades
-- lock at once (same as F&O Desk). Trade details are kept (no 3-month archive).

create table if not exists public.gm_trades (
  id bigserial primary key,
  asset text not null check (asset in ('us', 'crypto', 'commodities')),
  symbol text not null,
  name text,
  side text not null check (side in ('Long', 'Short')),
  view text check (view in ('swing', 'positional')),          -- from an idea card; null = manual
  setup text,
  yahoo text,                                                   -- price symbol the job checks (BTC-USD, GC=F, AAPL)
  tv text,                                                      -- TradingView symbol for the chart button
  entry_time timestamptz not null,
  entry double precision not null,
  stop double precision,
  target double precision,
  qty double precision,                                         -- shares / coins / ounces or pounds
  charges_usd double precision default 0,
  cost_pct double precision,                                    -- round-trip cost used for net %
  status text not null default 'open' check (status in ('open', 'closed')),
  exit_time timestamptz,
  exit double precision,
  exit_reason text,
  net_pct double precision,                                     -- after cost_pct
  pnl_usd double precision,                                     -- (sell - buy) x qty - charges
  usdinr double precision,                                      -- rate used for pnl_inr
  pnl_inr double precision,
  source text,
  notes text,
  owner text default (auth.jwt() ->> 'email'),
  closed_at timestamptz,                                        -- set by trigger: closed by hand on the site
  created_at timestamptz not null default now()
);
create index if not exists gm_trades_status on public.gm_trades (status, asset);

drop trigger if exists gm_trades_closed_at on public.gm_trades;
create trigger gm_trades_closed_at before insert or update on public.gm_trades
  for each row execute function public.trade_set_closed_at();

-- only vs916491@gmail.com (signed in on the website); the jobs use the service key
alter table public.gm_trades enable row level security;
drop policy if exists "owner reads gm trades" on public.gm_trades;
drop policy if exists "owner adds gm trades" on public.gm_trades;
drop policy if exists "owner edits open or just-closed gm trades" on public.gm_trades;
drop policy if exists "owner deletes open gm trades" on public.gm_trades;
create policy "owner reads gm trades" on public.gm_trades for select to authenticated
  using ((auth.jwt() ->> 'email') = 'vs916491@gmail.com');
create policy "owner adds gm trades" on public.gm_trades for insert to authenticated
  with check ((auth.jwt() ->> 'email') = 'vs916491@gmail.com');
create policy "owner edits open or just-closed gm trades" on public.gm_trades for update to authenticated
  using ((auth.jwt() ->> 'email') = 'vs916491@gmail.com'
         and (status = 'open' or now() < public.trade_fix_until(closed_at)))
  with check ((auth.jwt() ->> 'email') = 'vs916491@gmail.com');
create policy "owner deletes open gm trades" on public.gm_trades for delete to authenticated
  using ((auth.jwt() ->> 'email') = 'vs916491@gmail.com' and status = 'open');
