"""Rebuild the last N days of score history (gm_hist) from past market and Fed data.

  python -m gmd.backfill [--days 365] [--dry]

For each weekday it cuts every price and FRED series at that date and runs the same macro and money-flow
code as the hourly job. News and FII flows are not available for past days, so those parts are left out
(their weight goes to the other parts). Days already written by the live job are never overwritten."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

import pandas as pd

from . import config as C
from . import flows, macro, sources, store
from .run import get_doc


def cut(df: pd.DataFrame, end: pd.Timestamp) -> pd.DataFrame:
    out = df[df.index < end].copy()
    out.attrs = {}                      # no live price: the last close is "now"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    db = store.Local() if a.dry else store.connect()
    hist = get_doc(db, "gm_hist") or {"days": {}, "fii": {}}
    syms = sorted({v[0] for v in C.MACRO.values()} | {x[1] for x in C.ASSETS.values() if x[1]}
                  | {x[2] for x in C.ASSETS.values() if x[2]} | {"INR=X"})
    candles = sources.yahoo_many(syms, "1d", "5y")
    fred = sources.fred_many(list(C.FRED), days=a.days + 1000)
    today = pd.Timestamp.now().normalize()
    dates = pd.bdate_range(today - pd.Timedelta(days=a.days), today - pd.Timedelta(days=1))
    added = 0
    for d in dates:
        key = d.strftime("%Y-%m-%d")
        if key in hist["days"] and hist["days"][key].get("assets"):
            continue
        end = d + pd.Timedelta(days=1)
        cs = {k: cut(v, end) for k, v in candles.items()}
        cs = {k: v for k, v in cs.items() if len(v) > 30}
        fs = {k: v[v.index < end] for k, v in fred.items()}
        mac = macro.build(cs, fs, {"items": [], "sentiment": {}}, {"sum5": None})
        mac["_news"] = {}
        fl = flows.analyse(cs, mac, None)
        hist["days"][key] = {"global": mac["global"]["score"], "india": mac["india"]["score"],
                             "overall": mac["overall"]["score"],
                             "assets": {x["key"]: x["score"] for x in fl["assets"]}, "backfilled": True}
        added += 1
        if added % 40 == 0:
            print(key, hist["days"][key])
    hist["days"] = {k: hist["days"][k] for k in sorted(hist["days"])[-400:]}
    db.put_doc("gm_hist", hist)
    print(f"Backfilled {added} days ({dates[0].date()} .. {dates[-1].date()}); problems: {sources.PROBLEMS}",
          datetime.now(timezone.utc).isoformat(timespec="seconds"))


if __name__ == "__main__":
    main()
