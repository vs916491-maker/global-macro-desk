"""Crypto tab: market overview (dominance, Fear & Greed, altseason), trending coins ranked by price
action, and Swing (4-hour) / Positional (daily) ideas. Long only (spot investing)."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from . import config as C
from . import setups, sources, ta


def universe() -> tuple[list[dict], dict, list[str]]:
    mk = sources.coingecko("/coins/markets", {"vs_currency": "usd", "order": "market_cap_desc", "per_page": 120,
                                             "page": 1, "price_change_percentage": "24h,7d,30d"}) or []
    coins = []
    for c in mk:
        sym = str(c.get("symbol", "")).lower()
        name = str(c.get("name", ""))
        if sym in C.STABLES or any(w in name.lower() for w in C.SKIP_COIN_WORDS):
            continue
        if (c.get("current_price") or 0) and 0.97 < c["current_price"] < 1.03 and abs(c.get("price_change_percentage_30d_in_currency") or 0) < 2:
            continue                                   # an unlisted stablecoin
        coins.append({"id": c["id"], "sym": sym.upper(), "name": name, "rank": c.get("market_cap_rank"),
                      "price": c.get("current_price"), "mcap": c.get("market_cap"), "vol24": c.get("total_volume"),
                      "d1": c.get("price_change_percentage_24h_in_currency"), "w1": c.get("price_change_percentage_7d_in_currency"),
                      "m1": c.get("price_change_percentage_30d_in_currency"), "ath_chg": c.get("ath_change_percentage"),
                      "yahoo": C.YAHOO_COIN.get(sym, f"{sym.upper()}-USD")})
        if len(coins) >= C.CRYPTO_TOP:
            break
    g = (sources.coingecko("/global") or {}).get("data", {})
    tr = sources.coingecko("/search/trending") or {}
    trending = [str(x.get("item", {}).get("symbol", "")).upper() for x in tr.get("coins", [])]
    if not coins:      # CoinGecko down: fall back to a fixed list priced by Yahoo
        for s in ["BTC", "ETH", "XRP", "BNB", "SOL", "DOGE", "ADA", "TRX", "LINK", "AVAX", "XLM", "SUI", "HBAR",
                  "BCH", "LTC", "DOT", "TON", "UNI", "NEAR", "APT", "AAVE", "ICP", "ETC", "PEPE"]:
            coins.append({"id": s.lower(), "sym": s, "name": s, "rank": None, "yahoo": C.YAHOO_COIN.get(s.lower(), f"{s}-USD")})
    return coins, g, trending


def pct_rank(vals: dict[str, float]) -> dict[str, float]:
    s = pd.Series({k: v for k, v in vals.items() if v is not None})
    return {} if s.empty else (s.rank(pct=True)).to_dict()


def analyse(fit: float, hist: dict) -> tuple[dict, dict]:
    coins, g, trending = universe()
    syms = [c["yahoo"] for c in coins]
    daily = sources.yahoo_many(syms, "1d", "2y")
    hourly = sources.yahoo_many(syms, "1h", "120d")
    btc_d = daily.get("BTC-USD")
    frames, rows = {}, []
    r90, r30 = {}, {}
    prep = {}
    for c in coins:
        dd = daily.get(c["yahoo"])
        if dd is None or len(dd) < 60:
            continue
        dd = ta.complete_daily(dd, "crypto")
        h4 = ta.resample(hourly[c["yahoo"]], "4h") if c["yahoo"] in hourly else pd.DataFrame()
        prep[c["sym"]] = (dd, h4)
        r90[c["sym"]] = ta.ret(dd.Close, 90)
        r30[c["sym"]] = ta.ret(dd.Close, 30)
    btc90, btc30 = r90.get("BTC"), r30.get("BTC")
    rs90 = pct_rank({k: (v - (btc90 or 0)) if v is not None else None for k, v in r90.items()})
    rs30 = pct_rank({k: (v - (btc30 or 0)) if v is not None else None for k, v in r30.items()})
    w7 = pct_rank({c["sym"]: c.get("w1") for c in coins})
    m30 = pct_rank({c["sym"]: c.get("m1") for c in coins})
    views = {"swing": [], "positional": []}
    for c in coins:
        if c["sym"] not in prep:
            continue
        dd, h4 = prep[c["sym"]]
        dI = ta.add(dd, 50)
        wk = ta.weekly(dd)
        wk_t = ta.trend_state(ta.add(wk, 20)) if len(wk) >= 60 else {"state": "unknown"}
        d_t = ta.trend_state(ta.add(dd, 20))
        row = {**{k: c.get(k) for k in ("id", "sym", "name", "rank", "mcap", "vol24", "d1", "w1", "m1", "ath_chg")},
               "price": c.get("price") or float(dd.Close.iloc[-1]), **setups.summary_row(dI),
               "trend_d": d_t["state"], "trend_w": wk_t["state"], "rs90": round(rs90.get(c["sym"], 0.5), 2),
               "vs_btc_90d": None if r90.get(c["sym"]) is None or btc90 is None else round(r90[c["sym"]] - btc90, 1),
               "r90": None if r90.get(c["sym"]) is None else round(r90[c["sym"]], 1), "cg_trending": c["sym"] in trending,
               "tv": f"CRYPTO:{c['sym']}USD"}
        if not row.get("w1") and len(dd) > 8:
            row["w1"] = round(ta.ret(dd.Close, 7) or 0, 2)
        avgv = dd.Volume.tail(31).iloc[:-1].mean()
        row["vol_surge"] = round(float(dd.Volume.iloc[-1] / avgv), 2) if avgv and avgv > 0 else None
        tsc = 25 * w7.get(c["sym"], 0.5) + 25 * m30.get(c["sym"], 0.5) + 25 * (row["trend_pts"] + 5) / 10 \
            + 15 * min(1, (row["vol_surge"] or 1) / 2) + 10 * row["cg_trending"]
        row["trend_score"] = round(tsc)
        rows.append(row)
        base_ctx = {"symbol": c["sym"], "name": c["name"], "fit": fit, "tv": row["tv"], "max_risk_pct": 12, "yahoo": c["yahoo"]}
        if len(h4) >= 80:
            h4I = ta.add(h4, 20)
            frames[("swing", c["sym"])] = h4
            views["swing"] += setups.find(h4I, "swing", {**base_ctx, "tf": "4h", "rs": rs30.get(c["sym"]), "htf": d_t,
                                                           "htf_name": "daily"}, allow_short=False)
        frames[("positional", c["sym"])] = dd
        views["positional"] += setups.find(dI, "positional", {**base_ctx, "tf": "1d", "rs": rs90.get(c["sym"]),
                                                               "htf": wk_t, "htf_name": "weekly"}, allow_short=False)
    for v in views:
        views[v].sort(key=lambda x: x["score"], reverse=True)
    rows.sort(key=lambda r: r["trend_score"], reverse=True)

    # market overview
    fng = sources.fear_greed(60)
    dom = (g.get("market_cap_percentage") or {})
    days = (hist or {}).get("days", {})
    keys = sorted(days)
    dom7 = next((days[k].get("btc_dom") for k in reversed(keys[:-6]) if days[k].get("btc_dom")), None) if len(keys) > 6 else None
    alt = [r for r in rows if r["sym"] != "BTC" and r.get("vs_btc_90d") is not None]
    altseason = round(100 * sum(r["vs_btc_90d"] > 0 for r in alt) / len(alt)) if alt else None
    btc = next((r for r in rows if r["sym"] == "BTC"), {})
    market = {
        "total_mcap": g.get("total_market_cap", {}).get("usd"), "mcap_chg24": g.get("market_cap_change_percentage_24h_usd"),
        "btc_dom": dom.get("btc"), "eth_dom": dom.get("eth"), "btc_dom_7d_ago": dom7,
        "fng": fng[0] if fng else None, "fng_avg7": round(sum(x["value"] for x in fng[:7]) / len(fng[:7])) if fng else None,
        "fng_hist": list(reversed(fng)), "altseason": altseason,
        "btc": {k: btc.get(k) for k in ("price", "d1", "w1", "m1", "trend_d", "trend_w", "rsi", "from_high", "above200")},
        "fit": round(fit), "trending_cg": trending,
    }
    market["regime"] = crypto_regime(market)
    doc = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "market": market, "coins": rows,
           "views": {k: {"ideas": v[:15], "count": len(v)} for k, v in views.items()}}
    return doc, frames


def crypto_regime(m: dict) -> dict:
    b = m.get("btc") or {}
    pts, why = 0, []
    if b.get("trend_d") == "up":
        pts += 2; why.append("Bitcoin daily uptrend")
    elif b.get("trend_d") == "down":
        pts -= 2; why.append("Bitcoin daily downtrend")
    if b.get("above200") is True:
        pts += 1; why.append("BTC above its 200-day average")
    elif b.get("above200") is False:
        pts -= 1; why.append("BTC below its 200-day average")
    f = (m.get("fng") or {}).get("value")
    if f is not None:
        if f <= 20:
            why.append(f"Extreme fear ({f}): historically better for patient buying than chasing"); pts += 0
        elif f >= 80:
            why.append(f"Extreme greed ({f}): late-stage, size down"); pts -= 1
    if m.get("altseason") is not None:
        why.append(f"{m['altseason']}% of the top coins beat BTC over 90 days" + (" (alt season)" if m["altseason"] >= 75 else " (Bitcoin season)" if m["altseason"] <= 25 else ""))
    if m.get("btc_dom") and m.get("btc_dom_7d_ago"):
        dd = m["btc_dom"] - m["btc_dom_7d_ago"]
        why.append(f"BTC dominance {dd:+.1f} pp in a week ({'money moving to BTC' if dd > 0 else 'money moving to altcoins'})")
    label = "Bullish" if pts >= 2 else "Bearish" if pts <= -2 else "Mixed"
    return {"label": label, "points": pts, "why": why}
