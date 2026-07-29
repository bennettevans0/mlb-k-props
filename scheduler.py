"""
Persistent scheduler for the MLB props jobs — run this in a terminal and leave it open.

Because the PC gets fully shut down (which stops Windows Task Scheduler), this loop is
the reliable alternative: as long as the window is up it fires the jobs on time, and the
moment it STARTS it catches up a missed daily run (so turning the PC on after a shutdown
immediately posts that day's picks). A small state file dedups so nothing double-fires.

Jobs:
  - nightly grade + publish  -> k_tracker_1.py --publish   once/day, 00:30-07:59
  - daily full run           -> main.py                    once/day, at/after 08:00 (catch-up)
  - intraday HR scans        -> hr_scan.py                 at 10/12/14/16/18/20

Env vars (ODDS_API_KEY, GMAIL_*) are inherited from run_scheduler.ps1.
"""
import argparse
import datetime
import json
import subprocess
import time
from pathlib import Path

REPO = Path(r"C:\Users\benne\mlb-k-props")
TRACKER_DIR = Path(r"C:\Users\benne\OneDrive\Documents\KTracker")
STATE_FILE = REPO / "cache" / "scheduler_state.json"
LOG = REPO / "logs" / "scheduler.log"
PY = r"C:\Users\benne\AppData\Local\Programs\Python\Launcher\py.exe"

DAILY_HOUR = 8
NIGHTLY_START = (0, 30)           # 00:30
HR_SCAN_HOURS = [10, 12, 14, 16, 18, 20]   # 8 AM HR is covered by the daily run


def log(msg: str) -> None:
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(s: dict) -> None:
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(s))


def decide(now: datetime.datetime, state: dict) -> dict | None:
    """Return the job to run right now, or None if idle."""
    today = now.date().isoformat()
    # Nightly grade + publish (once/day, overnight window)
    if state.get("nightly") != today and (now.hour, now.minute) >= NIGHTLY_START and now.hour < DAILY_HOUR:
        return {"name": "nightly", "args": ["k_tracker_1.py", "--publish"], "cwd": TRACKER_DIR, "key": "nightly", "val": today}
    # Daily full run (once/day, at/after 08:00 — catches up if the terminal opened later)
    if state.get("daily") != today and now.hour >= DAILY_HOUR:
        return {"name": "daily", "args": ["main.py"], "cwd": REPO, "key": "daily", "val": today}
    # Intraday HR scan for the most recent due even-hour (once each)
    due = [h for h in HR_SCAN_HOURS if now.hour >= h]
    if due:
        key = f"hr-{today}-{due[-1]}"
        if state.get("hr_last") != key:
            return {"name": "hr-scan", "args": ["hr_scan.py"], "cwd": REPO, "key": "hr_last", "val": key}
    return None


def run_job(name: str, args: list, cwd: Path) -> None:
    log(f"START {name}: {' '.join(args)}")
    try:
        r = subprocess.run([PY] + args, cwd=str(cwd), capture_output=True, text=True, timeout=2400)
        for t in (r.stdout or "").strip().splitlines()[-8:]:
            log(f"  | {t}")
        if r.returncode != 0:
            log(f"  {name} exited {r.returncode}: {(r.stderr or '')[-400:]}")
        log(f"DONE {name}")
    except Exception as e:
        log(f"ERROR {name}: {e}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="print the decision for right now and exit")
    args = ap.parse_args()

    if args.dry:
        now = datetime.datetime.now()
        d = decide(now, load_state())
        print("now:", now.strftime("%Y-%m-%d %H:%M"))
        print("state:", load_state())
        print("would run:", d["name"] if d else "nothing (idle)")
        return

    log("Scheduler started. LEAVE THIS WINDOW OPEN (Ctrl+C to stop).")
    log("nightly grade 12:30am | daily picks 8am (catch-up on start) | HR scans 10/12/2/4/6/8pm")
    while True:
        try:
            now = datetime.datetime.now()
            state = load_state()
            d = decide(now, state)
            if d:
                run_job(d["name"], d["args"], d["cwd"])
                state[d["key"]] = d["val"]
                save_state(state)
        except Exception as e:
            log(f"loop error: {e}")
        time.sleep(60)


if __name__ == "__main__":
    main()
