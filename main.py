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
from hr_model import run_hr_model

PICKS_CSV      = Path(r"C:\Users\benne\OneDrive\Documents\KTracker\picks.csv")
TRACKER_DIR    = Path(r"C:\Users\benne\OneDrive\Documents\KTracker")
TRACKER_SCRIPT = TRACKER_DIR / "k_tracker_1.py"
RESULTS_CSV    = TRACKER_DIR / "results.csv"
DOCS_DIR       = Path(__file__).parent / "docs" / "data"

HIDDEN_COLS = ["_edge_val", "_raw_odds"]

# Canonical picks.csv schema. `prop_type` ("K" or "HR") is appended last so old
# rows (which lack it) read back as "" and are treated as K.
PICKS_HEADER = [
    "game_date", "pitcher_name", "line", "pick", "odds",
    "model_projection", "edge", "team", "opp", "book", "prop_type",
]


def _migrate_picks_csv() -> None:
    """Ensure picks.csv has the current columns; backfill old rows as K picks."""
    if not PICKS_CSV.exists():
        return
    df = pd.read_csv(PICKS_CSV, dtype=str).fillna("")
    changed = False
    if "edge" not in df.columns:
        df["edge"] = ""
        changed = True
    if "prop_type" not in df.columns:
        df["prop_type"] = "K"   # everything written before HR support was a K pick
        changed = True
    if changed:
        cols = [c for c in PICKS_HEADER if c in df.columns] + \
               [c for c in df.columns if c not in PICKS_HEADER]
        df[cols].to_csv(PICKS_CSV, index=False, encoding="utf-8")
        print("[picks] Migrated picks.csv schema (edge/prop_type).")


def _existing_pick_keys() -> set[tuple]:
    """Return {(game_date, name, line, prop_type)} for dedup."""
    if not PICKS_CSV.exists():
        return set()
    df = pd.read_csv(PICKS_CSV, dtype=str).fillna("")
    keys = set()
    for row in df.itertuples():
        pt = (getattr(row, "prop_type", "") or "K").strip() or "K"
        keys.add((row.game_date, row.pitcher_name, str(row.line), pt))
    return keys


def _append_pick_rows(new_rows: list[list]) -> None:
    """Append full-width rows (matching PICKS_HEADER) to picks.csv as UTF-8."""
    PICKS_CSV.parent.mkdir(parents=True, exist_ok=True)
    file_exists = PICKS_CSV.exists()
    with open(PICKS_CSV, "a", newline="", encoding="utf-8") as f:
        # Ensure we start on a fresh line if the file has no trailing newline
        if file_exists and PICKS_CSV.stat().st_size > 0:
            with open(PICKS_CSV, "rb") as rf:
                rf.seek(-1, 2)
                if rf.read(1) not in (b"\n", b"\r"):
                    f.write("\n")
        w = csv.writer(f)
        if not file_exists:
            w.writerow(PICKS_HEADER)
        w.writerows(new_rows)


def log_picks(edges_df: pd.DataFrame, date_str: str) -> int:
    """Append positive-edge K picks to picks.csv. Returns number of new rows."""
    if edges_df is None or edges_df.empty:
        return 0
    plays = edges_df[edges_df["_edge_val"] > 0].copy()
    if plays.empty:
        return 0

    _migrate_picks_csv()
    existing = _existing_pick_keys()

    new_rows = []
    for _, row in plays.iterrows():
        key = (date_str, row["Pitcher"], str(row["Line"]), "K")
        if key in existing:
            continue
        new_rows.append([
            date_str, row["Pitcher"], row["Line"], row["Side"].lower(),
            int(row["_raw_odds"]), row["Proj K"], round(float(row["_edge_val"]), 4),
            row.get("Team", ""), row.get("Opp", ""), row.get("Book", ""), "K",
        ])

    if not new_rows:
        print(f"[picks] No new K rows to write (all already logged for {date_str}).")
        return 0

    _append_pick_rows(new_rows)
    print(f"[picks] Wrote {len(new_rows)} new K row(s) to {PICKS_CSV}")
    return len(new_rows)


