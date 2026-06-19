"""
Game/matchup context for the anytime-HR model, from the (free) MLB Stats API.

For each batter we need to know, structurally (no batter-vs-pitcher history):
  - which team they're on  -> which game/park they're in
  - the OPPOSING probable starter (for pitcher HR-vulnerability)
  - the park (home team's stadium) and the game start time (UTC)
  - batting-order spot if the lineup is posted (to refine expected PA)

We resolve a batter -> team by MLB team id (not abbreviation) to avoid the
city-name ambiguity in Baseball Reference team labels (e.g. "New York").
The whole context is cached per date.
"""
import json
from datetime import date
from pathlib import Path

import requests

import config
from data.starters import _normalize

CACHE_DIR = Path(__file__).parent.parent / "cache"
SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
ROSTER_URL = "https://statsapi.mlb.com/api/v1/teams/{team_id}/roster"

# Expected plate appearances by batting-order spot (used only when the lineup is
# posted). Falls back to config.HR_DEFAULT_PA when the spot is unknown.
PA_BY_SPOT = {1: 4.6, 2: 4.5, 3: 4.4, 4: 4.3, 5: 4.1, 6: 4.0, 7: 3.9, 8: 3.8, 9: 3.7}


def _context_cache_path(date_str: str) -> Path:
    CACHE_DIR.mkdir(exist_ok=True)
    return CACHE_DIR / f"hr_context_{date_str}.json"


def get_hr_context(date_str: str | None = None, use_cache: bool = True) -> dict | None:
    """Build (or load) the matchup context for a date. Returns None on failure."""
    if date_str is None:
        date_str = date.today().isoformat()

    cache_path = _context_cache_path(date_str)
    if use_cache and cache_path.exists():
        print(f"[hr-ctx] Loading matchup context from cache: {cache_path.name}")
        with open(cache_path) as f:
            return json.load(f)

    try:
        games = _fetch_games(date_str)
        player_team = _fetch_rosters()
    except Exception as exc:
        print(f"[hr-ctx] WARNING: could not build context: {exc}")
        return None

    if not games:
        print("[hr-ctx] No games found for context.")
        return None

    context = {
        "date": date_str,
        # JSON keys are strings; resolve_batter() handles that.
        "player_team": player_team,        # {normname: team_id}
        "games": games,                    # {str(team_id): {...}}
    }
    with open(cache_path, "w") as f:
        json.dump(context, f, indent=2)
    print(f"[hr-ctx] Built context for {len(games)} team-slots, {len(player_team)} players.")
    return context


def _fetch_games(date_str: str) -> dict:
    resp = requests.get(
        SCHEDULE_URL,
        params={"sportId": 1, "date": date_str, "hydrate": "probablePitcher,venue,lineups"},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()

    games: dict[str, dict] = {}
    for date_entry in data.get("dates", []):
        for game in date_entry.get("games", []):
            home = game["teams"]["home"]
            away = game["teams"]["away"]
            home_id = home["team"]["id"]
            away_id = away["team"]["id"]
            home_pp = (home.get("probablePitcher") or {}).get("fullName", "")
            away_pp = (away.get("probablePitcher") or {}).get("fullName", "")
            venue = (game.get("venue") or {}).get("name", "")
            time_utc = game.get("gameDate", "")

            lineups = game.get("lineups") or {}
            home_spots = _spots(lineups.get("homePlayers", []))
            away_spots = _spots(lineups.get("awayPlayers", []))

            games[str(home_id)] = {
                "is_home": True,
                "home_team_id": home_id,
                "opp_team_id": away_id,
                "opp_pitcher": away_pp,
                "venue": venue,
                "time_utc": time_utc,
                "lineup_spot": home_spots,
            }
            games[str(away_id)] = {
                "is_home": False,
                "home_team_id": home_id,
                "opp_team_id": home_id,   # away team's opponent is the home team
                "opp_pitcher": home_pp,
                "venue": venue,
                "time_utc": time_utc,
                "lineup_spot": away_spots,
            }
    return games


def _spots(players: list) -> dict:
    """Map {str(person_id): batting_order_spot} from a posted lineup list (in order)."""
    out: dict[str, int] = {}
    for i, p in enumerate(players, start=1):
        pid = p.get("id") if isinstance(p, dict) else None
        if pid is not None:
            out[str(pid)] = i
    return out


def _fetch_rosters() -> dict:
    """
    Build {normalized_name: team_id} from the 40-man rosters of all 30 teams.
    40-man is used (not the 26-man active roster) so recently-activated or
    IL-returning batters are still resolvable; players not actually in a game
    just won't have a HR prop, so including them is harmless.
    """
    player_team: dict[str, int] = {}
    for team_id in config.TEAM_ID_TO_ABBREV:
        try:
            resp = requests.get(
                ROSTER_URL.format(team_id=team_id),
                params={"rosterType": "40Man"},
                timeout=20,
            )
            resp.raise_for_status()
            for entry in resp.json().get("roster", []):
                person = entry.get("person", {})
                name = person.get("fullName", "")
                if name:
                    player_team[_normalize(name)] = team_id
        except Exception as exc:
            print(f"[hr-ctx] roster fetch failed for team {team_id}: {exc}")
    return player_team


def resolve_batter(context: dict, batter_name: str, mlbid: str = "") -> dict | None:
    """
    Resolve a batter to their game context.
    Returns None if the batter's team / game can't be determined (pick is skipped).
    """
    if not context:
        return None
    norm = _normalize(batter_name)
    team_id = context["player_team"].get(norm)
    if team_id is None:
        return None

    game = context["games"].get(str(team_id))
    if game is None:
        return None

    abbr = config.TEAM_ID_TO_ABBREV
    team_abbr = abbr.get(team_id, "")
    opp_abbr = abbr.get(game["opp_team_id"], "")
    park_abbr = abbr.get(game["home_team_id"], "")

    spot = game.get("lineup_spot", {}).get(str(mlbid)) if mlbid else None
    expected_pa = PA_BY_SPOT.get(spot, config.HR_DEFAULT_PA)

    is_home = game.get("is_home", False)
    home_abbr = team_abbr if is_home else opp_abbr
    away_abbr = opp_abbr if is_home else team_abbr

    return {
        "team_id": team_id,
        "team_abbr": team_abbr,
        "opp_abbr": opp_abbr,
        "park_abbr": park_abbr,
        "home_abbr": home_abbr,
        "away_abbr": away_abbr,
        "opp_pitcher": game.get("opp_pitcher", ""),
        "time_utc": game.get("time_utc", ""),
        "is_home": is_home,
        "lineup_spot": spot,
        "expected_pa": expected_pa,
    }
