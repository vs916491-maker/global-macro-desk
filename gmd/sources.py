"""Free data sources. All are public endpoints that can change without notice; every
function returns an empty result on failure and records the problem in PROBLEMS, which
each run shows in its summary and on the site."""

from __future__ import annotations

import io
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import pandas as pd
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
PROBLEMS: list[str] = []


def problem(msg: str):
    if msg not in PROBLEMS:
        PROBLEMS.append(msg)
    print("PROBLEM:", msg)


def _get(url, params=None, timeout=25, tries=2, headers=None):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": UA, **(headers or {})})
            if r.status_code == 429:
                time.sleep(4 * (i + 1))
                last = "HTTP 429 (rate limit)"
                continue
            if r.status_code != 200:
                last = f"HTTP {r.status_code}"
                time.sleep(1.5)
                continue
            return r
        except requests.RequestException as e:
            last = str(e)[:120]
            time.sleep(1.5)
    raise ConnectionError(last or "no answer")


# ====================================================================== Yahoo candles
def yahoo(symbol: str, interval: str = "1d", rng: str = "2y") -> pd.DataFrame:
    """OHLCV candles indexed by UTC start time (naive). Empty frame on failure.
    attrs: price (latest), prev_close, name."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(symbol)}"
    try:
        r = _get(url, {"interval": interval, "range": rng, "includePrePost": "false"}, timeout=20)
        res = r.json()["chart"]["result"][0]
    except Exception:  # noqa: BLE001
        try:   # second host
            r = _get(url.replace("query1", "query2"), {"interval": interval, "range": rng}, timeout=20, tries=1)
            res = r.json()["chart"]["result"][0]
        except Exception:  # noqa: BLE001
            return pd.DataFrame()
    meta = res.get("meta", {})
    ts = res.get("timestamp")
    if not ts:
        return pd.DataFrame()
    q = res["indicators"]["quote"][0]
    idx = pd.to_datetime(ts, unit="s", utc=True).tz_localize(None)
    df = pd.DataFrame({"Open": q.get("open"), "High": q.get("high"), "Low": q.get("low"),
                       "Close": q.get("close"), "Volume": q.get("volume")}, index=idx).dropna(subset=["Close"])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    for c in ("Open", "High", "Low"):
        df[c] = df[c].fillna(df["Close"])
    df["Volume"] = df["Volume"].fillna(0)
    df.attrs["price"] = meta.get("regularMarketPrice")
    df.attrs["prev_close"] = meta.get("chartPreviousClose") or meta.get("previousClose")
    df.attrs["name"] = meta.get("shortName") or meta.get("longName") or symbol
    df.attrs["symbol"] = symbol
    return df


def yahoo_many(symbols: list[str], interval="1d", rng="2y", workers=8, gap=0.05) -> dict[str, pd.DataFrame]:
    out = {}

    def one(sym):
        time.sleep(gap)
        return sym, yahoo(sym, interval, rng)

    with ThreadPoolExecutor(workers) as ex:
        for sym, df in ex.map(one, symbols):
            if not df.empty:
                out[sym] = df
    missing = [s for s in symbols if s not in out]
    if missing:
        problem(f"Yahoo: no {interval} candles for {len(missing)} of {len(symbols)} symbols"
                f" ({', '.join(missing[:8])}{'…' if len(missing) > 8 else ''})")
    return out


# ====================================================================== FRED (St. Louis Fed)
def fred(series: str) -> pd.Series:
    try:
        r = _get("https://fred.stlouisfed.org/graph/fredgraph.csv", {"id": series}, timeout=30)
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = ["date", "v"]
        df["v"] = pd.to_numeric(df["v"], errors="coerce")
        s = df.dropna().set_index(pd.to_datetime(df.dropna()["date"]))["v"]
        return s[s.index >= pd.Timestamp.now() - pd.Timedelta(days=800)]
    except Exception as e:  # noqa: BLE001
        problem(f"FRED {series}: {e}")
        return pd.Series(dtype=float)


def fred_many(ids) -> dict[str, pd.Series]:
    with ThreadPoolExecutor(6) as ex:
        return dict(zip(ids, ex.map(fred, ids)))


# ====================================================================== crypto
CG = "https://api.coingecko.com/api/v3"


def coingecko(path: str, params=None):
    try:
        return _get(CG + path, params, timeout=30, tries=3).json()
    except Exception as e:  # noqa: BLE001
        problem(f"CoinGecko {path}: {e}")
        return None


def fear_greed(days=60) -> list[dict]:
    """Crypto Fear & Greed index (alternative.me), newest first."""
    try:
        j = _get("https://api.alternative.me/fng/", {"limit": days}).json()
        return [{"date": datetime.fromtimestamp(int(x["timestamp"]), timezone.utc).strftime("%Y-%m-%d"),
                 "value": int(x["value"]), "label": x["value_classification"]} for x in j.get("data", [])]
    except Exception as e:  # noqa: BLE001
        problem(f"Crypto Fear & Greed: {e}")
        return []


# ====================================================================== news (RSS)
def rss(url: str, source: str, limit=40) -> list[dict]:
    try:
        r = _get(url, timeout=20)
        root = ET.fromstring(r.content)
    except Exception as e:  # noqa: BLE001
        problem(f"News feed {source}: {e}")
        return []
    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    out = []
    for it in items[:limit]:
        def tx(tag):
            n = it.find(tag)
            if n is None:
                n = it.find("{http://www.w3.org/2005/Atom}" + tag)
            return (n.text or "").strip() if n is not None and n.text else ""
        title = re.sub(r"\s+", " ", tx("title"))
        link = tx("link")
        if not link:
            ln = it.find("{http://www.w3.org/2005/Atom}link")
            link = ln.get("href", "") if ln is not None else ""
        when = tx("pubDate") or tx("published") or tx("updated")
        try:
            ts = parsedate_to_datetime(when).astimezone(timezone.utc) if when and not when[:4].isdigit() \
                else datetime.fromisoformat(when.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:  # noqa: BLE001
            ts = datetime.now(timezone.utc)
        desc = re.sub(r"<[^>]+>", " ", tx("description") or tx("summary"))
        desc = re.sub(r"\s+", " ", desc).strip()[:300]
        if title:
            out.append({"title": title, "link": link, "ts": ts.isoformat(), "source": source, "desc": desc})
    return out


# ====================================================================== lists
def wiki_table(url: str, must_have: str) -> pd.DataFrame:
    try:
        r = _get(url, timeout=30)
        for t in pd.read_html(io.StringIO(r.text)):
            cols = [str(c) for c in t.columns]
            if any(must_have.lower() in c.lower() for c in cols):
                t.columns = cols
                return t
    except Exception as e:  # noqa: BLE001
        problem(f"Stock list {url.rsplit('/', 1)[-1]}: {e}")
    return pd.DataFrame()


def us_universe() -> list[dict]:
    """S&P 500 + Nasdaq 100 with GICS sector. Empty list on failure (caller falls back)."""
    out = {}
    sp = wiki_table("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "GICS Sector")
    if not sp.empty:
        sc = next(c for c in sp.columns if c.lower() in ("symbol", "ticker"))
        for _, r in sp.iterrows():
            t = str(r[sc]).strip().replace(".", "-")
            out[t] = {"symbol": t, "name": str(r.get("Security", t)), "sector": str(r.get("GICS Sector", "")),
                      "index": "S&P 500"}
    nq = wiki_table("https://en.wikipedia.org/wiki/Nasdaq-100", "Ticker")
    if not nq.empty:
        tc = next(c for c in nq.columns if "ticker" in c.lower() or c.lower() == "symbol")
        secc = next((c for c in nq.columns if "sector" in c.lower()), None)
        namec = next((c for c in nq.columns if c.lower() in ("company", "security")), None)
        for _, r in nq.iterrows():
            t = str(r[tc]).strip().replace(".", "-")
            if t in out:
                out[t]["index"] = "S&P 500 + Nasdaq 100"
            else:
                out[t] = {"symbol": t, "name": str(r[namec]) if namec else t,
                          "sector": str(r[secc]) if secc else "", "index": "Nasdaq 100"}
    return list(out.values())


# ====================================================================== India: FII/DII cash flows (NSE)
def nse_fii() -> list[dict]:
    """Latest FII/FPI and DII cash-market net (₹ crore). Unofficial NSE endpoint."""
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*",
                      "Referer": "https://www.nseindia.com/reports/fii-dii"})
    try:
        s.get("https://www.nseindia.com/", timeout=20)
        j = s.get("https://www.nseindia.com/api/fiidiiTradeReact", timeout=20).json()
        out = []
        for row in j:
            cat = str(row.get("category", "")).upper()
            out.append({"cat": "FII" if "FII" in cat or "FPI" in cat else "DII" if "DII" in cat else cat,
                        "date": row.get("date"), "net": float(str(row.get("netValue", 0)).replace(",", ""))})
        return out
    except Exception as e:  # noqa: BLE001
        problem(f"NSE FII/DII: {e}")
        return []
