# Global Macro Desk — project notes

Owner: Vivek (GitHub `vs916491-maker`). Personal analysis only, not investment advice.
Repo: `vs916491-maker/global-macro-desk` (public). Site: GitHub Pages, behind the same email + password sign-in as F&O Desk.
Built 22 Nov 2026. Sister sites: F&O Desk (`fno-desk`), Sector Strength, NSE Fundamentals Desk — all share one Supabase project.

## Decisions (his answers, 22 Nov 2026)
- Separate site (not tabs in F&O Desk); same Supabase project and sign-in.
- News / Fed interpretation: rule-based and free (RSS + keyword scoring + FRED). No paid AI API.
- Commodities: COMEX prices and charts in USD (he is fine with USD; no MCX).
- **Brent crude and aluminium added 26 Nov 2026** (his request): Brent `BZ=F` (TV `TVC:UKOIL`), aluminium COMEX `ALI=F` (TV `COMEX:ALI1!`, thinly traded); long + short ideas like the metals (his choice); **no Euphoria meter** for them until backtested (his choice). Drivers in `commodities.DRIVERS` (Brent: growth 0.3, risk 0.2, dollar 0.15, oil-price headlines `news_oil_px` 0.35; aluminium: growth 0.35, risk 0.25, dollar 0.2, aluminium headlines 0.2) - untested. News: Google News feeds for Brent and aluminium, tag `aluminium`, sentiment key `oil_px` = oil price direction (the `oil` key stays market mood). Card exchange/unit from `config.COMMOD_INFO`.
- Ideas in two views everywhere: **Swing** (days–weeks) and **Positional** (weeks–months), logged in a Track record.
- US: long only. Commodities: long and short. Crypto: long only at first; **shorts added 22 Nov 2026** (his request, both Swing and Positional; perpetual futures; squeeze warning on all crypto shorts, funding-fee warning on positional ones).

## Tabs and docs (Supabase `docs` keys)
| Tab | Doc | Job |
|---|---|---|
| Global macro | `gm_macro`, `gm_news` | hourly |
| Money flow | `gm_flows` | hourly |
| Crypto | `gm_crypto` | hourly |
| Commodities | `gm_commod` | hourly |
| US equity | `gm_us` (+ `gm_us_universe` cached stock list) | daily after US close |
| Track record | table `gm_ideas` | both |
| My trades (`#/trades`) | table `gm_trades` (`supabase/003_my_trades.sql`), live prices doc `gm_trade_prices` | hourly |
| Euphoria meter (on Global macro; tags on Money flow, Crypto, Commodities) | `gm_euphoria` | hourly |
| (status) | `gm_status` (per job: time, problems, counts), `gm_hist` (daily scores, FII days, BTC dominance; 400 days) | |

- Idea cards (US equity, Crypto, Commodities): **Chart** button next to the symbol opens TradingView at the card's interval (4-hour for crypto/commodity swing, daily otherwise); his request, 26 Nov 2026. US class shares are converted BRK-B → BRK.B (`tvSym()` in site/app.js).

## My trades (his request, 26 Nov 2026: "same as F&O Desk's stock trades section")
- His choices: P&L as net % + US $ + ₹ (USD/INR on the closing day, `gm_trades.usdinr`); **auto-close at the stop only** (target by hand); round-trip cost per asset class (`config.TRADE_COST_PCT` us 0.2, crypto 0.2, commodities 0.05; keep `TRADE_COST` in site/app.js in step); lock rule same as F&O Desk (closed by hand → fixable until next weekday 19:40 IST via shared `trade_fix_until()` / `trade_set_closed_at()` trigger; job-closed lock at once).
- `gmd/mytrades.py` runs inside the hourly job (all assets, US stocks too): Yahoo 1h candles that start at/after the entry time; gap past the stop fills at the open. Yahoo symbol from the trade's `yahoo` column, else derived (crypto `SYM-USD` / `config.YAHOO_COIN`, GOLD/SILVER/COPPER → GC=F/SI=F/HG=F, US BRK.B → BRK-B).
- Site: "I took this trade" on every idea card (prefills levels, source "Swing idea"/"Positional idea"); FY (Apr–Mar, IST) totals, Year by year, Month by month, Open (Now, P&L %, $/₹) and Closed tables, asset filter, Export CSV. No 3-month archive (details kept).

## Rules in brief (all numbers in `gmd/config.py`; site Readme tab has the full text — **update `viewReadme` in site/app.js when a rule changes**)
- Global score: VIX 20, HY credit 15, S&P trend 15, DXY 1m 15, US10Y 1m 10, curve 5, copper/gold 10, news 10. India: Nifty trend 25, India VIX 15, USDINR 15, Brent 15, FII 5-session 15, India news 15. Zones ±20 / ±60.
- Money flow (INR terms): score = 55% momentum (risk-adjusted 1/3/6m return, trend, CMF) + 45% macro fit (factor weights in `flows.FIT`). FD uses `FD_RATE` and `INDIA_CPI` — edit when they change. Suggested mix = `BASE_MIX` tilted ±50% max.
- Setups (`gmd/setups.py`): base breakout, trend pullback, momentum leader (positional); shorts = mirrors (commodities and crypto). Score: trend 25, momentum 20, setup 25, volume 10, macro 20; −5 against the higher timeframe. Swing: 4h (crypto, commodities) / daily (US), 1:2, 14 days. Positional: daily, 1:3, 90 days. Ideas ≥ 50 logged.
- Track record: fill at next candle open; stop/target on highs/lows; both in one candle = "unclear" (excluded); gaps exit at the open; time exit at the last close before the limit.
- Central bank dates in `config.FOMC` / `config.RBI_MPC` (2027 FOMC revised 12 Nov 2026: last meeting Nov 16–17, Oct 26–27 strategy only). Add new years when published.

