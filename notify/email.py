import smtplib
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

PICKS_CSV   = Path(r"C:\Users\benne\OneDrive\Documents\KTracker\picks.csv")
RESULTS_CSV = Path(r"C:\Users\benne\OneDrive\Documents\KTracker\results.csv")

PACIFIC = ZoneInfo("America/Los_Angeles")

# MLB team logo URLs keyed by abbreviation.
TEAM_LOGOS: dict[str, str] = {
    "ARI": "https://www.mlbstatic.com/team-logos/109.svg",
    "ATL": "https://www.mlbstatic.com/team-logos/144.svg",
    "BAL": "https://www.mlbstatic.com/team-logos/110.svg",
    "BOS": "https://www.mlbstatic.com/team-logos/111.svg",
    "CHC": "https://www.mlbstatic.com/team-logos/112.svg",
    "CWS": "https://www.mlbstatic.com/team-logos/145.svg",
    "CIN": "https://www.mlbstatic.com/team-logos/113.svg",
    "CLE": "https://www.mlbstatic.com/team-logos/114.svg",
    "COL": "https://www.mlbstatic.com/team-logos/115.svg",
    "DET": "https://www.mlbstatic.com/team-logos/116.svg",
    "HOU": "https://www.mlbstatic.com/team-logos/117.svg",
    "KC":  "https://www.mlbstatic.com/team-logos/118.svg",
    "LAA": "https://www.mlbstatic.com/team-logos/108.svg",
    "LAD": "https://www.mlbstatic.com/team-logos/119.svg",
    "MIA": "https://www.mlbstatic.com/team-logos/146.svg",
    "MIL": "https://www.mlbstatic.com/team-logos/158.svg",
    "MIN": "https://www.mlbstatic.com/team-logos/142.svg",
    "NYM": "https://www.mlbstatic.com/team-logos/121.svg",
    "NYY": "https://www.mlbstatic.com/team-logos/147.svg",
    "OAK": "https://www.mlbstatic.com/team-logos/133.svg",
    "PHI": "https://www.mlbstatic.com/team-logos/143.svg",
    "PIT": "https://www.mlbstatic.com/team-logos/134.svg",
    "SD":  "https://www.mlbstatic.com/team-logos/135.svg",
    "SEA": "https://www.mlbstatic.com/team-logos/136.svg",
    "SF":  "https://www.mlbstatic.com/team-logos/137.svg",
    "STL": "https://www.mlbstatic.com/team-logos/138.svg",
    "TB":  "https://www.mlbstatic.com/team-logos/139.svg",
    "TEX": "https://www.mlbstatic.com/team-logos/140.svg",
    "TOR": "https://www.mlbstatic.com/team-logos/141.svg",
    "WSH": "https://www.mlbstatic.com/team-logos/120.svg",
}

# Normalize the various abbreviation styles used across the app (config style vs
# MLB-API style) to the keys in TEAM_LOGOS.
ABBR_ALIAS = {
    "CHW": "CWS", "KCR": "KC", "SDP": "SD", "SFG": "SF", "TBR": "TB",
    "WSN": "WSH", "WS": "WSH", "AZ": "ARI", "ATH": "OAK", "ARZ": "ARI",
}


def _canon_abbr(abbr: str) -> str:
    a = (abbr or "").strip().upper()
    return ABBR_ALIAS.get(a, a)


def _logo_img(abbr: str) -> str:
    """Return an <img> tag for the team logo, or the abbreviation text if unknown."""
    if not abbr or str(abbr).strip().lower() in ("", "nan", "none"):
        return "—"
    canon = _canon_abbr(abbr)
    url = TEAM_LOGOS.get(canon)
    if not url:
        return canon
    return (
        f'<img src="{url}" alt="{canon}" '
        f'style="height:20px;width:20px;vertical-align:middle;margin-right:4px">'
        f'{canon}'
    )


