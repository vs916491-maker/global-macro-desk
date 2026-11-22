"""Money Flow tab: where money is moving across asset classes, for an Indian investor (INR terms).

Asset score 0-100 = 55% momentum & flow (returns in rupees, trend, volume-based money flow)
                  + 45% macro fit (how today's macro backdrop usually treats that asset)."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import config as C
from . import ta


def _r(v, d=2):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), d)


def inr_series(px: pd.Series, usdinr: pd.Series | None, in_usd: bool) -> pd.Series:
    px = px.copy()
    px.index = px.index.normalize()
    px = px[~px.index.duplicated(keep="last")]
    if not in_usd or usdinr is None or usdinr.empty:
        return px
    fx = usdinr.copy()
    fx.index = fx.index.normalize()
    fx = fx[~fx.index.duplicated(keep="last")]
    fx = fx.reindex(px.index.union(fx.index)).ffill().reindex(px.index)
    return (px * fx).dropna()


def factors(macro: dict) -> dict:
    q, fr, d = macro.get("quotes", {}), macro.get("fred", {}), macro.get("derived", {})
    sent = macro.get("_news", {})
    f = {}
    if macro.get("global", {}).get("score") is not None:
        f["risk_g"] = macro["global"]["score"] / 100
    if macro.get("india", {}).get("score") is not None:
        f["risk_i"] = macro["india"]["score"] / 100
    if q.get("dxy", {}).get("m1") is not None:
        f["weak_dollar"] = ta.lin(-q["dxy"]["m1"], C.DXY_FULL_PCT)
    if fr.get("DGS10", {}).get("m1") is not None:
        f["falling_yields"] = ta.lin(-fr["DGS10"]["m1"] * 100, C.YIELD_FULL_BP)
    if fr.get("DFII10", {}).get("m1") is not None:
        f["falling_real"] = ta.lin(-fr["DFII10"]["m1"], 0.3)
    if d.get("walcl_3m_pct") is not None:
        f["liquidity"] = ta.lin(d["walcl_3m_pct"], 2.0)
    if q.get("brent", {}).get("m1") is not None:
        f["cheap_oil"] = ta.lin(-q["brent"]["m1"], C.CRUDE_FULL_PCT)
    if q.get("usdinr", {}).get("m1") is not None:
        f["strong_inr"] = ta.lin(-q["usdinr"]["m1"], C.INR_FULL_PCT)
    if d.get("cpi_yoy") is not None and d.get("cpi_yoy_3m_ago") is not None:
        f["inflation_up"] = ta.lin(d["cpi_yoy"] - d["cpi_yoy_3m_ago"], 0.6)
    if d.get("cu_au_m1") is not None:
        f["growth"] = ta.lin(d["cu_au_m1"], C.CU_AU_FULL_PCT)
    for k in ("us_eq", "in_eq", "gold", "silver", "crypto"):
        s = sent.get(k, {}).get("score")
        if s is not None:
            f[f"news_{k}"] = ta.clamp(s / 60)
    return f


# how each asset usually reacts (weight, factor, sign)
FIT = {
    "us_eq": [(0.35, "risk_g", 1), (0.2, "falling_yields", 1), (0.15, "liquidity", 1), (0.2, "news_us_eq", 1), (0.1, "strong_inr", -1)],
    "in_eq": [(0.4, "risk_i", 1), (0.15, "weak_dollar", 1), (0.15, "cheap_oil", 1), (0.15, "strong_inr", 1), (0.15, "news_in_eq", 1)],
    "us_bond": [(0.45, "falling_yields", 1), (0.25, "risk_g", -1), (0.15, "inflation_up", -1), (0.15, "strong_inr", -1)],
    "gold": [(0.3, "falling_real", 1), (0.25, "weak_dollar", 1), (0.15, "risk_g", -1), (0.15, "news_gold", 1), (0.15, "inflation_up", 1)],
    "silver": [(0.2, "falling_real", 1), (0.2, "weak_dollar", 1), (0.2, "growth", 1), (0.2, "news_silver", 1), (0.2, "risk_g", 1)],
    "crypto": [(0.3, "risk_g", 1), (0.2, "liquidity", 1), (0.2, "weak_dollar", 1), (0.1, "falling_yields", 1), (0.2, "news_crypto", 1)],
}
FACTOR_NAME = {"risk_g": "Global risk appetite", "risk_i": "India risk appetite", "weak_dollar": "Weaker dollar",
               "falling_yields": "Falling US yields", "falling_real": "Falling real yields", "liquidity": "Fed liquidity",
               "cheap_oil": "Cheaper crude", "strong_inr": "Stronger rupee", "inflation_up": "Rising inflation",
               "growth": "Growth (copper/gold)", "news_us_eq": "US equity news", "news_in_eq": "India news",
               "news_gold": "Gold news", "news_silver": "Silver news", "news_crypto": "Crypto news"}


def fit_score(key: str, f: dict) -> tuple[float, list[dict]]:
    num = den = 0.0
    parts = []
    for w, k, sg in FIT.get(key, []):
        v = f.get(k)
        if v is None:
            continue
        num += w * sg * v
        den += w
        parts.append({"factor": FACTOR_NAME.get(k, k), "effect": round(sg * v, 2), "weight": w,
                      "inverse": sg < 0})
    return (50 + 50 * num / den if den else 50.0), parts


def analyse(candles: dict[str, pd.DataFrame], macro: dict, hist: dict) -> dict:
    usdinr = candles.get("INR=X", pd.DataFrame()).get("Close")
    f = factors(macro)
    overall = macro.get("overall", {}).get("score") or 0
    assets = []
    for key, (label, sym, flow_sym, in_usd) in C.ASSETS.items():
        row = {"key": key, "label": label, "symbol": sym}
        if key == "fd":
            real = C.FD_RATE - C.INDIA_CPI
            mom = max(30, min(70, 50 + real * 5))
            fit = max(20, min(80, 50 - overall / 2.5))
            row.update({"mom": round(mom), "fit": round(fit), "r1m": round(C.FD_RATE / 12, 2), "r3m": round(C.FD_RATE / 4, 2),
                        "r6m": round(C.FD_RATE / 2, 2), "r1y": C.FD_RATE, "vol": 0, "trend": "flat", "flow": None,
                        "fit_parts": [{"factor": "Real FD rate (FD − India CPI)", "effect": round(real / 4, 2), "weight": 0.5, "inverse": False},
                                      {"factor": "Risk-off (safety demand)", "effect": round(-overall / 100, 2), "weight": 0.5, "inverse": True}],
                        "note": f"FD at {C.FD_RATE}% vs India CPI {C.INDIA_CPI}% (edit in gmd/config.py)"})
        else:
            df = candles.get(sym)
            if df is None or len(df) < 130:
                continue
            s = inr_series(df.Close, usdinr, in_usd)
            r1, r3, r6, r12 = ta.ret(s, 30), ta.ret(s, 91), ta.ret(s, 182), ta.ret(s, 365)
            dr = s.pct_change().dropna().tail(60)
            vol = float(dr.std() * math.sqrt(365 if key == "crypto" else 252) * 100) if len(dr) > 20 else 20
            raw = 0.3 * (r1 or 0) + 0.4 * (r3 or 0) + 0.3 * (r6 or 0)
            riskadj = raw / max(vol, 5) * 10
            e50, e200 = s.tail(50).mean(), s.tail(200).mean() if len(s) >= 200 else s.mean()
            last = s.iloc[-1]
            tr = 1 if last > e50 > e200 else -1 if last < e50 < e200 else 0
            fdf = candles.get(flow_sym)
            cm = ta.cmf(fdf, 20) if fdf is not None else None
            ob = ta.obv_slope(fdf, 20) if fdf is not None else None
            mom = 50 + 25 * math.tanh(riskadj / 6) + 15 * tr + (max(-10, min(10, cm * 60)) if cm is not None else 0)
            mom = max(0, min(100, mom))
            fit, parts = fit_score(key, f)
            row.update({"mom": round(mom), "fit": round(fit), "r1m": _r(r1), "r3m": _r(r3), "r6m": _r(r6), "r1y": _r(r12),
                        "vol": round(vol, 1), "trend": {1: "up", -1: "down", 0: "mixed"}[tr], "cmf": _r(cm, 3),
                        "obv": _r(ob, 2), "fit_parts": parts, "flow_symbol": flow_sym,
                        "flow": None if cm is None else "in" if cm > 0.08 else "out" if cm < -0.08 else "flat"})
        row["score"] = round(C.FLOW_MOM_W * row["mom"] + (1 - C.FLOW_MOM_W) * row["fit"])
        row["stance"] = "Overweight" if row["score"] >= 62 else "Underweight" if row["score"] < 45 else "Neutral"
        assets.append(row)

    # tilt vs the base mix
    raw = {a["key"]: C.BASE_MIX.get(a["key"], 0) * (1 + C.TILT_MAX * (a["score"] - 50) / 50) for a in assets}
    tot = sum(raw.values()) or 1
    days = sorted((hist or {}).get("days", {}))
    old = (hist or {}).get("days", {}).get(days[-7]) if len(days) >= 7 else None
    for a in assets:
        a["base"] = C.BASE_MIX.get(a["key"], 0)
        a["tilt"] = round(100 * raw[a["key"]] / tot, 1)
        prev = ((old or {}).get("assets") or {}).get(a["key"])
        a["chg7"] = None if prev is None else a["score"] - prev
    assets.sort(key=lambda a: a["score"], reverse=True)
    hist_rows = [{"date": k, **{kk: vv for kk, vv in ((hist["days"][k].get("assets") or {}).items())}}
                 for k in days[-370:]] if hist else []
    return {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "assets": assets, "factors": {FACTOR_NAME.get(k, k): round(v, 2) for k, v in f.items()},
            "regime": {k: macro.get(k, {}).get("regime") for k in ("global", "india", "overall")},
            "scores": {k: macro.get(k, {}).get("score") for k in ("global", "india", "overall")},
            "history": hist_rows, "fd_rate": C.FD_RATE, "india_cpi": C.INDIA_CPI}


__all__ = ["analyse", "np"]
