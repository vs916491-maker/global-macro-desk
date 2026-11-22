"""Offline smoke test: fake market data (random walks) through the whole pipeline.
Run: python tests/offline_run.py   (writes ./out/*.json; copy them to site/sample for the preview)"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gmd import run, sources, store  # noqa: E402

rng = np.random.default_rng(7)
BASE = {"^GSPC": 6800, "^NDX": 24000, "^DJI": 46000, "^RUT": 2400, "^NSEI": 26000, "^NSEBANK": 59000, "^VIX": 16,
        "^INDIAVIX": 12, "DX-Y.NYB": 99, "INR=X": 88.5, "^TNX": 4.1, "^FVX": 3.8, "^TYX": 4.7, "^IRX": 3.9, "BZ=F": 64,
        "CL=F": 60, "GC=F": 4100, "SI=F": 50, "HG=F": 5.0, "BTC-USD": 90000, "ETH-USD": 3000, "TLT": 90, "SPY": 670,
        "GLD": 380, "SLV": 45, "NIFTYBEES.NS": 290}


def fake(symbol, interval="1d", rng_s="2y"):
    hourly = interval == "1h"
    n = 120 * 24 if hourly else 520
    end = pd.Timestamp.now("UTC").tz_localize(None).floor("h" if hourly else "D")
    idx = pd.date_range(end=end, periods=n, freq="h" if hourly else "D")
    p0 = BASE.get(symbol, 20 + (abs(hash(symbol)) % 300))
    r = np.random.default_rng(abs(hash(symbol + interval)) % 2**32)
    drift = (abs(hash(symbol)) % 7 - 3) * (0.00004 if hourly else 0.0008)
    vol = 0.004 if hourly else 0.018
    ret = r.normal(drift, vol, n)
    c = p0 * np.exp(np.cumsum(ret) - np.cumsum(ret)[-1] * 0.0)
    o = np.r_[c[0], c[:-1]] * (1 + r.normal(0, vol / 4, n))
    h = np.maximum(o, c) * (1 + abs(r.normal(0, vol / 2, n)))
    lo = np.minimum(o, c) * (1 - abs(r.normal(0, vol / 2, n)))
    v = r.integers(1e5, 1e7, n).astype(float) * (5 if symbol in ("SPY",) else 1)
    df = pd.DataFrame({"Open": o, "High": h, "Low": lo, "Close": c, "Volume": v}, index=idx)
    df.attrs.update({"price": float(c[-1]), "name": symbol, "symbol": symbol})
    return df


def fake_fred(sid, days=800):
    idx = pd.date_range(end=pd.Timestamp.now().normalize(), periods=600, freq="D")
    base = {"DGS10": 4.1, "DGS2": 3.6, "T10Y2Y": 0.5, "DFII10": 1.8, "DFEDTARU": 4.0, "DFF": 3.9,
            "BAMLH0A0HYM2": 3.0, "CPIAUCSL": 320, "PCEPILFE": 125, "UNRATE": 4.3, "WALCL": 6.6e6, "T10YIE": 2.3}[sid]
    s = pd.Series(base + np.cumsum(rng.normal(0, base * 0.002, 600)), index=idx)
    if sid in ("CPIAUCSL", "PCEPILFE", "UNRATE"):
        s = s.resample("MS").last()
    return s


COINS = ["btc", "eth", "xrp", "bnb", "sol", "usdt", "doge", "ada", "trx", "link", "avax", "sui", "xlm", "ton"]


def fake_cg(path, params=None):
    if path == "/coins/markets":
        return [{"id": s, "symbol": s, "name": s.upper() + " coin", "market_cap_rank": i + 1, "current_price": 1.0 if s == "usdt" else 100 / (i + 1),
                 "market_cap": 1e11 / (i + 1), "total_volume": 1e9 / (i + 1), "price_change_percentage_24h_in_currency": rng.normal(0, 3),
                 "price_change_percentage_7d_in_currency": rng.normal(0, 8), "price_change_percentage_30d_in_currency": rng.normal(0, 15),
                 "ath_change_percentage": -abs(rng.normal(30, 20))} for i, s in enumerate(COINS)]
    if path == "/global":
        return {"data": {"total_market_cap": {"usd": 3.1e12}, "market_cap_change_percentage_24h_usd": 1.2,
                         "market_cap_percentage": {"btc": 58.2, "eth": 11.9}}}
    if path == "/search/trending":
        return {"coins": [{"item": {"symbol": "SUI"}}, {"item": {"symbol": "TON"}}]}


def fake_rss(url, source, limit=40):
    heads = ["Gold rises to record high as war fears grow", "Treasury yields jump after hot inflation data",
             "Stocks rally as Fed signals rate cut", "Bitcoin plunges below $80,000 amid liquidations",
             "Nifty falls 1% as FIIs sell, rupee slips", "Oil surges on Middle East attack",
             "Copper slides on China slowdown worries", "Sensex, Nifty end higher on strong earnings"]
    now = datetime.now(timezone.utc)
    return [{"title": f"{h} ({source})", "link": "https://example.com", "ts": (now - timedelta(hours=i * 5)).isoformat(),
             "source": source, "desc": ""} for i, h in enumerate(heads)]


sources.yahoo = fake
sources.fred = fake_fred
sources.coingecko = fake_cg
sources.fear_greed = lambda days=60: [{"date": (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d"), "value": int(40 + 20 * np.sin(i / 5)),
                                       "label": "Neutral"} for i in range(days)]
sources.rss = fake_rss
sources.nse_fii = lambda: [{"cat": "FII", "date": "21-Nov-2026", "net": -2310.5}, {"cat": "DII", "date": "21-Nov-2026", "net": 3120.2}]
sources.us_universe = lambda: [{"symbol": s, "name": s + " Inc", "sector": ["Information Technology", "Financials", "Energy", "Health Care"][i % 4],
                                "index": "S&P 500"} for i, s in enumerate([f"T{i:03d}" for i in range(320)])]

db = store.Local()
run.hourly(db, force=True)
sources.PROBLEMS.clear()
run.us(db, force=True)
print({k: len(v) for k, v in db.tables.items()})
import json  # noqa: E402
Path("out/gm_ideas.json").write_text(json.dumps(db.tables.get("gm_ideas", []), indent=1, default=str))
