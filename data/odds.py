import json
from datetime import date
from pathlib import Path

import requests

import config

CACHE_DIR = Path(__file__).parent.parent / "cache"

# Only these three books are used for line shopping
ALLOWED_BOOKS = {"fanduel", "draftkings", "mybookieag"}
BOOK_DISPLAY = {"fanduel": "FanDuel", "draftkings": "DraftKings", "mybookieag": "MyBookie"}


def _raw_cache_path(date_str: str) -> Path:
    CACHE_DIR.mkdir(exist_ok=True)
    return CACHE_DIR / f"raw_odds_{date_str}.json"


def get_todays_props(api_key: str, date_str: str | None = None) -> list[dict]:
    if date_str is None:
        date_str = date.today().isoformat()

    raw_cache = _raw_cache_path(date_str)

    if raw_cache.exists():
        print(f"[odds] Loading raw odds from cache: {raw_cache.name}")
        with open(raw_cache) as f:
            raw_events = json.load(f)
    else:
        raw_events = _fetch_raw(api_key, date_str)
        with open(raw_cache, "w") as f:
            json.dump(raw_events, f, indent=2)
        print(f"[odds] Cached raw odds for {len(raw_events)} events to {raw_cache.name}")

    # Always parse from raw so the book filter applies even to cached data
    all_props = []
    for ev in raw_events:
        all_props.extend(_parse_event_odds(ev["odds"], ev["home_team"], ev["away_team"]))

    print(f"[odds] {len(all_props)} props from {', '.join(BOOK_DISPLAY.values())}")
    return all_props


def _fetch_raw(api_key: str, date_str: str) -> list[dict]:
    print("[odds] Fetching today's MLB games from The Odds API...")
    events_resp = requests.get(
        f"{config.ODDS_API_BASE}/sports/baseball_mlb/events",
        params={"apiKey": api_key},
        timeout=15,
    )
    events_resp.raise_for_status()
    events = events_resp.json()

    if not events:
        print("[odds] No MLB events found for today.")
        return []

    print(f"[odds] Found {len(events)} games. Fetching K prop lines...")
    raw_events = []

    for event in events:
        event_id = event["id"]
        odds_resp = requests.get(
            f"{config.ODDS_API_BASE}/sports/baseball_mlb/events/{event_id}/odds",
            params={
                "apiKey": api_key,
                "markets": "pitcher_strikeouts",
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
    pitcher_data: dict[str, dict] = {}

    for book in event_odds.get("bookmakers", []):
        if book["key"] not in ALLOWED_BOOKS:
            continue
        book_name = BOOK_DISPLAY.get(book["key"], book["title"])

        for market in book.get("markets", []):
            if market["key"] != "pitcher_strikeouts":
                continue
            for outcome in market.get("outcomes", []):
                name = outcome["description"]
                side = outcome["name"]
                line = outcome["point"]
                price = outcome["price"]

                if name not in pitcher_data:
                    pitcher_data[name] = {
                        "pitcher": name,
                        "home_team": home_team,
                        "away_team": away_team,
                        "line": line,
                        "over_odds": None,
                        "over_book": None,
                        "under_odds": None,
                        "under_book": None,
                    }

                entry = pitcher_data[name]
                if side == "Over":
                    if entry["over_odds"] is None or price > entry["over_odds"]:
                        entry["over_odds"] = price
                        entry["over_book"] = book_name
                elif side == "Under":
                    if entry["under_odds"] is None or price > entry["under_odds"]:
                        entry["under_odds"] = price
                        entry["under_book"] = book_name

    return [p for p in pitcher_data.values() if p["over_odds"] is not None and p["under_odds"] is not None]
