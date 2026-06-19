"""
Batter power profiles and pitcher HR-vulnerability from Baseball Reference
(via pybaseball), for the anytime-HR model.

Phase 1 metrics only:
  - Batter:  HR, PA, AB, BA, SLG  ->  HR/PA and ISO (SLG - BA)
  - Pitcher: HR, IP               ->  HR/9
Statcast metrics (barrel%, HR/FB, exit velo) are Phase 2 (Baseball Savant).

Pitcher stats are loaded with the same pybaseball call the K side uses, but kept
in a SEPARATE cache file so we never touch the K model's pitching cache.
"""
from pathlib import Path

import pandas as pd
import pybaseball

from data.starters import _normalize

CACHE_DIR = Path(__file__).parent.parent / "cache"

pybaseball.cache.enable()

# Fallbacks if league rates can't be computed from the data.
DEFAULT_LEAGUE_HR_PER_PA = 0.032
DEFAULT_LEAGUE_HR_PER9 = 1.20

# Minimum batter PA to be considered (regression handles small samples, but skip
# truly tiny samples that are pure noise).
MIN_BATTER_PA = 20


def get_batting(season: int) -> pd.DataFrame:
    """Return a batter DataFrame with HR/PA and ISO, indexed for name lookup."""
    cache_file = CACHE_DIR / f"hr_batting_{season}.pkl"
    CACHE_DIR.mkdir(exist_ok=True)

    if cache_file.exists():
        print(f"[hr-stats] Loading batting stats from cache: {cache_file.name}")
        return pd.read_pickle(cache_file)

    print(f"[hr-stats] Fetching {season} Baseball Reference batting stats...")
    df = pybaseball.batting_stats_bref(season)

    df = df.rename(columns={"Tm": "Team"})
    for col in ("PA", "AB", "HR"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    for col in ("BA", "SLG"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df["HR_per_PA"] = df["HR"] / df["PA"].replace(0, float("nan"))
    df["ISO"] = (df["SLG"] - df["BA"]).clip(lower=0)

    keep = [c for c in ["Name", "Team", "PA", "AB", "HR", "BA", "SLG", "ISO", "HR_per_PA", "mlbID"] if c in df.columns]
    df = df[keep].copy()
    df["Name"] = df["Name"].astype(str).str.strip()
    df["_norm"] = df["Name"].map(_normalize)
    df.to_pickle(cache_file)
    return df


def get_pitching_hr(season: int) -> pd.DataFrame:
    """Return a pitcher DataFrame with HR/9 (separate cache from the K model)."""
    cache_file = CACHE_DIR / f"hr_pitching_{season}.pkl"
    CACHE_DIR.mkdir(exist_ok=True)

    if cache_file.exists():
        print(f"[hr-stats] Loading pitcher HR stats from cache: {cache_file.name}")
        return pd.read_pickle(cache_file)

    print(f"[hr-stats] Fetching {season} Baseball Reference pitching stats (HR)...")
    df = pybaseball.pitching_stats_bref(season)

    name_col = "Name" if "Name" in df.columns else "Player"
    df = df.rename(columns={name_col: "Name", "Tm": "Team"})
    df["IP"] = pd.to_numeric(df["IP"], errors="coerce").fillna(0)
    df["HR"] = pd.to_numeric(df["HR"], errors="coerce").fillna(0)
    df["HR_per9"] = (df["HR"] / df["IP"].replace(0, float("nan"))) * 9

    keep = [c for c in ["Name", "Team", "IP", "HR", "HR_per9"] if c in df.columns]
    df = df[keep].copy()
    df["Name"] = df["Name"].astype(str).str.strip()
    df["_norm"] = df["Name"].map(_normalize)
    df.to_pickle(cache_file)
    return df


def league_hr_per_pa(batting_df: pd.DataFrame) -> float:
    pa = batting_df["PA"].sum()
    hr = batting_df["HR"].sum()
    return (hr / pa) if pa else DEFAULT_LEAGUE_HR_PER_PA


def league_hr_per9(pitching_df: pd.DataFrame) -> float:
    ip = pitching_df["IP"].sum()
    hr = pitching_df["HR"].sum()
    return (hr / ip * 9) if ip else DEFAULT_LEAGUE_HR_PER9


def _lookup(df: pd.DataFrame, name: str):
    norm = _normalize(name)
    match = df[df["_norm"] == norm]
    if not match.empty:
        return match.iloc[0]
    # last-name fallback (unique only)
    last = norm.split()[-1] if norm else ""
    if last:
        match = df[df["_norm"].str.endswith(" " + last) | (df["_norm"] == last)]
        if len(match) == 1:
            return match.iloc[0]
    return None


def lookup_batter(name: str, batting_df: pd.DataFrame) -> dict | None:
    row = _lookup(batting_df, name)
    if row is None:
        return None
    pa = float(row.get("PA", 0) or 0)
    if pa < MIN_BATTER_PA:
        return None
    return {
        "name": str(row.get("Name", name)),
        "team": str(row.get("Team", "") or ""),
        "pa": pa,
        "hr": float(row.get("HR", 0) or 0),
        "hr_per_pa": float(row.get("HR_per_PA", 0) or 0),
        "iso": float(row.get("ISO", 0) or 0),
        "mlbid": str(row.get("mlbID", "") or ""),
    }


def lookup_pitcher_hr(name: str, pitching_df: pd.DataFrame) -> dict | None:
    if not name:
        return None
    row = _lookup(pitching_df, name)
    if row is None:
        return None
    return {
        "name": str(row.get("Name", name)),
        "ip": float(row.get("IP", 0) or 0),
        "hr": float(row.get("HR", 0) or 0),
        "hr_per9": float(row.get("HR_per9", 0) or 0),
    }