def _fmt_pacific(iso: str) -> str:
    """UTC ISO time -> 'h:mm AM/PM PT' in America/Los_Angeles, or '' if unparseable."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return ""
    s = dt.astimezone(PACIFIC).strftime("%I:%M %p")
    return s.lstrip("0") + " PT"


def _read_results() -> pd.DataFrame:
    df = pd.read_csv(RESULTS_CSV)
    if "prop_type" not in df.columns:
        df["prop_type"] = "K"
    df["prop_type"] = df["prop_type"].fillna("").replace("", "K")
    return df


def _record_line(df: pd.DataFrame) -> str:
    """One-line W-L / hit / P&L / ROI from a settled-results DataFrame."""
    settled = df[df["result"].isin(["win", "loss", "push"])]
    if settled.empty:
        return "No graded picks yet"
    w = (settled["result"] == "win").sum()
    l = (settled["result"] == "loss").sum()
    p = (settled["result"] == "push").sum()
    decided = w + l
    hit = w / decided * 100 if decided else 0
    units = settled["profit_units"].sum()
    roi = units / len(settled) * 100 if len(settled) else 0
    record = f"{w}-{l}" + (f"-{p}" if p else "")
    return (f"<b>Record:</b> {record} &nbsp;|&nbsp; <b>Hit:</b> {hit:.1f}% "
            f"&nbsp;|&nbsp; <b>P&L:</b> {units:+.2f}u &nbsp;|&nbsp; <b>ROI:</b> {roi:+.1f}%")


def _load_total_record(prop_type: str = "K") -> str:
    if not RESULTS_CSV.exists():
        return "No record yet"
    df = _read_results()
    return _record_line(df[df["prop_type"] == prop_type])


def _load_last_night_record(prop_type: str = "K") -> tuple[str, str]:
    """(summary_line, grades_html) for the most recent graded night of one prop type."""
    if not RESULTS_CSV.exists():
        return "No graded results yet", ""

    df = _read_results()
    df = df[df["prop_type"] == prop_type]
    settled = df[df["result"].isin(["win", "loss", "push"])]
    if settled.empty:
        return "No graded results yet", ""

    last_date = settled["game_date"].max()
    last = settled[settled["game_date"] == last_date]

    w = (last["result"] == "win").sum()
    l = (last["result"] == "loss").sum()
    p = (last["result"] == "push").sum()
    decided = w + l
    hit = w / decided * 100 if decided else 0
    units = last["profit_units"].sum()
    record = f"{w}-{l}" + (f"-{p}" if p else "")
    summary = (f"{last_date}: <b>Record:</b> {record} &nbsp;|&nbsp; <b>Hit:</b> {hit:.1f}% "
               f"&nbsp;|&nbsp; <b>P&L:</b> {units:+.2f}u")

    def _result_color(result: str) -> str:
        return {"win": "#1a7f37", "loss": "#cf222e", "push": "#888888"}.get(result, "#000")

    stat_label = "HR" if prop_type == "HR" else "Ks"
    rows_html = ""
    for _, r in last.iterrows():
        color = _result_color(r["result"])
        emoji = {"win": "✅", "loss": "❌", "push": "➖"}.get(r["result"], "")
        actual = int(r["actual_K"]) if pd.notna(r.get("actual_K")) else "—"
        pick_txt = "Yes" if prop_type == "HR" else f"{str(r['pick']).upper()} {r['line']}"
        rows_html += f"""
        <tr>
          <td style="padding:6px 10px;border-bottom:1px solid #e8e8e8">{r['pitcher_name']}</td>
          <td style="padding:6px 10px;border-bottom:1px solid #e8e8e8;text-align:center">{pick_txt}</td>
          <td style="padding:6px 10px;border-bottom:1px solid #e8e8e8;text-align:center">{actual} {stat_label}</td>
          <td style="padding:6px 10px;border-bottom:1px solid #e8e8e8;text-align:center;color:{color};font-weight:bold">{emoji} {r['result'].upper()}</td>
          <td style="padding:6px 10px;border-bottom:1px solid #e8e8e8;text-align:center;color:{color}">{r['profit_units']:+.2f}u</td>
        </tr>"""

    th = "style=\"background:#2d2d2d;color:#fff;padding:7px 10px;text-align:left;font-size:12px\""
    grades_html = f"""
    <table style="border-collapse:collapse;width:100%;font-size:13px;margin-top:8px">
      <thead><tr>
        <th {th}>{'Batter' if prop_type == 'HR' else 'Pitcher'}</th><th {th}>Pick</th><th {th}>Actual</th>
        <th {th}>Result</th><th {th}>P&L</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>"""

    return summary, grades_html


def _record_block() -> str:
    """Season + last-night record cards, split into K and HR."""
    k_total = _load_total_record("K")
    k_last, k_grades = _load_last_night_record("K")
    hr_total = _load_total_record("HR")
    hr_last, hr_grades = _load_last_night_record("HR")

    return f"""
    <div style="margin:16px 0">
      <div style="background:#f6f8fa;border-radius:8px;padding:14px 18px;margin-bottom:10px">
        <span style="font-weight:bold;color:#1a1a2e;font-size:14px">⚾ K — Season</span><br>
        <span style="font-size:13px">{k_total}</span>
      </div>
      <div style="background:#f6f8fa;border-radius:8px;padding:14px 18px;margin-bottom:10px">
        <span style="font-weight:bold;color:#1a1a2e;font-size:14px">⚾ K — Last Night</span><br>
        <span style="font-size:13px">{k_last}</span>
        {k_grades}
      </div>
      <div style="background:#fdf2f0;border-radius:8px;padding:14px 18px;margin-bottom:10px">
        <span style="font-weight:bold;color:#a3402d;font-size:14px">💣 HR — Season</span><br>
        <span style="font-size:13px">{hr_total}</span>
      </div>
      <div style="background:#fdf2f0;border-radius:8px;padding:14px 18px">
        <span style="font-weight:bold;color:#a3402d;font-size:14px">💣 HR — Last Night</span><br>
        <span style="font-size:13px">{hr_last}</span>
        {hr_grades}
      </div>
    </div>"""


def _k_table(edges_df: pd.DataFrame) -> str:
    """K plays/fades tables (unchanged styling)."""
    if edges_df.empty:
        return ("<p style=\"background:#fff8c5;border-left:4px solid #d4a017;padding:12px 16px;"
                "margin:16px 0;font-size:14px\"><b>No qualifying K picks today.</b></p>")

    positive = edges_df[edges_df["Edge%"].str.startswith("+")]
    negative = edges_df[edges_df["Edge%"].str.startswith("-")]
    th = "style=\"background:#1a1a2e;color:#fff;padding:8px 12px;text-align:left;white-space:nowrap\""

    def df_to_html_rows(df: pd.DataFrame) -> str:
        rows = ""
        for _, row in df.iterrows():
            edge = row["Edge%"]
            color = "#1a7f37" if edge.startswith("+") else "#cf222e"
            try:
                edge_val = float(edge.rstrip("%"))
            except ValueError:
                edge_val = 0.0
            if edge_val > 15.0:
                edge_cell = (
                    f"⚠️ {edge}<br>"
                    f"<span style=\"font-size:11px;font-weight:normal;color:#b35900\">"
                    f"verify manually — check pitch limits or roster news</span>"
                )
            else:
                edge_cell = edge
            rows += f"""
            <tr>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0">{row['Pitcher']}</td>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0">{_logo_img(row['Team'])}</td>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0">{_logo_img(row['Opp'])}</td>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0;text-align:center">{row['Proj K']}</td>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0;text-align:center">{row['Line']}</td>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0;text-align:center"><b>{row['Side']}</b></td>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0;text-align:center;color:{color};font-weight:bold">{edge_cell}</td>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0;text-align:center">{row['Odds']}</td>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0">{row['Book']}</td>
            </tr>"""
        return rows

    def section(title: str, df: pd.DataFrame, accent: str) -> str:
        if df.empty:
            return ""
        return f"""
        <h3 style="color:{accent};margin:24px 0 8px">{title} ({len(df)})</h3>
        <table style="border-collapse:collapse;width:100%;font-size:14px">
          <thead><tr>
            <th {th}>Pitcher</th><th {th}>Team</th><th {th}>Opp</th>
            <th {th}>Proj K</th><th {th}>Line</th><th {th}>Side</th>
            <th {th}>Edge%</th><th {th}>Odds</th><th {th}>Book</th>
          </tr></thead>
          <tbody>{df_to_html_rows(df)}</tbody>
        </table>"""

    return section("Plays (model favors)", positive, "#1a7f37") + \
        section("Fades (model against)", negative, "#cf222e")


def _hr_table(hr_df: pd.DataFrame | None, hr_n_props: int) -> str:
    """HR plays table: batter, team, matchup, opposing pitcher, model P, odds."""
    if hr_df is None or hr_df.empty:
        msg = "lines not posted yet" if hr_n_props == 0 else f"{hr_n_props} checked, none cleared the edge"
        return (f"<p style=\"background:#fbeeec;border-left:4px solid #a3402d;padding:12px 16px;"
                f"margin:16px 0;font-size:14px\"><b>No anytime-HR picks today</b> ({msg}).</p>")

    th = "style=\"background:#a3402d;color:#fff;padding:8px 12px;text-align:left;white-space:nowrap\""
    rows = ""
    for _, row in hr_df.iterrows():
        t = _fmt_pacific(row.get("_time", ""))
        time_html = f"<br><span style=\"font-size:11px;color:#888\">{t}</span>" if t else ""
        matchup = f"{_logo_img(row['Team'])} <span style=\"color:#888\">vs</span> {_logo_img(row['Opp'])}"
        rows += f"""
        <tr>
          <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0"><b>{row['Batter']}</b></td>
          <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0">{matchup}{time_html}</td>
          <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0">{row.get('Pitcher', '—')}</td>
          <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0;text-align:center;font-weight:bold">{row['Model P']}</td>
          <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0;text-align:center;color:#1a7f37;font-weight:bold">{row['Edge%']}</td>
          <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0;text-align:center">{row['Odds']}</td>
          <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0">{row['Book']}</td>
        </tr>"""

    return f"""
    <h3 style="color:#a3402d;margin:24px 0 8px">Anytime HR — Plays ({len(hr_df)})</h3>
    <table style="border-collapse:collapse;width:100%;font-size:14px">
      <thead><tr>
        <th {th}>Batter</th><th {th}>Matchup</th><th {th}>Pitcher</th>
        <th {th}>Model P</th><th {th}>Edge%</th><th {th}>Odds</th><th {th}>Book</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>"""


def _starter_notice(dropped: list[dict], starter_error: str | None) -> str:
    if starter_error:
        return f"""
        <p style="background:#fff8c5;border-left:4px solid #d4a017;padding:10px 14px;
                   margin:16px 0;font-size:13px">
          ⚠️ <b>Starter verification skipped</b> — {starter_error}<br>
          K picks above are unfiltered and may include relievers or scratched starters.
        </p>"""
    if not dropped:
        return ""
    rows = "".join(f"<li><b>{d['pitcher']}</b> — {d['reason']}</li>" for d in dropped)
    return f"""
    <div style="margin-top:20px">
      <h3 style="color:#888;margin-bottom:6px">K dropped — not confirmed starters ({len(dropped)})</h3>
      <ul style="font-size:13px;color:#555;margin:0;padding-left:20px">{rows}</ul>
    </div>"""


def _build_html(
    edges_df: pd.DataFrame,
    date_str: str,
    dropped: list[dict],
    starter_error: str | None,
    n_props: int = 0,
    hr_df: pd.DataFrame | None = None,
    hr_n_props: int = 0,
) -> str:
    n_k = 0 if edges_df.empty else len(edges_df[edges_df["Edge%"].str.startswith("+")])
    n_hr = 0 if (hr_df is None or hr_df.empty) else len(hr_df)

    return f"""
    <html><body style="font-family:sans-serif;max-width:900px;margin:0 auto;padding:16px">
      <h2 style="margin-bottom:4px">⚾ MLB Props — {date_str}</h2>
      <p style="color:#666;margin-top:0">{n_k} K play{'s' if n_k != 1 else ''}
         &nbsp;|&nbsp; {n_hr} HR play{'s' if n_hr != 1 else ''}</p>
      {_record_block()}

      <h2 style="border-bottom:3px solid #1a1a2e;padding-bottom:4px;margin-top:28px">⚾ Strikeouts</h2>
      {_k_table(edges_df)}
      {_starter_notice(dropped, starter_error)}

      <h2 style="border-bottom:3px solid #a3402d;padding-bottom:4px;margin-top:32px;color:#a3402d">💣 Home Runs</h2>
      {_hr_table(hr_df, hr_n_props)}
    </body></html>
    """


def send_picks(
    edges_df: pd.DataFrame,
    date_str: str,
    recipient: str,
    smtp_user: str,
    smtp_password: str,
    dropped: list[dict] | None = None,
    starter_error: str | None = None,
    n_props: int = 0,
    hr_df: pd.DataFrame | None = None,
    hr_n_props: int = 0,
) -> None:
    n_k = 0 if edges_df.empty else len(edges_df[edges_df["Edge%"].str.startswith("+")])
    n_hr = 0 if (hr_df is None or hr_df.empty) else len(hr_df)
    subject = f"MLB Props — {date_str} ({n_k} K, {n_hr} HR)"
    html = _build_html(
        edges_df, date_str, dropped or [], starter_error,
        n_props=n_props, hr_df=hr_df, hr_n_props=hr_n_props,
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = recipient
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, recipient, msg.as_string())

    print(f"[email] Sent to {recipient}")


def send_hr_alert(
    hr_df: pd.DataFrame,
    date_str: str,
    recipient: str,
    smtp_user: str,
    smtp_password: str,
) -> None:
    """Send an HR-only alert for newly-found anytime-HR picks (intraday scan)."""
    n = len(hr_df)
    subject = f"🔔 New anytime-HR pick{'s' if n != 1 else ''} — {date_str} ({n})"
    html = f"""
    <html><body style="font-family:sans-serif;max-width:900px;margin:0 auto;padding:16px">
      <h2 style="color:#a3402d;margin-bottom:4px">💣 New anytime-HR pick{'s' if n != 1 else ''} — {date_str}</h2>
      <p style="color:#666;margin-top:0">The intraday scan found {n} new HR edge{'s' if n != 1 else ''} the model likes.</p>
      {_hr_table(hr_df, n)}
      <div style="background:#fdf2f0;border-radius:8px;padding:12px 16px;margin-top:16px">
        <span style="font-weight:bold;color:#a3402d;font-size:13px">💣 HR — Season</span><br>
        <span style="font-size:13px">{_load_total_record('HR')}</span>
      </div>
      <p style="color:#888;font-size:12px;margin-top:16px">Anytime HR is high-variance — small, noisy edges. Flat 1u.</p>
    </body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = recipient
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, recipient, msg.as_string())

    print(f"[email] HR alert sent to {recipient}")
