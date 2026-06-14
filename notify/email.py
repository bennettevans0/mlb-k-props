import smtplib
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import pandas as pd

PICKS_CSV   = Path(r"C:\Users\benne\OneDrive\Documents\KTracker\picks.csv")
RESULTS_CSV = Path(r"C:\Users\benne\OneDrive\Documents\KTracker\results.csv")

# MLB team logo URLs keyed by abbreviation
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


def _logo_img(abbr: str) -> str:
    """Return an <img> tag for the team logo, or just the abbr if not found."""
    url = TEAM_LOGOS.get(abbr.upper())
    if not url:
        return abbr
    return (
        f'<img src="{url}" alt="{abbr}" '
        f'style="height:20px;width:20px;vertical-align:middle;margin-right:4px">'
        f'{abbr}'
    )


def _load_total_record() -> str:
    """Return overall W-L-P record string from results.csv."""
    if not RESULTS_CSV.exists():
        return "No record yet"
    df = pd.read_csv(RESULTS_CSV)
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
    return f"<b>Record:</b> {record} &nbsp;|&nbsp; <b>Hit:</b> {hit:.1f}% &nbsp;|&nbsp; <b>P&L:</b> {units:+.2f}u &nbsp;|&nbsp; <b>ROI:</b> {roi:+.1f}%"


def _load_last_night_record() -> tuple[str, str]:
    """
    Return (summary_line, grades_html) for picks graded on the most recent
    night (yesterday or the last date with graded results).
    """
    if not RESULTS_CSV.exists():
        return "No graded results yet", ""

    df = pd.read_csv(RESULTS_CSV)
    settled = df[df["result"].isin(["win", "loss", "push"])]
    if settled.empty:
        return "No graded results yet", ""

    # Find the most recent graded date
    last_date = settled["game_date"].max()
    last = settled[settled["game_date"] == last_date]

    w = (last["result"] == "win").sum()
    l = (last["result"] == "loss").sum()
    p = (last["result"] == "push").sum()
    decided = w + l
    hit = w / decided * 100 if decided else 0
    units = last["profit_units"].sum()
    record = f"{w}-{l}" + (f"-{p}" if p else "")
    summary = f"{last_date}: <b>Record:</b> {record} &nbsp;|&nbsp; <b>Hit:</b> {hit:.1f}% &nbsp;|&nbsp; <b>P&L:</b> {units:+.2f}u"

    # Build mini table of those picks
    def _result_color(result: str) -> str:
        return {"win": "#1a7f37", "loss": "#cf222e", "push": "#888888"}.get(result, "#000")

    rows_html = ""
    for _, r in last.iterrows():
        color = _result_color(r["result"])
        emoji = {"win": "✅", "loss": "❌", "push": "➖"}.get(r["result"], "")
        rows_html += f"""
        <tr>
          <td style="padding:6px 10px;border-bottom:1px solid #e8e8e8">{r['pitcher_name']}</td>
          <td style="padding:6px 10px;border-bottom:1px solid #e8e8e8;text-align:center">{r['pick'].upper()} {r['line']}</td>
          <td style="padding:6px 10px;border-bottom:1px solid #e8e8e8;text-align:center">{int(r['actual_K']) if pd.notna(r.get('actual_K')) else '—'} Ks</td>
          <td style="padding:6px 10px;border-bottom:1px solid #e8e8e8;text-align:center;color:{color};font-weight:bold">{emoji} {r['result'].upper()}</td>
          <td style="padding:6px 10px;border-bottom:1px solid #e8e8e8;text-align:center;color:{color}">{r['profit_units']:+.2f}u</td>
        </tr>"""

    th = "style=\"background:#2d2d2d;color:#fff;padding:7px 10px;text-align:left;font-size:12px\""
    grades_html = f"""
    <table style="border-collapse:collapse;width:100%;font-size:13px;margin-top:8px">
      <thead><tr>
        <th {th}>Pitcher</th><th {th}>Pick</th><th {th}>Actual</th>
        <th {th}>Result</th><th {th}>P&L</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>"""

    return summary, grades_html


