"""Entry point for the scheduled jobs.

  python -m gmd.run hourly [--force] [--dry]   macro, news, money flow, crypto, commodities, track record
  python -m gmd.run us [--force] [--dry]       US equity scan (after the US close)

--dry: no database writes, documents go to ./out (also used when the Supabase secrets are missing).
Each job skips itself when it already ran recently (Supabase pg_cron starts it, GitHub cron is a backup)."""

from __future__ import annotations

import argparse
import json
import os
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import commodities, config as C, crypto, euphoria, flows, macro, news, record, sources, store, usequity

IST = timezone(timedelta(hours=5, minutes=30))


def get_doc(db, key):
    if isinstance(db, store.Local):
        p = Path("out") / f"{key}.json"
        return json.loads(p.read_text()) if p.exists() else None
    try:
        rows = db.select("docs", {"select": "data", "key": f"eq.{key}"})
        return rows[0]["data"] if rows else None
    except Exception as e:  # noqa: BLE001
        sources.problem(f"read {key}: {e}")
        return None


def step(name, fn, status):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        sources.problem(f"{name} failed: {type(e).__name__}: {str(e)[:200]}")
        status.setdefault("failed", []).append(name)
        return None


def recently(status_doc, job, minutes) -> bool:
    t = ((status_doc or {}).get(job) or {}).get("at")
    if not t:
        return False
    return datetime.now(timezone.utc) - datetime.fromisoformat(t) < timedelta(minutes=minutes)


def hourly(db, force=False):
    st_all = get_doc(db, "gm_status") or {}
    if not force and recently(st_all, "hourly", 40):
        print("hourly job already ran in the last 40 minutes: skipping")
        return
    st = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    hist = get_doc(db, "gm_hist") or {"days": {}, "fii": {}}
    syms = sorted({v[0] for v in C.MACRO.values()} | {a[1] for a in C.ASSETS.values() if a[1]}
                  | {a[2] for a in C.ASSETS.values() if a[2]} | {"INR=X"})
    candles = step("market data", lambda: sources.yahoo_many(syms, "1d", "2y"), st) or {}
    fred = step("FRED data", lambda: sources.fred_many(list(C.FRED)), st) or {}
    nw = step("news", news.collect, st) or {"items": [], "sentiment": {}}
    fii = step("FII flows", lambda: macro.fii_summary(hist.get("fii", {}), sources.nse_fii()), st) or {"sum5": None}
    hist["fii"] = fii.get("days", hist.get("fii", {}))
    mac = step("macro", lambda: macro.build(candles, fred, nw, fii), st) or {}
    mac["_news"] = nw.get("sentiment", {})
    fl = step("money flow", lambda: flows.analyse(candles, mac, hist), st) or {"assets": []}
    fit = {a["key"]: a["fit"] for a in fl.get("assets", [])}
    cr = step("crypto", lambda: crypto.analyse(fit.get("crypto", 50), hist), st)
    cm = step("commodities", lambda: commodities.analyse(mac, candles), st)
    eu = step("euphoria", lambda: euphoria.live(hist, nw.get("sentiment", {}), cr[0] if cr else None,
                                                get_doc(db, "gm_us"), candles), st)
    if eu:
        add_euphoria(eu, cr, cm, fl)
    if cr:
        st["record_crypto"] = step("crypto record", lambda: record.update(
            db, "crypto", cr[0]["views"]["swing"]["ideas"] + cr[0]["views"]["positional"]["ideas"], cr[1]), st)
    if cm:
        st["record_commod"] = step("commodity record", lambda: record.update(
            db, "commodities", cm[0]["views"]["swing"]["ideas"] + cm[0]["views"]["positional"]["ideas"], cm[1]), st)

    today = datetime.now(IST).strftime("%Y-%m-%d")
    day = hist["days"].setdefault(today, {})
    day.update({"global": mac.get("global", {}).get("score"), "india": mac.get("india", {}).get("score"),
                "overall": mac.get("overall", {}).get("score"),
                "assets": {a["key"]: a["score"] for a in fl.get("assets", [])}})
    day["news"] = {k: {kk: v.get(kk) for kk in ("score", "n", "pos", "neg")} for k, v in nw.get("sentiment", {}).items()}
    if eu:
        day["euphoria"] = {k: v["score"] for k, v in eu["assets"].items()}
    if cr and cr[0]["market"].get("btc_dom"):
        day["btc_dom"] = round(cr[0]["market"]["btc_dom"], 2)
    if cr and (cr[0]["market"].get("fng") or {}).get("value") is not None:
        day["fng"] = cr[0]["market"]["fng"]["value"]
    hist["days"] = {k: hist["days"][k] for k in sorted(hist["days"])[-400:]}

    mac.pop("_news", None)
    mac["news_sentiment"] = nw.get("sentiment", {})
    mac["history"] = [{"date": k, "global": v.get("global"), "india": v.get("india"), "overall": v.get("overall")}
                      for k, v in sorted(hist["days"].items())[-180:]]
    if mac.get("quotes"):
        db.put_doc("gm_macro", mac)
    if nw.get("items"):
        db.put_doc("gm_news", nw)
    if fl.get("assets"):
        db.put_doc("gm_flows", fl)
    if cr:
        db.put_doc("gm_crypto", cr[0])
    if cm:
        db.put_doc("gm_commod", cm[0])
    if eu:
        db.put_doc("gm_euphoria", eu)
    db.put_doc("gm_hist", hist)
    st.update({"problems": list(sources.PROBLEMS), "finished": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "counts": {"quotes": len(mac.get("quotes", {})), "news": len(nw.get("items", [])),
                          "coins": len(cr[0]["coins"]) if cr else 0,
                          "ideas_crypto": {k: v["count"] for k, v in cr[0]["views"].items()} if cr else None,
                          "ideas_commod": {k: v["count"] for k, v in cm[0]["views"].items()} if cm else None}})
    st_all["hourly"] = st
    db.put_doc("gm_status", st_all)
    report("Hourly job", st)


