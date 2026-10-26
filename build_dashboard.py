"""Turn the cached Garmin JSON into a single self-contained dashboard.html.

Reads data/activities.json + data/wellness.json, normalises sports, and injects
the result into template.html. No network, no dependencies -- run it any time
after garmin_pull.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
TEMPLATE = HERE / "template.html"
OUTPUT = HERE / "dashboard.html"

# Garmin has a long tail of typeKeys; map the ones that matter to five buckets.
SPORT_MAP = {
    "run": (
        "running", "trail_running", "treadmill_running", "track_running",
        "street_running", "virtual_run", "indoor_running", "obstacle_run",
        "ultra_run",
    ),
    "bike": (
        "cycling", "road_biking", "mountain_biking", "gravel_cycling",
        "indoor_cycling", "virtual_ride", "cyclocross", "downhill_biking",
        "recumbent_cycling", "track_cycling", "bmx", "e_bike_fitness",
    ),
    "swim": (
        "lap_swimming", "open_water_swimming", "swimming", "indoor_swimming",
    ),
    "strength": (
        "strength_training", "indoor_cardio", "hiit", "pilates", "yoga",
        "elliptical", "stair_climbing", "indoor_rowing", "rowing",
        "bouldering", "indoor_climbing", "mobility",
    ),
}
SPORT_LOOKUP = {key: bucket for bucket, keys in SPORT_MAP.items() for key in keys}


def bucket_for(type_key: str | None) -> str:
    if not type_key:
        return "other"
    if type_key in SPORT_LOOKUP:
        return SPORT_LOOKUP[type_key]
    # catch variants the explicit list misses (e.g. "virtual_indoor_running")
    for token, bucket in (("run", "run"), ("bik", "bike"), ("cycl", "bike"),
                          ("swim", "swim"), ("strength", "strength")):
        if token in type_key:
            return bucket
    return "other"


def load(path: Path) -> Any:
    if not path.exists():
        print(f"Missing {path} -- run garmin_pull.py first.")
        sys.exit(1)
    return json.loads(path.read_text(encoding="utf-8"))


def rnd(v: Any, nd: int = 0) -> Any:
    return None if v is None else round(v, nd) if nd else round(v)


def compact_lap(lap: dict[str, Any]) -> dict[str, Any]:
    """Short keys: laps are the bulkiest thing embedded in the page."""
    row = {
        "d": rnd(lap.get("distance_m"), 1),
        "t": rnd(lap.get("moving_s") or lap.get("duration_s"), 1),
        "hr": rnd(lap.get("avg_hr")),
        "mhr": rnd(lap.get("max_hr")),
        "up": rnd(lap.get("elev_gain_m"), 1),
        "cad": rnd(lap.get("run_cadence")),
        "pw": rnd(lap.get("avg_power")),
        "swolf": rnd(lap.get("swolf")),
        "str": lap.get("strokes"),
    }
    return {k: v for k, v in row.items() if v is not None}


def build_activities(raw: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for act in raw.values():
        start = act.get("start") or ""
        date = start.split(" ")[0]
        if not date:
            continue
        zones_raw = act.get("hr_zones") or {}
        zones = [round(zones_raw.get(f"hrTimeInZone_{i}", 0) or 0) for i in range(1, 6)]
        row = {
            "id": act.get("activityId"),
            "date": date,
            "time": start[11:16] or None,
            "name": act.get("name") or "Activity",
            "sport": bucket_for(act.get("sport")),
            "sportRaw": act.get("sport"),
            "dist_m": round(act.get("distance_m") or 0, 1) or None,
            "dur_s": round(act.get("duration_s") or 0),
            "moving_s": rnd(act.get("moving_s")),
            "elapsed_s": rnd(act.get("elapsed_s")),
            "avg_hr": act.get("avg_hr"),
            "max_hr": act.get("max_hr"),
            "cal": act.get("calories"),
            "elev_m": act.get("elev_gain_m"),
            "aerobic_te": act.get("aerobic_te"),
            "anaerobic_te": act.get("anaerobic_te"),
            "load": rnd(act.get("training_load")),
            "power": act.get("avg_power"),
            "np": act.get("norm_power"),
            "speed": act.get("avg_speed_mps"),
            "max_speed": act.get("max_speed_mps"),
            "cad": act.get("run_cadence"),
            "bike_cad": act.get("bike_cadence"),
            "temp": act.get("min_temp_c"),
            "strokes": act.get("swim_strokes"),
            "swolf": act.get("swolf"),
            "pool_m": act.get("pool_length_m"),
            "vo2max": act.get("vo2max"),
        }
        if any(zones):
            row["zones"] = zones
        if act.get("laps"):
            row["laps"] = [compact_lap(lap) for lap in act["laps"]]
        out.append({k: v for k, v in row.items() if v is not None})
    out.sort(key=lambda r: (r["date"], r.get("time") or ""))
    return out


def build_wellness(raw: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "date", "resting_hr", "hrv_avg", "hrv_baseline_low", "hrv_baseline_high",
        "sleep_s", "sleep_score", "vo2max_run", "bb_high", "bb_low", "steps",
        "stress_avg", "hrv_status", "intensity_min",
    )
    return {
        day: {k: v for k, v in rec.items() if k in keep}
        for day, rec in sorted(raw.items())
    }


def main() -> int:
    activities = build_activities(load(DATA / "activities.json"))
    wellness = build_wellness(load(DATA / "wellness.json"))
    meta = load(DATA / "meta.json") if (DATA / "meta.json").exists() else {}
    # race target lives in its own file: meta.json is rewritten on every pull
    goal = load(DATA / "goal.json") if (DATA / "goal.json").exists() else {}
    # Garmin's daily race predictor; absent until garmin_pull.py has run once
    preds = load(DATA / "race_predictions.json") if (DATA / "race_predictions.json").exists() else {}

    # optional day-by-day training plan (see README); the card hides without it
    plan = load(DATA / "plan.json") if (DATA / "plan.json").exists() else None
    plan2 = load(DATA / "plan2.json") if (DATA / "plan2.json").exists() else None  # optional alternate

    payload = {"activities": activities, "wellness": wellness, "meta": meta,
               "goal": goal, "predictions": dict(sorted(preds.items())), "plan": plan, "plan2": plan2}
    blob = json.dumps(payload, separators=(",", ":"))

    template = TEMPLATE.read_text(encoding="utf-8")
    if "/*__DATA__*/" not in template:
        print("template.html is missing the /*__DATA__*/ placeholder.")
        return 1
    OUTPUT.write_text(template.replace("/*__DATA__*/", blob), encoding="utf-8")

    counts: dict[str, int] = {}
    for a in activities:
        counts[a["sport"]] = counts.get(a["sport"], 0) + 1
    size_kb = OUTPUT.stat().st_size / 1024

    print(f"{len(activities)} activities  {counts}")
    print(f"{len(wellness)} wellness days, {len(preds)} race-prediction days")
    print(f"-> {OUTPUT}  ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
