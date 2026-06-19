"""
Intraday anytime-HR scan.

Anytime-HR lines aren't posted at 8 AM — the books put them up a few hours before
first pitch. This script is meant to run every couple of hours through the day
(via a Windows scheduled task). Each run:

  1. Runs the HR model against whatever HR lines are currently posted.
  2. Finds picks that clear the edge threshold and are NOT already logged today.
  3. ONLY if there are new picks: logs them, emails an HR-only alert, refreshes the
     site's HR picks (preserving the morning run's K picks), and publishes.

If there are no new picks (no lines yet, or everything already alerted), it does
nothing and sends no email. It never touches the K model, grading, or results.
"""
from datetime import date

import config
import main
from hr_model import run_hr_model
from notify.email import send_hr_alert


def main_scan():
    api_key = config.get_api_key()
    date_str = date.today().isoformat()
    season = int(date_str[:4])

    hr_df, n_props = run_hr_model(api_key, date_str, season, use_cache=False)  # always re-fetch live lines
    if hr_df is None or hr_df.empty:
        print("[hr-scan] No anytime-HR picks this scan.")
        return

    # Which picks are new (not already logged today)?
    existing = main._existing_pick_keys()
    is_new = hr_df.apply(
        lambda row: (date_str, row["Batter"], str(row["Line"]), "HR") not in existing,
        axis=1,
    )
    new_df = hr_df[is_new]

    if new_df.empty:
        print("[hr-scan] HR picks found, but all already logged today — no email.")
        return

    print(f"[hr-scan] {len(new_df)} NEW HR pick(s) found.")
    main.log_hr_picks(hr_df, date_str)   # dedups; writes only the new rows

    if config.GMAIL_USER and config.GMAIL_PASSWORD:
        try:
            send_hr_alert(new_df, date_str, config.GMAIL_TO, config.GMAIL_USER, config.GMAIL_PASSWORD)
        except Exception as exc:
            print(f"[hr-scan] email failed: {exc}")
    else:
        print("[hr-scan] email skipped (no GMAIL creds).")

    # Refresh site HR picks (all of today's current HR picks) and publish.
    main.scan_update_site_hr(hr_df, date_str, n_props)
    main.publish_site(date_str)


if __name__ == "__main__":
    main_scan()
