import os

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
EDGE_THRESHOLD = 0.05
MIN_IP_FILTER = 25

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


ODDS_API_KEY    = os.environ.get("ODDS_API_KEY",       "c87cc0c5b57c258cb6b099a85bb70372")
GMAIL_USER      = os.environ.get("GMAIL_USER",         "bennettevans0@gmail.com")
GMAIL_PASSWORD  = os.environ.get("GMAIL_APP_PASSWORD", "ptno rwle tdyb dtnx")
GMAIL_TO        = os.environ.get("GMAIL_TO",           "bennettevans0@gmail.com")


def get_api_key() -> str:
    if not ODDS_API_KEY:
        raise RuntimeError(
            "ODDS_API_KEY is not set.\n"
            "Get a free key at https://the-odds-api.com"
        )
    return ODDS_API_KEY
