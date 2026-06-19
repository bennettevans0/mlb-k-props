"""
Find anytime-HR edges: model P(>=1 HR) vs the de-vigged market price.

Mirrors model/edge.py (same edge-threshold + flat-stake philosophy). Anytime HR
has a single side ("yes"), so we only ever back the Over 0.5 when our edge clears
the threshold. We reuse the K model's odds helpers so the math stays identical.
"""
import pandas as pd

import config
from data import hr_stats
from data.hr_context import resolve_batter
from data.park_factors import park_factor
from model.edge import american_to_prob, remove_vig
from model.hr_projection import adjusted_p_per_pa, prob_at_least_one_hr


def _fair_yes_prob(yes_odds: int, no_odds: int | None) -> float:
    """De-vigged P(yes) if both sides exist; otherwise the raw implied P(yes)."""
    raw_yes = american_to_prob(yes_odds)
    if no_odds is None:
        return raw_yes
    raw_no = american_to_prob(no_odds)
    fair_yes, _ = remove_vig(raw_yes, raw_no)
    return fair_yes


def find_hr_edges(
    props: list[dict],
    batting_df: pd.DataFrame,
    pitching_df: pd.DataFrame,
    context: dict | None,
    league_hr_per_pa: float,
    league_hr_per9: float,
    min_edge: float = config.HR_EDGE_THRESHOLD,
) -> pd.DataFrame:
    rows = []

    for prop in props:
        batter = prop["batter"]
        line = prop["line"]
        yes_odds = prop["yes_odds"]
        no_odds = prop.get("no_odds")

        stats = hr_stats.lookup_batter(batter, batting_df)
        if stats is None:
            print(f"[hr-edge] Skipping {batter}: no batting stats / sample too small")
            continue

        ctx = resolve_batter(context, batter, stats.get("mlbid", ""))
        if ctx is None:
            print(f"[hr-edge] Skipping {batter}: could not resolve team/matchup")
            continue

        opp_pitcher = ctx["opp_pitcher"]
        pstats = hr_stats.lookup_pitcher_hr(opp_pitcher, pitching_df)

        pf_pitcher_hr = pstats["hr"] if pstats else None
        pf_pitcher_ip = pstats["ip"] if pstats else None

        park = park_factor(ctx["park_abbr"])

        p_adj, pitcher_factor = adjusted_p_per_pa(
            batter_hr=stats["hr"],
            batter_pa=stats["pa"],
            league_hr_per_pa=league_hr_per_pa,
            pitcher_hr=pf_pitcher_hr,
            pitcher_ip=pf_pitcher_ip,
            league_hr_per9=league_hr_per9,
            park_factor=park,
        )
        model_p = prob_at_least_one_hr(p_adj, ctx["expected_pa"])

        fair_yes = _fair_yes_prob(yes_odds, no_odds)
        edge = model_p - fair_yes

        if edge < min_edge:
            continue

        rows.append({
            "Batter": stats["name"],
            "Team": ctx["team_abbr"],
            "Opp": ctx["opp_abbr"],
            "Pitcher": opp_pitcher or "—",
            "Line": line,
            "Side": "yes",
            "Model P": f"{model_p * 100:.1f}%",
            "Edge%": f"{edge * 100:+.1f}%",
            "Odds": f"{yes_odds:+d}",
            "Book": prop.get("yes_book", ""),
            "ISO": round(stats["iso"], 3),
            "PA": ctx["expected_pa"],
            "_edge_val": edge,
            "_raw_odds": int(yes_odds),
            "_model_p": round(model_p, 4),
            "_park": park,
            "_pitcher_factor": round(pitcher_factor, 3),
            "_time": ctx["time_utc"],
            "_home": ctx["home_abbr"],
            "_away": ctx["away_abbr"],
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("_edge_val", ascending=False).reset_index(drop=True)
