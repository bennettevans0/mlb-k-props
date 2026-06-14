import argparse
import csv
import subprocess
from datetime import date
from pathlib import Path

import pandas as pd
from tabulate import tabulate

import config
from data.odds import get_todays_props
from data.savant import get_season_pitching, get_team_k_rates
from data.starters import get_probable_starters, filter_to_starters
from model.edge import find_edges

PICKS_CSV   = Path(r"C:\Users\REDACTED\OneDrive\Documents\KTracker\picks.csv")
TRACKER_DIR = Path(r"C:\Users\REDACTED\OneDrive\Documents\KTracker")
TRACKER_SCRIPT = TRACKER_DIR / "k_tracker_1.py"

HIDDEN_COLS = ["_edge_val", "_raw_odds"]


def log_picks(edges_df: pd.DataFrame, date_str: str) -> int:
    """Append positive-edge picks to picks.csv. Returns number of new rows written."""
    plays = edges_df[edges_df["_edge_val"] > 0].copy()
    if plays.empty:
        return 0

    # Load existing picks to check for duplicates
    existing: set[tuple] = set()
    if PICKS_CSV.exists():
        existing_df = pd.read_csv(PICKS_CSV, dtype=str)
        existing = {
            (row.game_date, row.pitcher_name, str(row.line))
            for row in existing_df.itertuples()
        }

    new_rows = []
    for _, row in plays.iterrows():
        key = (date_str, row["Pitcher"], str(row["Line"]))
        if key in existing:
            continue
        new_rows.append([
            date_str,
            row["Pitcher"],
            row["Line"],
            row["Side"].lower(),
            int(row["_raw_odds"]),
            row["Proj K"],
        ])

    if not new_rows:
        print(f"[picks] No new rows to write (all already logged for {date_str}).")
        return 0

    file_exists = PICKS_CSV.exists()
    PICKS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(PICKS_CSV, "a", newline="") as f:
        # Ensure we start on a fresh line if the file has no trailing newline
        if file_exists and PICKS_CSV.stat().st_size > 0:
            with open(PICKS_CSV, "rb") as rf:
                rf.seek(-1, 2)
                if rf.read(1) not in (b"\n", b"\r"):
                    f.write("\n")
        w = csv.writer(f)
        if not file_exists:
            w.writerow(["game_date", "pitcher_name", "line", "pick", "odds", "model_projection"])
        w.writerows(new_rows)

    print(f"[picks] Wrote {len(new_rows)} new row(s) to {PICKS_CSV}")
    return len(new_rows)


def run_tracker() -> None:
    if not TRACKER_SCRIPT.exists():
        print(f"[tracker] Script not found: {TRACKER_SCRIPT}")
        return
    print(f"[tracker] Running {TRACKER_SCRIPT.name}...")
    result = subprocess.run(
        ["py", TRACKER_SCRIPT.name],
        cwd=str(TRACKER_DIR),
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0 and result.stderr:
        print(f"[tracker] stderr: {result.stderr}")


def display_df(edges_df: pd.DataFrame) -> pd.DataFrame:
    return edges_df.drop(columns=HIDDEN_COLS, errors="ignore")


def main():
    parser = argparse.ArgumentParser(description="MLB pitcher K prop edge finder")
    parser.add_argument("--min-edge", type=float, default=config.EDGE_THRESHOLD,
                        help="Minimum edge %% to display (default: 0.05)")
    parser.add_argument("--top-n", type=int, default=None,
                        help="Show only top N results")
    parser.add_argument("--date", type=str, default=None,
                        help="Date to fetch props for (YYYY-MM-DD, default: today)")
    args = parser.parse_args()

    api_key = config.get_api_key()
    today = date.today()
    season = today.year
    date_str = args.date or today.isoformat()

    props = get_todays_props(api_key, date_str=args.date)
    if not props:
        print("No pitcher K props found for today.")
        return

    print(f"[main] Found {len(props)} pitcher props. Loading stats...")
    pitching_df = get_season_pitching(season)
    team_k_rates, league_k_rate = get_team_k_rates(season)

    edges_df = find_edges(
        props,
        pitching_df,
        team_k_rates,
        league_k_rate,
        min_edge=args.min_edge,
    )

    print()
    if edges_df.empty:
        print(f"No edges found above {args.min_edge * 100:.0f}% threshold.")
        return

    # Verify probable starters
    print("[starters] Fetching probable starters from MLB Stats API...")
    starters, starter_error = get_probable_starters(date_str)
    if starter_error:
        print(f"[starters] WARNING: {starter_error} — skipping verification.")
        dropped = []
    else:
        print(f"[starters] Found {len(starters)} probable starters.")
        edges_df, dropped = filter_to_starters(edges_df, starters)
        for d in dropped:
            print(f"[starters] Dropped {d['pitcher']}: {d['reason']}")
        if edges_df.empty:
            print("[starters] No verified picks remaining after starter filter.")

    out_df = display_df(edges_df)
    if args.top_n:
        out_df = out_df.head(args.top_n)

    if not out_df.empty:
        print(tabulate(out_df, headers="keys", tablefmt="simple", showindex=True))
    print(f"\n{len(out_df)} verified edge(s). {len(dropped)} dropped by starter filter.")

    if config.GMAIL_USER and config.GMAIL_PASSWORD:
        from notify.email import send_picks
        send_picks(
            out_df, date_str,
            config.GMAIL_TO, config.GMAIL_USER, config.GMAIL_PASSWORD,
            dropped=dropped,
            starter_error=starter_error,
        )
    else:
        print("[email] Skipping — GMAIL_USER / GMAIL_APP_PASSWORD not configured.")

    log_picks(edges_df, date_str)
    run_tracker()


if __name__ == "__main__":
    main()