def _build_html(
    edges_df: pd.DataFrame,
    date_str: str,
    dropped: list[dict],
    starter_error: str | None,
    n_props: int = 0,
) -> str:
    total_record = _load_total_record()
    last_night_summary, last_night_grades = _load_last_night_record()

    record_block = f"""
    <div style="margin:16px 0">
      <div style="background:#f6f8fa;border-radius:8px;padding:14px 18px;margin-bottom:10px">
        <span style="font-weight:bold;color:#1a1a2e;font-size:14px">📊 Season Record</span><br>
        <span style="font-size:13px">{total_record}</span>
      </div>
      <div style="background:#f6f8fa;border-radius:8px;padding:14px 18px">
        <span style="font-weight:bold;color:#1a1a2e;font-size:14px">🌙 Last Night</span><br>
        <span style="font-size:13px">{last_night_summary}</span>
        {last_night_grades}
      </div>
    </div>"""

    if edges_df.empty:
        return f"""
    <html><body style="font-family:sans-serif;max-width:900px;margin:0 auto;padding:16px">
      <h2 style="margin-bottom:4px">⚾ MLB K Props — {date_str}</h2>
      {record_block}
      <p style="background:#fff8c5;border-left:4px solid #d4a017;padding:12px 16px;
                 margin:20px 0;font-size:14px">
        <b>No qualifying picks today.</b><br>
        {n_props} prop line{'s' if n_props != 1 else ''} evaluated — none cleared the edge threshold.
      </p>
    </body></html>"""

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
            team_cell = _logo_img(row["Team"])
            opp_cell  = _logo_img(row["Opp"])
            rows += f"""
            <tr>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0">{row['Pitcher']}</td>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0">{team_cell}</td>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0">{opp_cell}</td>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0;text-align:center">{row['Proj K']}</td>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0;text-align:center">{row['Line']}</td>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0;text-align:center"><b>{row['Side']}</b></td>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0;text-align:center;color:{color};font-weight:bold">{edge_cell}</td>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0;text-align:center">{row['Odds']}</td>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0">{row['Book']}</td>
            </tr>"""
        return rows

    def table_section(title: str, df: pd.DataFrame, accent: str) -> str:
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

    def starter_notice() -> str:
        if starter_error:
            return f"""
            <p style="background:#fff8c5;border-left:4px solid #d4a017;padding:10px 14px;
                       margin:16px 0;font-size:13px">
              ⚠️ <b>Starter verification skipped</b> — {starter_error}<br>
              Picks above are unfiltered and may include relievers or scratched starters.
            </p>"""
        if not dropped:
            return "<p style=\"color:#666;font-size:13px\">✅ All picks verified as probable starters.</p>"
        rows = "".join(
            f"<li><b>{d['pitcher']}</b> — {d['reason']}</li>" for d in dropped
        )
        return f"""
        <div style="margin-top:20px">
          <h3 style="color:#888;margin-bottom:6px">Dropped — not confirmed starters ({len(dropped)})</h3>
          <ul style="font-size:13px;color:#555;margin:0;padding-left:20px">{rows}</ul>
        </div>"""

    return f"""
    <html><body style="font-family:sans-serif;max-width:900px;margin:0 auto;padding:16px">
      <h2 style="margin-bottom:4px">⚾ MLB K Props — {date_str}</h2>
      <p style="color:#666;margin-top:0">{len(edges_df)} total edges &nbsp;|&nbsp;
         {len(positive)} plays &nbsp;|&nbsp; {len(negative)} fades</p>
      {record_block}
      {table_section("Plays (model favors)", positive, "#1a7f37")}
      {table_section("Fades (model against)", negative, "#cf222e")}
      {starter_notice()}
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
) -> None:
    if edges_df.empty:
        n_plays = 0
    else:
        n_plays = len(edges_df[edges_df["Edge%"].str.startswith("+")])
    subject = f"MLB K Props — {date_str} ({n_plays} plays)"
    html = _build_html(edges_df, date_str, dropped or [], starter_error, n_props=n_props)

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
