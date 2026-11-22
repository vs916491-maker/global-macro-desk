"""Indicators on OHLCV frames (columns Open High Low Close Volume, time index)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def now_utc() -> pd.Timestamp:
    return pd.Timestamp.now("UTC").tz_localize(None)


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=max(2, n // 2)).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df.Close.shift()
    tr = pd.concat([df.High - df.Low, (df.High - pc).abs(), (df.Low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    up, dn = df.High.diff(), -df.Low.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = atr(df, n)
    pdi = 100 * pd.Series(pdm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / a
    ndi = 100 * pd.Series(ndm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / a
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean().fillna(0)


def cmf(df: pd.DataFrame, n: int = 20) -> float | None:
    """Chaikin money flow over the last n candles (-1..+1): buying vs selling pressure."""
    if len(df) < n or df.Volume.tail(n).sum() <= 0:
        return None
    t = df.tail(n)
    rng = (t.High - t.Low).replace(0, np.nan)
    mfm = (((t.Close - t.Low) - (t.High - t.Close)) / rng).fillna(0)
    return float((mfm * t.Volume).sum() / t.Volume.sum())


def obv_slope(df: pd.DataFrame, n: int = 20) -> float | None:
    """On-balance volume change over n candles as a share of average volume (+ = accumulation)."""
    if len(df) < n + 1 or df.Volume.tail(n).mean() <= 0:
        return None
    obv = (np.sign(df.Close.diff()).fillna(0) * df.Volume).cumsum()
    return float((obv.iloc[-1] - obv.iloc[-n - 1]) / (df.Volume.tail(n).mean() * n))


def ret(s: pd.Series, days: int) -> float | None:
    """% change over `days` calendar days (by date), using the last value on or before."""
    s = s.dropna()
    if s.empty:
        return None
    t0 = s.index[-1] - pd.Timedelta(days=days)
    past = s[s.index <= t0]
    if past.empty or past.iloc[-1] == 0:
        return None
    return float((s.iloc[-1] / past.iloc[-1] - 1) * 100)


def chg(s: pd.Series, days: int) -> float | None:
    """Absolute change over `days` calendar days (for yields and spreads)."""
    s = s.dropna()
    if s.empty:
        return None
    past = s[s.index <= s.index[-1] - pd.Timedelta(days=days)]
    return None if past.empty else float(s.iloc[-1] - past.iloc[-1])


def resample(df: pd.DataFrame, rule: str = "4h") -> pd.DataFrame:
    """Hourly -> 4-hour candles aligned to 00:00 UTC; drops a last candle that is not complete."""
    if df.empty:
        return df
    g = df.resample(rule, origin="start_day", label="left", closed="left")
    out = pd.DataFrame({"Open": g.Open.first(), "High": g.High.max(), "Low": g.Low.min(),
                        "Close": g.Close.last(), "Volume": g.Volume.sum(), "n": g.Close.count()}).dropna(subset=["Close"])
    # incomplete last candle: the period has not ended yet
    end = out.index[-1] + pd.Timedelta(rule)
    if end > now_utc() + pd.Timedelta(minutes=1):
        out = out.iloc[:-1]
    out.attrs.update(df.attrs)
    return out.drop(columns="n")


SESSION_H = {"us": 6.75, "crypto": 24.0, "futures": 17.5}


def complete_daily(df: pd.DataFrame, kind: str = "crypto") -> pd.DataFrame:
    """Drop today's still-forming daily candle. Yahoo stamps daily candles at the session start:
    US stocks at the 9:30 ET open (session 6.5 h), crypto at 00:00 UTC (24 h), COMEX futures at
    midnight ET (closes 17:00 ET, ~17 h later)."""
    if df.empty:
        return df
    now = now_utc()
    last = df.index[-1]
    if now - last < pd.Timedelta(hours=SESSION_H[kind]):
        out = df.iloc[:-1].copy()
        out.attrs.update(df.attrs)
        return out
    return df


def weekly(df: pd.DataFrame) -> pd.DataFrame:
    g = df.resample("W-FRI")
    return pd.DataFrame({"Open": g.Open.first(), "High": g.High.max(), "Low": g.Low.min(),
                         "Close": g.Close.last(), "Volume": g.Volume.sum()}).dropna(subset=["Close"])


def add(df: pd.DataFrame, pb_ema: int = 20) -> pd.DataFrame:
    d = df.copy()
    d["e20"], d["e50"], d["e200"] = ema(d.Close, 20), ema(d.Close, 50), ema(d.Close, 200)
    d["epb"] = d["e20"] if pb_ema == 20 else d["e50"]
    d["atr"] = atr(d)
    d["rsi"] = rsi(d.Close)
    d["adx"] = adx(d)
    d["v20"] = d.Volume.rolling(20).mean()
    d.attrs.update(df.attrs)
    return d


def clamp(x, lo=-1.0, hi=1.0):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return max(lo, min(hi, x))


def lin(x, full):
    """x scaled to -1..+1 where |x| == full scores the full point."""
    return None if x is None else clamp(x / full)


def trend_state(d: pd.DataFrame) -> dict:
    """Trend of the last candle: up / down / sideways with a 0-1 strength."""
    if len(d) < 60:
        return {"state": "unknown", "strength": 0}
    c, e20, e50, e200 = d.Close.iloc[-1], d.e20.iloc[-1], d.e50.iloc[-1], d.e200.iloc[-1]
    slope = (d.e50.iloc[-1] / d.e50.iloc[-11] - 1) * 100 if len(d) > 11 else 0
    long_ok = len(d) >= 200
    up_pts = sum([c > e20, c > e50, e20 > e50, (e50 > e200) if long_ok else c > e50, slope > 0.3])
    dn_pts = sum([c < e20, c < e50, e20 < e50, (e50 < e200) if long_ok else c < e50, slope < -0.3])
    if up_pts >= 4:
        state = "up"
    elif dn_pts >= 4:
        state = "down"
    else:
        state = "sideways"
    return {"state": state, "up": up_pts, "down": dn_pts, "slope": round(slope, 2),
            "adx": round(float(d.adx.iloc[-1]), 1), "above200": bool(c > e200) if long_ok else None,
            "strength": round(max(up_pts, dn_pts) / 5, 2)}


def rrg(px: pd.Series, bench: pd.Series, n: int = 50, m: int = 10) -> dict | None:
    """Relative rotation (JdK-style approximation) of daily closes vs a benchmark."""
    j = pd.concat([px, bench], axis=1, join="inner").dropna()
    if len(j) < n + m + 5:
        return None
    rs = 100 * j.iloc[:, 0] / j.iloc[:, 1]
    ratio = 100 + (rs / rs.rolling(n).mean() - 1) * 100
    mom = 100 + (ratio / ratio.shift(m) - 1) * 100
    r, mo = float(ratio.iloc[-1]), float(mom.iloc[-1])
    q = "Leading" if r >= 100 and mo >= 100 else "Weakening" if r >= 100 else "Lagging" if mo < 100 else "Improving"
    return {"ratio": round(r, 2), "mom": round(mo, 2), "quadrant": q}
