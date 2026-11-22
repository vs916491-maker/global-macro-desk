"""Track Record: every idea scoring >= MIN_SCORE is logged once (table gm_ideas), filled at the
open of the next candle (no look-ahead), and closed at its stop, its target, or the time exit
(swing 14 days, positional 90 days) on the same timeframe it was found on. A candle that reaches
both the stop and the target is "unclear" and left out of every average."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from . import sources

TF_HOURS = {"4h": 4, "1d": 24}
DAILY_END_H = {"us": 6.75, "crypto": 24, "commodities": 17.5}


def _ts(s) -> pd.Timestamp:
    t = pd.Timestamp(s)
    return t.tz_convert(None) if t.tzinfo else t


def candle_end(tab: str, tf: str, candle: str) -> pd.Timestamp:
    t = _ts(candle)
    if tf == "4h":
        return t + pd.Timedelta(hours=4)
    return t + pd.Timedelta(hours=DAILY_END_H.get(tab, 24))


def key_of(tab, i):
    return f"{tab}|{i['view']}|{i['symbol']}|{i['side']}|{i['setup']}|{i['candle'][:16]}"


def walk(row: dict, df: pd.DataFrame) -> dict | None:
    """New values for the row (fill and/or close), or None if nothing changed."""
    if df is None or df.empty:
        return None
    long = row["side"] == "Long"
    stop, tgt = float(row["stop"]), float(row["target"])
    upd = {}
    if row["status"] == "pending":
        after = df[df.index >= _ts(row["entry_after"])]
        if after.empty:
            return None
        first = after.iloc[0]
        entry = float(first.Open)
        upd.update({"status": "open", "entry": entry, "entry_ts": after.index[0].isoformat() + "Z"})
        row = {**row, **upd}
    entry = float(row["entry"])
    t0 = _ts(row["entry_ts"])
    limit = t0 + pd.Timedelta(days=int(row.get("max_days") or 14))
    bars = df[df.index >= t0]
    prev = None
    for ts, b in bars.iterrows():
        if ts >= limit and prev is not None:
            return {**upd, **close(row, float(prev[1].Close), prev[0], "time")}
        hit_s = b.Low <= stop if long else b.High >= stop
        hit_t = b.High >= tgt if long else b.Low <= tgt
        if hit_s and hit_t:
            if ts == t0 and ((b.Open <= stop) if long else (b.Open >= stop)):
                return {**upd, **close(row, float(b.Open), ts, "stop")}
            return {**upd, **close(row, None, ts, "unclear")}
        if hit_s:
            gap = (b.Open < stop) if long else (b.Open > stop)
            return {**upd, **close(row, float(b.Open) if gap else stop, ts, "stop")}
        if hit_t:
            gap = (b.Open > tgt) if long else (b.Open < tgt)
            return {**upd, **close(row, float(b.Open) if gap else tgt, ts, "target")}
        prev = (ts, b)
    if prev is not None:
        last = float(prev[1].Close)
        upd.update({"last_price": last, "last_ts": prev[0].isoformat() + "Z",
                    "last_pct": round(((last / entry - 1) * 100) * (1 if long else -1), 2)})
    return upd or None


def close(row, exit_px, ts, result) -> dict:
    out = {"status": "closed", "result": result, "exit_ts": pd.Timestamp(ts).isoformat() + "Z"}
    if exit_px is None:
        return {**out, "exit": None, "net_pct": None, "r_mult": None}
    entry, stop = float(row["entry"]), float(row["stop"])
    long = row["side"] == "Long"
    net = (exit_px / entry - 1) * 100 * (1 if long else -1)
    risk = abs(entry - stop) / entry * 100
    return {**out, "exit": exit_px, "net_pct": round(net, 3), "r_mult": round(net / risk, 3) if risk > 0 else None}


def update(db, tab: str, ideas: list[dict], frames: dict) -> dict:
    """Advance open ideas of this tab, then log today's new ideas. Returns counts."""
    try:
        live = db.select("gm_ideas", {"select": "*", "tab": f"eq.{tab}", "status": "in.(pending,open)"})
    except Exception as e:  # noqa: BLE001
        sources.problem(f"Track record table: {e} (run supabase/001_global_macro_desk.sql)")
        return {"error": str(e)}
    closed = filled = 0
    cache = {}
    for r in live:
        df = frames.get((r["view"], r["symbol"]))
        if df is None:
            y = (r.get("info") or {}).get("yahoo")
            if not y:
                continue
            tf = r.get("tf") or "1d"
            if (y, tf) not in cache:
                from . import ta
                raw = sources.yahoo(y, "1h" if tf == "4h" else "1d", "120d" if tf == "4h" else "1y")
                cache[(y, tf)] = ta.resample(raw, "4h") if tf == "4h" and not raw.empty else raw
            df = cache[(y, tf)]
        upd = walk(r, df)
        if upd:
            db.update("gm_ideas", {"id": f"eq.{r['id']}"}, upd)
            closed += upd.get("status") == "closed"
            filled += r["status"] == "pending" and upd.get("status") in ("open", "closed")
            r.update(upd)
    busy = {(r["view"], r["symbol"], r["side"]) for r in live if r["status"] in ("pending", "open")}
    new = []
    for i in ideas:
        if not i.get("logged") or (i["view"], i["symbol"], i["side"]) in busy:
            continue
        busy.add((i["view"], i["symbol"], i["side"]))
        new.append({"key": key_of(tab, i), "tab": tab, "view": i["view"], "symbol": i["symbol"], "name": i.get("name"),
                    "side": i["side"], "setup": i["setup"], "score": i["score"], "tf": i.get("tf"),
                    "signal_ts": i["candle"] + "Z", "entry_after": candle_end(tab, i.get("tf"), i["candle"]).isoformat() + "Z",
                    "planned_entry": i["entry"], "stop": i["stop"], "target": i["target"], "status": "pending",
                    "max_days": i.get("max_days"),
                    "info": {"parts": i.get("parts"), "reasons": i.get("reasons"), "warns": i.get("warns"),
                             "trend": i.get("trend"), "yahoo": i.get("yahoo"), "sector": i.get("sector"),
                             "risk_pct": i.get("risk_pct"), "rr": i.get("rr")}})
    if new:
        db.insert_new("gm_ideas", new, "key")
    return {"open": len([r for r in live if r["status"] != "closed"]), "closed_now": closed, "filled_now": filled,
            "logged_now": len(new), "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


__all__ = ["update", "walk", "timedelta"]
