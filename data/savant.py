import time
from pathlib import Path

import pandas as pd
import pybaseball

CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_TTL_SECONDS = 86400  # refresh once per day

pybaseball.cache.enable()


def _cache_is_fresh(path: Path) -> bool:
    """True if cache file exists and was written within the TTL window."""
    return path.exists() and (time.time() - path.stat().st_mtime) < CACHE_TTL_SECONDS


def get_season_pitching(season: int) -> pd.DataFrame:
    cache_file = CACHE_DIR / f"pitching_{season}.pkl"
    CACHE_DIR.mkdir(exist_ok=True)

    if _cache_is_fresh(cache_file):
        print(f"[savant] Loading pitching stats from cache: {cache_file.name}")
        return pd.read_pickle(cache_file)

    if cache_file.exists():
        age_days = (time.time() - cache_file.stat().st_mtime) / 86400
        print(f"[savant] Pitching cache is {age_days:.1f}d old — refreshing...")
        cache_file.unlink()

    print(f"[savant] Fetching {season} Baseball Reference pitching stats...")
    df = pybaseball.pitching_stats_bref(season)

    # BRef columns: Name/Player, Tm, SO, IP, G, GS
    name_col = "Name" if "Name" in df.columns else "Player"
    team_col = "Tm" if "Tm" in df.columns else "Team"

    df = df.rename(columns={name_col: "Name", team_col: "Team"})

    # Compute K/9 from raw SO and IP
    df["IP"] = pd.to_numeric(df["IP"], errors="coerce").fillna(0)
    df["SO"] = pd.to_numeric(df["SO"], errors="coerce").fillna(0)
    df["K/9"] = (df["SO"] / df["IP"].replace(0, float("nan"))) * 9

    cols = [c for c in ["Name", "Team", "K/9", "SO", "IP", "G", "GS"] if c in df.columns]
    df = df[cols].copy()
    df["Name"] = df["Name"].str.strip()
    df.to_pickle(cache_file)
    return df


def get_team_k_rates(season: int) -> tuple[dict[str, float], float]:
    """Returns ({bref_team_abbrev: k_rate}, league_k_rate) from MLB Stats API."""
    import json
    import requests as _requests

    cache_file = CACHE_DIR / f"team_batting_{season}.json"
    CACHE_DIR.mkdir(exist_ok=True)

    if _cache_is_fresh(cache_file):
        print(f"[savant] Loading team K rates from cache: {cache_file.name}")
        with open(cache_file) as f:
            data = json.load(f)
        return data["team_k_rates"], data["league_k_rate"]

    if cache_file.exists():
        age_days = (time.time() - cache_file.stat().st_mtime) / 86400
        print(f"[savant] Team K rate cache is {age_days:.1f}d old — refreshing...")
        cache_file.unlink()

    print(f"[savant] Fetching {season} team batting stats from MLB Stats API...")
    # MLB Stats API: team hitting stats aggregated by team
    url = (
        f"https://statsapi.mlb.com/api/v1/teams/stats"
        f"?season={season}&group=hitting&stats=season&sportId=1"
    )
    resp = _requests.get(url, timeout=15)
    resp.raise_for_status()
    splits = resp.json()["stats"][0]["splits"]

    team_so: dict[str, int] = {}
    team_pa: dict[str, int] = {}

    for split in splits:
        team_name = split["team"]["name"]
        stat = split["stat"]
        so = int(stat.get("strikeOuts", 0))
        ab = int(stat.get("atBats", 0))
        bb = int(stat.get("baseOnBalls", 0))
        hbp = int(stat.get("hitByPitch", 0))
        sf = int(stat.get("sacFlies", 0))
        pa = ab + bb + hbp + sf
        team_so[team_name] = so
        team_pa[team_name] = pa

    total_so = sum(team_so.values())
    total_pa = sum(team_pa.values())
    league_k_rate = total_so / total_pa if total_pa else 0.22

    team_k_rates = {
        name: team_so[name] / team_pa[name]
        for name in team_so
        if team_pa.get(name, 0) > 0
    }

    with open(cache_file, "w") as f:
        json.dump({"team_k_rates": team_k_rates, "league_k_rate": league_k_rate}, f)

    return team_k_rates, league_k_rate


MAX_IP_PER_START = 7.0
MIN_GS = 2

def get_recent_ip(pitcher_name: str, pitching_df: pd.DataFrame) -> list[float]:
    row = _find_pitcher(pitcher_name, pitching_df)
    if row is None:
        return []

    gs = row.get("GS", 0) or 0
    ip = row.get("IP", 0) or 0
    if gs >= MIN_GS:
        avg_ip = min(ip / gs, MAX_IP_PER_START)
        return [avg_ip]
    return []


def _find_pitcher(name: str, df: pd.DataFrame):
    match = df[df["Name"].str.lower() == name.lower()]
    if not match.empty:
        return match.iloc[0]
    last = name.split()[-1].lower()
    match = df[df["Name"].str.lower().str.endswith(last)]
    if len(match) == 1:
        return match.iloc[0]
    return None


def lookup_pitcher(name: str, pitching_df: pd.DataFrame) -> dict | None:
    row = _find_pitcher(name, pitching_df)
    if row is None:
        return None
    return {
        "k_per9": float(row.get("K/9", 0) or 0),
        "ip": float(row.get("IP", 0) or 0),
        "gs": int(row.get("GS", 0) or 0),
        "team": str(row.get("Team", "") or ""),
    }
