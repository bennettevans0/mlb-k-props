import argparse
import csv
import json
import subprocess
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from tabulate import tabulate

import config
from data.odds import get_todays_props
from data.savant import get_season_pitching, get_team_k_rates
from data.starters import get_probable_starters, filter_to_starters
from model.edge import find_edges

PICKS_CSV      = Path(r"C:\Users\benne\OneDrive\Documents\KTracker\picks.csv")
TRACKER_DIR    = Path(r"C:\Users\benne\OneDrive\Documents\KTracker")
TRACKER_SCRIPT = TRACKER_DIR / "k_tracker_1.py"
RESULTS_CSV    = TRACKER_DIR / "results.csv"
DOCS_DIR       = Path(__file__).parent / "docs" / "data"

HIDDEN_COLS = ["_edge_val", "_raw_odds"]


def log_picks(edges_df: pd.DataFrame, date_str: str) -> int:
    """Append positive-edge picks to picks.csv. Returns number of new rows written."""
    plays = edges_df[edges_df["_edge_val"] > 0].copy()
    if plays.empty:
        return 0

    # Load existing picks to check for duplicates; migrate if edge column is missing
    existing: set[tuple] = set()
    needs_migration = False
    if PICKS_CSV.exists():
        existing_df = pd.read_csv(PICKS_CSV, dtype=str)
        existing = {
            (row.game_date, row.pitcher_name, str(row.line))
            for row in existing_df.itertuples()
        }
        if "edge" not in existing_df.columns:
            needs_migration = True

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
            round(float(row["_edge_val"]), 4),
        ])

    PICKS_CSV.parent.mkdir(parents=True, exist_ok=True)

    # One-time migration: add edge column (blank) to rows written before this version
    if needs_migration:
        existing_df["edge"] = ""
        existing_df.to_csv(PICKS_CSV, index=False)
        print("[picks] Migrated picks.csv: added 'edge' column to existing rows.")

    if not new_rows:
        print(f"[picks] No new rows to write (all already logged for {date_str}).")
        return 0

    file_exists = PICKS_CSV.exists()
    with open(PICKS_CSV, "a", newline="") as f:
        # Ensure we start on a fresh line if the file has no trailing newline
        if file_exists and PICKS_CSV.stat().st_size > 0:
            with open(PICKS_CSV, "rb") as rf:
                rf.seek(-1, 2)
                if rf.read(1) not in (b"\n", b"\r"):
                    f.write("\n")
        w = csv.writer(f)
        if not file_exists:
            w.writerow(["game_date", "pitcher_name", "line", "pick", "odds", "model_projection", "edge"])
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


def export_site_data(edges_df: pd.DataFrame, date_str: str, n_props: int) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    picks = []
    if not edges_df.empty:
        for _, row in edges_df[edges_df["_edge_val"] > 0].iterrows():
            picks.append({
                "pitcher": row["Pitcher"],
                "team": row.get("Team", ""),
                "opp": row.get("Opp", ""),
                "line": float(row["Line"]),
                "pick": row["Side"].lower(),
                "odds": row["Odds"],
                "proj_k": float(row["Proj K"]),
                "edge": row["Edge%"],
                "edge_val": round(float(row["_edge_val"]), 4),
                "book": row.get("Book", ""),
            })
    with open(DOCS_DIR / "today.json", "w") as f:
        json.dump({"date": date_str, "picks": picks}, f, indent=2)

    results = []
    if RESULTS_CSV.exists():
        rdf = pd.read_csv(RESULTS_CSV, dtype=str)
        for _, row in rdf.iterrows():
            result_val = (row.get("result") or "").strip()
            if not result_val:
                continue
            try:
                units = round(float(row.get("profit_units") or 0), 4)
                proj = float(row.get("model_projection") or 0)
                actual_raw = row.get("actual_K", "")
                actual = float(actual_raw) if str(actual_raw).strip() not in ("", "nan") else None
                edge_raw = row.get("edge", "")
                edge = float(edge_raw) if str(edge_raw).strip() not in ("", "nan") else None
            except (ValueError, TypeError):
                continue
            results.append({
                "date": (row.get("game_date") or "").strip(),
                "pitcher": (row.get("pitcher_name") or "").strip(),
                "line": float(row.get("line") or 0),
                "pick": (row.get("pick") or "").strip(),
                "odds": (row.get("odds") or "").strip(),
                "proj_k": proj,
                "actual_k": actual,
                "result": result_val,
                "units": units,
                "edge": edge,
            })
    with open(DOCS_DIR / "results.json", "w") as f:
        json.dump({"results": results}, f, indent=2)

    with open(DOCS_DIR / "meta.json", "w") as f:
        json.dump({
            "last_run": datetime.now().isoformat(timespec="seconds"),
            "props_checked": n_props,
        }, f)

    print(f"[site] Exported data to {DOCS_DIR}")


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
    n_props = len(props)
    if not props:
        print("No pitcher K props found for today.")
        if config.GMAIL_USER and config.GMAIL_PASSWORD:
            from notify.email import send_picks
            send_picks(
                pd.DataFrame(), date_str,
                config.GMAIL_TO, config.GMAIL_USER, config.GMAIL_PASSWORD,
                n_props=0,
            )
        return

    print(f"[main] Found {n_props} pitcher props. Loading stats...")
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

    dropped = []
    starter_error = None
    # Verify probable starters (skip if nothing to filter)
    if not edges_df.empty:
        print("[starters] Fetching probable starters from MLB Stats API...")
        starters, starter_error = get_probable_starters(date_str)
        if starter_error:
            print(f"[starters] WARNING: {starter_error} — skipping verification.")
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
            n_props=n_props,
        )
    else:
        print("[email] Skipping — GMAIL_USER / GMAIL_APP_PASSWORD not configured.")

    log_picks(edges_df, date_str)
    run_tracker()
    export_site_data(edges_df, date_str, n_props)


if __name__ == "__main__":
    main()
