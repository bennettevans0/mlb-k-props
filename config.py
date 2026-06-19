import os

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
EDGE_THRESHOLD = 0.05
MIN_IP_FILTER = 25

# --- Anytime HR model (separate from the K model) ---
# Minimum model-vs-market edge for an anytime-HR pick. Kept the same as the K
# threshold to start. HR edges are noisier/smaller, so do NOT tune this until
# there is a meaningful sample of graded HR picks.
HR_EDGE_THRESHOLD = 0.05
# Default expected plate appearances for a starting-lineup batter (used when the
# batting-order spot isn't posted yet). Refined by lineup spot when available.
HR_DEFAULT_PA = 4.2

# --- Kalshi (read-only price source for best-price line shopping) ---
# Market data is PUBLIC: no API key, no request signing needed for reading prices.
KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
KALSHI_K_SERIES = "KXMLBKS"     # per-game pitcher strikeout markets
KALSHI_HR_SERIES = "KXMLBHR"    # per-game batter home-run markets
# Liquidity guard: a Kalshi price is only eligible to be "best" if the market is
# tradeable, deep enough, and tight enough that it could actually be filled.
KALSHI_MIN_OPEN_INTEREST = 50      # contracts (open_interest, fp)
KALSHI_MAX_SPREAD_CENTS = 5        # max yes bid/ask spread, in cents
# Tie-break on equal implied cost: prefer FanDuel/DraftKings (deeper liquidity).
KALSHI_TIEBREAK_PREFER_ODDSAPI = True
# Fees: add Kalshi's per-contract fee to its cost BEFORE comparing (apples-to-
# apples). Historical sports fee ~= 0.07 * p * (1 - p); set ENABLED=False to zero
# it out if the current schedule is free. Owner confirmed current trading is free.
KALSHI_FEE_ENABLED = False
KALSHI_FEE_COEF = 0.07

TEAM_NAME_TO_ABBREV = {
    "Arizona Diamondbacks": "ARI",
    "Atlanta Braves": "ATL",
    "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC",
    "Chicago White Sox": "CHW",
    "Cincinnati Reds": "CIN",
    "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL",
    "Detroit Tigers": "DET",
    "Houston Astros": "HOU",
    "Kansas City Royals": "KCR",
    "Los Angeles Angels": "LAA",
    "Los Angeles Dodgers": "LAD",
    "Miami Marlins": "MIA",
    "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN",
    "New York Mets": "NYM",
    "New York Yankees": "NYY",
    "Athletics": "OAK",
    "Oakland Athletics": "OAK",
    "Philadelphia Phillies": "PHI",
    "Pittsburgh Pirates": "PIT",
    "San Diego Padres": "SDP",
    "San Francisco Giants": "SFG",
    "Seattle Mariners": "SEA",
    "St. Louis Cardinals": "STL",
    "Tampa Bay Rays": "TBR",
    "Texas Rangers": "TEX",
    "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WSN",
}


# MLB Stats API team id -> abbreviation, using the SAME abbreviation style the K
# side already uses (CHW/KCR/SDP/SFG/TBR/WSN) so K and HR rows match on the site.
TEAM_ID_TO_ABBREV = {
    109: "ARI", 144: "ATL", 110: "BAL", 111: "BOS", 112: "CHC", 145: "CHW",
    113: "CIN", 114: "CLE", 115: "COL", 116: "DET", 117: "HOU", 118: "KCR",
    108: "LAA", 119: "LAD", 146: "MIA", 158: "MIL", 142: "MIN", 121: "NYM",
    147: "NYY", 133: "OAK", 143: "PHI", 134: "PIT", 135: "SDP", 137: "SFG",
    136: "SEA", 138: "STL", 139: "TBR", 140: "TEX", 141: "TOR", 120: "WSN",
}


ODDS_API_KEY    = os.environ.get("ODDS_API_KEY",       "")
GMAIL_USER      = os.environ.get("GMAIL_USER",         "bennettevans0@gmail.com")
GMAIL_PASSWORD  = os.environ.get("GMAIL_APP_PASSWORD", "")
GMAIL_TO        = os.environ.get("GMAIL_TO",           "bennettevans0@gmail.com")


def get_api_key() -> str:
    if not ODDS_API_KEY:
        raise RuntimeError(
            "ODDS_API_KEY is not set.\n"
            "Get a free key at https://the-odds-api.com"
        )
    return ODDS_API_KEY