def log_hr_picks(hr_df: pd.DataFrame, date_str: str) -> int:
    """Append anytime-HR picks to picks.csv (prop_type='HR'). Returns new rows."""
    if hr_df is None or hr_df.empty:
        return 0
    plays = hr_df[hr_df["_edge_val"] > 0].copy()
    if plays.empty:
        return 0

    _migrate_picks_csv()
    existing = _existing_pick_keys()

    new_rows = []
    for _, row in plays.iterrows():
        key = (date_str, row["Batter"], str(row["Line"]), "HR")
        if key in existing:
            continue
        new_rows.append([
            date_str, row["Batter"], row["Line"], "yes",
            int(row["_raw_odds"]), row["_model_p"], round(float(row["_edge_val"]), 4),
            row.get("Team", ""), row.get("Opp", ""), row.get("Book", ""), "HR",
        ])

    if not new_rows:
        print(f"[picks] No new HR rows to write (all already logged for {date_str}).")
        return 0

    _append_pick_rows(new_rows)
    print(f"[picks] Wrote {len(new_rows)} new HR row(s) to {PICKS_CSV}")
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


BREF_TO_ABBREV = {
    # Short abbreviations
    "ARI":"ARI","ATL":"ATL","BAL":"BAL","BOS":"BOS","CHC":"CHC","CHW":"CWS",
    "CIN":"CIN","CLE":"CLE","COL":"COL","DET":"DET","HOU":"HOU","KCR":"KCR",
    "KC":"KCR","LAA":"LAA","LAD":"LAD","MIA":"MIA","MIL":"MIL","MIN":"MIN",
    "NYM":"NYM","NYY":"NYY","OAK":"OAK","PHI":"PHI","PIT":"PIT","SDP":"SDP",
    "SD":"SDP","SFG":"SFG","SF":"SFG","SEA":"SEA","STL":"STL","TBR":"TBR",
    "TB":"TBR","TEX":"TEX","TOR":"TOR","WSN":"WSN","WSH":"WSN",
    # BRef full/city team names (from pitching_stats_bref)
    "Arizona":"ARI","Atlanta":"ATL","Baltimore":"BAL","Boston":"BOS",
    "Chi Cubs":"CHC","Chi White Sox":"CWS","Cincinnati":"CIN","Cleveland":"CLE",
    "Colorado":"COL","Detroit":"DET","Houston":"HOU","Kansas City":"KCR",
    "LA Angels":"LAA","LA Dodgers":"LAD","Miami":"MIA","Milwaukee":"MIL",
    "Minnesota":"MIN","NY Mets":"NYM","NY Yankees":"NYY","Oakland":"OAK",
    "Athletics":"OAK","Philadelphia":"PHI","Pittsburgh":"PIT","San Diego":"SDP",
    "San Francisco":"SFG","Seattle":"SEA","St. Louis":"STL","Tampa Bay":"TBR",
    "Texas":"TEX","Toronto":"TOR","Washington":"WSN",
    # Ambiguous city names â€” default to NL/more common team
    "New York":"NYM","Los Angeles":"LAD","Chicago":"CHC",
}


def _cumulative_series(results: list[dict]) -> list[dict]:
    """Cumulative units over time: [{date, cum}] from a list of result dicts."""
    by_date: dict[str, float] = {}
    for r in results:
        d = r.get("date") or ""
        if not d:
            continue
        by_date[d] = by_date.get(d, 0.0) + (r.get("units") or 0.0)
    out, cum = [], 0.0
    for d in sorted(by_date):
        cum += by_date[d]
        out.append({"date": d, "cum": round(cum, 3)})
    return out


