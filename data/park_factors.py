"""
Hardcoded home-run park factors, keyed by the HOME team's abbreviation
(config-style abbreviations, e.g. CHW/KCR/SDP/SFG/TBR/WSN).

1.00 = neutral. >1 inflates HR, <1 suppresses. These are standard published
HR park factors (approximate, multi-year). v1 keeps them hardcoded; refine with
current-season values later. Park = the home team's stadium for the game.
"""

HR_PARK_FACTORS: dict[str, float] = {
    "ARI": 1.05,
    "ATL": 1.03,
    "BAL": 1.10,
    "BOS": 1.06,
    "CHC": 1.04,
    "CHW": 1.04,
    "CIN": 1.18,
    "CLE": 0.99,
    "COL": 1.18,
    "DET": 0.95,
    "HOU": 1.04,
    "KCR": 0.97,
    "LAA": 1.01,
    "LAD": 1.02,
    "MIA": 0.92,
    "MIL": 1.07,
    "MIN": 1.01,
    "NYM": 0.97,
    "NYY": 1.12,
    "OAK": 0.90,
    "PHI": 1.07,
    "PIT": 0.92,
    "SDP": 0.95,
    "SEA": 0.93,
    "SFG": 0.90,
    "STL": 0.97,
    "TBR": 0.97,
    "TEX": 1.05,
    "TOR": 1.03,
    "WSN": 1.01,
}

# Keep adjustments sane even if a park is missing or a value is extreme.
PARK_FACTOR_MIN = 0.85
PARK_FACTOR_MAX = 1.20


def park_factor(home_abbrev: str) -> float:
    """HR park factor for a game played in `home_abbrev`'s stadium (1.0 if unknown)."""
    pf = HR_PARK_FACTORS.get((home_abbrev or "").upper(), 1.0)
    return max(PARK_FACTOR_MIN, min(PARK_FACTOR_MAX, pf))
