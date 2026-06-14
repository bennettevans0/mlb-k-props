import pandas as pd
import scipy.stats

import config
from data import savant
from model.projection import project_ks


def american_to_prob(odds: int) -> float:
    if odds < 0:
        return abs(odds) / (abs(odds) + 100)
    return 100 / (odds + 100)


def remove_vig(over_prob: float, under_prob: float) -> tuple[float, float]:
    total = over_prob + under_prob
    return over_prob / total, under_prob / total


def model_prob_over(projected_ks: float, std_dev: float, line: float) -> float:
    return float(scipy.stats.norm.sf(line + 0.5, loc=projected_ks, scale=std_dev))


def _abbrev(full_name: str) -> str:
    return config.TEAM_NAME_TO_ABBREV.get(full_name, full_name.split()[-1])


def _match_team(bref_short: str, full_names: list[str]) -> str | None:
    """Match a BRef short team name (e.g. 'Cincinnati') to an Odds API full name."""
    low = bref_short.lower()
    for full in full_names:
        if low in full.lower():
            return full
    return None


def _find_team_k_rate(team_full_name: str, team_k_rates: dict[str, float], league_k_rate: float) -> float:
    """Look up team K rate by full name with fallback to league average."""
    if team_full_name in team_k_rates:
        return team_k_rates[team_full_name]
    low = team_full_name.lower()
    for key, rate in team_k_rates.items():
        if low in key.lower() or key.lower() in low:
            return rate
    return league_k_rate


def find_edges(
    props: list[dict],
    pitching_df: pd.DataFrame,
    team_k_rates: dict[str, float],
    league_k_rate: float,
    min_edge: float = config.EDGE_THRESHOLD,
) -> pd.DataFrame:
    rows = []

    for prop in props:
        pitcher_name = prop["pitcher"]
        line = prop["line"]
        over_odds = prop["over_odds"]
        under_odds = prop["under_odds"]
        home_full = prop.get("home_team", "")
        away_full = prop.get("away_team", "")

        stats = savant.lookup_pitcher(pitcher_name, pitching_df)
        if stats is None:
            print(f"[edge] Skipping {pitcher_name}: no stats found")
            continue

        if stats["k_per9"] == 0 or stats["ip"] < config.MIN_IP_FILTER:
            print(f"[edge] Skipping {pitcher_name}: insufficient IP ({stats['ip']:.1f})")
            continue

        # Resolve opponent: BRef team names are short (e.g. "Cincinnati")
        # Odds API uses full names (e.g. "Cincinnati Reds")
        bref_team = stats.get("team", "")
        pitcher_full = _match_team(bref_team, [home_full, away_full]) if bref_team else None

        if pitcher_full == home_full:
            opp_full = away_full
            opp_k_rate = _find_team_k_rate(away_full, team_k_rates, league_k_rate)
            opp_label = _abbrev(away_full)
        elif pitcher_full == away_full:
            opp_full = home_full
            opp_k_rate = _find_team_k_rate(home_full, team_k_rates, league_k_rate)
            opp_label = _abbrev(home_full)
        else:
            # Unknown side — use average of both teams' K rates
            r1 = _find_team_k_rate(home_full, team_k_rates, league_k_rate)
            r2 = _find_team_k_rate(away_full, team_k_rates, league_k_rate)
            opp_k_rate = (r1 + r2) / 2
            opp_label = f"{_abbrev(away_full)}/{_abbrev(home_full)}"

        recent_ip = savant.get_recent_ip(pitcher_name, pitching_df)
        proj_ks, std_dev = project_ks(stats["k_per9"], recent_ip, opp_k_rate, league_k_rate)

        if proj_ks == 0:
            continue

        raw_over = american_to_prob(over_odds)
        raw_under = american_to_prob(under_odds)
        nv_over, nv_under = remove_vig(raw_over, raw_under)

        mp_over = model_prob_over(proj_ks, std_dev, line)
        mp_under = 1 - mp_over

        over_edge = mp_over - nv_over
        under_edge = mp_under - nv_under

        if abs(over_edge) >= abs(under_edge):
            best_edge = over_edge
            side = "Over"
            odds = over_odds
            book = prop["over_book"]
        else:
            best_edge = under_edge
            side = "Under"
            odds = under_odds
            book = prop["under_book"]

        pitcher_team_label = _abbrev(pitcher_full) if pitcher_full else bref_team

        if abs(best_edge) >= min_edge:
            rows.append({
                "Pitcher": pitcher_name,
                "Team": pitcher_team_label,
                "Opp": opp_label,
                "Proj K": round(proj_ks, 1),
                "Line": line,
                "Side": side,
                "Edge%": f"{best_edge * 100:+.1f}%",
                "Odds": f"{odds:+d}",
                "Book": book,
                "_edge_val": best_edge,
                "_raw_odds": int(odds),
            })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("_edge_val", ascending=False).reset_index(drop=True)
