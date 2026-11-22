"""Price-action setups shared by the Crypto, Commodities and US Equity tabs.

Views
  swing       4-hour candles (crypto, commodities) or daily (US); higher timeframe = daily (US: weekly)
  positional  daily candles; higher timeframe = weekly
Setups (longs; shorts are the mirror where a tab allows them)
  BO  Base breakout: a sideways base (8-30 candles swing, 15-60 positional) no wider than 3x / 4.5x ATR,
      first-to-last close within half the range; a solid candle closes above the base by 0.1 ATR,
      above the 50 EMA, body >= half the candle, close in the upper half. Stop below the base
      (or the breakout candle if the base is too deep).
  PB  Trend pullback: uptrend (price, 20/50/200 EMA in order), price dips to the 20 EMA (swing) /
      50 EMA (positional) within 0.5 ATR in the last 5 candles, then a bullish candle closes above
      the previous high and the EMA. RSI 38-68. Stop below the pullback low.
  ML  Momentum leader (positional only, long only): within 5% of the 1-year high, closes at a new
      50-day high, uptrend above the 200 EMA, relative strength in the top 30% of its group.
Score 0-100: trend 25 + momentum 20 + setup quality 25 + volume 10 + macro fit 20.
Targets: swing 1:2, positional 1:3; time exit 14 / 90 days. All numbers in config.py."""

from __future__ import annotations

import math

import pandas as pd

from . import config as C
from . import ta

SETUP_NAME = {"BO": "Base breakout", "PB": "Trend pullback", "ML": "Momentum leader",
              "BD": "Base breakdown", "PS": "Rally into resistance (short)"}


def _f(v, d=4):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), d)


def base_breakout(d: pd.DataFrame, v: dict, side: str) -> dict | None:
    if len(d) < v["base_max"] + 5:
        return None
    c, p = d.iloc[-1], d.iloc[-2]
    a = float(d.atr.iloc[-2])
    if a <= 0:
        return None
    rng_c = c.High - c.Low
    if rng_c <= 0 or abs(c.Close - c.Open) < C.BO_BODY * rng_c:
        return None
    best = None
    for n in range(v["base_max"], v["base_min"] - 1, -1):
        base = d.iloc[-1 - n:-1]
        hi, lo = float(base.High.max()), float(base.Low.min())
        rng = hi - lo
        if rng <= 0 or rng > v["base_atr"] * a:
            continue
        if abs(base.Close.iloc[-1] - base.Close.iloc[0]) > C.BASE_DRIFT * rng:
            continue
        if side == "Long":
            ok = (c.Close > hi + C.BO_CLEAR_ATR * a and p.Close <= hi and c.Close > c.Open
                  and (c.Close - c.Low) >= 0.5 * rng_c and c.Close > d.e50.iloc[-1])
        else:
            ok = (c.Close < lo - C.BO_CLEAR_ATR * a and p.Close >= lo and c.Close < c.Open
                  and (c.High - c.Close) >= 0.5 * rng_c and c.Close < d.e50.iloc[-1])
        if ok:
            best = (n, hi, lo, rng)
            break
    if not best:
        return None
    n, hi, lo, rng = best
    entry = float(c.Close)
    if side == "Long":
        stop = lo - C.STOP_BUFFER_ATR * a
        if entry - stop > v["stop_max_atr"] * a:
            stop = float(c.Low) - C.STOP_BUFFER_ATR * a
    else:
        stop = hi + C.STOP_BUFFER_ATR * a
        if stop - entry > v["stop_max_atr"] * a:
            stop = float(c.High) + C.STOP_BUFFER_ATR * a
    if abs(entry - stop) > v["stop_max_atr"] * a:
        return None
    tight = 1 - rng / (v["base_atr"] * a)
    length = (n - v["base_min"]) / max(1, v["base_max"] - v["base_min"])
    body = abs(c.Close - c.Open) / rng_c
    quality = 0.4 * tight + 0.25 * length + 0.35 * body
    return {"setup": "BO" if side == "Long" else "BD", "entry": entry, "stop": stop, "quality": quality,
            "reasons": [f"{n}-candle base, range {rng / a:.1f}× ATR", f"breakout candle body {body * 100:.0f}% of its range",
                        f"closed {abs(entry - (hi if side == 'Long' else lo)) / a:.2f} ATR {'above' if side == 'Long' else 'below'} the base"],
            "level": hi if side == "Long" else lo}


