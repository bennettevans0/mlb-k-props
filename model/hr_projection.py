"""
Anytime-HR projection math (Phase 1).

Steps:
  1. Batter per-PA HR rate, regressed toward league mean (HR is rare and
     stabilizes slowly, so shrinkage matters a lot for honesty).
  2. Multiply by the opposing pitcher's HR-vulnerability factor (also shrunk)
     and the park factor.
  3. Convert to a game probability of >= 1 HR over the expected plate appearances.

Handedness platoon splits, weather/wind, and Statcast (barrel%, HR/FB) are
Phase 2 -- they need data we don't pull in v1.
"""

# Regression-to-the-mean strengths (in PA / IP of "league-average" prior).
BATTER_PA_PRIOR = 170.0     # HR/PA stabilizes around here
PITCHER_IP_PRIOR = 50.0

# Sanity clamps.
PITCHER_FACTOR_MIN = 0.60
PITCHER_FACTOR_MAX = 1.60
P_PER_PA_MIN = 0.003
P_PER_PA_MAX = 0.120


def batter_hr_rate(hr: float, pa: float, league_hr_per_pa: float) -> float:
    """Batter HR/PA shrunk toward the league mean."""
    return (hr + BATTER_PA_PRIOR * league_hr_per_pa) / (pa + BATTER_PA_PRIOR)


def pitcher_hr_factor(hr: float, ip: float, league_hr_per9: float) -> float:
    """Opposing pitcher's HR-vulnerability as a multiplier vs league (shrunk)."""
    if league_hr_per9 <= 0:
        return 1.0
    league_hr_per_ip = league_hr_per9 / 9.0
    shrunk_per_ip = (hr + PITCHER_IP_PRIOR * league_hr_per_ip) / (ip + PITCHER_IP_PRIOR)
    factor = shrunk_per_ip / league_hr_per_ip
    return max(PITCHER_FACTOR_MIN, min(PITCHER_FACTOR_MAX, factor))


def adjusted_p_per_pa(
    batter_hr: float,
    batter_pa: float,
    league_hr_per_pa: float,
    pitcher_hr: float | None,
    pitcher_ip: float | None,
    league_hr_per9: float,
    park_factor: float,
) -> tuple[float, float]:
    """
    Return (p_adjusted_per_pa, pitcher_factor_used).
    pitcher_* may be None when the opposing starter is unknown -> factor 1.0.
    """
    p_bat = batter_hr_rate(batter_hr, batter_pa, league_hr_per_pa)

    if pitcher_ip and pitcher_ip > 0:
        pf = pitcher_hr_factor(pitcher_hr or 0.0, pitcher_ip, league_hr_per9)
    else:
        pf = 1.0

    p_adj = p_bat * pf * park_factor
    p_adj = max(P_PER_PA_MIN, min(P_PER_PA_MAX, p_adj))
    return p_adj, pf


def prob_at_least_one_hr(p_per_pa: float, expected_pa: float) -> float:
    """P(>=1 HR) = 1 - (1 - p)^PA."""
    p_per_pa = max(0.0, min(1.0, p_per_pa))
    return 1.0 - (1.0 - p_per_pa) ** expected_pa