def export_site_data(
    edges_df: pd.DataFrame,
    date_str: str,
    n_props: int,
    pitching_df: pd.DataFrame | None = None,
    starter_times: dict | None = None,
    hr_edges_df: pd.DataFrame | None = None,
    hr_n_props: int = 0,
) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # Build pitcher->team lookup from savant data (fills team for old K results)
    pitcher_teams: dict[str, str] = {}
    if pitching_df is not None and not pitching_df.empty:
        for _, row in pitching_df.iterrows():
            name = str(row.get("Name", "") or "").strip()
            team = str(row.get("Team", "") or "").strip()
            if not name or not team:
                continue
            last_team = team.split(",")[-1].strip()
            abbrev = BREF_TO_ABBREV.get(last_team, BREF_TO_ABBREV.get(team, ""))
            if abbrev:
                pitcher_teams[name.lower()] = abbrev

    # Build (date, name) -> {team, opp, book} lookup from picks.csv (K and HR)
    pick_lookup: dict[tuple, dict] = {}
    if PICKS_CSV.exists():
        pdf = pd.read_csv(PICKS_CSV, dtype=str).fillna("")
        for _, row in pdf.iterrows():
            key = ((row.get("game_date") or "").strip(), (row.get("pitcher_name") or "").strip())
            pick_lookup[key] = {
                "team": (row.get("team") or "").strip(),
                "opp": (row.get("opp") or "").strip(),
                "book": (row.get("book") or "").strip(),
            }

    from data.starters import _normalize

    # ---- Today's picks (K + HR), unified schema with prop_type ----
    picks = []
    if edges_df is not None and not edges_df.empty:
        for _, row in edges_df[edges_df["_edge_val"] > 0].iterrows():
            picks.append({
                "prop_type": "K",
                "name": row["Pitcher"],
                "team": row.get("Team", ""),
                "opp": row.get("Opp", ""),
                "line": float(row["Line"]),
                "pick": row["Side"].lower(),
                "odds": row["Odds"],
                "model": float(row["Proj K"]),           # projected Ks
                "edge_val": round(float(row["_edge_val"]), 4),
                "book": row.get("Book", ""),
                "time": (starter_times or {}).get(_normalize(row["Pitcher"]), ""),
            })
    if hr_edges_df is not None and not hr_edges_df.empty:
        for _, row in hr_edges_df[hr_edges_df["_edge_val"] > 0].iterrows():
            picks.append({
                "prop_type": "HR",
                "name": row["Batter"],
                "opp_pitcher": row.get("Pitcher", ""),
                "team": row.get("Team", ""),
                "opp": row.get("Opp", ""),
                "home": row.get("_home", ""),
                "away": row.get("_away", ""),
                "line": float(row["Line"]),
                "pick": "yes",
                "odds": row["Odds"],
                "model": float(row["_model_p"]),          # P(>=1 HR), 0-1
                "edge_val": round(float(row["_edge_val"]), 4),
                "book": row.get("Book", ""),
                "time": row.get("_time", ""),
            })
    with open(DOCS_DIR / "today.json", "w") as f:
        json.dump({"date": date_str, "picks": picks}, f, indent=2)

    # ---- Graded results (K + HR), unified schema with prop_type ----
    results = []
    if RESULTS_CSV.exists():
        rdf = pd.read_csv(RESULTS_CSV, dtype=str).fillna("")
        for _, row in rdf.iterrows():
            result_val = (row.get("result") or "").strip()
            if not result_val:
                continue
            try:
                units = round(float(row.get("profit_units") or 0), 4)
                model = float(row.get("model_projection") or 0)
                actual_raw = row.get("actual_K", "")
                actual = float(actual_raw) if str(actual_raw).strip() not in ("", "nan") else None
                edge_raw = row.get("edge", "")
                edge = float(edge_raw) if str(edge_raw).strip() not in ("", "nan") else None
            except (ValueError, TypeError):
                continue
            date_val = (row.get("game_date") or "").strip()
            name_val = (row.get("pitcher_name") or "").strip()
            prop_type = (row.get("prop_type") or "").strip() or "K"
            pl = pick_lookup.get((date_val, name_val), {})
            team = (row.get("team") or "").strip() or pl.get("team") or pitcher_teams.get(name_val.lower(), "")
            opp = (row.get("opp") or "").strip() or pl.get("opp", "")
            book = (row.get("book") or "").strip() or pl.get("book", "")
            results.append({
                "prop_type": prop_type,
                "date": date_val,
                "name": name_val,
                "team": team,
                "opp": opp,
                "book": book,
                "line": float(row.get("line") or 0),
                "pick": (row.get("pick") or "").strip(),
                "odds": (row.get("odds") or "").strip(),
                "model": model,
                "actual": actual,
                "result": result_val,
                "units": units,
                "edge": edge,
            })

    k_results = [r for r in results if r["prop_type"] == "K"]
    hr_results = [r for r in results if r["prop_type"] == "HR"]
    series = {
        "combined": _cumulative_series(results),
        "K": _cumulative_series(k_results),
        "HR": _cumulative_series(hr_results),
    }
    with open(DOCS_DIR / "results.json", "w") as f:
        json.dump({"results": results, "series": series}, f, indent=2)

    with open(DOCS_DIR / "meta.json", "w") as f:
        json.dump({
            "last_run": datetime.now().isoformat(timespec="seconds"),
            "props_checked": n_props,
            "hr_props_checked": hr_n_props,
        }, f)

    print(f"[site] Exported data to {DOCS_DIR}")


