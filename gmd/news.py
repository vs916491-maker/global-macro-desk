"""Financial news from free RSS feeds, tagged by asset and scored with simple word rules.

Score per headline: -1 (bad for risk / for that asset) .. +1 (good). It is crude keyword
scoring, not understanding: "gold rises" is +1 for gold; "yields jump" is negative for
stocks; "war fears" is negative for risk but positive for gold and bonds."""

from __future__ import annotations

import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import sources

GN = "https://news.google.com/rss/search?hl=en-US&gl=US&ceid=US:en&q="
GNI = "https://news.google.com/rss/search?hl=en-IN&gl=IN&ceid=IN:en&q="
FEEDS = [
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("CNBC Economy", "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
    ("CNBC Finance", "https://www.cnbc.com/id/10000664/device/rss/rss.html"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("MarketWatch Pulse", "https://feeds.content.dowjones.io/public/rss/mw_marketpulse"),
    ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("Economic Times", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("Livemint", "https://www.livemint.com/rss/markets"),
    ("Moneycontrol", "https://www.moneycontrol.com/rss/marketreports.xml"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Google News: gold", GN + "gold+price+when:2d"),
    ("Google News: silver", GN + "silver+price+when:2d"),
    ("Google News: copper", GN + "copper+price+when:3d"),
    ("Google News: Fed", GN + "Federal+Reserve+rates+when:2d"),
    ("Google News: Wall Street", GN + "Wall+Street+stocks+when:1d"),
    ("Google News: India markets", GNI + "Sensex+Nifty+when:1d"),
]

TAGS = {
    "fed": ["fed", "fomc", "powell", "warsh", "federal reserve", "rate cut", "rate cuts", "rate hike", "fed funds",
            "central bank", "ecb", "boj", "monetary policy"],
    "us_eq": ["s&p", "s&p 500", "nasdaq", "dow", "wall street", "us stocks", "u.s. stocks", "stocks", "equities",
              "nvidia", "apple", "microsoft", "tesla", "earnings", "magnificent seven", "russell"],
    "in_eq": ["nifty", "sensex", "dalal street", "indian stocks", "indian shares", "rbi", "sebi", "rupee", "fii",
              "fpi", "fiis", "fpis", "india", "indian", "bank nifty", "mpc"],
    "bonds": ["treasury", "treasuries", "bond", "bonds", "yield", "yields", "10-year", "2-year", "gilt", "gilts"],
    "dollar": ["dollar", "dxy", "greenback", "currency", "currencies", "yen", "euro", "forex"],
    "gold": ["gold", "bullion", "precious metals", "precious metal"],
    "silver": ["silver"],
    "copper": ["copper", "base metals", "industrial metals"],
    "oil": ["oil", "crude", "opec", "brent", "wti"],
    "crypto": ["bitcoin", "btc", "crypto", "cryptocurrency", "ether", "ethereum", "solana", "xrp", "stablecoin",
               "stablecoins", "altcoin", "altcoins", "binance", "coinbase", "defi", "token", "tokens", "memecoin"],
    "macro": ["inflation", "cpi", "pce", "jobs", "payrolls", "unemployment", "gdp", "recession", "tariff", "tariffs",
              "trade war", "war", "geopolitical", "shutdown", "deficit", "economy", "pmi", "retail sales"],
}
TAG_NAME = {"fed": "Fed / rates", "us_eq": "US equity", "in_eq": "India", "bonds": "Bonds", "dollar": "Dollar / FX",
            "gold": "Gold", "silver": "Silver", "copper": "Copper", "oil": "Oil", "crypto": "Crypto", "macro": "Macro"}

UP = set("rally rallies rallied surge surges surged soar soars soared jump jumps jumped gain gains gained rise rises "
         "rose risen climb climbs climbed rebound rebounds rebounded higher advance advances advanced spike spikes "
         "spiked boost boosts boosted extends recovers recovered".split()) | {"record high", "all-time high", "hits record"}
DOWN = set("fall falls fell drop drops dropped slide slides slid slump slumps slumped plunge plunges plunged "
           "tumble tumbles tumbled sink sinks sank crash crashes crashed lower decline declines declined selloff "
           "sell-off rout loses retreat retreats retreated dips dipped slips slipped sheds shed erases wipes "
           "plummet plummets plummeted".split())
GOOD = set("beat beats upbeat optimism optimistic deal agreement ceasefire truce stimulus easing dovish upgrade "
           "upgrades bullish inflows approval approves approved cools cooling resilient strong robust breakthrough "
           "buyback buybacks".split()) | {"rate cut", "rate cuts", "soft landing", "eases tensions"}
BAD = set("miss misses missed recession fears fear worries worry concern concerns warning warns crisis war attack "
          "attacks sanctions tariff tariffs default defaults layoffs downgrade downgrades bearish outflows hawkish "
          "hike hikes shutdown probe ban hack hacked bankruptcy turmoil uncertainty slowdown contraction stagflation "
          "escalation escalates invasion liquidation liquidations exploit sticky".split()) | {"rate hike", "rate hikes"}
NEG = {"no", "not", "without", "unlikely", "rules out", "hold off"}

# who is moving: subject word -> (asset key, sign for risk tone)
SUBJECT = {
    "gold": ("gold", 0), "bullion": ("gold", 0), "silver": ("silver", 0), "copper": ("copper", 1),
    "bitcoin": ("crypto", 1), "btc": ("crypto", 1), "crypto": ("crypto", 1), "ether": ("crypto", 1),
    "ethereum": ("crypto", 1), "solana": ("crypto", 1), "xrp": ("crypto", 1), "tokens": ("crypto", 1),
    "nifty": ("in_eq", 1), "sensex": ("in_eq", 1), "rupee": ("inr", 1),
    "stocks": ("eq", 1), "shares": ("eq", 1), "s&p": ("us_eq", 1), "nasdaq": ("us_eq", 1), "dow": ("us_eq", 1),
    "equities": ("eq", 1), "futures": ("eq", 1), "market": ("eq", 1), "markets": ("eq", 1),
    "treasuries": ("bonds", 0), "bonds": ("bonds", 0), "yields": ("bonds", -1), "yield": ("bonds", -1),
    "dollar": ("dollar", -1), "greenback": ("dollar", -1), "oil": ("oil", -1), "crude": ("oil", -1),
    "brent": ("oil", -1), "inflation": ("macro", -1), "prices": ("macro", -1), "vix": ("macro", -1),
    "volatility": ("macro", -1), "unemployment": ("macro", -1), "jobless": ("macro", -1),
}
SAFE = {"gold", "silver", "bonds"}          # risk-off news helps these


def _tokens(t):
    return re.findall(r"[a-z][a-z&'\-\.]*|\d+(?:\.\d+)?%?", t.lower())


def _has(text, words):
    return [w for w in words if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", text)]


def score_headline(title: str, desc: str = "") -> dict:
    text = f"{title}".lower()
    tags = [k for k, ws in TAGS.items() if _has(text + " " + desc.lower()[:160], ws)]
    if "in_eq" in tags and "us_eq" in tags and not _has(text, ["s&p", "nasdaq", "dow", "wall street", "us stocks",
                                                                "u.s. stocks", "nvidia", "apple", "microsoft", "tesla"]):
        tags.remove("us_eq")
    tok = _tokens(text)
    risk, asset = 0.0, {}
    # 1) moves with a subject: "gold rises", "yields jump"
    for i, w in enumerate(tok):
        two = " ".join(tok[i:i + 2])
        mv = 1 if (w in UP or two in UP) else -1 if w in DOWN else 0
        if not mv:
            continue
        subj = None
        for j in range(i - 1, max(-1, i - 6), -1):
            if tok[j] in SUBJECT:
                subj = SUBJECT[tok[j]]
                break
        if not subj:
            risk += 0.5 * mv
            continue
        key, rsign = subj
        if key == "eq":
            key = "in_eq" if "in_eq" in tags and "us_eq" not in tags else "us_eq"
        if key == "bonds" and rsign == -1:            # yields up = bond prices down
            asset["bonds"] = asset.get("bonds", 0) - mv
        elif key == "inr":
            asset["in_eq"] = asset.get("in_eq", 0) + 0.5 * mv
        elif key not in ("macro", "dollar", "oil"):
            asset[key] = asset.get(key, 0) + mv
        if key == "dollar":
            asset["dollar"] = asset.get("dollar", 0) + mv
        if key == "oil":
            asset["oil"] = asset.get("oil", 0) + mv
        risk += mv * rsign
    # 2) good / bad words (with simple negation)
    for words, sgn in ((GOOD, 1), (BAD, -1)):
        for w in _has(text, words):
            pos = text.find(w)
            before = text[max(0, pos - 14):pos]
            s = -sgn if any(n in before.split() or n in before for n in NEG) else sgn
            risk += 0.8 * s
            for k in tags:
                if k in ("us_eq", "in_eq", "crypto", "copper"):
                    asset[k] = asset.get(k, 0) + 0.6 * s
                elif k in SAFE:
                    asset[k] = asset.get(k, 0) - 0.4 * s
    sq = lambda v: round(math.tanh(v / 1.5), 3)  # noqa: E731
    return {"tags": tags, "risk": sq(risk), "asset": {k: sq(v) for k, v in asset.items() if v}}


def collect() -> dict:
    with ThreadPoolExecutor(8) as ex:
        lists = list(ex.map(lambda f: sources.rss(f[1], f[0]), FEEDS))
    seen, items = set(), []
    now = datetime.now(timezone.utc)
    for lst in lists:
        for it in lst:
            key = re.sub(r"[^a-z0-9]", "", it["title"].lower())[:70]
            if key in seen:
                continue
            seen.add(key)
            # Google News titles end with " - Source"
            if it["source"].startswith("Google News") and " - " in it["title"]:
                t, _, src = it["title"].rpartition(" - ")
                it["title"], it["source"] = t, src
            age_h = (now - datetime.fromisoformat(it["ts"])).total_seconds() / 3600
            if age_h > 96 or age_h < -2:
                continue
            it.update(score_headline(it["title"], it.get("desc", "")))
            it["age_h"] = round(age_h, 1)
            items.append(it)
    items.sort(key=lambda x: x["ts"], reverse=True)
    return summarize(items)


def summarize(items: list[dict]) -> dict:
    """Weighted sentiment (-100..+100) overall and per asset; recent news counts more."""
    def w(it):
        return 1.0 if it["age_h"] <= 24 else 0.5 if it["age_h"] <= 48 else 0.25
    out = {}
    groups = {"risk": items, **{k: [i for i in items if k in i["tags"] or k in i["asset"]] for k in TAGS}}
    for k, lst in groups.items():
        num = den = 0.0
        n_pos = n_neg = 0
        for it in lst:
            v = it["risk"] if k in ("risk", "fed", "macro", "bonds", "dollar", "oil") else it["asset"].get(k, it["risk"] if k not in SAFE else 0)
            if k in ("bonds",):
                v = it["asset"].get("bonds", 0)
            num += w(it) * v
            den += w(it)
            n_pos += v > 0.15
            n_neg += v < -0.15
        # shrink towards 0 when there are few headlines
        out[k] = {"score": round(100 * num / (den + 3), 1) if den else None, "n": len(lst), "pos": n_pos, "neg": n_neg}
    return {"items": items[:250], "sentiment": out, "feeds": len(FEEDS), "count": len(items),
            "tag_names": TAG_NAME}
