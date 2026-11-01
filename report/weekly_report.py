#!/usr/bin/env python3
"""Weekly training report -> email (no LLM).

Run it weekly (e.g. Sat 5 AM from cron). It optionally refreshes the Garmin data,
reviews the last 7 days (runs/rides/swims, plus each morning's sleep, HRV and
resting HR) against a plan card, and emails a plain-text recap via Gmail.

  python report/weekly_report.py CONFIG.json              refresh, build, send
  python report/weekly_report.py CONFIG.json --dry-run    build and print only
  python report/weekly_report.py CONFIG.json --dry-run --date 2026-10-31

Everything personal lives in the config (copy report/example.json): recipient,
data folder, plan file, HR caps, Gmail token path, optional refresh command.
Keep your filled-in config OUT of this repo (report/*.local.json is gitignored).
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from statistics import mean

MI = 1609.344
HERE = Path(__file__).resolve().parent


def load_config(path: str) -> dict:
    cfg = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    data = Path(cfg.get("data_dir", HERE.parent / "data")).expanduser()
    return {
        "to": cfg["to"],
        "data": data,
        "plan": data / cfg.get("plan_file", "plan.json"),
        "token": Path(cfg.get("gmail_token", "~/.hermes/google_token.json")).expanduser(),
        "easy_hr": int(cfg.get("easy_hr_max", 152)),
        "recovery_hr": int(cfg.get("recovery_hr_max", 140)),
        "refresh": cfg.get("refresh_cmd") or [],
        "dashboard": cfg.get("dashboard_note", ""),
    }


def arg(name):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else None


def pace(sec_per_mi):
    return f"{int(sec_per_mi // 60)}:{int(sec_per_mi % 60):02d}"


def avg(xs):
    xs = [x for x in xs if x is not None]
    return mean(xs) if xs else None


def f0(x, unit=""):
    return "n/a" if x is None else f"{x:.0f}{unit}"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--") and a != arg("--date")]
    if not args:
        print(__doc__)
        return 2
    C = load_config(args[0])
    DATA, PLAN_FILE, EASY_HR, RECOVERY_HR = C["data"], C["plan"], C["easy_hr"], C["recovery_hr"]
    dry = "--dry-run" in sys.argv
    today = date.fromisoformat(arg("--date")) if arg("--date") else date.today()
    if not dry and C["refresh"]:  # refresh so Friday's run and last night's sleep are included
        subprocess.run(C["refresh"], timeout=280, check=False, capture_output=True)

    act_start, act_end = today - timedelta(days=7), today - timedelta(days=1)       # Sat..Fri
    well_days = [today - timedelta(days=i) for i in range(6, -1, -1)]               # Sun..Sat mornings
    prev_days = [d - timedelta(days=7) for d in well_days]

    acts = json.loads((DATA / "activities.json").read_text())
    acts = sorted((a for a in acts.values()
                   if act_start.isoformat() <= a["start"][:10] <= act_end.isoformat()),
                  key=lambda a: a["start"])
    well = json.loads((DATA / "wellness.json").read_text())
    plan = json.loads(PLAN_FILE.read_text()) if PLAN_FILE.exists() else {"days": []}
    pdays = {d["date"]: d for d in plan["days"]}
    meta = json.loads((DATA / "meta.json").read_text())

    W = [well.get(d.isoformat(), {}) for d in well_days]
    P = [well.get(d.isoformat(), {}) for d in prev_days]

    # ---------------- training
    lines, flags, run_mi, hot_easy = [], [], 0.0, 0
    for a in acts:
        d = date.fromisoformat(a["start"][:10])
        mi = (a.get("distance_m") or 0) / MI
        sport = (a.get("sport") or "").replace("_", " ")
        hr = a.get("avg_hr")
        z = a.get("hr_zones") or {}
        z4 = round(((z.get("hrTimeInZone_4") or 0) + (z.get("hrTimeInZone_5") or 0)) / 60)
        p = f" at {pace(a['moving_s'] / mi)}/mi" if "run" in sport and mi > 0.3 else ""
        planned = pdays.get(d.isoformat())
        note = ""
        if "run" in sport:
            run_mi += mi
            kind = (planned or {}).get("kind")
            limit = RECOVERY_HR if planned and "recovery" in planned["title"] else EASY_HR
            if kind in ("easy", "long", "ml") and hr and hr > limit:
                hot_easy += 1
                note = f"  <- HR {hr:.0f} over the {limit} cap for an easy day"
        mins = round((a.get("moving_s") or a.get("duration_s") or 0) / 60)
        lines.append(f"- {d:%a %b %d}: {sport} {mi:.1f} mi{p}, {mins} min, avg HR {f0(hr)}"
                     f" (max {f0(a.get('max_hr'))}), {z4} min in zone 4-5{note}")
        if planned:
            lines.append(f"    planned: {planned['title']}")

    planned_mi = sum(pdays[d]["mi"] for d in pdays if act_start.isoformat() <= d <= act_end.isoformat())
    missed = [pdays[d]["title"] for d in sorted(pdays)
              if act_start.isoformat() <= d <= act_end.isoformat() and pdays[d]["mi"] > 0
              and not any(a["start"][:10] == d and "run" in (a.get("sport") or "") for a in acts)]

    # ---------------- recovery
    hrv, hrv_prev = avg(w.get("hrv_avg") for w in W), avg(w.get("hrv_avg") for w in P)
    rhr, rhr_prev = avg(w.get("resting_hr") for w in W), avg(w.get("resting_hr") for w in P)
    sleep_h = avg((w.get("sleep_s") or None) and w["sleep_s"] / 3600 for w in W)
    score, score_prev = avg(w.get("sleep_score") for w in W), avg(w.get("sleep_score") for w in P)
    bb = avg(w.get("bb_high") for w in W)
    base_lo = next((w["hrv_baseline_low"] for w in reversed(W) if w.get("hrv_baseline_low")), None)
    base_hi = next((w["hrv_baseline_high"] for w in reversed(W) if w.get("hrv_baseline_high")), None)
    unbal = sum(1 for w in W if (w.get("hrv_status") or "") in ("UNBALANCED", "LOW", "POOR"))
    short = sum(1 for w in W if w.get("sleep_s") and w["sleep_s"] < 6 * 3600)
    rest_days = sum(1 for i in range(7)
                    if not any(a["start"][:10] == (act_start + timedelta(days=i)).isoformat() for a in acts))

    daily = []
    for d, w in zip(well_days, W):
        if not w or not w.get("sleep_s"):
            daily.append(f"- {d:%a %b %d}: sleep/HRV not synced yet" + (f", resting HR {f0(w.get('resting_hr'))}" if w else ""))
            continue
        sh = (w.get("sleep_s") or 0) / 3600
        daily.append(f"- {d:%a %b %d}: sleep {sh:.1f} h (score {f0(w.get('sleep_score'))}), "
                     f"HRV {f0(w.get('hrv_avg'))} {(w.get('hrv_status') or '').lower()}, "
                     f"resting HR {f0(w.get('resting_hr'))}, Body Battery peak {f0(w.get('bb_high'))}")

    # ---------------- verdict
    if hrv and base_lo and hrv < base_lo:
        flags.append(f"HRV averaged {hrv:.0f}, below your normal range ({base_lo}-{base_hi}).")
    if unbal >= 3:
        flags.append(f"Garmin marked HRV unbalanced or low on {unbal} of 7 mornings.")
    if rhr and rhr_prev and rhr - rhr_prev >= 2:
        flags.append(f"Resting HR is up {rhr - rhr_prev:.1f} bpm on last week.")
    if hot_easy >= 2:
        flags.append(f"{hot_easy} easy runs ran over their heart-rate cap. Slow the easy days down.")
    if short:
        flags.append(f"{short} night(s) under 6 hours of sleep.")
    if bb and bb < 85:
        flags.append(f"Body Battery peaks averaged {bb:.0f}, so you're not fully recharging overnight.")
    if not flags:
        verdict = "GREEN: recovery looks good. Carry on with next week's plan as written."
    elif len(flags) <= 2:
        verdict = "YELLOW: some fatigue. Keep easy runs truly easy and protect sleep; do the key workout only if you feel good that day."
    else:
        verdict = "RED: you're carrying fatigue. Swap next week's workout for easy miles and shorten the long run until HRV and resting HR recover."

    nxt = [pdays[d] for d in sorted(pdays) if today.isoformat() <= d <= (today + timedelta(days=6)).isoformat()]

    def delta(cur, prev, unit=""):
        if cur is None:
            return "n/a"
        return f"{cur:.0f}{unit}" + (f" (last week {prev:.0f}{unit})" if prev is not None else "")

    body = [
        f"Weekly training report: {act_start:%b %d} - {act_end:%b %d}",
        "",
        verdict,
        *[f"  * {x}" for x in flags],
        "",
        "TRAINING",
        f"Running: {run_mi:.1f} mi of {planned_mi:g} planned ({plan.get('name', 'plan')})",
        f"Rest days: {rest_days}",
        *(lines or ["- No activities recorded."]),
        *([f"Planned runs with no run recorded: {', '.join(missed)}"] if missed else []),
        "",
        "RECOVERY (7-day averages)",
        f"HRV: {delta(hrv, hrv_prev)}" + (f", normal range {base_lo}-{base_hi}" if base_lo else ""),
        f"Resting HR: {delta(rhr, rhr_prev)}",
        f"Sleep: {f'{sleep_h:.1f}' if sleep_h else 'n/a'} h/night, score {delta(score, score_prev)}",
        f"Body Battery peak: {f0(bb)}",
        "",
        "DAY BY DAY",
        *daily,
        "",
        "NEXT 7 DAYS",
        *([f"- {date.fromisoformat(d['date']):%a %b %d}: {d['title']}" for d in nxt] or ["- Plan has ended."]),
        "",
        f"Garmin data as of {meta.get('last_pull', '?').replace('T', ' ')}." + (f" {C['dashboard']}" if C["dashboard"] else ""),
        "Sent by report/weekly_report.py.",
    ]
    text = "\n".join(body)
    subject = f"Training week {act_start:%b %d}-{act_end:%b %d}: {verdict.split(':')[0]} · {run_mi:.0f} mi"

    if dry:
        print(subject, "\n", text, sep="")
        return 0

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    TOKEN = C["token"]
    c = Credentials.from_authorized_user_file(str(TOKEN))
    if not c.valid:
        c.refresh(Request())
        TOKEN.write_text(c.to_json())
    m = EmailMessage()
    m["To"], m["Subject"] = C["to"], subject
    m.set_content(text)
    build("gmail", "v1", credentials=c, cache_discovery=False).users().messages().send(
        userId="me", body={"raw": base64.urlsafe_b64encode(m.as_bytes()).decode()}).execute()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # stdout goes to Telegram via cron, so only failures speak up
        print(f"Weekly training report failed: {type(e).__name__}: {e}")
        sys.exit(1)
