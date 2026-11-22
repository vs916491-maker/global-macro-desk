"""US Equity tab: trend and sentiment scores, breadth, sector / style money flow, and the
Top 10 ideas (Swing and Positional, long only) from the S&P 500 + Nasdaq 100, daily candles."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from . import config as C
from . import macro as M
from . import setups, sources, ta


def analyse(macro: dict, us_fit: float, cached_universe: list[dict] | None) -> tuple[dict, dict, list[dict]]:
    uni = sources.us_universe()
    if len(uni) < 300:
        uni = cached_universe if cached_universe and len(cached_universe) >= 300 else \
            uni or [{"symbol": s, "name": s, "sector": "", "index": "fallback"} for s in C.US_FALLBACK]
    meta = {u["symbol"]: u for u in uni}
    etfs = ["SPY", *C.US_SECTORS, *C.US_STYLE]
    data = sources.yahoo_many(list(meta) + etfs, "1d", "2y", workers=10)
    data = {k: ta.complete_daily(v, "us") for k, v in data.items()}
    spy = data.get("SPY")
    if spy is None or len(spy) < 200:
        raise RuntimeError("no SPY candles from Yahoo")
    spy_c = spy.Close

    # ---------------- per stock
    rs_raw, prep = {}, {}
    nh = nl = adv = dec = a50 = a200 = n = 0
    sec_b = {}
    for sym, df in data.items():
        if sym not in meta or len(df) < 220:
            continue
        c = df.Close
        n += 1
        last = float(c.iloc[-1])
        above50 = last > c.tail(50).mean()
        above200 = last > c.tail(200).mean()
        a50 += above50
        a200 += above200
        adv += last > c.iloc[-2]
        dec += last < c.iloc[-2]
        nh += float(df.High.iloc[-1]) >= float(df.High.tail(252).max())
        nl += float(df.Low.iloc[-1]) <= float(df.Low.tail(252).min())
        sec = _etf_name(meta[sym].get("sector") or "")
        b = sec_b.setdefault(sec, [0, 0])
        b[0] += above50
        b[1] += 1
        dv = float((df.Close * df.Volume).tail(20).mean())
        if last < C.US_MIN_PRICE or dv < C.US_MIN_DOLLAR_VOL:
            continue
        r3, r6, r1 = ta.ret(c, 91), ta.ret(c, 182), ta.ret(c, 30)
        rs_raw[sym] = {"pos": 0.4 * (r3 or 0) + 0.6 * (r6 or 0), "swing": 0.5 * (r1 or 0) + 0.5 * (r3 or 0)}
        prep[sym] = (df, dv, r1, r3, r6)
    rs_pos = pd.Series({k: v["pos"] for k, v in rs_raw.items()}).rank(pct=True).to_dict()
    rs_sw = pd.Series({k: v["swing"] for k, v in rs_raw.items()}).rank(pct=True).to_dict()
    breadth = {"n": n, "above50": round(100 * a50 / n, 1) if n else None, "above200": round(100 * a200 / n, 1) if n else None,
               "new_highs": int(nh), "new_lows": int(nl), "adv": int(adv), "dec": int(dec),
               "sectors": {k: round(100 * v[0] / v[1]) for k, v in sec_b.items() if v[1] >= 5 and k}}

    # ---------------- sector & style money flow
    spy_r = {d: ta.ret(spy_c, d) for d in (7, 30, 91)}
    sectors = []
    for etf, name in {**C.US_SECTORS, **C.US_STYLE}.items():
        df = data.get(etf)
        if df is None or len(df) < 80:
            continue
        r = {d: ta.ret(df.Close, d) for d in (7, 30, 91)}
        rr = ta.rrg(df.Close, spy_c)
        cm = ta.cmf(df, 20)
        sectors.append({"etf": etf, "name": name, "style": etf in C.US_STYLE, "w1": r[7], "m1": r[30], "m3": r[91],
                        "rs1m": None if r[30] is None else round(r[30] - (spy_r[30] or 0), 2),
                        "rs3m": None if r[91] is None else round(r[91] - (spy_r[91] or 0), 2),
                        "cmf": None if cm is None else round(cm, 3), "obv": ta.obv_slope(df, 20),
                        "rrg": rr, "breadth50": breadth["sectors"].get(name)})
    sec_only = [s for s in sectors if not s["style"]]
    rk = pd.Series({s["etf"]: (s["rs1m"] or 0) + 0.5 * (s["rs3m"] or 0) for s in sec_only}).rank(pct=True).to_dict() if sec_only else {}
    QV = {"Leading": 1, "Improving": 0.65, "Weakening": 0.35, "Lagging": 0}
    for s in sectors:
        q = QV.get((s["rrg"] or {}).get("quadrant"), 0.5)
        cmq = 0.5 if s["cmf"] is None else max(0, min(1, 0.5 + s["cmf"] * 3))
        s["flow_score"] = round(100 * (0.4 * rk.get(s["etf"], 0.5) + 0.3 * cmq + 0.3 * q))
        s["flow"] = "Inflow" if s["flow_score"] >= 60 else "Outflow" if s["flow_score"] < 40 else "Neutral"
        for k in ("w1", "m1", "m3", "obv"):
            s[k] = None if s[k] is None else round(s[k], 2)
    sectors.sort(key=lambda s: (s["style"], -s["flow_score"]))
    sec_score = {s["name"]: s["flow_score"] for s in sec_only}

    # ---------------- index trend + sentiment
    def idx_trend(df):
        d = ta.add(df, 20)
        t = ta.trend_state(d)
        m3 = ta.ret(df.Close, 91) or 0
        hi = float(df.High.tail(252).max())
        dd = (float(df.Close.iloc[-1]) / hi - 1) * 100
        sc = 50 + 30 * (t.get("up", 0) - t.get("down", 0)) / 5 + 10 * ta.clamp(m3 / 8) + 10 * ta.clamp((dd + 5) / 5)
        return {"score": round(max(0, min(100, sc))), "state": t["state"], "m3": round(m3, 2), "from_high": round(dd, 2),
                "rsi": round(float(d.rsi.iloc[-1]), 1), "adx": t.get("adx")}
    trend = {"spx": idx_trend(spy)}
    if "QQQ" in data:
        trend["ndx"] = idx_trend(data["QQQ"])
    if "IWM" in data:
        trend["rut"] = idx_trend(data["IWM"])
    vix = macro.get("quotes", {}).get("vix", {}).get("last")
    credit = next((p["score"] for p in macro.get("global", {}).get("parts", []) if p["key"] == "credit"), None)
    news = (macro.get("_news") or {}).get("us_eq", {}).get("score")
    sp = {
        "spx": ("S&P 500 trend", trend["spx"]["score"] / 100, f"{trend['spx']['score']}/100 ({trend['spx']['state']})"),
        "ndx": ("Nasdaq 100 trend", trend.get("ndx", {}).get("score", 50) / 100, f"{trend.get('ndx', {}).get('score', '–')}/100"),
        "b50": ("Stocks above 50-day avg", (breadth["above50"] or 50) / 100, f"{breadth['above50']}%"),
        "b200": ("Stocks above 200-day avg", (breadth["above200"] or 50) / 100, f"{breadth['above200']}%"),
        "nhnl": ("New highs vs new lows", (nh - nl) / (nh + nl + 5) / 2 + 0.5, f"{nh} highs / {nl} lows"),
        "vix": ("US VIX", None if vix is None else (M.zone(vix, C.VIX_ZONES) + 1) / 2, f"{vix:.1f}" if vix else "–"),
        "credit": ("Credit spreads", None if credit is None else (credit + 1) / 2, "from the Macro tab"),
        "news": ("US equity news tone", None if news is None else (ta.clamp(news / 60) + 1) / 2, f"{news}" if news is not None else "–"),
    }
    parts, num, den = [], 0.0, 0.0
    for k, (lbl, v, txt) in sp.items():
        parts.append({"key": k, "label": lbl, "value": txt, "score": None if v is None else round(v * 100), "weight": C.US_W[k]})
        if v is not None:
            num += C.US_W[k] * v
            den += C.US_W[k]
    senti = round(100 * num / den) if den else None
    label = None if senti is None else ("Extreme fear" if senti < 20 else "Fear" if senti < 40 else "Neutral" if senti < 60
                                        else "Greed" if senti < 80 else "Extreme greed")

    # ---------------- ideas
    spy_w = ta.trend_state(ta.add(ta.weekly(spy), 20))
    views, frames, leaders = {"swing": [], "positional": []}, {}, []
    for sym, (df, dv, r1, r3, r6) in prep.items():
        m = meta[sym]
        sec = m.get("sector") or ""
        fit = 0.5 * us_fit + 0.5 * sec_score.get(_etf_name(sec), 50)
        wk = ta.weekly(df)
        wt = ta.trend_state(ta.add(wk, 20)) if len(wk) >= 60 else {"state": "unknown"}
        base = {"symbol": sym, "name": m.get("name", sym), "fit": fit, "tv": sym, "yahoo": sym, "max_risk_pct": 10, "htf": wt, "htf_name": "weekly",
                "tf": "1d", "extra_warns": [] if spy_w["state"] != "down" else ["S&P 500 weekly trend is down"]}
        d20 = ta.add(df, 20)
        d50 = ta.add(df, 50)
        frames[("swing", sym)] = df
        frames[("positional", sym)] = df
        for idea in setups.find(d20, "swing", {**base, "rs": rs_sw.get(sym)}):
            idea.update({"sector": sec, "dollar_vol": round(dv / 1e6)})
            views["swing"].append(idea)
        for idea in setups.find(d50, "positional", {**base, "rs": rs_pos.get(sym)}):
            idea.update({"sector": sec, "dollar_vol": round(dv / 1e6)})
            views["positional"].append(idea)
        if rs_pos.get(sym, 0) >= 0.9:
            t = ta.trend_state(d50)
            if t["state"] == "up":
                leaders.append({"symbol": sym, "name": m.get("name", sym), "sector": sec, "rs": round(rs_pos[sym], 2),
                                "m1": round(r1 or 0, 1), "m3": round(r3 or 0, 1), "m6": round(r6 or 0, 1),
                                "from_high": round((float(df.Close.iloc[-1]) / float(df.High.tail(252).max()) - 1) * 100, 1),
                                "price": round(float(df.Close.iloc[-1]), 2)})
    for v in views:
        views[v].sort(key=lambda x: x["score"], reverse=True)
    leaders.sort(key=lambda x: x["rs"], reverse=True)
    doc = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "asof": spy.index[-1].strftime("%Y-%m-%d"),
           "trend": trend, "sentiment": {"score": senti, "label": label, "parts": parts}, "breadth": breadth,
           "sectors": sectors, "fit": round(us_fit), "universe": len(meta), "scanned": len(prep),
           "views": {k: {"ideas": v[:C.US_TOP_N], "more": v[C.US_TOP_N:C.US_TOP_N + 15], "count": len(v)} for k, v in views.items()},
           "leaders": leaders[:25]}
    return doc, frames, uni


_SECTOR_ETF_NAME = {v: v for v in C.US_SECTORS.values()}
_ALIASES = {"Information Technology": "Technology", "Health care": "Health Care", "Consumer discretionary": "Consumer Discretionary",
            "Consumer staples": "Consumer Staples", "Communication services": "Communication Services", "Real estate": "Real Estate"}


def _etf_name(gics: str) -> str:
    return _ALIASES.get(gics, gics)
