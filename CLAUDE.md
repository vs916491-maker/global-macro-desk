# Global Macro Desk — project notes

Owner: Vivek (GitHub `vs916491-maker`). Personal analysis only, not investment advice.
Repo: `vs916491-maker/global-macro-desk` (public). Site: GitHub Pages, behind the same email + password sign-in as F&O Desk.
Built 22 Nov 2026. Sister sites: F&O Desk (`fno-desk`), Sector Strength, NSE Fundamentals Desk — all share one Supabase project.

## Decisions (his answers, 22 Nov 2026)
- Separate site (not tabs in F&O Desk); same Supabase project and sign-in.
- News / Fed interpretation: rule-based and free (RSS + keyword scoring + FRED). No paid AI API.
- Commodities: COMEX prices and charts in USD (he is fine with USD; no MCX).
- Ideas in two views everywhere: **Swing** (days–weeks) and **Positional** (weeks–months), logged in a Track record.
- Crypto and US: long only. Commodities: long and short.

## Tabs and docs (Supabase `docs` keys)
| Tab | Doc | Job |
|---|---|---|
| Global macro | `gm_macro`, `gm_news` | hourly |
| Money flow | `gm_flows` | hourly |
| Crypto | `gm_crypto` | hourly |
| Commodities | `gm_commod` | hourly |
| US equity | `gm_us` (+ `gm_us_universe` cached stock list) | daily after US close |
| Track record | table `gm_ideas` | both |
| (status) | `gm_status` (per job: time, problems, counts), `gm_hist` (daily scores, FII days, BTC dominance; 400 days) | |

## Rules in brief (all numbers in `gmd/config.py`; site Readme tab has the full text — **update `viewReadme` in site/app.js when a rule changes**)
- Global score: VIX 20, HY credit 15, S&P trend 15, DXY 1m 15, US10Y 1m 10, curve 5, copper/gold 10, news 10. India: Nifty trend 25, India VIX 15, USDINR 15, Brent 15, FII 5-session 15, India news 15. Zones ±20 / ±60.
- Money flow (INR terms): score = 55% momentum (risk-adjusted 1/3/6m return, trend, CMF) + 45% macro fit (factor weights in `flows.FIT`). FD uses `FD_RATE` and `INDIA_CPI` — edit when they change. Suggested mix = `BASE_MIX` tilted ±50% max.
- Setups (`gmd/setups.py`): base breakout, trend pullback, momentum leader (positional); shorts = mirrors (commodities only). Score: trend 25, momentum 20, setup 25, volume 10, macro 20; −5 against the higher timeframe. Swing: 4h (crypto, commodities) / daily (US), 1:2, 14 days. Positional: daily, 1:3, 90 days. Ideas ≥ 50 logged.
- Track record: fill at next candle open; stop/target on highs/lows; both in one candle = "unclear" (excluded); gaps exit at the open; time exit at the last close before the limit.
- Central bank dates in `config.FOMC` / `config.RBI_MPC` (2027 FOMC revised 12 Nov 2026: last meeting Nov 16–17, Oct 26–27 strategy only). Add new years when published.

## Scheduling
Supabase pg_cron → `dispatch_repo_workflow('global-macro-desk', …)`: `gm-hourly` at :07 every hour, `gm-us-equity` 21:40 UTC Mon–Fri. GitHub cron is a backup; jobs skip if they ran recently (hourly 40 min, US 5 h). The Vault token must include this repo.

## Testing
- `python tests/offline_run.py` — fake data through everything, writes ./out (copy to site/sample for the preview).
- Push to branch `selftest` → live-data dry run, results on branch `selftest-out` (`run.log` + JSON docs).

## Known limits
- Free endpoints (Yahoo, CoinGecko, NSE, RSS) can block or change; each run lists problems on the site and in the Actions summary.
- Keyword news tone is crude. No earnings calendar for US ideas. Yahoo crypto symbols for some coins need `config.YAHOO_COIN` entries.
