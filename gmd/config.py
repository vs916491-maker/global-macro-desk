"""Global Macro Desk - every rule threshold and list in one place.

All numbers are untested starting values (Nov 2026). Judge them in the Track Record
before trusting them, and change them here (the site's Readme tab explains them in words).
"""

TZ = "Asia/Kolkata"

# ---------------------------------------------------------------- market symbols (Yahoo)
MACRO = {
    # key: (yahoo symbol, label, unit)
    "spx":    ("^GSPC", "S&P 500", "pts"),
    "ndx":    ("^NDX", "Nasdaq 100", "pts"),
    "dji":    ("^DJI", "Dow Jones", "pts"),
    "rut":    ("^RUT", "Russell 2000", "pts"),
    "nifty":  ("^NSEI", "Nifty 50", "pts"),
    "bnf":    ("^NSEBANK", "Bank Nifty", "pts"),
    "vix":    ("^VIX", "US VIX", "pts"),
    "ivix":   ("^INDIAVIX", "India VIX", "pts"),
    "dxy":    ("DX-Y.NYB", "Dollar index (DXY)", "pts"),
    "usdinr": ("INR=X", "USD-INR", "₹"),
    "us10y":  ("^TNX", "US 10Y yield", "%"),
    "us5y":   ("^FVX", "US 5Y yield", "%"),
    "us30y":  ("^TYX", "US 30Y yield", "%"),
    "us3m":   ("^IRX", "US 3M bill", "%"),
    "us2y":   ("2YY=F", "US 2Y yield (futures)", "%"),
    "hyg":    ("HYG", "High-yield bond ETF (HYG)", "$"),
    "ief":    ("IEF", "7-10Y Treasury ETF (IEF)", "$"),
    "brent":  ("BZ=F", "Brent crude", "$"),
    "wti":    ("CL=F", "WTI crude", "$"),
    "gold":   ("GC=F", "Gold (COMEX)", "$/oz"),
    "silver": ("SI=F", "Silver (COMEX)", "$/oz"),
    "copper": ("HG=F", "Copper (COMEX)", "$/lb"),
    "btc":    ("BTC-USD", "Bitcoin", "$"),
    "eth":    ("ETH-USD", "Ether", "$"),
    "tlt":    ("TLT", "US 20Y+ bond ETF (TLT)", "$"),
}

# FRED series (free CSV, no key): id -> label
FRED = {
    "DGS10": "US 10Y yield", "DGS2": "US 2Y yield", "T10Y2Y": "10Y minus 2Y",
    "DFII10": "US 10Y real yield (TIPS)", "DFEDTARU": "Fed funds target (upper)",
    "DFF": "Fed funds effective", "BAMLH0A0HYM2": "US high-yield credit spread",
    "CPIAUCSL": "US CPI", "PCEPILFE": "US core PCE", "UNRATE": "US unemployment",
    "WALCL": "Fed balance sheet", "T10YIE": "10Y breakeven inflation",
    "INDIRLTLT01STM": "India 10Y yield (monthly, OECD)",
}

# India 10Y government bond yield: TradingView (daily, his choice 22 Nov 2026), FRED monthly as the backup
IN10Y_TV = "TVC:IN10Y"

# Central bank calendar (decision on the last day). Update each year.
FOMC = ["2026-12-09", "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09",
        "2027-07-28", "2027-09-15", "2027-11-17"]          # Oct 26-27 2027 = strategy only, no decision
RBI_MPC = ["2026-12-04", "2027-02-05"]

# ---------------------------------------------------------------- risk scores (-100..+100)
# weights of each part; parts with no data are left out and the rest re-weighted
GLOBAL_W = {"vix": 20, "credit": 15, "spx": 15, "dxy": 15, "yield": 10, "curve": 5, "cu_au": 10, "news": 10}
INDIA_W = {"nifty": 25, "ivix": 15, "inr": 15, "crude": 15, "fii": 15, "news": 15}
VIX_ZONES = [(14, 1.0), (18, 0.5), (22, 0.0), (28, -0.5), (999, -1.0)]
IVIX_ZONES = [(12, 1.0), (15, 0.5), (18, 0.0), (22, -0.5), (999, -1.0)]
DXY_FULL_PCT = 2.5          # 1-month DXY move that scores the full -1/+1
YIELD_FULL_BP = 40          # 1-month 10Y move (bp)
CREDIT_FULL_PP = 0.5        # 1-month HY spread move (percentage points)
CREDIT_PROXY_FULL_PCT = 3.0 # stand-in when FRED is down: 1-month HYG/IEF move
INR_FULL_PCT = 1.5          # 1-month USD-INR move
CRUDE_FULL_PCT = 12         # 1-month Brent move
CU_AU_FULL_PCT = 8          # 1-month copper/gold ratio move
FII_FULL_CR = 15000         # 5-session FII cash net (₹ crore)
REGIME_ZONES = [(-60, "Strong risk-off"), (-20, "Risk-off"), (20, "Neutral"), (60, "Risk-on"), (101, "Strong risk-on")]

