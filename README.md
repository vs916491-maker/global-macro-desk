# Global Macro Desk

Personal website for global macro, money flow across asset classes, crypto, commodities (gold, silver, copper)
and US equity ideas. Works like F&O Desk: GitHub Actions collects free data → Supabase stores it →
GitHub Pages shows it, behind the same email + password sign-in. No laptop needed.

Site: https://vs916491-maker.github.io/global-macro-desk/ (after step 4)

## Tabs
| Tab | What it shows | Updates |
|---|---|---|
| Global macro | Global, India and overall risk-appetite scores (−100..+100) with their parts; "What it means" rules; US/India/rates/commodity/crypto quotes; Fed, rates and inflation (FRED); next FOMC and RBI decisions; news with keyword tone | hourly |
| Money flow | Indian equity, US equity, US bonds, bank FDs, gold, silver, crypto ranked by score (momentum + money flow + macro fit, INR terms), stance, suggested mix vs your base mix | hourly |
| Crypto | Market cap, BTC dominance, Fear & Greed, alt season; trending coins table; Swing (4-hour) / Positional (daily) long ideas | hourly |
| Commodities | Gold, silver, copper (COMEX, USD): direction score with drivers, trends, ratios; Swing / Positional ideas, long and short | hourly |
| US equity | Trend and sentiment scores, breadth, sector and style money flow (rotation), Top 10 ideas per view, momentum leaders | daily, after the US close |
| Track record | Every idea scoring 50+: filled at the next candle's open, closed at stop / target / time exit | with each job |
| Readme | Every rule in plain words | — |

## One-time setup (about 10 minutes)
1. **Repo secrets** – GitHub → this repo → Settings → Secrets and variables → Actions → New repository secret.
   Add the same two values F&O Desk uses: `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`.
2. **Let Supabase start the jobs** – the GitHub token stored in Supabase Vault (`github_token`, named
   `fno-desk-supabase` on GitHub) must include this repo: GitHub → Settings → Developer settings →
   Fine-grained tokens → fno-desk-supabase → Edit → Repository access → add `global-macro-desk`
   (permission Actions: Read and write) → Update. The token value stays the same.
3. **Database** – Supabase → SQL Editor → New query → paste `supabase/001_global_macro_desk.sql` → Run.
   Then run `select status_code, content from net._http_response order by id desc limit 3;` → 204 = OK.
4. **Website** – GitHub → this repo → Settings → Pages → Source: **GitHub Actions**. Then Actions →
   "Publish website" → Run workflow.
5. **FRED key (recommended, free)** – FRED's public download blocks GitHub's servers, so without a key the desk
   uses Yahoo stand-ins for yields and credit and shows no CPI, PCE, Fed funds or Fed balance sheet.
   Get a free key at https://fredaccount.stlouisfed.org/apikeys (sign up → Request API key), then add it as
   repo secret `FRED_API_KEY`.
6. **AI view (Gemini, free)** – go to https://aistudio.google.com/apikey → sign in with Google → **Create API key**
   → copy it. Add it as repo secret `GEMINI_API_KEY`. Then Supabase → SQL Editor → run
   `supabase/002_ai_brief.sql` (schedules it at 8:25 am and 6:55 pm IST). First run: Actions → "AI view" →
   Run workflow (tick *force*).
7. **First data** – Actions → "Hourly update" → Run workflow (tick *force*); then "US equity scan" → Run workflow (tick *force*).
   Each run's summary lists any data source problems.

## Main files
- `gmd/config.py` – **all thresholds, weights, lists, FD rate and India CPI in one place**
- `gmd/sources.py` – Yahoo candles, FRED, CoinGecko, Fear & Greed, RSS, Wikipedia stock lists, NSE FII/DII
- `gmd/macro.py` – Global macro tab; `gmd/news.py` – news and keyword tone; `gmd/flows.py` – Money flow
- `gmd/setups.py` – shared price-action setups and scores; `gmd/crypto.py`, `gmd/commodities.py`, `gmd/usequity.py`
- `gmd/record.py` – Track record; `gmd/run.py` – jobs (`python -m gmd.run hourly|us|all [--force] [--dry]`)
- `site/` – plain HTML/CSS/JS; `site/sample/` – preview data (open the site without Supabase settings)
- `tests/offline_run.py` – offline test with fake data

## Workflows
- `hourly.yml` – Supabase pg_cron at :07 every hour; GitHub cron :37 as backup (skips if it already ran)
- `us-equity.yml` – pg_cron 21:40 UTC Mon–Fri; GitHub cron 22:25 UTC backup
- `selftest.yml` – push to branch `selftest`: dry run with live data, results saved to branch `selftest-out`
- `ai-brief.yml` – Gemini AI view, pg_cron 02:55 and 13:25 UTC (backup 03:20 / 14:20); skips if it ran in 3 h
- `pages.yml` – publishes `site/`; `keepalive.yml` – Sundays, keeps schedules alive

For personal analysis only, not investment advice. All data sources are free and unofficial and can change without notice.
