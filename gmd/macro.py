"""Global Macro tab: market data, Fed data, risk-appetite scores (global and India),
central-bank calendar and plain-words interpretation of what moved."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd

from . import config as C
from . import sources, ta


def _num(v, d=2):
    return None if v is None or pd.isna(v) else round(float(v), d)


def zone(v, zones):
    for hi, sc in zones:
        if v < hi:
            return sc
    return zones[-1][1]


def quote_row(df: pd.DataFrame, label: str, unit: str, scale_yield=False) -> dict:
    c = df.Close.copy()
    if scale_yield and c.iloc[-1] > 20:
        c = c / 10
    last = float(df.attrs.get("price") or c.iloc[-1])
    if scale_yield and last > 20:
        last /= 10
    prev = float(c.iloc[-2]) if len(c) > 1 else None
    is_y = unit == "%"
    f = ta.chg if is_y else ta.ret
    row = {"label": label, "unit": unit, "last": round(last, 4),
           "d1": (round(last - prev, 3) if is_y else round((last / prev - 1) * 100, 2)) if prev else None,
           "w1": _num(f(c, 7), 3), "m1": _num(f(c, 30), 3), "m3": _num(f(c, 91), 3), "y1": _num(f(c, 365), 3),
           "spark": [round(float(x), 4) for x in c.tail(90)], "is_yield": is_y,
           "asof": df.index[-1].strftime("%Y-%m-%d")}
    if len(c) >= 200:
        row["above200"] = bool(last > c.tail(200).mean())
        row["above50"] = bool(last > c.tail(50).mean())
    return row


def fred_row(s: pd.Series, label: str) -> dict | None:
    if s.empty:
        return None
    return {"label": label, "last": _num(s.iloc[-1], 3), "date": s.index[-1].strftime("%Y-%m-%d"),
            "m1": _num(ta.chg(s, 31), 3), "m3": _num(ta.chg(s, 92), 3), "y1": _num(ta.chg(s, 365), 3),
            "spark": [round(float(x), 3) for x in s.tail(120)]}


def yoy(s: pd.Series) -> tuple[float | None, float | None]:
    """year-on-year % now and 3 releases ago (monthly series)."""
    if len(s) < 16:
        return None, None
    now = (s.iloc[-1] / s.iloc[-13] - 1) * 100
    before = (s.iloc[-4] / s.iloc[-16] - 1) * 100
    return round(now, 2), round(before, 2)


def regime(score):
    if score is None:
        return "No data"
    for hi, name in C.REGIME_ZONES:
        if score < hi:
            return name
    return C.REGIME_ZONES[-1][1]


def combine(parts: list[dict], weights: dict) -> int | None:
    num = den = 0.0
    for p in parts:
        if p["score"] is None:
            continue
        w = weights[p["key"]]
        p["weight"] = w
        num += w * p["score"]
        den += w
    return round(100 * num / den) if den else None


def part(key, label, value, score, why):
    return {"key": key, "label": label, "value": value, "score": None if score is None else round(score, 2), "why": why}


def fmt_pct(v, d=1):
    return "–" if v is None else f"{v:+.{d}f}%"


def build(candles: dict[str, pd.DataFrame], fred: dict[str, pd.Series], news: dict, fii: dict) -> dict:
    q = {}
    for k, (sym, label, unit) in C.MACRO.items():
        df = candles.get(sym)
        if df is not None and len(df) > 5:
            q[k] = quote_row(df, label, unit, scale_yield=unit == "%")
    fr = {k: fred_row(fred.get(k, pd.Series(dtype=float)), lbl) for k, lbl in C.FRED.items()}
    fr = {k: v for k, v in fr.items() if v}
    # stand-ins from Yahoo when FRED is not answering
    if "DGS10" not in fr and "us10y" in q:
        fr["DGS10"] = {"label": "US 10Y yield (Yahoo)", "last": q["us10y"]["last"], "date": q["us10y"]["asof"],
                       "m1": q["us10y"]["m1"], "m3": q["us10y"]["m3"], "y1": q["us10y"]["y1"], "spark": q["us10y"]["spark"], "proxy": True}
    if "DGS2" not in fr and "us2y" in q:
        fr["DGS2"] = {"label": "US 2Y yield (Yahoo futures)", "last": q["us2y"]["last"], "date": q["us2y"]["asof"],
                      "m1": q["us2y"]["m1"], "m3": q["us2y"]["m3"], "y1": q["us2y"]["y1"], "spark": q["us2y"]["spark"], "proxy": True}
    if "T10Y2Y" not in fr and "DGS10" in fr and "DGS2" in fr:
        c10, c2 = fr["DGS10"]["spark"], fr["DGS2"]["spark"]
        n = min(len(c10), len(c2))
        sp = [round(a - b, 3) for a, b in zip(c10[-n:], c2[-n:])]
        fr["T10Y2Y"] = {"label": "10Y minus 2Y (Yahoo)", "last": round(fr["DGS10"]["last"] - fr["DGS2"]["last"], 3),
                        "date": fr["DGS10"]["date"], "m1": None, "m3": round(sp[-1] - sp[-64], 3) if n > 64 else None,
                        "y1": None, "spark": sp, "proxy": True}

    # ---------------- derived macro facts
    d = {}
    g = lambda k: fr.get(k, {}).get("last")  # noqa: E731
    d["us10y"] = q.get("us10y", {}).get("last") or g("DGS10")
    d["us2y"] = g("DGS2")
    d["curve"] = g("T10Y2Y")
    d["real10"] = g("DFII10")
    d["breakeven"] = g("T10YIE")
    d["fed_upper"] = g("DFEDTARU")
    d["fed_eff"] = g("DFF")
    d["hy"] = g("BAMLH0A0HYM2")
    d["unrate"] = g("UNRATE")
    if fred.get("CPIAUCSL") is not None:
        d["cpi_yoy"], d["cpi_yoy_3m_ago"] = yoy(fred["CPIAUCSL"])
    if fred.get("PCEPILFE") is not None:
        d["core_pce_yoy"], d["core_pce_3m_ago"] = yoy(fred["PCEPILFE"])
    if d.get("us2y") is None and q.get("us2y"):
        d["us2y"] = q["us2y"]["last"]
    if d.get("us2y") is not None and d.get("fed_eff") is not None:
        d["two_minus_ff"] = round(d["us2y"] - d["fed_eff"], 2)
    elif d.get("us2y") is not None and q.get("us3m"):
        d["two_minus_ff"] = round(d["us2y"] - q["us3m"]["last"], 2)      # 3-month bill as the stand-in for Fed funds
        d["two_minus_ff_proxy"] = True
    w = fred.get("WALCL", pd.Series(dtype=float))
    if len(w) > 14:
        d["walcl_3m_pct"] = round((w.iloc[-1] / w.iloc[-14] - 1) * 100, 2)
        d["walcl_tn"] = round(w.iloc[-1] / 1e6, 2)
    if "copper" in q and "gold" in q:
        cu, au = candles[C.MACRO["copper"][0]].Close, candles[C.MACRO["gold"][0]].Close
        ratio = (cu / au).dropna()
        d["cu_au_m1"] = _num(ta.ret(ratio, 30))
    if "gold" in q and "silver" in q:
        d["au_ag"] = round(q["gold"]["last"] / q["silver"]["last"], 1)

    # ---------------- global risk appetite
    sent = (news or {}).get("sentiment", {})
    gp = []
    vix = q.get("vix")
    if vix:
        sc = zone(vix["last"], C.VIX_ZONES)
        avg20 = sum(vix["spark"][-20:]) / len(vix["spark"][-20:])
        sc = ta.clamp(sc + (0.25 if vix["last"] < avg20 * 0.92 else -0.25 if vix["last"] > avg20 * 1.08 else 0))
        gp.append(part("vix", "US VIX (fear gauge)", f"{vix['last']:.1f} (20-day avg {avg20:.1f})", sc,
                       "Low and falling = calm, risk-on; above 22 and rising = fear"))
    else:
        gp.append(part("vix", "US VIX (fear gauge)", "–", None, "no data"))
    hy = fr.get("BAMLH0A0HYM2")
    if hy:
        sc = ta.lin(-(hy["m1"] or 0), C.CREDIT_FULL_PP)
        sc = ta.clamp(sc - (0.5 if hy["last"] > 5 else 0) + (0.2 if hy["last"] < 3.2 else 0))
        gp.append(part("credit", "US high-yield credit spread", f"{hy['last']:.2f}% ({(hy['m1'] or 0):+.2f} in 1m)", sc,
                       "Narrowing spreads = lenders relaxed (risk-on); widening = credit stress"))
    elif C.MACRO["hyg"][0] in candles and C.MACRO["ief"][0] in candles:
        ratio = (candles[C.MACRO["hyg"][0]].Close / candles[C.MACRO["ief"][0]].Close).dropna()
        m1 = ta.ret(ratio, 30)
        d["hyg_ief_m1"] = _num(m1)
        gp.append(part("credit", "Credit (junk bonds vs Treasuries, HYG/IEF)", f"{fmt_pct(m1)} in 1m (FRED spread not available)",
                       ta.lin(m1, C.CREDIT_PROXY_FULL_PCT), "Junk bonds lagging Treasuries = credit stress (stand-in for the spread)"))
    else:
        gp.append(part("credit", "US high-yield credit spread", "–", None, "no data"))
    spx = q.get("spx")
    if spx:
        sc = ta.clamp(0.4 * (1 if spx.get("above200") else -1) + 0.3 * (1 if spx.get("above50") else -1)
                      + 0.3 * (ta.lin(spx["m1"], 6) or 0))
        gp.append(part("spx", "S&P 500 trend", f"{fmt_pct(spx['m1'])} in 1m, {'above' if spx.get('above200') else 'below'} 200-day avg", sc,
                       "World's main risk asset: above its 50 and 200-day averages = uptrend"))
    dxy = q.get("dxy")
    if dxy:
        gp.append(part("dxy", "Dollar index (DXY)", f"{dxy['last']:.2f} ({fmt_pct(dxy['m1'])} in 1m)", ta.lin(-(dxy["m1"] or 0), C.DXY_FULL_PCT),
                       "A rising dollar tightens global money: bad for emerging markets, gold, crypto"))
    y10 = fr.get("DGS10")
    if y10:
        bp = (y10["m1"] or 0) * 100
        gp.append(part("yield", "US 10Y yield", f"{y10['last']:.2f}% ({bp:+.0f} bp in 1m)", ta.lin(-bp, C.YIELD_FULL_BP),
                       "Fast-rising yields hurt stock valuations, bonds and gold"))
    cv = fr.get("T10Y2Y")
    if cv:
        sc = -0.6 if cv["last"] < 0 else 0.4 if cv["last"] > 0.5 else 0.1
        gp.append(part("curve", "Yield curve (10Y − 2Y)", f"{cv['last']:+.2f} pp", sc,
                       "Inverted (below 0) has warned of recessions; positive and steady = normal"))
    if d.get("cu_au_m1") is not None:
        gp.append(part("cu_au", "Copper / gold ratio", f"{fmt_pct(d['cu_au_m1'])} in 1m", ta.lin(d["cu_au_m1"], C.CU_AU_FULL_PCT),
                       "Copper (growth) beating gold (safety) = growth optimism"))
    ns = sent.get("risk", {})
    gp.append(part("news", "News tone (all headlines)", f"{ns.get('score')} from {ns.get('n', 0)} headlines" if ns.get("score") is not None else "–",
                   None if ns.get("score") is None else ns["score"] / 60,
                   "Keyword score of the last 4 days of headlines, recent ones count more"))
    gscore = combine(gp, C.GLOBAL_W)

    # ---------------- India
    ip = []
    nf = q.get("nifty")
    if nf:
        sc = ta.clamp(0.4 * (1 if nf.get("above200") else -1) + 0.3 * (1 if nf.get("above50") else -1)
                      + 0.3 * (ta.lin(nf["m1"], 5) or 0))
        ip.append(part("nifty", "Nifty 50 trend", f"{fmt_pct(nf['m1'])} in 1m, {'above' if nf.get('above200') else 'below'} 200-day avg", sc,
                       "Above the 50 and 200-day averages = uptrend"))
    iv = q.get("ivix")
    if iv:
        ip.append(part("ivix", "India VIX", f"{iv['last']:.1f}", zone(iv["last"], C.IVIX_ZONES), "Below 14 = calm; above 18 = nervous"))
    inr = q.get("usdinr")
    if inr:
        ip.append(part("inr", "Rupee (USD-INR)", f"₹{inr['last']:.2f} ({fmt_pct(inr['m1'])} in 1m)", ta.lin(-(inr["m1"] or 0), C.INR_FULL_PCT),
                       "Weakening rupee usually comes with foreign selling"))
    br = q.get("brent")
    if br:
        ip.append(part("crude", "Brent crude", f"${br['last']:.1f} ({fmt_pct(br['m1'])} in 1m)", ta.lin(-(br["m1"] or 0), C.CRUDE_FULL_PCT),
                       "India imports most of its oil: rising crude hurts inflation and the rupee"))
    if fii.get("sum5") is not None:
        ip.append(part("fii", "FII cash flow (last 5 sessions)", f"₹{fii['sum5']:,.0f} Cr ({fii['n']} sessions)",
                       ta.lin(fii["sum5"], C.FII_FULL_CR), "Foreign investors net buying = support for Indian equity"))
    else:
        ip.append(part("fii", "FII cash flow", "–", None, "no data yet (NSE)"))
    nsi = sent.get("in_eq", {})
    ip.append(part("news", "India news tone", f"{nsi.get('score')} from {nsi.get('n', 0)} headlines" if nsi.get("score") is not None else "–",
                   None if nsi.get("score") is None else nsi["score"] / 60, "Keyword score of India headlines"))
    iscore = combine(ip, C.INDIA_W)
    overall = None if gscore is None and iscore is None else round(((gscore or 0) + (iscore or 0)) / (2 - (gscore is None) - (iscore is None)))

    return {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "quotes": q, "fred": fr, "derived": d,
        "global": {"score": gscore, "regime": regime(gscore), "parts": gp},
        "india": {"score": iscore, "regime": regime(iscore), "parts": ip},
        "overall": {"score": overall, "regime": regime(overall)},
        "fii": fii, "calendar": calendar(), "interpret": interpret(q, fr, d, fii),
    }


def calendar() -> list[dict]:
    today = date.today()
    out = []
    for lst, name in ((C.FOMC, "US Fed (FOMC) rate decision"), (C.RBI_MPC, "RBI MPC rate decision")):
        for s in lst:
            dt = date.fromisoformat(s)
            if dt >= today:
                out.append({"date": s, "event": name, "days": (dt - today).days})
    return sorted(out, key=lambda x: x["date"])[:6]


def interpret(q, fr, d, fii) -> list[dict]:
    """Plain-words rules: what the moves mean for each asset class. tone: + good for risk, - bad, 0 info."""
    out = []

    def add(tone, text, assets):
        out.append({"tone": tone, "text": text, "assets": assets})
    dxy = q.get("dxy", {}).get("m1")
    if dxy is not None and abs(dxy) >= 1.5:
        add(-1 if dxy > 0 else 1, f"Dollar {'strengthening' if dxy > 0 else 'weakening'} ({dxy:+.1f}% in a month): "
            + ("headwind for gold, crypto and emerging markets; FII selling risk for India; US assets gain in rupee terms."
               if dxy > 0 else "tailwind for gold, crypto and emerging markets including India."),
            ["gold", "crypto", "in_eq"])
    y = fr.get("DGS10", {})
    if y.get("m1") is not None and abs(y["m1"]) >= 0.25:
        up = y["m1"] > 0
        add(-1 if up else 1, f"US 10Y yield {'up' if up else 'down'} {abs(y['m1']) * 100:.0f} bp in a month (now {y['last']:.2f}%): "
            + ("pressure on growth stocks, long bonds and gold." if up else "supports bonds, growth stocks and gold."),
            ["us_eq", "us_bond", "gold"])
    r10 = fr.get("DFII10", {})
    if r10.get("last") is not None:
        add(0, f"Real 10Y yield (after inflation) is {r10['last']:.2f}%"
            + (" and rising: gold usually struggles when real yields climb." if (r10.get("m1") or 0) > 0.15 else
               " and falling: lower real yields have historically helped gold." if (r10.get("m1") or 0) < -0.15 else "."),
            ["gold"])
    cv = fr.get("T10Y2Y", {})
    if cv.get("last") is not None:
        if cv["last"] < 0:
            add(-1, f"Yield curve inverted ({cv['last']:+.2f} pp): the bond market expects slower growth / rate cuts.", ["us_eq"])
        elif (cv.get("m3") or 0) > 0.3:
            add(0, f"Yield curve steepening ({cv['last']:+.2f} pp, {cv['m3']:+.2f} in 3 months): watch whether it is growth (good) or long-end inflation fear (bad).", ["us_bond"])
    if d.get("two_minus_ff") is not None:
        t = d["two_minus_ff"]
        ref = "the 3-month bill" if d.get("two_minus_ff_proxy") else "Fed funds"
        if t <= -0.4:
            add(1, f"US 2Y yield is {abs(t):.2f} pp below {ref}: the market is pricing rate cuts ahead.", ["us_eq", "gold", "crypto"])
        elif t >= 0.25:
            add(-1, f"US 2Y yield is {t:.2f} pp above {ref}: the market is pricing rate hikes.", ["us_eq", "gold", "crypto"])
        else:
            add(0, f"US 2Y yield is close to {ref} ({t:+.2f} pp): no big rate change priced soon.", ["us_bond"])
    if d.get("cpi_yoy") is not None:
        rising = d["cpi_yoy"] > (d.get("cpi_yoy_3m_ago") or d["cpi_yoy"]) + 0.2
        falling = d["cpi_yoy"] < (d.get("cpi_yoy_3m_ago") or d["cpi_yoy"]) - 0.2
        add(-1 if rising else 1 if falling else 0, f"US CPI inflation {d['cpi_yoy']:.1f}% a year "
            f"({'rising' if rising else 'falling' if falling else 'steady'} vs {d.get('cpi_yoy_3m_ago', 0):.1f}% three months ago).",
            ["us_bond", "gold"])
    if d.get("walcl_3m_pct") is not None:
        g = d["walcl_3m_pct"]
        add(1 if g > 0.5 else -1 if g < -0.5 else 0, f"Fed balance sheet {g:+.1f}% in 3 months (${d['walcl_tn']} tn): "
            + ("liquidity being added - supportive for risk assets and crypto." if g > 0.5 else
               "liquidity being drained (QT)." if g < -0.5 else "roughly flat liquidity."), ["crypto", "us_eq"])
    vix = q.get("vix", {}).get("last")
    if vix is not None:
        if vix >= 25:
            add(-1, f"US VIX {vix:.1f}: fear is high. Big swings; historically good long-term entries but risky short term.", ["us_eq"])
        elif vix <= 13.5:
            add(0, f"US VIX {vix:.1f}: very calm market - complacency can precede sharp moves.", ["us_eq"])
    hy = fr.get("BAMLH0A0HYM2", {})
    if (hy.get("m1") or 0) >= 0.3:
        add(-1, f"Credit spreads widened {hy['m1']:+.2f} pp in a month: lenders demand more - an early stress signal.", ["us_eq"])
    br = q.get("brent", {}).get("m1")
    if br is not None and abs(br) >= 8:
        add(-1 if br > 0 else 1, f"Brent crude {br:+.1f}% in a month: " + ("inflation and rupee risk for India." if br > 0 else "relief for India's inflation and rupee."), ["in_eq"])
    inr = q.get("usdinr", {}).get("m1")
    if inr is not None and abs(inr) >= 1:
        add(-1 if inr > 0 else 1, f"Rupee {'weakened' if inr > 0 else 'strengthened'} {abs(inr):.1f}% against the dollar in a month.", ["in_eq"])
    if fii.get("sum5") is not None and abs(fii["sum5"]) >= 5000:
        add(1 if fii["sum5"] > 0 else -1, f"FIIs net {'bought' if fii['sum5'] > 0 else 'sold'} ₹{abs(fii['sum5']):,.0f} Cr in the cash market over {fii['n']} sessions.", ["in_eq"])
    if d.get("cu_au_m1") is not None and abs(d["cu_au_m1"]) >= 5:
        add(1 if d["cu_au_m1"] > 0 else -1, f"Copper/gold ratio {d['cu_au_m1']:+.1f}% in a month: markets are pricing {'stronger' if d['cu_au_m1'] > 0 else 'weaker'} growth.", ["copper", "us_eq"])
    for ev in calendar():
        if ev["days"] <= 7:
            add(0, f"{ev['event']} in {ev['days']} day{'s' if ev['days'] != 1 else ''} ({ev['date']}): expect bigger moves around it.", ["us_eq", "in_eq", "gold"])
    return out


def fii_summary(hist_days: dict, latest: list[dict]) -> dict:
    """Merge today's NSE FII/DII numbers into the stored history; sum the last 5 sessions."""
    fii = [x for x in latest if x["cat"] == "FII"]
    dii = [x for x in latest if x["cat"] == "DII"]
    store = dict(hist_days)
    if fii:
        key = sources_date(fii[0]["date"])
        if key:
            store[key] = {"fii": fii[0]["net"], "dii": dii[0]["net"] if dii else None}
    keys = sorted(store)[-5:]
    if not keys:
        return {"sum5": None, "days": {}, "n": 0}
    return {"sum5": round(sum(store[k]["fii"] for k in keys)), "dii5": round(sum((store[k].get("dii") or 0) for k in keys)),
            "n": len(keys), "last": store[keys[-1]], "last_date": keys[-1],
            "days": {k: store[k] for k in sorted(store)[-60:]}}


def sources_date(s) -> str | None:
    for f in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(s).strip(), f).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


__all__ = ["build", "fii_summary", "sources"]
