"""Euphoria meter (0-100) per asset class: a warning when a move looks crowded and over-loved.

Parts (each 0..1, 0 = normal, 1 = extreme), all measured against the asset's OWN history, point in time:
  stretch    price far above its 200-day average (percentile of the gap), 30-day gain percentile,
             weekly RSI above 60 (80 = full)
  mood       crypto: Fear & Greed 7-day average (50 = 0, 90 = 1); US: VIX low (20 = 0, 12 = 1);
             India: India VIX low (16 = 0, 10 = 1)
  crowd      CFTC large speculators (non-commercial) net long as % of open interest, percentile over
             3 years (weekly; usable 3 days after the Tuesday report date)
  breadth    live only: crypto = share of top coins beating BTC (alt season) / above their 200-day;
             US = share of stocks above their 200-day average
  news       live only, after 20 days of stored history: today's positive share and headline share for
             the asset vs its own last 60 days
Percentile parts score 0 at the median and 1 at the top 5%.
Levels: Calm < 40, Warm 40-60, Hot 60-80, Euphoric 80+. Warning only: it never changes scores or ideas."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import sources, ta

ASSETS = {
    # key: label, Yahoo symbol, CFTC contract code (legacy report), mood source
    "crypto": ("Crypto (Bitcoin)", "BTC-USD", None, "fng"),     # CME BTC speculators are mostly basis trades: left out (backtest 22 Nov 2026)
    "gold": ("Gold", "GC=F", "088691", None),
    "silver": ("Silver", "SI=F", "084691", None),
    "copper": ("Copper", "HG=F", "085692", None),
    "us_eq": ("US equity (S&P 500)", "SPY", "13874A", "vix"),
    "in_eq": ("Indian equity (Nifty)", "^NSEI", None, "ivix"),
}
WEIGHTS = {"stretch": 40, "mood": 20, "crowd": 20, "breadth": 10, "news": 10}
LEVELS = [(40, "Calm"), (60, "Warm"), (80, "Hot"), (101, "Euphoric")]
PCT_WIN = 1260          # ~5 years of daily values for percentiles
COT_WIN = 156           # 3 years of weekly reports
# what to do with the meter, from the backtest (22 Nov 2026)
POLICY = {"crypto": "crack", "silver": "euphoric", "copper": "euphoric", "gold": "info", "us_eq": "info", "in_eq": "info"}
POLICY_NOTE = {
    "crypto": "Backtest 2014-2026: when the meter had been 60+ and Bitcoin then closed below its 50-day average, it was lower "
              "90 days later 70% of the time and fell 25%+ in 41% of cases (e.g. 27 Dec 2024, 7 Jan 2025).",
    "silver": "Backtest 2000-2026: at 80+ silver was lower 90 days later 56% of the time; 10 of 12 such episodes saw a 15%+ drop from the next peak.",
    "copper": "Backtest 2000-2026: the May 2021 and May 2024 copper tops came with readings of 89 and 100.",
    "gold": "Backtest: here a high reading has meant a strong trend, not a top - shown for information only.",
    "us_eq": "Backtest: here a high reading has meant a strong trend, not a top (2022 and 2025 tops were macro-driven) - information only.",
    "in_eq": "Backtest: here a high reading has meant a strong trend, not a top - information only.",
}
NEWS_TAG = {"crypto": "crypto", "gold": "gold", "silver": "silver", "copper": "copper", "us_eq": "us_eq", "in_eq": "in_eq"}


def level(score):
    if score is None:
        return "No data"
    for hi, name in LEVELS:
        if score < hi:
            return name
    return "Euphoric"


def top_scale(p):
    """percentile 0..1 -> 0 at the median, 1 at the top 5%."""
    return ((p - 0.5) / 0.45).clip(0, 1)


def rolling_pct(s: pd.Series, win: int, minp: int) -> pd.Series:
    return s.rolling(win, min_periods=minp).rank(pct=True)


def stretch(close: pd.Series) -> pd.DataFrame:
    """Daily stretch parts for a daily close series (index = dates)."""
    c = close.dropna()
    gap = c / c.rolling(200, min_periods=150).mean() - 1
    r30 = c / c.shift(30) - 1
    p_gap = top_scale(rolling_pct(gap, PCT_WIN, 500))
    p_r30 = top_scale(rolling_pct(r30, PCT_WIN, 500))
    wk = c.resample("W-FRI").last().dropna()
    wrsi = ta.rsi(wk, 14)
    wrsi_d = wrsi.reindex(c.index.union(wrsi.index)).ffill().reindex(c.index).shift(1)   # last completed week
    p_rsi = ((wrsi_d - 60) / 20).clip(0, 1)
    out = pd.DataFrame({"gap": gap, "p_gap": p_gap, "r30": r30, "p_r30": p_r30, "wrsi": wrsi_d, "p_rsi": p_rsi})
    out["stretch"] = 0.45 * out.p_gap + 0.35 * out.p_r30 + 0.20 * out.p_rsi.fillna(0)
    return out


def mood(kind: str, idx: pd.DatetimeIndex, fng: pd.Series | None, vix: pd.Series | None) -> pd.Series:
    if kind == "fng" and fng is not None and not fng.empty:
        s = fng.rolling(7, min_periods=3).mean()
        return ((s - 50) / 40).clip(0, 1).reindex(idx, method="ffill")
    if kind in ("vix", "ivix") and vix is not None and not vix.empty:
        hi, full = (20, 8) if kind == "vix" else (16, 6)
        s = vix.rolling(5, min_periods=2).mean()
        return ((hi - s) / full).clip(0, 1).reindex(idx, method="ffill")
    return pd.Series(np.nan, index=idx)


def cot_history(code: str, since: str = "2014-01-01") -> pd.DataFrame:
    """CFTC legacy futures-only report: non-commercial (large speculator) net long % of open interest."""
    url = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
    try:
        r = sources._get(url, {"cftc_contract_market_code": code, "$limit": 5000,
                               "$where": f"report_date_as_yyyy_mm_dd >= '{since}'",
                               "$order": "report_date_as_yyyy_mm_dd"}, timeout=60)
        rows = r.json()
    except Exception as e:  # noqa: BLE001
        sources.problem(f"CFTC {code}: {e}")
        return pd.DataFrame()
    if not rows:
        sources.problem(f"CFTC {code}: no rows")
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    cols = df.columns
    lc = next((c for c in cols if c.startswith("noncomm_positions_long")), None)
    sc = next((c for c in cols if c.startswith("noncomm_positions_short")), None)
    oc = next((c for c in cols if c.startswith("open_interest_all")), None)
    dc = next((c for c in cols if c.startswith("report_date")), None)
    if not all((lc, sc, oc, dc)):
        sources.problem(f"CFTC {code}: unexpected columns {list(cols)[:12]}")
        return pd.DataFrame()
    out = pd.DataFrame({"date": pd.to_datetime(df[dc]).dt.tz_localize(None),
                        "long": pd.to_numeric(df[lc], errors="coerce"), "short": pd.to_numeric(df[sc], errors="coerce"),
                        "oi": pd.to_numeric(df[oc], errors="coerce")}).dropna()
    out = out.groupby("date").sum().sort_index()
    out["net_pct"] = (out.long - out.short) / out.oi * 100
    out["pctile"] = out.net_pct.rolling(COT_WIN, min_periods=52).rank(pct=True)
    out["avail"] = out.index + pd.Timedelta(days=3)          # published on Friday
    return out


def crowd(cot: pd.DataFrame, idx: pd.DatetimeIndex) -> pd.Series:
    if cot is None or cot.empty:
        return pd.Series(np.nan, index=idx)
    s = pd.Series(top_scale(cot.pctile).values, index=cot.avail)
    return s.reindex(idx.union(s.index)).ffill().reindex(idx)


def combine(parts: dict[str, pd.Series | float | None], weights=WEIGHTS):
    """weighted mean of the available parts x 100 (Series or scalars)."""
    num = den = 0
    for k, v in parts.items():
        if v is None:
            continue
        w = weights[k]
        if isinstance(v, pd.Series):
            m = v.notna()
            num = num + v.fillna(0) * w
            den = den + m * w
        elif not (isinstance(v, float) and np.isnan(v)):
            num += v * w
            den += w
    if isinstance(den, pd.Series):
        return (100 * num / den.replace(0, np.nan)).round(1)
    return round(100 * num / den, 1) if den else None


# ---------------------------------------------------------------- history (backtest and live chart)
def history(key: str, daily: pd.DataFrame, fng: pd.Series | None, vixs: dict, cot: pd.DataFrame | None) -> pd.DataFrame:
    label, sym, code, mk = ASSETS[key]
    c = daily.Close.copy()
    c.index = c.index.normalize()
    c = c[~c.index.duplicated(keep="last")]
    st = stretch(c)
    md = mood(mk, c.index, fng, vixs.get(mk)) if mk else None
    cr = crowd(cot, c.index) if code else None
    st["mood"] = md
    st["crowd"] = cr
    st["score"] = combine({"stretch": st.stretch, "mood": md, "crowd": cr})
    st["close"] = c
    return st


# ---------------------------------------------------------------- live
def live(hist_doc: dict, news_sent: dict, crypto_doc: dict | None, us_doc: dict | None, candles: dict) -> dict:
    """Current meter for each asset (called by the hourly job)."""
    vix = candles.get("^VIX")
    ivix = candles.get("^INDIAVIX")
    vixs = {"vix": vix.Close if vix is not None else None, "ivix": ivix.Close if ivix is not None else None}
    fng_list = sources.fear_greed(400)
    fng = pd.Series({pd.Timestamp(x["date"]): x["value"] for x in fng_list}).sort_index() if fng_list else None
    days = (hist_doc or {}).get("days", {})
    out = {}
    for key, (label, sym, code, mk) in ASSETS.items():
        df = candles.get(sym)
        df = sources.yahoo(sym, "1d", "10y")            # percentiles need years of history
        if (df is None or df.empty) and candles.get(sym) is not None:
            df = candles[sym]
        if df is None or df.empty:
            continue
        cot = cot_history(code, "2019-01-01") if code else None
        h = history(key, df, fng, vixs, cot)
        last = h.iloc[-1]
        br = breadth(key, crypto_doc, us_doc)
        nw = news_part(key, news_sent, days)
        parts = {"stretch": float(last.stretch) if pd.notna(last.stretch) else None,
                 "mood": float(last["mood"]) if pd.notna(last["mood"]) else None,
                 "crowd": float(last.crowd) if pd.notna(last.crowd) else None,
                 "breadth": br[0], "news": nw[0]}
        score = combine(parts)
        cot_now = None
        if cot is not None and not cot.empty:
            r = cot.iloc[-1]
            cot_now = {"date": cot.index[-1].strftime("%Y-%m-%d"), "net_pct": round(float(r.net_pct), 1),
                       "pctile": round(float(r.pctile) * 100) if pd.notna(r.pctile) else None}
        why = []
        if pd.notna(last.gap):
            pg = 0 if pd.isna(last.p_gap) else last.p_gap
            why.append(f"{last.gap * 100:+.1f}% vs 200-day average (stretch {round(pg * 100)}/100)")
        if pd.notna(last.r30):
            why.append(f"{last.r30 * 100:+.1f}% in 30 days")
        if pd.notna(last.wrsi):
            why.append(f"weekly RSI {last.wrsi:.0f}")
        if cot_now:
            why.append(f"large speculators net {cot_now['net_pct']:+.1f}% of open interest (percentile {cot_now['pctile']}/100 over 3 years)")
        why += br[1] + nw[1]
        if mk == "fng" and fng is not None:
            why.append(f"Fear & Greed {int(fng.iloc[-1])} (7-day avg {fng.tail(7).mean():.0f})")
        if mk in ("vix", "ivix") and vixs.get(mk) is not None:
            why.append(f"{'US VIX' if mk == 'vix' else 'India VIX'} {vixs[mk].iloc[-1]:.1f}")
        hist = h[["score"]].dropna().tail(365)
        c = h.close.dropna()
        ma50 = c.rolling(50).mean()
        hot60 = float(h.score.tail(60).max()) if h.score.tail(60).notna().any() else None
        below50 = bool(c.iloc[-1] < ma50.iloc[-1]) if pd.notna(ma50.iloc[-1]) else False
        alert = make_alert(key, score, hot60, below50)
        out[key] = {"label": label, "score": score, "level": level(score),
                    "parts": {k: None if v is None else round(v * 100) for k, v in parts.items()},
                    "why": why, "cot": cot_now, "alert": alert, "policy": POLICY[key], "note": POLICY_NOTE[key],
                    "hot60": hot60, "below50": below50,
                    "history": [{"date": d.strftime("%Y-%m-%d"), "score": float(v)} for d, v in hist.score.items()][::3]}
    return {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "assets": out}


def make_alert(key, score, hot60, below50):
    pol = POLICY[key]
    if score is None:
        return None
    if pol == "crack":
        if (hot60 or 0) >= 60 and below50:
            return {"level": "red", "title": "First crack after euphoria",
                    "text": "The crowd was Hot in the last 60 days and price has now closed below its 50-day average. "
                            "Don't buy the dip on hope: protect profits, tighten stops, no fresh buying until the trend repairs."}
        if score >= 60:
            return {"level": "amber", "title": f"{level(score)}: don't chase",
                    "text": "The move looks crowded. Avoid fresh buying on excitement, size down, tighten stops, consider booking part profits."}
        return None
    if pol == "euphoric" and score >= 80:
        return {"level": "red", "title": "Euphoric: don't chase",
                "text": "Over-loved move. No fresh buying on excitement; tighten stops and consider part profits."}
    return None


def breadth(key, crypto_doc, us_doc):
    if key == "crypto" and crypto_doc:
        alt = (crypto_doc.get("market") or {}).get("altseason")
        coins = crypto_doc.get("coins") or []
        a200 = [c.get("above200") for c in coins if c.get("above200") is not None]
        share = sum(a200) / len(a200) if a200 else None
        if alt is None and share is None:
            return None, []
        v = max(((alt or 0) - 50) / 40, ((share or 0) - 0.6) / 0.3)
        return max(0.0, min(1.0, v)), [f"{alt}% of top coins beat BTC over 90 days" if alt is not None else "",
                                       f"{round((share or 0) * 100)}% of top coins above their 200-day" if share is not None else ""]
    if key == "us_eq" and us_doc:
        b = (us_doc.get("breadth") or {}).get("above200")
        if b is None:
            return None, []
        return max(0.0, min(1.0, (b - 60) / 25)), [f"{b}% of S&P 500 + Nasdaq 100 stocks above their 200-day"]
    return None, []


def news_part(key, news_sent, days):
    tag = NEWS_TAG.get(key)
    now = (news_sent or {}).get(tag) or {}
    past = [d.get("news", {}).get(tag) for k, d in sorted(days.items())[-61:-1]]
    past = [p for p in past if p and p.get("n")]
    if not now.get("n") or len(past) < 20:
        return None, ["news check starts after 20 days of stored headlines"] if not past or len(past) < 20 else []
    pos_now = now.get("pos", 0) / max(1, now["n"])
    pos_past = np.array([p.get("pos", 0) / max(1, p["n"]) for p in past])
    n_past = np.array([p["n"] for p in past])
    z_pos = (pos_now - pos_past.mean()) / (pos_past.std() + 1e-6)
    z_n = (now["n"] - n_past.mean()) / (n_past.std() + 1e-6)
    v = max(0.0, min(1.0, (0.6 * z_pos + 0.4 * z_n) / 2.5))
    return v, [f"positive headlines {pos_now * 100:.0f}% (usual {pos_past.mean() * 100:.0f}%), {now['n']} headlines (usual {n_past.mean():.0f})"]
