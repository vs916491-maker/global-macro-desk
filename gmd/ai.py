"""AI view (Google Gemini, free tier): daily market brief, news reading and a second opinion on ideas.

  python -m gmd.ai [--force] [--dry]

Text only (his choice, 22 Nov 2026): never changes scores, ideas or the mix. Runs twice a day
(~8:25 am and ~6:55 pm IST, Supabase pg_cron -> workflow ai-brief.yml). Needs repo secret GEMINI_API_KEY.
Gemini sees only the numbers and headlines the desk sends (no web search on the free tier, no personal data).
Every number the brief quotes is checked against the data sent; sentences with numbers that are not in the
data are dropped and listed in `removed`."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

from . import sources, store
from .run import get_doc, recently

API = "https://generativelanguage.googleapis.com/v1beta"
# Only used if the model list cannot be read. gemini-2.0-flash and 2.5-flash-lite are retired for new keys (404).
FALLBACK_MODELS = ["gemini-flash-latest", "gemini-2.5-flash"]
BUSY = "busy/rate limit"
SKIP_WORDS = ("image", "tts", "audio", "live", "embedding", "aqa", "learnlm", "gemma", "robotics", "computer")
ASSETS = {"us_eq": "US equity", "in_eq": "Indian equity", "us_bond": "US bonds", "gold": "Gold", "silver": "Silver",
          "copper": "Copper", "crypto": "Crypto"}


# ---------------------------------------------------------------- Gemini
def pick_model(key: str) -> list[str]:
    """Best text 'flash' models this key can use, newest stable first; fixed list as fallback."""
    try:
        r = requests.get(f"{API}/models", params={"key": key, "pageSize": 200}, timeout=20)
        names = [m["name"].split("/")[-1] for m in r.json().get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
    except Exception:  # noqa: BLE001
        return FALLBACK_MODELS
    flash = [n for n in names if "flash" in n and not any(w in n for w in SKIP_WORDS)]

    def rank(n):
        v = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
        ver = float(v.group(1)) if v else 0
        unstable = any(w in n for w in ("preview", "exp"))
        return (not unstable, "lite" not in n, ver, -len(n))
    flash.sort(key=rank, reverse=True)
    full = [n for n in flash if "lite" not in n][:4]
    # Flash-Lite as backup: Google's free tier often answers 503 "high demand" on the full Flash models
    lite = [n for n in flash if "lite" in n and not any(w in n for w in ("preview", "exp"))][:2]
    picked = full + lite + [m for m in FALLBACK_MODELS if m not in full + lite]
    print("Gemini models to try:", ", ".join(picked))
    return picked


def gemini(key: str, models: list[str], prompt: str, system: str) -> tuple[dict, str]:
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json", "maxOutputTokens": 8192}}
    errors: list[str] = []
    for m in models:
        for attempt in range(2):
            try:
                r = requests.post(f"{API}/models/{m}:generateContent", headers={"x-goog-api-key": key},
                                  json=body, timeout=180)
                if r.status_code in (429, 500, 502, 503, 504):
                    # busy or rate-limited: wait and try the same model again
                    err = f"{m}: HTTP {r.status_code} {BUSY} (try {attempt + 1})"
                    errors.append(err)
                    print("  " + err)
                    if attempt == 0:
                        time.sleep(15)
                    continue
                if r.status_code != 200:
                    err = f"{m}: HTTP {r.status_code} {short_error(r)}"
                    errors.append(err)
                    print("  " + err)
                    break
                j = r.json()
                cand = (j.get("candidates") or [{}])[0]
                parts = (cand.get("content") or {}).get("parts") or []
                text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                text = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
                if not text:
                    raise ValueError(f"empty answer (finishReason {cand.get('finishReason')})")
                return json.loads(text), m
            except Exception as e:  # noqa: BLE001
                err = f"{m}: {type(e).__name__} {str(e)[:160]}"
                errors.append(err)
                print("  " + err)
                break
    # show every model's problem, not just the last one (a retired fallback model used to hide the real cause)
    raise RuntimeError(" | ".join(errors) or "no model answered")


def short_error(r) -> str:
    try:
        return str(r.json().get("error", {}).get("message", ""))[:200]
    except Exception:  # noqa: BLE001
        return r.text[:200]


# ---------------------------------------------------------------- what we send
def r1(v, d=2):
    return None if v is None else round(float(v), d)


def build_input(docs: dict) -> dict:
    mac, fl, eu, nw = docs.get("gm_macro") or {}, docs.get("gm_flows") or {}, docs.get("gm_euphoria") or {}, docs.get("gm_news") or {}
    cr, cm, us = docs.get("gm_crypto") or {}, docs.get("gm_commod") or {}, docs.get("gm_us") or {}
    q, fr, dv = mac.get("quotes", {}), mac.get("fred", {}), mac.get("derived", {})
    drivers = {k: {"label": v.get("label"), "last": r1(v.get("last"), 3), "change_1d": r1(v.get("d1"), 3),
                   "change_1m": r1(v.get("m1"), 3), "unit": "percentage points" if v.get("is_yield") else "%"}
               for k, v in q.items() if k in ("spx", "ndx", "nifty", "bnf", "vix", "ivix", "us10y", "in10y", "usdinr",
                                              "brent", "dxy", "gold", "silver", "copper", "btc", "eth")}
    walcl = fr.get("WALCL", {})
    data = {
        "date_ist": datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M IST"),
        "market_prices": drivers,
        "fed_and_inflation": {"fed_balance_sheet_trillion_usd": dv.get("walcl_tn"), "fed_balance_sheet_3m_change_pct": dv.get("walcl_3m_pct"),
                              "us_cpi_yoy_pct": dv.get("cpi_yoy"), "us_cpi_yoy_3m_ago": dv.get("cpi_yoy_3m_ago"),
                              "us_core_pce_yoy_pct": dv.get("core_pce_yoy"), "us_2y_minus_fed_funds_pp": dv.get("two_minus_ff"),
                              "us_real_10y_pct": dv.get("real10"), "fed_funds_upper_pct": dv.get("fed_upper"),
                              "fed_balance_sheet_latest": walcl.get("date")},
        "risk_scores_minus100_to_100": {"global": mac.get("global", {}).get("score"), "india": mac.get("india", {}).get("score")},
        "fii_5_sessions_crore": (mac.get("fii") or {}).get("sum5"),
        "calendar": mac.get("calendar", [])[:4],
        "rule_based_notes": [x["text"] for x in mac.get("interpret", [])],
        "asset_class_scores_minus100_to_100": {a["key"]: {"score": round((a["score"] - 50) * 2), "stance": a["stance"],
                                                          "momentum_0_100": a["mom"], "macro_fit_0_100": a["fit"],
                                                          "return_1m_inr_pct": a.get("r1m"), "return_3m_inr_pct": a.get("r3m"),
                                                          "money_flow": a.get("flow")}
                                               for a in fl.get("assets", []) if a["key"] != "fd"},
        "euphoria_0_100": {k: {"score": v.get("score"), "level": v.get("level"), "alert": (v.get("alert") or {}).get("title")}
                           for k, v in (eu.get("assets") or {}).items()},
        "crypto_market": {k: (cr.get("market") or {}).get(k) for k in ("btc_dom", "altseason", "mcap_chg24")}
        | {"fear_greed": ((cr.get("market") or {}).get("fng") or {}).get("value")},
        "us_breadth_pct_above_200d": (us.get("breadth") or {}).get("above200"),
        "us_sentiment_0_100": (us.get("sentiment") or {}).get("score"),
    }
    heads = []
    for i, it in enumerate((nw.get("items") or [])[:140]):
        heads.append({"id": i, "title": it["title"][:180], "source": it.get("source"), "hours_ago": it.get("age_h"),
                      "tags": it.get("tags", [])})
    ideas = []
    for tab, d in (("crypto", cr), ("commodities", cm), ("us", us)):
        for view, v in (d.get("views") or {}).items():
            for x in v.get("ideas", [])[:6]:
                ideas.append({"id": f"{tab}|{view}|{x['symbol']}|{x['side']}|{x['setup']}", "tab": tab, "view": view,
                              "symbol": x["symbol"], "name": x.get("name"), "side": x["side"], "setup": x["setup_name"],
                              "score_0_100": x["score"], "entry": x["entry"], "stop": x["stop"], "target": x["target"],
                              "risk_pct": x["risk_pct"], "trend": x.get("trend"), "rsi": x.get("rsi"),
                              "reasons": x.get("reasons"), "warnings": x.get("warns"), "sector": x.get("sector")})
    ideas.sort(key=lambda x: -x["score_0_100"])
    return {"data": data, "headlines": heads, "ideas": ideas[:20]}


SYSTEM = """You are a careful macro and markets analyst writing for one Indian retail investor and trader who
holds Indian equity, US equity, US bonds, bank FDs, gold, silver and crypto. Write plain, simple English.
Rules:
- Use ONLY the numbers in the JSON you are given. Never invent prices, levels, dates or statistics. If you mention
  a number, copy it exactly as given (you may round to 1 decimal). Prefer words over numbers when unsure.
