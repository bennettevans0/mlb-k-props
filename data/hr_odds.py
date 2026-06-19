"""
Anytime home-run odds from The Odds API.

Mirrors data/odds.py but for the `batter_home_runs` market. "Anytime HR" is the
Over 0.5 line (point == 0.5). We keep the same three-book filter the K side uses.

Returned props (one per batter, best price across the allowed books):
    {
        "batter":     str,
        "home_team":  str,   # Odds API full name, e.g. "New York Yankees"
        "away_team":  str,
        "line":       0.5,
        "yes_odds":   int,   # American odds for "Over 0.5" (anytime HR = Yes)
        "yes_book":   str,
        "no_odds":    int | None,   # "Under 0.5" if a book offers it (for de-vig)
        "no_book":    str | None,
    }
"""
import json
from datetime import date
from pathlib import Path

import requests

import config
from data.odds import ALLOWED_BOOKS, BOOK_DISPLAY

CACHE_DIR = Path(__file__).parent.parent / "cache"

HR_MARKET = "batter_home_runs"
ANYTIME_POINT = 0.5


def _raw_cache_path(date_str: str) -> Path:
    CACHE_DIR.mkdir(exist_ok=True)
    return CACHE_DIR / f"raw_hr_odds_{date_str}.json"


def get_todays_hr_props(api_key: str, date_str: str | None = None) -> list[dict]:
    if date_str is None:
        date_str = date.today().isoformat()

    raw_cache = _raw_cache_path(date_str)

    if raw_cache.exists():
        print(f"[hr-odds] Loading raw HR odds from cache: {raw_cache.name}")
        with open(raw_cache) as f:
            raw_events = json.load(f)
    else:
        raw_events = _fetch_raw(api_key, date_str)
        with open(raw_cache, "w") as f:
            json.dump(raw_events, f, indent=2)
        print(f"[hr-odds] Cached raw HR odds for {len(raw_events)} events to {raw_cache.name}")

    all_props = []
    for ev in raw_events:
        all_props.extend(_parse_event_odds(ev["odds"], ev["home_team"], ev["away_team"]))

    print(f"[hr-odds] {len(all_props)} anytime-HR props from {', '.join(BOOK_DISPLAY.values())}")
    return all_props


def _fetch_raw(api_key: str, date_str: str) -> list[dict]:
    print("[hr-odds] Fetching today's MLB games from The Odds API...")
    events_resp = requests.get(
        f"{config.ODDS_API_BASE}/sports/baseball_mlb/events",
        params={"apiKey": api_key},
        timeout=15,
    )
    events_resp.raise_for_status()
    events = events_resp.json()

    if not events:
        print("[hr-odds] No MLB events found for today.")
        return []

    print(f"[hr-odds] Found {len(events)} games. Fetching anytime-HR lines...")
    raw_events = []

    for event in events:
        event_id = event["id"]
        odds_resp = requests.get(
            f"{config.ODDS_API_BASE}/sports/baseball_mlb/events/{event_id}/odds",
            params={
                "apiKey": api_key,
                "markets": HR_MARKET,
                "oddsFormat": "american",
                "bookmakers": ",".join(ALLOWED_BOOKS),
            },
            timeout=15,
        )
        if odds_resp.status_code in (404, 422):
            continue
        odds_resp.raise_for_status()
        raw_events.append({
            "home_team": event.get("home_team", ""),
            "away_team": event.get("away_team", ""),
            "odds": odds_resp.json(),
        })

    return raw_events


def _parse_event_odds(event_odds: dict, home_team: str, away_team: str) -> list[dict]:
    batter_data: dict[str, dict] = {}

    for book in event_odds.get("bookmakers", []):
        if book["key"] not in ALLOWED_BOOKS:
            continue
        book_name = BOOK_DISPLAY.get(book["key"], book["title"])

        for market in book.get("markets", []):
            if market["key"] != HR_MARKET:
                continue
            for outcome in market.get("outcomes", []):
                # Only the anytime line (Over/Under 0.5); skip 1.5+ (2+ HR) markets.
                if outcome.get("point") != ANYTIME_POINT:
                    continue
                name = outcome["description"]
                side = outcome["name"]
                price = outcome["price"]

                if name not in batter_data:
                    batter_data[name] = {
                        "batter": name,
                        "home_team": home_team,
                        "away_team": away_team,
                        "line": ANYTIME_POINT,
                        "yes_odds": None,
                        "yes_book": None,
                        "no_odds": None,
                        "no_book": None,
                    }

                entry = batter_data[name]
                if side == "Over":
                    if entry["yes_odds"] is None or price > entry["yes_odds"]:
                        entry["yes_odds"] = price
                        entry["yes_book"] = book_name
                elif side == "Under":
                    if entry["no_odds"] is None or price > entry["no_odds"]:
                        entry["no_odds"] = price
                        entry["no_book"] = book_name

    # An anytime-HR pick only needs a Yes price; No is optional (used for de-vig).
    return [p for p in batter_data.values() if p["yes_odds"] is not None]