def add_euphoria(eu, cr, cm, fl):
    """Warning only: put each asset's meter next to its data and add a line to its long ideas."""
    A = eu["assets"]
    short = lambda a: {k: a.get(k) for k in ("score", "level", "alert", "policy", "note")}  # noqa: E731
    if cr and "crypto" in A:
        cr[0]["market"]["euphoria"] = short(A["crypto"])
        if A["crypto"].get("alert"):
            for v in cr[0]["views"].values():
                for i in v["ideas"]:
                    i["warns"].append(f"Euphoria: {A['crypto']['alert']['title']}")
    if cm:
        for k, m in cm[0]["metals"].items():
            if k in A:
                m["euphoria"] = short(A[k])
        for v in cm[0]["views"].values():
            for i in v["ideas"]:
                a = A.get(i["symbol"].lower(), {})
                if a.get("alert") and i["side"] == "Long":
                    i["warns"].append(f"Euphoria: {a['alert']['title']}")
    for a in (fl or {}).get("assets", []):
        if a["key"] in A:
            a["euphoria"] = short(A[a["key"]])


def us(db, force=False):
    st_all = get_doc(db, "gm_status") or {}
    if not force and recently(st_all, "us", 300):
        print("US scan already ran in the last 5 hours: skipping")
        return
    st = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    mac = get_doc(db, "gm_macro") or {}
    mac["_news"] = mac.get("news_sentiment", {})
    fl = get_doc(db, "gm_flows") or {}
    us_fit = next((a["fit"] for a in fl.get("assets", []) if a["key"] == "us_eq"), 50)
    cached = (get_doc(db, "gm_us_universe") or {}).get("list")
    res = step("US equity", lambda: usequity.analyse(mac, us_fit, cached), st)
    if res:
        doc, frames, uni = res
        st["record_us"] = step("US record", lambda: record.update(
            db, "us", doc["views"]["swing"]["ideas"] + doc["views"]["positional"]["ideas"], frames), st)
        db.put_doc("gm_us", doc)
        if len(uni) >= 300:
            db.put_doc("gm_us_universe", {"list": uni, "at": st["at"]})
        st["counts"] = {"universe": doc["universe"], "scanned": doc["scanned"],
                        "ideas": {k: v["count"] for k, v in doc["views"].items()}}
    st.update({"problems": list(sources.PROBLEMS), "finished": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    st_all["us"] = st
    db.put_doc("gm_status", st_all)
    report("US equity scan", st)


def report(title, st):
    lines = [f"## {title}", "", f"Started {st['at']}, finished {st.get('finished')}", ""]
    for k, v in st.items():
        if k.startswith("record") or k == "counts":
            lines.append(f"- **{k}**: `{json.dumps(v)}`")
    if st.get("failed"):
        lines.append(f"- **failed steps**: {', '.join(st['failed'])}")
    lines += ["", "### Problems" if st.get("problems") else "No problems."] + [f"- {p}" for p in st.get("problems", [])]
    text = "\n".join(lines)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(text + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job", choices=["hourly", "us", "all"])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    force = a.force or os.environ.get("FORCE") == "true"
    db = store.Local() if a.dry else store.connect()
    if a.job in ("hourly", "all"):
        hourly(db, force)
    if a.job in ("us", "all"):
        sources.PROBLEMS.clear()
        us(db, force)


if __name__ == "__main__":
    main()
