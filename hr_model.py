"""
Anytime home-run prop model (Phase 1).

Reuses the existing pipeline pieces (The Odds API, MLB Stats API, pybaseball,
config). It does NOT touch the K model.

Used two ways:
  - main.py imports run_hr_model() for the daily 8 AM run.
  - Run directly (`py hr_model.py [--date YYYY-MM-DD]`) to print the HR slate for
    sanity-checking. Running it directly has NO side effects: it does not write
    picks, send email, or publish. main.py owns logging/email/site/publish.
"""
import argparse
from datetime import date

import pandas as pd
from tabulate import tabulate

import config
from data.hr_odds import get_todays_hr_props
from data.hr_context import get_hr_context
from data import hr_stats
from model.hr_edge import find_hr_edges

HIDDEN_COLS = ["_edge_val", "_raw_odds", "_model_p", "_park", "_pitcher_factor", "_time", "_home", "_away"]


def run_hr_model(api_key: str, date_str: str, season: int, min_edge: float | None = None):
    """
    Run the HR model for a date.
    Returns (edges_df, n_props). edges_df may be empty (no lines / no edges).
    """
    if min_edge is None:
        min_edge = config.HR_EDGE_THRESHOLD

    props = get_todays_hr_props(api_key, date_str=date_str)
    n_props = len(props)
    if not props:
        print("[hr] No anytime-HR props available (books may not have posted them yet).")
        return pd.DataFrame(), 0

    print(f"[hr] Found {n_props} anytime-HR props. Loading stats...")
    batting_df = hr_stats.get_batting(season)
    pitching_df = hr_stats.get_pitching_hr(season)
    lg_hr_pa = hr_stats.league_hr_per_pa(batting_df)
    lg_hr_9 = hr_stats.league_hr_per9(pitching_df)
    print(f"[hr] League HR/PA={lg_hr_pa:.4f}  HR/9={lg_hr_9:.2f}")

    print("[hr] Building matchup context (rosters, probable pitchers, parks)...")
    context = get_hr_context(date_str)
    if context is None:
        print("[hr] WARNING: no matchup context — cannot resolve batters, skipping HR.")
        return pd.DataFrame(), n_props

    edges_df = find_hr_edges(
        props, batting_df, pitching_df, context, lg_hr_pa, lg_hr_9, min_edge=min_edge,
    )
    return edges_df, n_props


def display_df(edges_df: pd.DataFrame) -> pd.DataFrame:
    return edges_df.drop(columns=HIDDEN_COLS, errors="ignore")


def main():
    parser = argparse.ArgumentParser(description="MLB anytime-HR prop edge finder (read-only)")
    parser.add_argument("--date", type=str, default=None, help="YYYY-MM-DD (default: today)")
    parser.add_argument("--min-edge", type=float, default=config.HR_EDGE_THRESHOLD,
                        help=f"Minimum edge (default: {config.HR_EDGE_THRESHOLD})")
    args = parser.parse_args()

    api_key = config.get_api_key()
    today = date.today()
    date_str = args.date or today.isoformat()
    season = int(date_str[:4])

    edges_df, n_props = run_hr_model(api_key, date_str, season, min_edge=args.min_edge)

    print()
    if edges_df.empty:
        print(f"No anytime-HR edges above {args.min_edge * 100:.0f}% (checked {n_props} props).")
        return

    out = display_df(edges_df)
    print(tabulate(out, headers="keys", tablefmt="simple", showindex=False))
    print(f"\n{len(out)} anytime-HR pick(s) at >= {args.min_edge * 100:.0f}% edge.")


if __name__ == "__main__":
    main()
