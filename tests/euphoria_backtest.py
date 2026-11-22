"""Euphoria meter backtest on real history (runs on GitHub: workflow euphoria-test.yml).

Prints, for each asset: the meter at known tops (and a few bottoms for contrast), every episode
where the meter first reached 80 / 60, what happened next (further rise, drop, 90-day return),
and average results by meter level. News and breadth are live-only, so they are not in the test."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gmd import euphoria as E, sources  # noqa: E402

KEY_DATES = {
    "crypto": [("2017-12-17", "top"), ("2021-04-14", "top"), ("2021-11-10", "top"), ("2024-03-14", "top"),
               ("2024-12-17", "top"), ("2025-01-20", "top (inauguration)"), ("2025-10-06", "top"),
               ("2020-03-12", "bottom"), ("2022-11-21", "bottom")],
    "gold": [("2011-09-06", "top"), ("2020-08-06", "top"), ("2025-10-20", "top"), ("2015-12-17", "bottom")],
    "silver": [("2011-04-28", "top"), ("2020-08-07", "top"), ("2021-02-01", "squeeze"), ("2025-10-17", "top"), ("2020-03-18", "bottom")],
    "copper": [("2011-02-14", "top"), ("2021-05-10", "top"), ("2022-03-04", "top"), ("2024-05-20", "top"), ("2020-03-23", "bottom")],
    "us_eq": [("2018-01-26", "top"), ("2020-02-19", "top"), ("2022-01-03", "top"), ("2025-02-19", "top"), ("2020-03-23", "bottom"), ("2022-10-12", "bottom")],
    "in_eq": [("2021-10-18", "top"), ("2024-09-27", "top"), ("2020-03-23", "bottom"), ("2025-03-03", "bottom")],
}
DROP = {"crypto": 25, "gold": 8, "silver": 15, "copper": 12, "us_eq": 10, "in_eq": 10}   # a "real" drop for each asset


def fwd_stats(c: pd.Series, d, days=90):
    after = c[(c.index > d) & (c.index <= d + pd.Timedelta(days=days))]
    if after.empty:
        return None
    p0 = c.loc[d]
    peak = after.max()
    trough_after_peak = after[after.index >= after.idxmax()].min()
    return {"ret": round((after.iloc[-1] / p0 - 1) * 100, 1), "max_up": round((peak / p0 - 1) * 100, 1),
            "max_dd": round((after.min() / p0 - 1) * 100, 1),
            "peak_to_low": round((trough_after_peak / peak - 1) * 100, 1)}


def episodes(h: pd.DataFrame, thr: float, gap_days=60):
    s = h.score.dropna()
    out, last = [], None
    for d, v in s.items():
        if v >= thr and (last is None or (d - last).days > gap_days):
            out.append(d)
        if v >= thr:
            last = d
    return out


def main():
    fng_list = sources.fear_greed(0)
    fng = pd.Series({pd.Timestamp(x["date"]): x["value"] for x in fng_list}).sort_index() if fng_list else None
    vix = sources.yahoo("^VIX", "1d", "max")
    ivix = sources.yahoo("^INDIAVIX", "1d", "max")
    norm = lambda df: df.Close.set_axis(df.index.normalize()).groupby(level=0).last() if df is not None and not df.empty else None  # noqa: E731
    vixs = {"vix": norm(vix), "ivix": norm(ivix)}
    report = {}
    for key, (label, sym, code, mk) in E.ASSETS.items():
        df = sources.yahoo(sym, "1d", "max")
        if df.empty:
            print("NO DATA", key)
            continue
        cot = E.cot_history(code, "2008-01-01") if code else None
        h = E.history(key, df, fng, vixs, cot)
        c = h.close
        print(f"\n================ {label}  ({sym}; {c.index[0].date()} .. {c.index[-1].date()}; COT rows {0 if cot is None else len(cot)})")
        rows = []
        for ds, what in KEY_DATES[key]:
            d = pd.Timestamp(ds)
            win = h.loc[(h.index >= d - pd.Timedelta(days=30)) & (h.index <= d)]
            if win.empty or win.score.dropna().empty:
                print(f"  {ds} {what:22s}  no score (not enough history)")
                continue
            on = win.iloc[-1]
            mx = win.score.max()
            fs = fwd_stats(c, win.index[-1], 180) or {}
            rows.append({"date": ds, "what": what, "score": on.score, "max30": mx, "stretch": round(on.stretch * 100) if pd.notna(on.stretch) else None,
                         "mood": None if pd.isna(on["mood"]) else round(on["mood"] * 100), "crowd": None if pd.isna(on.crowd) else round(on.crowd * 100), **fs})
            print(f"  {ds} {what:22s} meter {on.score:5.1f} (max in prior 30d {mx:5.1f}) | stretch {rows[-1]['stretch']} mood {rows[-1]['mood']} crowd {rows[-1]['crowd']}"
                  f" | next 180d: ret {fs.get('ret')}%, max drop {fs.get('max_dd')}%")
        ep = {}
        for thr in (80, 60):
            lst = []
            for d in episodes(h, thr):
                fs = fwd_stats(c, d, 180)
                if not fs:
                    continue
                lst.append({"date": d.strftime("%Y-%m-%d"), "score": float(h.score.loc[d]), **fs, "real_drop": fs["peak_to_low"] <= -DROP[key]})
            ep[thr] = lst
            hits = sum(x["real_drop"] for x in lst)
            print(f"  -- first reading >= {thr}: {len(lst)} episodes; a drop of {DROP[key]}%+ from the next peak within 180d in {hits} of them")
            for x in lst[-12:]:
                print(f"     {x['date']} meter {x['score']:5.1f} | further rise {x['max_up']:+6.1f}% | then peak-to-low {x['peak_to_low']:+6.1f}% | 180d ret {x['ret']:+6.1f}%")
        # by level
        s = h.score.dropna()
        f90 = (c.shift(-90) / c - 1) * 100
        dd90 = pd.Series([(c.iloc[i + 1:i + 91].min() / c.iloc[i] - 1) * 100 if i + 91 <= len(c) else np.nan for i in range(len(c))], index=c.index)
        bands = []
        for lo, hi, name in [(0, 40, "Calm"), (40, 60, "Warm"), (60, 80, "Hot"), (80, 101, "Euphoric")]:
            idx = s[(s >= lo) & (s < hi)].index
            r = f90.reindex(idx).dropna()
            dd = dd90.reindex(idx).dropna()
            bands.append({"level": name, "days": len(idx), "avg90": round(r.mean(), 1) if len(r) else None,
                          "neg90": round((r < 0).mean() * 100) if len(r) else None, "avg_dd90": round(dd.mean(), 1) if len(dd) else None})
            print(f"  {name:9s} days {len(idx):5d} | avg next-90d return {bands[-1]['avg90']}% | negative {bands[-1]['neg90']}% of the time | avg worst drop in 90d {bands[-1]['avg_dd90']}%")
        # "first crack": meter was Hot (>= 60) in the last 60 days, then the close drops below the 50-day average
        ma50 = c.rolling(50).mean()
        below = c < ma50
        cross = below & ~below.shift(1, fill_value=False)
        hot60 = h.score.rolling(60, min_periods=1).max()
        res = {}
        for name, mask in [("after Hot", cross & (hot60 >= 60)), ("no Hot before", cross & (hot60 < 40))]:
            ds = [d for d in c.index[mask] if d + pd.Timedelta(days=90) <= c.index[-1]]
            fs = [fwd_stats(c, d, 90) for d in ds]
            fs = [f for f in fs if f]
            if fs:
                res[name] = {"n": len(fs), "avg_ret": round(np.mean([f["ret"] for f in fs]), 1),
                             "neg": round(100 * np.mean([f["ret"] < 0 for f in fs])),
                             "avg_dd": round(np.mean([f["max_dd"] for f in fs]), 1),
                             "big_dd": round(100 * np.mean([f["max_dd"] <= -DROP[key] for f in fs]))}
                print(f"  CRACK below 50-day {name:14s}: {res[name]['n']:3d} times | next 90d avg {res[name]['avg_ret']:+.1f}% | negative {res[name]['neg']}% | avg worst drop {res[name]['avg_dd']}% | drop of {DROP[key]}%+ in {res[name]['big_dd']}%")
        cr_dates = [d.strftime("%Y-%m-%d") for d in c.index[cross & (hot60 >= 60)]][-8:]
        print("     recent cracks after Hot:", ", ".join(cr_dates))
        last = h.iloc[-1]
        print(f"  NOW {h.index[-1].date()}: meter {last.score} ({E.level(last.score)}) stretch {last.stretch} mood {last['mood']} crowd {last.crowd}")
        report[key] = {"label": label, "crack": res, "key_dates": rows, "episodes": ep, "bands": bands,
                       "now": {"date": h.index[-1].strftime("%Y-%m-%d"), "score": last.score},
                       "series": [{"d": d.strftime("%Y-%m-%d"), "s": float(v), "c": float(c.loc[d])} for d, v in s.iloc[::5].items()]}
    Path("out").mkdir(exist_ok=True)
    Path("out/euphoria_backtest.json").write_text(json.dumps(report, default=str))
    print("\nProblems:", sources.PROBLEMS)


if __name__ == "__main__":
    main()