- No web knowledge of events after the data: do not claim news, causes or events that are not in the headlines list
  or the data (e.g. do not say "on strong earnings" unless a headline says so). "watch" items must come from the
  calendar, the rule-based notes or the headlines - never add events (expiries, data releases) that are not given.
- Be balanced: give both what supports a view and what could go wrong. No hype, no certainty.
- This is personal analysis, not advice: never tell the reader to buy or sell everything; talk about tilts, sizing,
  patience, stops.
- Reply with JSON only, exactly in the schema requested."""

SCHEMA = """Return JSON:
{
 "brief": {
   "headline": "one sentence: the most important thing today",
   "summary": "3-5 sentences: what changed and why it matters",
   "assets": {"us_eq": {"view": "Bullish|Neutral|Bearish", "why": "1-2 sentences"}, "in_eq": {...}, "us_bond": {...},
              "gold": {...}, "silver": {...}, "crypto": {...}},
   "risks": ["up to 4 short risks to watch"],
   "watch": ["up to 4 things/events to watch next, from the calendar or data"]
 },
 "news": {
   "assets": {"us_eq": {"tone": -1.0 to 1.0, "label": "Positive|Mixed|Negative|Quiet", "hype": true/false,
                        "why": "1 sentence", "headline_ids": [ids of the 1-3 most important headlines]},
              "in_eq": {...}, "us_bond": {...}, "gold": {...}, "silver": {...}, "copper": {...}, "crypto": {...}, "fed": {...}},
   "hype_note": "1 sentence: is any asset's news flow one-sided / euphoric / panicky? say which, or 'none'"
 },
 "ideas": [{"id": "copy the idea id", "verdict": "Supports|Mixed|Caution", "supports": "1 sentence",
            "risks": "1 sentence"}]
}
"hype": true only when headlines about that asset are overwhelmingly one-sided and excited (crowd euphoria or panic).
Give an "ideas" entry for every idea provided (empty list if none)."""


# ---------------------------------------------------------------- number check
NUM = re.compile(r"(?<![\w.])[-+−]?\d[\d,]*(?:\.\d+)?")


def allowed_numbers(obj) -> set[float]:
    out = set()

    def walk(o):
        if isinstance(o, bool) or o is None:
            return
        if isinstance(o, (int, float)):
            for v in (o, abs(o)):
                out.update({round(v, 0), round(v, 1), round(v, 2), round(v, 3)})
                out.update({round(v * 100, 0), round(v * 100, 1)})        # pp -> bp
        elif isinstance(o, str):
            for m in NUM.findall(o):
                try:
                    walk(float(m.replace(",", "").replace("−", "-")))
                except ValueError:
                    pass
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(obj)
    return out


def ok_number(tok: str, allowed: set[float]) -> bool:
    v = float(tok.replace(",", "").replace("−", "-").lstrip("+"))
    if abs(v) <= 12 and v == int(v):          # small whole numbers: counts like "3 risks", "2 sessions"
        return True
    if 1990 <= v <= 2035:                    # years
        return True
    return any(abs(abs(v) - a) <= max(0.051, abs(a) * 0.002) for a in allowed)


def clean_text(text: str, allowed: set[float], removed: list[str]) -> str:
    if not isinstance(text, str):
        return text
    keep = []
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        bad = [t for t in NUM.findall(sent) if not ok_number(t, allowed)]
        if bad:
            removed.append(sent)
        else:
            keep.append(sent)
    return " ".join(keep)


def scrub(o, allowed, removed):
    if isinstance(o, str):
        return clean_text(o, allowed, removed)
    if isinstance(o, list):
        return [x for x in (scrub(v, allowed, removed) for v in o) if x not in ("", None)]
    if isinstance(o, dict):
        return {k: (v if k in ("id", "headline_ids", "tone", "hype", "view", "label", "verdict") else scrub(v, allowed, removed))
                for k, v in o.items()}
    return o


# ---------------------------------------------------------------- job
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    force = a.force or os.environ.get("FORCE") == "true"
    db = store.Local() if a.dry else store.connect()
    old = get_doc(db, "gm_ai") or {}
    if not force and recently({"ai": {"at": old.get("updated")}}, "ai", 180):
        print("AI view already made in the last 3 hours: skipping")
        return
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    out = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if not key:
        out["error"] = "GEMINI_API_KEY secret is not set (see README)"
        db.put_doc("gm_ai", {**old, **out})
        print(out["error"])
        return
    docs = {k: get_doc(db, k) for k in ("gm_macro", "gm_flows", "gm_euphoria", "gm_news", "gm_crypto", "gm_commod", "gm_us")}
    inp = build_input(docs)
    prompt = SCHEMA + "\n\nDATA:\n" + json.dumps(inp, ensure_ascii=False, separators=(",", ":"))
    try:
        res, model = gemini(key, pick_model(key), prompt, SYSTEM)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"Gemini did not answer: {e}"
        # keep the old 'updated' time so the next scheduled run tries again instead of skipping for 3 hours
        db.put_doc("gm_ai", {**old, "error": out["error"], "error_at": out["updated"], "stale": True})
        print(out["error"])
        errs = [x for x in str(e).split(" | ") if "HTTP 404" not in x]
        if errs and all(BUSY in x for x in errs):
            # Google-side capacity problem only: keep the last good view and let the next run retry,
            # without a "Run failed" email
            print("::warning::Gemini busy (503/429) on every model; last good AI view kept, next run will retry")
            return
        raise SystemExit(1)
    removed: list[str] = []
    allowed = allowed_numbers(inp)
    res = scrub(res, allowed, removed)
    removed = list(dict.fromkeys(removed))
    heads = {h["id"]: h for h in inp["headlines"]}
    items = (docs.get("gm_news") or {}).get("items") or []
    for k, v in ((res.get("news") or {}).get("assets") or {}).items():
        v["headlines"] = [{"title": items[i]["title"], "link": items[i].get("link"), "source": items[i].get("source")}
                          for i in (v.get("headline_ids") or []) if isinstance(i, int) and i in heads and i < len(items)][:3]
    out.update({"model": model, "brief": res.get("brief"), "news": res.get("news"),
                "ideas": {x.get("id"): x for x in (res.get("ideas") or []) if x.get("id")},
                "removed": removed, "inputs": {"headlines": len(inp["headlines"]), "ideas": len(inp["ideas"])}})
    db.put_doc("gm_ai", out)
    print(f"AI view saved with {model}; {len(out['ideas'])} idea comments; {len(removed)} sentence(s) dropped for unverified numbers")
    for s in removed:
        print("  dropped:", s)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(f"## AI view\nModel {model}. Headline: {(out.get('brief') or {}).get('headline')}\n\n"
                    f"Dropped {len(removed)} sentence(s) with numbers not in the data.\n")


if __name__ == "__main__":
    main()


__all__ = ["main", "sources"]
