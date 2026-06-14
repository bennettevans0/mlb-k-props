import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd


def _build_html(
    edges_df: pd.DataFrame,
    date_str: str,
    dropped: list[dict],
    starter_error: str | None,
) -> str:
    positive = edges_df[edges_df["Edge%"].str.startswith("+")]
    negative = edges_df[edges_df["Edge%"].str.startswith("-")]

    th = "style=\"background:#1a1a2e;color:#fff;padding:8px 12px;text-align:left;white-space:nowrap\""

    def df_to_html_rows(df: pd.DataFrame) -> str:
        rows = ""
        for _, row in df.iterrows():
            edge = row["Edge%"]
            color = "#1a7f37" if edge.startswith("+") else "#cf222e"
            rows += f"""
            <tr>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0">{row['Pitcher']}</td>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0">{row['Team']}</td>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0">{row['Opp']}</td>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0;text-align:center">{row['Proj K']}</td>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0;text-align:center">{row['Line']}</td>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0;text-align:center"><b>{row['Side']}</b></td>
              <td style="padding:7px 12px;border-bottom:1px solid #e0e0e0;text-align:center;color:{color};font-weight:bold">{edge}</td>
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
) -> None:
    subject = f"MLB K Props — {date_str} ({len(edges_df[edges_df['Edge%'].str.startswith('+')])} plays)"
    html = _build_html(edges_df, date_str, dropped or [], starter_error)

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