## Global macro tab layout (his request, 22 Nov 2026)
- Top: separate cards for US equity, Indian equity, US bonds, gold, silver, crypto = Money flow score rescaled (score − 50) × 2 (his choice; Global/India/Overall cards replaced — their parts tables stay lower down, titled with the score). Gold and silver separate.
- Score history right below: one line per asset class, tap legend buttons to hide/show, 3m/6m/1y. 12 months rebuilt by `gmd/backfill.py` (workflow `backfill.yml`, one-off, never overwrites live days; no news/FII for past days).
- **Key Drivers** section (his request; replaced "Rates and dollar"): US 10Y, Fed balance sheet (QE/QT, FRED WALCL weekly), USD/INR, India 10Y G-Sec (TradingView scanner `TVC:IN10Y`, his choice; daily values stored in `gm_hist.in10y`, FRED `INDIRLTLT01STM` monthly as backup and older history), Brent, DXY. Brent and USD/INR shown only here. Other rate cards (2Y/5Y/30Y/3M/TLT/HYG/IEF) removed from display but still used in scores.
- Quote cards tinted by the 1-month move's meaning for markets (green good / red bad / grey little change; `POL` and `FLAT` in site/app.js: rising yields, VIX, crude, DXY, USD-INR = bad), his request.
- Every section below the cards folds (remembered per section) + Collapse all / Expand all.
- Euphoria meter folds away (closed by default, remembers open/closed); alert banners still show above it.

## Euphoria meter (`gmd/euphoria.py`, added 22 Nov 2026 at his request: "don't get carried away by created euphoria", his Jan 2025 crypto example)
- His choices: **warning only** (never changes scores, ideas or the mix); Euphoria meter only (no Panic meter); CFTC positioning yes; backtest first.
- 0-100 = price stretch 40 (gap above 200-day and 30-day gain as 5-year percentiles, weekly RSI 60-80) + crowd mood 20 (crypto F&G 7-day avg; VIX / India VIX low) + large speculators 20 (CFTC legacy non-commercial net % OI, 3-year percentile; gold 088691, silver 084691, copper 085692, S&P 13874A; **not BTC**: CME BTC speculators are basis trades) + breadth 10 (live) + news flood 10 (live, after 20 days of `gm_hist.days[*].news`). Calm <40, Warm 40-60, Hot 60-80, Euphoric 80+.
- Backtest (`tests/euphoria_backtest.py`, workflow `euphoria-test.yml`, results branch `euphoria-test-out`): euphoria alone is momentum (prices often rose 10-40% more). Worked: crypto Hot then close below the 50-day (lower 90 days later 70%, 25%+ drop 41%; e.g. 27 Dec 2024, 7 Jan 2025); silver at 80+ (lower 90 days later 56%). Not useful: gold, US equity, Nifty (high = strong trend). BTC tops: Nov 2021 58, Mar 2024 67, Dec 2024 62, Jan 2025 57, Oct 2025 35 (missed).
- Live policy (`POLICY`): crypto = amber "don't chase" at 60+, red "first crack" when 60+ in the last 60 days and close < 50-day; silver/copper = red at 80+; gold/US/India = info only. Alerts add a warning line to crypto and long commodity ideas.

## AI view (`gmd/ai.py`, Gemini free tier; added 22 Nov 2026 at his request)
- His choices: daily brief + news reading per asset (with "hype" flag) + For/Against second opinion on ideas; twice a day (pg_cron `gm-ai-brief` 02:55 and 13:25 UTC, `supabase/002_ai_brief.sql`; workflow `ai-brief.yml`); **text only** (never changes scores/ideas/mix).
- One Gemini call per run (JSON output); model auto-picked from the key's list (newest stable "flash"), fallback gemini-2.5-flash / 2.0-flash. Sends only desk numbers, ~140 headlines, top 20 ideas (no personal data; free-tier inputs may be used by Google). Number check: any sentence with a number not in the data sent is dropped (`removed`). Doc `gm_ai`; idea comments keyed `tab|view|symbol|side|setup`. Needs secret `GEMINI_API_KEY`.

## Scheduling
Supabase pg_cron → `dispatch_repo_workflow('global-macro-desk', …)`: `gm-hourly` at :07 every hour, `gm-us-equity` 21:40 UTC Mon–Fri. GitHub cron is a backup; jobs skip if they ran recently (hourly 40 min, US 5 h). The Vault token must include this repo.

## Testing
- `python tests/offline_run.py` — fake data through everything, writes ./out (copy to site/sample for the preview).
- Push to branch `selftest` → live-data dry run, results on branch `selftest-out` (`run.log` + JSON docs).

## Known limits
- FRED's public CSV times out from GitHub runners (seen 22 Nov 2026). With repo secret `FRED_API_KEY` the FRED API is used; without it, Yahoo stand-ins: 10Y (^TNX), 2Y (2YY=F), curve = 10Y − 2Y, credit = HYG/IEF 1-month, "2Y minus 3-month bill" instead of 2Y minus Fed funds; CPI/PCE/Fed funds/balance sheet missing.
- Free endpoints (Yahoo, CoinGecko, NSE, RSS) can block or change; each run lists problems on the site and in the Actions summary.
- Keyword news tone is crude. No earnings calendar for US ideas. Yahoo crypto symbols for some coins need `config.YAHOO_COIN` entries.
