"""
Kalshi market data (READ-ONLY) for best-price line shopping.

Market data on Kalshi is public — no API key, no request signing needed to read
prices (only placing trades requires auth, which this project never does).

This module fetches the MLB per-game strikeout (KXMLBKS) and home-run (KXMLBHR)
markets and merges their prices into the K/HR props the models already evaluate,
choosing the lowest-cost (best) price per side and recording the winning book.

Discovery (logs/kalshi_discovery.json) confirmed the real API shape:
  - prices are dollar strings, e.g. yes_ask_dollars="0.07" == 0.07 implied prob
  - floor_strike IS the Over half-point line (a "6+ strikeouts" market -> 5.5)
  - status "active" means tradeable; liquidity in volume_fp / open_interest_fp
  - player name is in yes_sub_title ("Landen Roupp: 6+")
"""
import json
import urllib.request

import config
from data.starters import _normalize
from model.edge import american_to_prob


def _get(path: str) -> dict:
    req = urllib.request.Request(config.KALSHI_BASE + path, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def get_mlb_markets(series_ticker: str) -> list[dict]:
    """All currently-open markets for a series (handles pagination)."""
    markets: list[dict] = []
    cursor = None
    for _ in range(25):  # safety cap on pages
        q = f"/markets?series_ticker={series_ticker}&status=open&limit=200"
        if cursor:
            q += f"&cursor={cursor}"
        data = _get(q)
        markets.extend(data.get("markets", []))
        cursor = data.get("cursor")
        if not cursor:
            break
    return markets


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def kalshi_fee(p: float | None) -> float:
    """Per-contract fee added to Kalshi cost before comparison. Configurable; 0 when disabled."""
    if not config.KALSHI_FEE_ENABLED or p is None:
        return 0.0
    return config.KALSHI_FEE_COEF * p * (1 - p)


def american_from_prob(p: float | None) -> int | None:
    """Implied cost (0-1) -> American odds. None if degenerate."""
    if p is None or p <= 0 or p >= 1:
        return None
    return round((1 - p) / p * 100) if p < 0.5 else -round(p / (1 - p) * 100)


def _player(m: dict) -> str:
    sub = m.get("yes_sub_title") or m.get("title") or ""
    return sub.split(":")[0].strip()


def _side_ok(m: dict, bid, ask, spread_cents) -> bool:
    """
    Liquidity guard for ONE side (the side we'd buy at `ask`). Requires a genuine,
    fillable two-sided market — not a placeholder/one-sided book. Kalshi player-prop
    markets often sit at yes_bid=0.00 / yes_ask=0.01 (no real buyers); the lone 1c
    ask is NOT a real price, so bid>0 and ask<1.0 are required.
    """
    if (m.get("status") or "") != "active":
        return False
    if bid is None or ask is None:
        return False
    if bid <= 0 or ask >= 1.0:          # one-sided / degenerate -> not genuinely priced
        return False
    oi = _f(m.get("open_interest_fp")) or 0.0
    if oi < config.KALSHI_MIN_OPEN_INTEREST:
        return False
    if spread_cents is None or spread_cents > config.KALSHI_MAX_SPREAD_CENTS:
        return False
    return True


def _spread(bid, ask):
    return round((ask - bid) * 100) if (bid is not None and ask is not None) else None


def normalize_k_markets(raw: list[dict]) -> dict:
    """{(player_norm, line): market info} for strikeout markets (YES=Over floor_strike)."""
    idx = {}
    for m in raw:
        line = _f(m.get("floor_strike"))
        if line is None:
            continue
        yb, ya = _f(m.get("yes_bid_dollars")), _f(m.get("yes_ask_dollars"))
        nb, na = _f(m.get("no_bid_dollars")), _f(m.get("no_ask_dollars"))
        player = _player(m)
        idx[(_normalize(player), line)] = {
            "player": player, "line": line, "ticker": m.get("ticker"),
            "yes_ask": ya, "no_ask": na,
            "over_cost": (ya + kalshi_fee(ya)) if ya is not None else None,    # buy YES = Over
            "under_cost": (na + kalshi_fee(na)) if na is not None else None,   # buy NO = Under
            "over_ok": _side_ok(m, yb, ya, _spread(yb, ya)),                   # liquidity for the YES/Over side
            "under_ok": _side_ok(m, nb, na, _spread(nb, na)),                  # liquidity for the NO/Under side
            "volume": _f(m.get("volume_fp")), "open_interest": _f(m.get("open_interest_fp")),
            "over_spread": _spread(yb, ya), "under_spread": _spread(nb, na), "status": m.get("status"),
        }
    return idx


def normalize_hr_markets(raw: list[dict]) -> dict:
    """{player_norm: market info} for anytime-HR markets (YES on floor_strike 0.5)."""
    idx = {}
    for m in raw:
        if _f(m.get("floor_strike")) != 0.5:   # anytime HR only
            continue
        yb, ya = _f(m.get("yes_bid_dollars")), _f(m.get("yes_ask_dollars"))
        player = _player(m)
        idx[_normalize(player)] = {
            "player": player, "line": 0.5, "ticker": m.get("ticker"),
            "yes_ask": ya,
            "yes_cost": (ya + kalshi_fee(ya)) if ya is not None else None,
            "yes_ok": _side_ok(m, yb, ya, _spread(yb, ya)),
            "volume": _f(m.get("volume_fp")), "open_interest": _f(m.get("open_interest_fp")),
            "spread": _spread(yb, ya), "status": m.get("status"),
        }
    return idx


def _better(kalshi_cost, cur_cost) -> bool:
    """Is the Kalshi cost cheaper? Tie-break prefers FD/DK when configured."""
    if kalshi_cost is None:
        return False
    if config.KALSHI_TIEBREAK_PREFER_ODDSAPI:
        return kalshi_cost < cur_cost - 1e-9
    return kalshi_cost <= cur_cost + 1e-9


def best_price_k(props: list[dict]) -> list[dict]:
    """
    Merge Kalshi K prices into the props (best price per side). Mutates each prop's
    over/under odds+book in place when Kalshi is cheaper and liquid. Returns the
    3-way comparison rows (for dry-run display). No-ops if Kalshi is unreachable.
    """
    rows = []
    try:
        idx = normalize_k_markets(get_mlb_markets(config.KALSHI_K_SERIES))
    except Exception as e:
        print(f"[kalshi] K fetch failed, using FD/DK only: {e}")
        return rows

    for prop in props:
        km = idx.get((_normalize(prop["pitcher"]), prop["line"]))
        for side, odds_key, book_key, cost_key, ok_key in (
            ("over", "over_odds", "over_book", "over_cost", "over_ok"),
            ("under", "under_odds", "under_book", "under_cost", "under_ok"),
        ):
            cur_odds = prop.get(odds_key)
            if cur_odds is None:
                continue
            cur_cost = american_to_prob(cur_odds)
            row = {
                "market": "K", "player": prop["pitcher"], "line": prop["line"], "side": side,
                "oddsapi_book": prop.get(book_key), "oddsapi_odds": cur_odds, "oddsapi_cost": round(cur_cost, 4),
                "kalshi_odds": None, "kalshi_cost": None, "kalshi_liquid": None,
                "chosen": prop.get(book_key),
            }
            if km and km.get(cost_key) is not None:
                kc = km[cost_key]
                ka = american_from_prob(kc)
                ok = km[ok_key]
                row["kalshi_odds"], row["kalshi_cost"], row["kalshi_liquid"] = ka, round(kc, 4), ok
                if ok and ka is not None and _better(kc, cur_cost):
                    prop[odds_key] = ka
                    prop[book_key] = "Kalshi"
                    row["chosen"] = "Kalshi"
            rows.append(row)
    n_win = sum(1 for r in rows if r["chosen"] == "Kalshi")
    print(f"[kalshi] K: {len(idx)} markets; {n_win} side(s) improved to Kalshi.")
    return rows


def best_price_hr(hr_props: list[dict]) -> list[dict]:
    """
    Merge Kalshi anytime-HR prices into the HR props (YES side only). Mutates
    yes_odds/yes_book in place when Kalshi is cheaper and liquid. Returns comparison rows.
    """
    rows = []
    try:
        idx = normalize_hr_markets(get_mlb_markets(config.KALSHI_HR_SERIES))
    except Exception as e:
        print(f"[kalshi] HR fetch failed, using FD/DK only: {e}")
        return rows

    for prop in hr_props:
        km = idx.get(_normalize(prop["batter"]))
        cur_odds = prop.get("yes_odds")
        if cur_odds is None:
            continue
        cur_cost = american_to_prob(cur_odds)
        row = {
            "market": "HR", "player": prop["batter"], "line": 0.5, "side": "yes",
            "oddsapi_book": prop.get("yes_book"), "oddsapi_odds": cur_odds, "oddsapi_cost": round(cur_cost, 4),
            "kalshi_odds": None, "kalshi_cost": None, "kalshi_liquid": None,
            "chosen": prop.get("yes_book"),
        }
        if km and km.get("yes_cost") is not None:
            kc = km["yes_cost"]
            ka = american_from_prob(kc)
            ok = km["yes_ok"]
            row["kalshi_odds"], row["kalshi_cost"], row["kalshi_liquid"] = ka, round(kc, 4), ok
            if ok and ka is not None and _better(kc, cur_cost):
                prop["yes_odds"] = ka
                prop["yes_book"] = "Kalshi"
                row["chosen"] = "Kalshi"
        rows.append(row)
    n_win = sum(1 for r in rows if r["chosen"] == "Kalshi")
    print(f"[kalshi] HR: {len(idx)} markets; {n_win} pick(s) improved to Kalshi.")
    return rows


def print_price_table(rows: list[dict]) -> None:
    """Dry-run: print the 3-way (FD/DK vs Kalshi) price comparison."""
    if not rows:
        print("  (no Kalshi comparison rows)")
        return
    hdr = f"  {'Mkt':3} {'Player':20} {'Side':5} {'Line':5} {'FD/DK':>7} {'cost':>6} {'Kalshi':>7} {'cost':>6} {'liq':4}  BEST"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for r in rows:
        ko = "" if r["kalshi_odds"] is None else f"{r['kalshi_odds']:+d}"
        kc = "" if r["kalshi_cost"] is None else f"{r['kalshi_cost']:.3f}"
        liq = "" if r["kalshi_liquid"] is None else ("yes" if r["kalshi_liquid"] else "NO")
        oa = "" if r["oddsapi_odds"] is None else f"{int(r['oddsapi_odds']):+d}"
        print(f"  {r['market']:3} {r['player'][:20]:20} {r['side']:5} {str(r['line']):5} "
              f"{oa:>7} {r['oddsapi_cost']:.3f} {ko:>7} {kc:>6} {liq:4}  {r['chosen']}")
