import re
import unicodedata

import requests

MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"


def _normalize(name: str) -> str:
    """Lowercase, strip accents, remove Jr./Sr./II/III, collapse whitespace."""
    # Decompose accented chars then drop combining marks (e.g. é → e)
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.lower()
    # Remove generational suffixes
    name = re.sub(r"\b(jr\.?|sr\.?|ii|iii|iv)\b", "", name)
    # Remove stray periods (e.g. "A.J." → "aj")
    name = name.replace(".", "")
    return re.sub(r"\s+", " ", name).strip()


def get_probable_starters(date_str: str) -> tuple[dict[str, str], str | None]:
    """
    Returns ({normalized_name: display_name}, error_message_or_None).
    Fetches probable pitchers from the MLB Stats API schedule endpoint.
    """
    try:
        resp = requests.get(
            MLB_SCHEDULE_URL,
            params={"sportId": 1, "date": date_str, "hydrate": "probablePitcher"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return {}, f"MLB API error: {exc}"

    starters: dict[str, str] = {}
    for date_entry in data.get("dates", []):
        for game in date_entry.get("games", []):
            for side in ("home", "away"):
                pitcher = game["teams"][side].get("probablePitcher")
                if pitcher:
                    full_name = pitcher["fullName"]
                    starters[_normalize(full_name)] = full_name

    if not starters:
        return {}, "MLB API returned no probable starters (too early or off-day?)"

    return starters, None


def filter_to_starters(
    edges_df,
    starters: dict[str, str],
) -> tuple:
    """
    Split edges_df into (verified_df, dropped_list).
    dropped_list entries: {"pitcher": name, "reason": str}
    """
    keep, drop = [], []
    for _, row in edges_df.iterrows():
        norm = _normalize(row["Pitcher"])
        if norm in starters:
            keep.append(row)
        else:
            drop.append({"pitcher": row["Pitcher"], "reason": "not listed as probable starter"})

    import pandas as pd
    verified = pd.DataFrame(keep).reset_index(drop=True) if keep else pd.DataFrame(columns=edges_df.columns)
    return verified, drop