def pullback(d: pd.DataFrame, v: dict, side: str, trend: dict) -> dict | None:
    if len(d) < 60 or trend["state"] != ("up" if side == "Long" else "down"):
        return None
    c, p = d.iloc[-1], d.iloc[-2]
    a = float(d.atr.iloc[-1])
    zone = C.PB_ZONE_ATR * a
    last5 = d.iloc[-5:]
    prior = d.iloc[-25:-5]
    if side == "Long":
        touched = (last5.Low <= last5.epb + zone).any()
        held = (prior.Close > prior.epb).mean() >= 0.7
        trigger = c.Close > c.Open and c.Close > p.High and c.Close > d.epb.iloc[-1] and (c.Close - c.Low) >= 0.5 * (c.High - c.Low)
        not_broken = last5.Close.min() > d.e50.iloc[-1] - a if v["pb_ema"] == 20 else last5.Close.min() > d.e200.iloc[-1]
        rsi_ok = C.PB_RSI[0] <= d.rsi.iloc[-1] <= C.PB_RSI[1]
    else:
        touched = (last5.High >= last5.epb - zone).any()
        held = (prior.Close < prior.epb).mean() >= 0.7
        trigger = c.Close < c.Open and c.Close < p.Low and c.Close < d.epb.iloc[-1] and (c.High - c.Close) >= 0.5 * (c.High - c.Low)
        not_broken = last5.Close.max() < d.e50.iloc[-1] + a if v["pb_ema"] == 20 else last5.Close.max() < d.e200.iloc[-1]
        rsi_ok = 100 - C.PB_RSI[1] <= d.rsi.iloc[-1] <= 100 - C.PB_RSI[0]
    if not (touched and held and trigger and not_broken and rsi_ok):
        return None
    entry = float(c.Close)
    stop = (float(last5.Low.min()) - C.STOP_BUFFER_ATR * a) if side == "Long" else (float(last5.High.max()) + C.STOP_BUFFER_ATR * a)
    risk = abs(entry - stop)
    if risk > v["stop_max_atr"] * a or risk < 0.3 * a:
        return None
    # rejection wick at the EMA touch
    tc = last5.loc[(last5.Low <= last5.epb + zone) if side == "Long" else (last5.High >= last5.epb - zone)].iloc[-1]
    tr_rng = max(tc.High - tc.Low, 1e-9)
    wick = (min(tc.Open, tc.Close) - tc.Low) / tr_rng if side == "Long" else (tc.High - max(tc.Open, tc.Close)) / tr_rng
    depth = abs(float(d.e20.iloc[-1] - d.e50.iloc[-1])) / a
    quality = 0.35 * min(1, wick / 0.6) + 0.35 * (1 - min(1, risk / (v["stop_max_atr"] * a))) + 0.3 * min(1, depth / 2)
    return {"setup": "PB" if side == "Long" else "PS", "entry": entry, "stop": stop, "quality": quality,
            "reasons": [f"pulled back to the {v['pb_ema']} EMA in an {'up' if side == 'Long' else 'down'}trend",
                        f"turn candle closed {'above the previous high' if side == 'Long' else 'below the previous low'}",
                        f"{'lower' if side == 'Long' else 'upper'} wick {wick * 100:.0f}% at the EMA touch"],
            "level": float(d.epb.iloc[-1])}


def leader(d: pd.DataFrame, v: dict, trend: dict, rs: float | None) -> dict | None:
    if len(d) < 220 or trend["state"] != "up" or not trend.get("above200") or (rs is not None and rs < 0.7):
        return None
    c, p = d.iloc[-1], d.iloc[-2]
    hi_y = float(d.High.iloc[-252:].max())
    n = v["lookback_hi"]
    prev_hi = float(d.High.iloc[-1 - n:-1].max())
    if not (c.Close >= (1 - C.ML_NEAR_HIGH) * hi_y and c.Close > prev_hi and p.Close <= prev_hi):
        return None
    a = float(d.atr.iloc[-1])
    entry = float(c.Close)
    stop = max(float(d.e50.iloc[-1]) - 0.5 * a, entry - v["stop_max_atr"] * a)
    if entry - stop < 0.5 * a:
        stop = entry - 1.5 * a
    quality = 0.5 * min(1, (rs or 0.7)) + 0.5 * (1 - (hi_y - entry) / (C.ML_NEAR_HIGH * hi_y) if entry < hi_y else 1)
    return {"setup": "ML", "entry": entry, "stop": stop, "quality": max(0, min(1, quality)),
            "reasons": [f"new {n}-day closing high, {(hi_y - entry) / hi_y * 100:.1f}% from the 1-year high",
                        f"relative strength top {100 - (rs or 0.7) * 100:.0f}% of its group" if rs is not None else "relative strength n/a"],
            "level": prev_hi}