# ---------------------------------------------------------------- money flow (Indian investor, INR terms)
FD_RATE = 6.5               # bank FD rate % a year (1-year, large bank) - edit when banks change rates
INDIA_CPI = 4.0             # India CPI % (edit after each MOSPI release)
ASSETS = {
    # key: (label, price symbol, flow symbol (volume), in USD?)
    "in_eq":  ("Indian equity", "^NSEI", "NIFTYBEES.NS", False),
    "us_eq":  ("US equity", "SPY", "SPY", True),
    "us_bond": ("US bonds", "TLT", "TLT", True),
    "fd":     ("Bank fixed deposits", None, None, False),
    "gold":   ("Gold", "GC=F", "GLD", True),
    "silver": ("Silver", "SI=F", "SLV", True),
    "crypto": ("Crypto", "BTC-USD", "BTC-USD", True),
}
BASE_MIX = {"in_eq": 35, "us_eq": 15, "us_bond": 5, "fd": 20, "gold": 12, "silver": 5, "crypto": 8}
TILT_MAX = 0.5              # tilt at most +-50% of the base weight
FLOW_MOM_W = 0.55           # asset score = 55% momentum/flow + 45% macro fit

# ---------------------------------------------------------------- crypto
CRYPTO_TOP = 50
STABLES = {"usdt", "usdc", "dai", "fdusd", "tusd", "usde", "usds", "pyusd", "usdd", "busd", "frax", "usd1",
           "rlusd", "susde", "usdtb", "bfusd", "usdf", "gho", "lusd", "eurc", "usdg", "usd0", "buidl", "usyc"}
SKIP_COIN_WORDS = ("wrapped", "staked", "bridged", "liquid staking", " restaked", "wbtc", "steth", "tokenized",
                   "heloc", "treasur", "gold", "euro", " fund", "yield", "usd")
SKIP_COINS = {"xaut", "paxg", "usdy", "ousg", "figr_heloc", "eursafo", "syrupusdc", "buidl", "usyc"}
MIN_COIN_VOL = 1.0          # coins whose daily moves average under 1% (stable-like assets) are left out
YAHOO_COIN = {"sui": "SUI20947-USD", "uni": "UNI7083-USD", "ton": "TON11419-USD", "apt": "APT21794-USD",
              "pepe": "PEPE24478-USD", "hype": "HYPE32196-USD", "tao": "TAO22974-USD", "arb": "ARB11841-USD",
              "op": "OP-USD", "near": "NEAR-USD", "icp": "ICP-USD", "ena": "ENA-USD", "wld": "WLD-USD",
              "mnt": "MNT27075-USD", "pol": "POL28321-USD", "kas": "KAS-USD", "bgb": "BGB-USD"}

# ---------------------------------------------------------------- commodities (COMEX, USD)
COMMODS = {"gold": ("GC=F", "Gold", "COMEX:GC1!"), "silver": ("SI=F", "Silver", "COMEX:SI1!"),
           "copper": ("HG=F", "Copper", "COMEX:HG1!")}

# ---------------------------------------------------------------- US equity
US_SECTORS = {"XLK": "Technology", "XLF": "Financials", "XLE": "Energy", "XLV": "Health Care",
              "XLY": "Consumer Discretionary", "XLP": "Consumer Staples", "XLI": "Industrials",
              "XLB": "Materials", "XLU": "Utilities", "XLRE": "Real Estate", "XLC": "Communication Services"}
US_STYLE = {"QQQ": "Nasdaq 100 (growth)", "IWM": "Small caps", "RSP": "Equal-weight S&P", "DIA": "Dow 30"}
US_MIN_PRICE = 10
US_MIN_DOLLAR_VOL = 50e6    # 20-day average $ volume
US_TOP_N = 10
US_W = {"spx": 20, "ndx": 10, "b50": 15, "b200": 10, "nhnl": 10, "vix": 15, "credit": 10, "news": 10}
US_FALLBACK = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "BRK-B", "JPM", "LLY", "V",
               "UNH", "XOM", "MA", "COST", "HD", "PG", "JNJ", "NFLX", "ABBV", "BAC", "CRM", "ORCL", "AMD",
               "KO", "CVX", "MRK", "PEP", "ADBE", "WMT", "TMO", "LIN", "MCD", "CSCO", "ACN", "ABT", "WFC",
               "DIS", "INTU", "QCOM", "IBM", "GE", "CAT", "TXN", "AMGN", "NOW", "PM", "GS", "ISRG", "UBER",
               "SPGI", "BKNG", "RTX", "HON", "PLTR", "AMAT", "MU", "LRCX", "PANW", "ANET", "KLAC", "CEG"]

# ---------------------------------------------------------------- setups (both views)
# Swing: 4-hour candles (crypto, commodities) or daily (US); Positional: daily candles + weekly trend.
VIEWS = {
    "swing": {"pb_ema": 20, "base_min": 8, "base_max": 30, "base_atr": 3.0, "target_r": 2.0, "max_days": 14,
              "stop_max_atr": 3.0, "lookback_hi": 20},
    "positional": {"pb_ema": 50, "base_min": 15, "base_max": 60, "base_atr": 4.5, "target_r": 3.0, "max_days": 90,
                   "stop_max_atr": 3.5, "lookback_hi": 50},
}
BASE_DRIFT = 0.5            # base: first-to-last close move <= 50% of the base range (sideways)
BO_BODY = 0.5               # breakout candle body >= 50% of its range
BO_CLEAR_ATR = 0.1          # close beyond the base by >= 0.1 ATR
BO_VOL = 1.3                # breakout volume >= 1.3x the 20-candle average (where volume exists)
PB_ZONE_ATR = 0.5           # pullback low within 0.5 ATR of the pullback EMA
PB_RSI = (38, 68)           # RSI at the pullback signal (long; short is the mirror)
ML_NEAR_HIGH = 0.05         # momentum leader: within 5% of the 1-year high
STOP_BUFFER_ATR = 0.2
SCORE_W = {"trend": 25, "momentum": 20, "setup": 25, "volume": 10, "macro": 20}
MIN_SCORE = 50              # ideas below this are listed as "watch" only, not logged