def display_df(edges_df: pd.DataFrame) -> pd.DataFrame:
    return edges_df.drop(columns=HIDDEN_COLS, errors="ignore")


def publish_site(date_str):
    repo = r"C:\Users\benne\mlb-k-props"
    try:
        subprocess.run(["git", "add", "docs"], cwd=repo, check=True)
        # commit returns nonzero when nothing changed - that's fine
        subprocess.run(["git", "commit", "-m", f"Auto-publish {date_str}"], cwd=repo, check=False)
        subprocess.run(["git", "push"], cwd=repo, check=True)
        print("[publish] Pushed docs to GitHub Pages.")
    except Exception as e:
        print(f"[publish] Skipped: {e}")


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

    # ---------------- K model (unchanged logic) ----------------
    edges_df = pd.DataFrame()
    out_df = pd.DataFrame()
    pitching_df = None
    starter_times: dict = {}
    dropped: list = []
    starter_error = None

    props = get_todays_props(api_key, date_str=args.date)
    n_props = len(props)
    if not props:
        print("No pitcher K props found for today.")
    else:
        print(f"[main] Found {n_props} pitcher props. Loading stats...")
        pitching_df = get_season_pitching(season)
        team_k_rates, league_k_rate = get_team_k_rates(season)

        edges_df = find_edges(
            props, pitching_df, team_k_rates, league_k_rate, min_edge=args.min_edge,
        )

        print()
        if edges_df.empty:
            print(f"No edges found above {args.min_edge * 100:.0f}% threshold.")

        # Verify probable starters (skip if nothing to filter)
        if not edges_df.empty:
            print("[starters] Fetching probable starters from MLB Stats API...")
            starters, starter_times, starter_error = get_probable_starters(date_str)
            if starter_error:
                print(f"[starters] WARNING: {starter_error} - skipping verification.")
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
        print(f"\n{len(out_df)} verified K edge(s). {len(dropped)} dropped by starter filter.")

    # ---------------- HR model (separate module) ----------------
    print("\n[main] Running anytime-HR model...")
    try:
        hr_edges_df, hr_n_props = run_hr_model(api_key, date_str, int(date_str[:4]))
    except Exception as exc:
        # Never let an HR failure break the K pipeline.
        print(f"[main] HR model error (skipping HR): {exc}")
        hr_edges_df, hr_n_props = pd.DataFrame(), 0
    if hr_edges_df is not None and not hr_edges_df.empty:
        from hr_model import display_df as hr_display_df
        print(tabulate(hr_display_df(hr_edges_df), headers="keys", tablefmt="simple", showindex=False))
        print(f"{len(hr_edges_df)} anytime-HR pick(s).")
    else:
        print("No anytime-HR picks.")

    # ---------------- Email / log / grade / publish ----------------
    if config.GMAIL_USER and config.GMAIL_PASSWORD:
        from notify.email import send_picks
        send_picks(
            out_df, date_str,
            config.GMAIL_TO, config.GMAIL_USER, config.GMAIL_PASSWORD,
            dropped=dropped,
            starter_error=starter_error,
            n_props=n_props,
            hr_df=hr_edges_df,
            hr_n_props=hr_n_props,
        )
    else:
        print("[email] Skipping - GMAIL_USER / GMAIL_APP_PASSWORD not configured.")

    log_picks(edges_df, date_str)
    log_hr_picks(hr_edges_df, date_str)
    run_tracker()
    export_site_data(
        edges_df, date_str, n_props, pitching_df, starter_times,
        hr_edges_df=hr_edges_df, hr_n_props=hr_n_props,
    )
    publish_site(date_str)


if __name__ == "__main__":
    main()