def score(d: pd.DataFrame, side: str, trend: dict, hit: dict, ctx: dict) -> tuple[int, dict]:
    W = C.SCORE_W
    pts = trend.get("up" if side == "Long" else "down", 0) / 5
    tr = W["trend"] * (0.7 * pts + 0.3 * min(trend.get("adx", 0), 40) / 40)
    rs = ctx.get("rs")
    rsv = (rs if side == "Long" else 1 - rs) if rs is not None else 0.5
    r = float(d.rsi.iloc[-1])
    r = r if side == "Long" else 100 - r
    rsi_q = 1 if 50 <= r <= 70 else 0.5 if 40 <= r < 50 or 70 < r <= 78 else 0.2
    mo = W["momentum"] * (0.6 * rsv + 0.4 * rsi_q)
    se = W["setup"] * max(0, min(1, hit["quality"]))
    vr = None
    if d.v20.iloc[-1] and d.v20.iloc[-1] > 0 and d.Volume.iloc[-1] > 0:
        vr = float(d.Volume.iloc[-1] / d.v20.iloc[-1])
    vq = 0.5 if vr is None else 1 if vr >= 2 else 0.6 if vr >= C.BO_VOL else 0.3 if vr >= 1 else 0
    vo = W["volume"] * vq
    fit = ctx.get("fit", 50) / 100
    ma = W["macro"] * (fit if side == "Long" else 1 - fit)
    total = tr + mo + se + vo + ma
    htf = ctx.get("htf")
    if htf and htf.get("state") == ("down" if side == "Long" else "up"):
        total -= 5
    parts = {"trend": round(tr, 1), "momentum": round(mo, 1), "setup": round(se, 1), "volume": round(vo, 1),
             "macro": round(ma, 1)}
    return max(0, min(100, round(total))), {**parts, "vol_ratio": _f(vr, 2)}


def warnings(d: pd.DataFrame, side: str, entry: float, stop: float, ctx: dict) -> list[str]:
    w = []
    a = float(d.atr.iloc[-1])
    r = float(d.rsi.iloc[-1])
    if side == "Long" and r > 75 or side == "Short" and r < 25:
        w.append(f"RSI {r:.0f}: stretched")
    if abs(entry - float(d.e20.iloc[-1])) > 3 * a:
        w.append("far from the 20 EMA (extended)")
    risk_pct = abs(entry - stop) / entry * 100
    if risk_pct > ctx.get("max_risk_pct", 10):
        w.append(f"wide stop ({risk_pct:.1f}%)")
    htf = ctx.get("htf")
    if htf and htf.get("state") == ("down" if side == "Long" else "up"):
        w.append(f"against the {ctx.get('htf_name', 'higher timeframe')} trend")
    if d.v20.iloc[-1] and d.Volume.iloc[-1] and d.Volume.iloc[-1] < 0.8 * d.v20.iloc[-1]:
        w.append("volume below average")
    for x in ctx.get("extra_warns", []):
        w.append(x)
    return w


def find(d: pd.DataFrame, view: str, ctx: dict, allow_short: bool = False, leaders: bool = True) -> list[dict]:
    """All setups on the last (completed) candle of d (indicators already added)."""
    v = C.VIEWS[view]
    if len(d) < 60:
        return []
    trend = ta.trend_state(d)
    hits = []
    for side in (["Long", "Short"] if allow_short else ["Long"]):
        for fn in (lambda: base_breakout(d, v, side), lambda: pullback(d, v, side, trend)):
            h = fn()
            if h:
                hits.append((side, h))
    if view == "positional" and leaders:
        h = leader(d, v, trend, ctx.get("rs"))
        if h and not any(x[1]["setup"] == "BO" for x in hits):
            hits.append(("Long", h))
    out = []
    t_end = d.index[-1]
    for side, h in hits:
        entry, stop = h["entry"], h["stop"]
        risk = abs(entry - stop)
        tgt = entry + v["target_r"] * risk if side == "Long" else entry - v["target_r"] * risk
        sc, parts = score(d, side, trend, h, ctx)
        out.append({
            "symbol": ctx.get("symbol"), "name": ctx.get("name"), "side": side, "setup": h["setup"],
            "setup_name": SETUP_NAME[h["setup"]], "view": view, "tf": ctx.get("tf"),
            "candle": t_end.isoformat(), "entry": _f(entry, 6), "stop": _f(stop, 6), "target": _f(tgt, 6),
            "risk_pct": round(risk / entry * 100, 2), "rr": v["target_r"], "max_days": v["max_days"],
            "score": sc, "parts": parts, "reasons": h["reasons"], "warns": warnings(d, side, entry, stop, ctx),
            "trend": trend["state"], "rsi": round(float(d.rsi.iloc[-1]), 1), "tv": ctx.get("tv"),
            "level": _f(h.get("level"), 6), "logged": sc >= C.MIN_SCORE, "yahoo": ctx.get("yahoo"),
        })
    return out


def summary_row(d: pd.DataFrame) -> dict:
    """Trend snapshot of one instrument for the tables."""
    t = ta.trend_state(d)
    c = d.Close
    hi = float(d.High.iloc[-252:].max()) if len(d) else None
    return {"trend": t["state"], "trend_pts": t.get("up", 0) - t.get("down", 0), "adx": t.get("adx"),
            "rsi": round(float(d.rsi.iloc[-1]), 1), "from_high": round((float(c.iloc[-1]) / hi - 1) * 100, 1) if hi else None,
            "above200": t.get("above200")}
