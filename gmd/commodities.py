"""Commodities tab: Gold, Silver, Copper, Aluminium (COMEX futures) and Brent crude, USD. Direction score per metal from
price trend + macro drivers, ratios, and Swing (4-hour) / Positional (daily) ideas, long and short."""

from __future__ import annotations

from datetime import datetime, timezone

from . import config as C
from . import flows, setups, sources, ta

DRIVERS = {
    "gold": [(0.3, "falling_real", 1, "Falling real yields"), (0.3, "weak_dollar", 1, "Weaker dollar"),
             (0.2, "risk_g", -1, "Risk-off demand (safe haven)"), (0.2, "news_gold", 1, "Gold headlines")],
    "silver": [(0.25, "falling_real", 1, "Falling real yields"), (0.25, "weak_dollar", 1, "Weaker dollar"),
               (0.25, "growth", 1, "Industrial demand (copper/gold)"), (0.25, "news_silver", 1, "Silver headlines")],
    "copper": [(0.35, "growth", 1, "Growth (copper/gold ratio)"), (0.25, "risk_g", 1, "Global risk appetite"),
               (0.2, "weak_dollar", 1, "Weaker dollar"), (0.2, "news_copper", 1, "Copper headlines")],
    # added 26 Nov 2026: untested starting weights, judge them in the Track record
    "brent": [(0.3, "growth", 1, "Global growth (copper/gold ratio)"), (0.2, "risk_g", 1, "Global risk appetite"),
              (0.15, "weak_dollar", 1, "Weaker dollar"), (0.35, "news_oil_px", 1, "Oil headlines (supply, OPEC, war)")],
    "aluminium": [(0.35, "growth", 1, "Growth (copper/gold ratio)"), (0.25, "risk_g", 1, "Global risk appetite"),
                  (0.2, "weak_dollar", 1, "Weaker dollar"), (0.2, "news_aluminium", 1, "Aluminium headlines")],
}


def analyse(macro: dict, daily_cache: dict) -> tuple[dict, dict]:
    f = flows.factors(macro)
    for k in ("copper", "aluminium", "oil_px"):
        s = (macro.get("_news") or {}).get(k, {}).get("score")
        if s is not None:
            f[f"news_{k}"] = ta.clamp(s / 60)
    syms = [v[0] for v in C.COMMODS.values()]
    daily = {k: daily_cache[k] for k in syms if k in daily_cache}
    need = [k for k in syms if k not in daily]
    if need:
        daily.update(sources.yahoo_many(need, "1d", "2y"))
    hourly = sources.yahoo_many(syms, "1h", "180d")
    out, frames, views = {}, {}, {"swing": [], "positional": []}
    for key, (sym, label, tv) in C.COMMODS.items():
        dd = daily.get(sym)
        if dd is None or len(dd) < 60:
            continue
        raw = dd
        dd = ta.complete_daily(dd, "futures")
        dI = ta.add(dd, 50)
        h4 = ta.resample(hourly[sym], "4h") if sym in hourly else None
        h4I = ta.add(h4, 20) if h4 is not None and len(h4) >= 80 else None
        wk = ta.weekly(dd)
        t_w = ta.trend_state(ta.add(wk, 20)) if len(wk) >= 60 else {"state": "unknown"}
        t_d = ta.trend_state(ta.add(dd, 20))
        t_4 = ta.trend_state(h4I) if h4I is not None else {"state": "unknown"}
        # direction score -100..+100
        tr = lambda t: (t.get("up", 0) - t.get("down", 0)) / 5  # noqa: E731
        num = den = 0.0
        parts = []
        for w, k, sg, nm in DRIVERS[key]:
            v = f.get(k)
            if v is None:
                continue
            num += w * sg * v
            den += w
            parts.append({"driver": nm, "effect": round(sg * v, 2)})
        drv = num / den if den else 0
        direction = round(100 * (0.4 * tr(t_d) + 0.15 * tr(t_4) + 0.45 * drv))
        price = float(dd.attrs.get("price") or dd.Close.iloc[-1])
        c = dd.Close
        exch, unit = C.COMMOD_INFO.get(key, ("COMEX", "$"))
        out[key] = {"label": label, "symbol": sym, "tv": tv, "exchange": exch, "unit": unit, "price": round(price, 4),
                    "d1": round((float(raw.Close.iloc[-1]) / float(raw.Close.iloc[-2]) - 1) * 100, 2),
                    "w1": round(ta.ret(c, 7) or 0, 2), "m1": round(ta.ret(c, 30) or 0, 2), "m3": round(ta.ret(c, 91) or 0, 2),
                    "y1": round(ta.ret(c, 365) or 0, 2), "trend_w": t_w["state"], "trend_d": t_d["state"],
                    "trend_4h": t_4["state"], "rsi_d": round(float(dI.rsi.iloc[-1]), 1),
                    "atr_pct": round(float(dI.atr.iloc[-1]) / price * 100, 2),
                    "hi52": round(float(dd.High.tail(252).max()), 4), "lo52": round(float(dd.Low.tail(252).min()), 4),
                    "e50": round(float(dI.e50.iloc[-1]), 4), "e200": round(float(dI.e200.iloc[-1]), 4),
                    "direction": direction, "drivers": parts, "drivers_score": round(100 * drv),
                    "spark": [round(float(x), 4) for x in c.tail(120)]}
        out[key]["bias"] = "Bullish" if direction >= 25 else "Bearish" if direction <= -25 else "Neutral"
        fit = 50 + 50 * drv
        ctx = {"symbol": key.upper(), "name": label, "fit": fit, "tv": tv, "rs": 0.5 + tr(t_d) / 2 * 0.8, "max_risk_pct": 6, "yahoo": sym}
        frames[("positional", key.upper())] = dd
        views["positional"] += setups.find(dI, "positional", {**ctx, "tf": "1d", "htf": t_w, "htf_name": "weekly"},
                                           allow_short=True, leaders=False)
        if h4I is not None:
            frames[("swing", key.upper())] = h4
            views["swing"] += setups.find(h4I, "swing", {**ctx, "tf": "4h", "htf": t_d, "htf_name": "daily"}, allow_short=True)
    ratios = {}
    if "gold" in out and "silver" in out:
        g, sv = daily[C.COMMODS["gold"][0]].Close, daily[C.COMMODS["silver"][0]].Close
        r = (g / sv).dropna().tail(252)
        ratios["gold_silver"] = {"now": round(float(r.iloc[-1]), 1), "lo": round(float(r.min()), 1), "hi": round(float(r.max()), 1),
                                 "pctile": round(float((r < r.iloc[-1]).mean() * 100))}
    if "gold" in out and "copper" in out:
        cu = daily[C.COMMODS["copper"][0]].Close
        g = daily[C.COMMODS["gold"][0]].Close
        r = (cu / g).dropna()
        ratios["copper_gold"] = {"m1": round(ta.ret(r, 30) or 0, 2), "m3": round(ta.ret(r, 91) or 0, 2)}
    for v in views:
        views[v].sort(key=lambda x: x["score"], reverse=True)
    q, fr = macro.get("quotes", {}), macro.get("fred", {})
    context = {"dxy": q.get("dxy", {}).get("last"), "dxy_m1": q.get("dxy", {}).get("m1"),
               "real10": fr.get("DFII10", {}).get("last"), "real10_m1": fr.get("DFII10", {}).get("m1"),
               "vix": q.get("vix", {}).get("last"), "regime": macro.get("global", {}).get("regime")}
    doc = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "metals": out, "ratios": ratios,
           "context": context, "views": {k: {"ideas": v, "count": len(v)} for k, v in views.items()}}
    return doc, frames
