"""Pull training data from Garmin Connect into a local JSON cache.

Uses the OAuth tokens saved by garmin_login.py -- no password involved.
The cache is incremental: the first run backfills, every run after that only
fetches days it doesn't already have (plus today, which is always refreshed).

Usage:
    python garmin_pull.py                     # 365d activities, 90d wellness
    python garmin_pull.py --days 730 --wellness-days 180
    python garmin_pull.py --refresh           # ignore cache, refetch window
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from garminconnect import Garmin

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
TOKENSTORE = Path.home() / ".garminconnect"

# Garmin gets unhappy if you hammer it. One wellness day = ~5 calls.
PAUSE_BETWEEN_DAYS = 0.35

# Lap splits cost one call per activity, so they're fetched once, kept in the
# cache, and only for recent activities -- the week card is what shows them.
LAP_WINDOW_DAYS = 45
MAX_LAP_FETCHES = 40


def dig(obj: Any, *keys: Any, default: Any = None) -> Any:
    """Walk nested dicts/lists without exploding on a missing or None link."""
    cur = obj
    for key in keys:
        if cur is None:
            return default
        try:
            if isinstance(key, int):
                cur = cur[key]
            else:
                cur = cur.get(key)
        except (AttributeError, TypeError, IndexError, KeyError):
            return default
    return default if cur is None else cur


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return fallback


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")


def connect() -> Garmin:
    if not TOKENSTORE.exists():
        print(f"No saved tokens at {TOKENSTORE}.")
        print("Run garmin_login.py first (it's a one-time step).")
        sys.exit(1)
    client = Garmin()
    client.login(str(TOKENSTORE))
    return client


# --------------------------------------------------------------------------
# activities
# --------------------------------------------------------------------------

def trim_activity(raw: dict[str, Any]) -> dict[str, Any]:
    keep = {
        "activityId": raw.get("activityId"),
        "name": raw.get("activityName"),
        "start": raw.get("startTimeLocal"),
        "sport": dig(raw, "activityType", "typeKey"),
        "parentSport": dig(raw, "activityType", "parentTypeId"),
        "distance_m": raw.get("distance"),
        "duration_s": raw.get("duration"),
        "moving_s": raw.get("movingDuration"),
        "elapsed_s": raw.get("elapsedDuration"),
        "avg_hr": raw.get("averageHR"),
        "max_hr": raw.get("maxHR"),
        "calories": raw.get("calories"),
        "elev_gain_m": raw.get("elevationGain"),
        "avg_speed_mps": raw.get("averageSpeed"),
        "max_speed_mps": raw.get("maxSpeed"),
        "avg_power": raw.get("avgPower"),
        "norm_power": raw.get("normPower"),
        "aerobic_te": raw.get("aerobicTrainingEffect"),
        "anaerobic_te": raw.get("anaerobicTrainingEffect"),
        "training_load": raw.get("activityTrainingLoad"),
        "vo2max": raw.get("vO2MaxValue"),
        "run_cadence": raw.get("averageRunningCadenceInStepsPerMinute"),
        "bike_cadence": raw.get("averageBikingCadenceInRevPerMinute"),
        "swim_strokes": raw.get("avgStrokes"),
        "swolf": raw.get("avgSwolf"),
        "pool_length_m": raw.get("poolLength"),
        "min_temp_c": raw.get("minTemperature"),
    }
    # HR zone seconds come through as hrTimeInZone_1 .. hrTimeInZone_5
    zones = {k: v for k, v in raw.items() if k.startswith("hrTimeInZone")}
    if zones:
        keep["hr_zones"] = zones
    return {k: v for k, v in keep.items() if v is not None}


def pull_activities(client: Garmin, start: date, end: date) -> dict[str, Any]:
    print(f"Activities {start} -> {end} ...", end=" ", flush=True)
    try:
        raw = client.get_activities_by_date(start.isoformat(), end.isoformat())
    except Exception as exc:
        print(f"failed ({exc})")
        return {}
    out = {}
    for act in raw or []:
        trimmed = trim_activity(act)
        aid = trimmed.get("activityId")
        if aid is not None:
            out[str(aid)] = trimmed
    print(f"{len(out)} found")
    return out


def trim_lap(raw: dict[str, Any]) -> dict[str, Any]:
    keep = {
        "distance_m": raw.get("distance"),
        "duration_s": raw.get("duration"),
        "moving_s": raw.get("movingDuration"),
        "avg_hr": raw.get("averageHR"),
        "max_hr": raw.get("maxHR"),
        "avg_speed_mps": raw.get("averageSpeed"),
        "elev_gain_m": raw.get("elevationGain"),
        "elev_loss_m": raw.get("elevationLoss"),
        "run_cadence": raw.get("averageRunCadence"),
        "avg_power": raw.get("averagePower"),
        "calories": raw.get("calories"),
        "swolf": raw.get("averageSwolf"),
        "strokes": raw.get("totalNumberOfStrokes"),
        "lengths": raw.get("numberOfActiveLengths"),
        "intensity": raw.get("intensityType"),
    }
    return {k: v for k, v in keep.items() if v is not None}


def pull_laps(client: Garmin, activities: dict[str, Any], since: date) -> None:
    """Attach lap splits to recent activities that don't have them yet.

    An activity is marked with "laps" (possibly an empty list) once fetched, so
    it's never asked for again. A failed call leaves it unmarked and it's
    retried on the next run.
    """
    cutoff = since.isoformat()
    wanted = [
        a for a in activities.values()
        if "laps" not in a and a.get("activityId") and (a.get("start") or "")[:10] >= cutoff
    ]
    if not wanted:
        print("Laps: cache already current")
        return
    wanted.sort(key=lambda a: a.get("start") or "", reverse=True)  # newest first
    batch = wanted[:MAX_LAP_FETCHES]
    got = 0
    for a in batch:
        try:
            raw = client.get_activity_splits(a["activityId"]) or {}
        except Exception as exc:
            print(f"  laps for {a['activityId']} failed ({exc}) -- will retry next run")
            continue
        a["laps"] = [lap for lap in (trim_lap(l) for l in raw.get("lapDTOs") or []) if lap]
        got += 1
        time.sleep(PAUSE_BETWEEN_DAYS)
    left = len(wanted) - got
    print(f"Laps: fetched {got} activit{'y' if got == 1 else 'ies'}"
          + (f", {left} left for later runs" if left else ""))


# --------------------------------------------------------------------------
# daily wellness
# --------------------------------------------------------------------------

def pull_day(client: Garmin, day: str) -> dict[str, Any]:
    """Fetch one day of wellness. Each endpoint fails independently."""
    out: dict[str, Any] = {"date": day}

    try:
        s = client.get_stats(day) or {}
        out["steps"] = s.get("totalSteps")
        out["resting_hr"] = s.get("restingHeartRate")
        out["min_hr"] = s.get("minHeartRate")
        out["max_hr"] = s.get("maxHeartRate")
        out["stress_avg"] = s.get("averageStressLevel")
        out["bb_high"] = s.get("bodyBatteryHighestValue")
        out["bb_low"] = s.get("bodyBatteryLowestValue")
        out["calories"] = s.get("totalKilocalories")
        out["active_calories"] = s.get("activeKilocalories")
        out["intensity_min"] = (s.get("moderateIntensityMinutes") or 0) + 2 * (
            s.get("vigorousIntensityMinutes") or 0
        )
    except Exception:
        pass

    try:
        sl = client.get_sleep_data(day) or {}
        dto = sl.get("dailySleepDTO") or {}
        out["sleep_s"] = dto.get("sleepTimeSeconds")
        out["deep_s"] = dto.get("deepSleepSeconds")
        out["light_s"] = dto.get("lightSleepSeconds")
        out["rem_s"] = dto.get("remSleepSeconds")
        out["awake_s"] = dto.get("awakeSleepSeconds")
        out["sleep_score"] = dig(dto, "sleepScores", "overall", "value")
        out["spo2_avg"] = sl.get("averageSpO2Value")
        out["sleep_stress"] = sl.get("avgSleepStress")
    except Exception:
        pass

    try:
        h = client.get_hrv_data(day) or {}
        summary = h.get("hrvSummary") or {}
        out["hrv_avg"] = summary.get("lastNightAvg")
        out["hrv_high5"] = summary.get("lastNight5MinHigh")
        out["hrv_status"] = summary.get("status")
        out["hrv_baseline_low"] = dig(summary, "baseline", "balancedLow")
        out["hrv_baseline_high"] = dig(summary, "baseline", "balancedUpper")
    except Exception:
        pass

    try:
        m = client.get_max_metrics(day) or []
        first = m[0] if isinstance(m, list) and m else {}
        out["vo2max_run"] = dig(first, "generic", "vo2MaxPreciseValue")
        out["vo2max_bike"] = dig(first, "cycling", "vo2MaxPreciseValue")
    except Exception:
        pass

    # Training Status / Training Load / ACWR / Training Readiness are not
    # fetched: Garmin only computes them on "primary training capable" devices,
    # and the Forerunner 165 (and 235) are not -- the trainingstatus endpoint
    # answers with every field null. The dashboard derives load from HR zones
    # instead. Garmin's race predictor IS supported; see pull_race_predictions.

    return {k: v for k, v in out.items() if v is not None}


def pull_wellness(
    client: Garmin, start: date, end: date, cache: dict[str, Any], refresh: bool
) -> dict[str, Any]:
    today = date.today().isoformat()
    wanted = []
    cursor = start
    while cursor <= end:
        key = cursor.isoformat()
        # always refetch today -- it's still filling in
        if refresh or key not in cache or key == today:
            wanted.append(key)
        cursor += timedelta(days=1)

    if not wanted:
        print("Wellness: cache already current")
        return cache

    print(f"Wellness: fetching {len(wanted)} day(s)")
    for i, day in enumerate(wanted, 1):
        cache[day] = pull_day(client, day)
        if i % 10 == 0 or i == len(wanted):
            print(f"  {i}/{len(wanted)} ({day})")
        time.sleep(PAUSE_BETWEEN_DAYS)
    return cache


# --------------------------------------------------------------------------
# race predictions
# --------------------------------------------------------------------------

def pull_race_predictions(
    client: Garmin, start: date, end: date, cache: dict[str, Any]
) -> dict[str, Any]:
    """Garmin's daily race-time predictions (5K / 10K / half / marathon).

    One call covers the whole window, so the full range is refetched every
    run -- the predictor is recomputed retroactively as VO2max settles, and
    the cost is a single request. Days with no prediction are dropped.
    """
    try:
        rows = client.get_race_predictions(
            start.isoformat(), end.isoformat(), "daily"
        ) or []
    except Exception as exc:
        print(f"Race predictions: skipped ({exc})")
        return cache

    fetched = 0
    for row in rows:
        day = row.get("calendarDate")
        if not day or row.get("timeHalfMarathon") is None:
            continue
        cache[day] = {
            "5k_s": row.get("time5K"),
            "10k_s": row.get("time10K"),
            "hm_s": row.get("timeHalfMarathon"),
            "marathon_s": row.get("timeMarathon"),
        }
        fetched += 1
    print(f"Race predictions: {fetched} day(s) {start} -> {end}")
    return cache


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365, help="activity history window")
    ap.add_argument("--wellness-days", type=int, default=90, help="wellness window")
    ap.add_argument("--refresh", action="store_true", help="ignore cache, refetch")
    args = ap.parse_args()

    end = date.today()
    act_start = end - timedelta(days=args.days)
    well_start = end - timedelta(days=args.wellness_days)

    client = connect()
    try:
        print(f"Connected as {client.get_full_name()}\n")
    except Exception:
        print("Connected\n")

    activities = {} if args.refresh else load_json(DATA / "activities.json", {})
    for aid, fresh in pull_activities(client, act_start, end).items():
        # the summary is refetched every run; keep laps already downloaded
        old = activities.get(aid) or {}
        if "laps" in old:
            fresh["laps"] = old["laps"]
        activities[aid] = fresh
    pull_laps(client, activities, end - timedelta(days=LAP_WINDOW_DAYS))
    save_json(DATA / "activities.json", activities)

    wellness = {} if args.refresh else load_json(DATA / "wellness.json", {})
    wellness = pull_wellness(client, well_start, end, wellness, args.refresh)
    save_json(DATA / "wellness.json", wellness)

    predictions = {} if args.refresh else load_json(DATA / "race_predictions.json", {})
    predictions = pull_race_predictions(client, act_start, end, predictions)
    save_json(DATA / "race_predictions.json", dict(sorted(predictions.items())))

    save_json(
        DATA / "meta.json",
        {
            "last_pull": datetime.now().isoformat(timespec="seconds"),
            "activity_count": len(activities),
            "wellness_days": len(wellness),
            "activity_window_start": act_start.isoformat(),
        },
    )

    print(f"\nCached {len(activities)} activities, {len(wellness)} wellness days, "
          f"{len(predictions)} prediction days")
    print(f"-> {DATA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
