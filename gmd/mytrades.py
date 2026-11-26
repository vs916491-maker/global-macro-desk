"""My Trades (table gm_trades): his own trades, added on the site (by hand or "I took this trade").

Every hourly run: each open trade is checked on Yahoo hourly candles after its entry time and closed
automatically at the stop only (his choice, 26 Nov 2026; the target is closed by hand). A candle that
opens beyond the stop fills at its open (gap). Open trades get a live price in doc gm_trade_prices.
P&L: net % after config.TRADE_COST_PCT, US $ = (sell - buy) x qty - charges, rupees at USD/INR."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from . import config as C, sources

COMMOD_YAHOO = {k: v[0] for k, v in C.COMMODS.items()}            # gold -> GC=F, brent -> BZ=F
COMMOD_YAHOO["aluminum"] = COMMOD_YAHOO.get("aluminium")
COMMOD_YAHOO["hrc"] = COMMOD_YAHOO.get("steel")


def yahoo_of(tr: dict) -> str | None:
    if tr.get("yahoo"):
        return tr["yahoo"]
    sym = str(tr.get("symbol") or "").strip()
    if not sym:
        return None
    if tr["asset"] == "crypto":
        return C.YAHOO_COIN.get(sym.lower(), f"{sym.upper()}-USD")
    if tr["asset"] == "commodities":
        return COMMOD_YAHOO.get(sym.lower(), sym.upper())
    return sym.upper().replace(".", "-")                            # BRK.B -> BRK-B


def close_values(tr: dict, exit_px: float, usdinr: float | None) -> dict:
    sign = 1 if tr["side"] == "Long" else -1
    entry = float(tr["entry"])
    cost = tr.get("cost_pct")
    if cost is None:
        cost = C.TRADE_COST_PCT.get(tr["asset"], 0.1)
    out = {"exit": round(exit_px, 8), "net_pct": round((exit_px / entry - 1) * 100 * sign - cost, 3), "cost_pct": cost}
    if tr.get("qty"):
        usd = (exit_px - entry) * sign * float(tr["qty"]) - float(tr.get("charges_usd") or 0)
        out["pnl_usd"] = round(usd, 2)
        if usdinr:
            out.update({"usdinr": round(usdinr, 4), "pnl_inr": round(usd * usdinr, 2)})
    return out


def check(db, usdinr: float | None) -> dict:
    try:
        rows = db.select("gm_trades", {"select": "*", "status": "eq.open"})
    except Exception as e:  # noqa: BLE001
        sources.problem(f"My Trades table: {e} (run supabase/003_my_trades.sql)")
        return {"error": str(e)}
    now = datetime.now(timezone.utc)
    prices, cache, closed = {}, {}, 0
    for tr in rows:
        y = yahoo_of(tr)
        if not y:
            continue
        if y not in cache:
            cache[y] = sources.yahoo(y, "1h", "60d")
        df = cache[y]
        if df is None or df.empty:
            sources.problem(f"My Trades: no price for {tr['symbol']} ({y})")
            continue
        t0 = pd.Timestamp(tr["entry_time"])
        t0 = t0.tz_convert(None) if t0.tzinfo else t0
        bars = df[df.index >= t0]                                    # candles that start after the entry
        stop = tr.get("stop")
        long = tr["side"] == "Long"
        hit = None
        if stop:
            stop = float(stop)
            for ts, b in bars.iterrows():
                if (b.Low <= stop) if long else (b.High >= stop):
                    gap = (b.Open < stop) if long else (b.Open > stop)
                    hit = (float(b.Open) if gap else stop, ts)
                    break
        if hit:
            vals = close_values(tr, hit[0], usdinr)
            vals.update({"status": "closed", "exit_reason": "stop hit (auto)",
                         "exit_time": pd.Timestamp(hit[1]).isoformat() + "Z"})
            db.update("gm_trades", {"id": f"eq.{tr['id']}"}, vals)
            closed += 1
        else:
            last = df.attrs.get("price") or float(df.Close.iloc[-1])
            prices[str(tr["id"])] = {"px": float(last), "t": now.isoformat(timespec="minutes")}
    db.put_doc("gm_trade_prices", {"prices": prices, "usdinr": usdinr, "updated": now.isoformat(timespec="seconds")})
    return {"open": len(rows) - closed, "closed_now": closed}
