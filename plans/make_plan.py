"""Generate a day-by-day marathon plan for the dashboard's plan card.

    python plans/make_plan.py plans/beans-plans/higdon.json data/plan.json
    python plans/make_plan.py plans/beans-plans/pfitz.json  data/plan2.json
    python build_dashboard.py

Everything personal lives in the config file: race date and distance, goal time,
a recent race (sets the training paces), easy-HR ceiling, minimum run length,
and per-date overrides for trips and holidays. Copy plans/example.json to start.

Templates (16 weeks, ending on race day):
  higdon_adv2  Hal Higdon Advanced 2, adapted: Tue speed (pyramids, 800s, mile
               repeats), Thu tempo miles 3 -> 4 -> 5, Sat marathon pace, Sun long,
               three 20-milers, Fri rest.
  pfitz_18_70  Pfitzinger 18/70 structure (book weeks 3-18): Mon rest, one hard day
               (lactate threshold, later VO2 1000s), Wed medium-long, long runs to 22,
               marathon-pace long runs, two tune-up races, 3-week taper.
Both are adaptations built from each plan's documented structure, not copies of
the published daily tables.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

MI = 1609.344


# ------------------------------------------------------------ paces
def clock(sec: float) -> str:
    sec = int(round(sec))
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def secs(t: str) -> int:
    parts = [int(p) for p in t.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def r5(x: float) -> float:
    return round(x / 5) * 5


class Paces:
    """Training paces from a recent race (Riegel to half-marathon pace), MP from the goal."""

    def __init__(self, cfg: dict):
        dist = cfg["race_distance_mi"]
        self.goal_s = secs(cfg["goal_time"])
        self.mp = self.goal_s / dist
        rr = cfg.get("recent_race")
        if rr:
            half_s = secs(rr["time"]) * (13.1094 / rr["distance_mi"]) ** 1.06
        else:  # no recent race: back the half out of the goal time
            half_s = self.goal_s * (13.1094 / dist) ** 1.06
        self.hp = half_s / 13.1094  # half-marathon pace, s/mi
        self.hr = cfg.get("easy_hr_max", 150)

    def rng(self, lo: float, hi: float) -> str:  # offsets from half pace, s/mi
        return f"{clock(r5(self.hp + lo))}-{clock(r5(self.hp + hi))}"

    def rep(self, meters: float, lo: float, hi: float, rnd=r5) -> str:
        f = meters / MI
        return f"{clock(rnd((self.hp + lo) * f))}-{clock(rnd((self.hp + hi) * f))}"

    @property
    def easy(self): return self.rng(98, 143)
    @property
    def recovery(self): return clock(r5(self.hp + 143)) + "+"
    @property
    def tempo(self): return self.rng(-12, 3)
    @property
    def mile(self): return self.rng(-42, -32)
    @property
    def m400(self): return self.rep(400, -65, -58, rnd=round)
    @property
    def m800(self): return self.rep(800, -54, -46)
    @property
    def m1000(self): return self.rep(1000, -44, -38)
    @property
    def m1200(self): return self.rep(1200, -44, -38)
    @property
    def m1600(self): return self.rep(1600, -47, -37)
    @property
    def mpace(self): return clock(self.mp)


# ------------------------------------------------------------ day builders
def make_days(P: Paces):
    easy = f"Easy pace {P.easy}, HR at or under {P.hr}."
    d = {}
    d["REST"] = lambda: ("rest", "Rest", 0, "Rest or easy cross-training.")
    d["TRIP"] = lambda label="Trip", note="No run.": ("trip", label, 0, note)
    d["E"] = lambda mi: ("easy", f"{mi} easy", mi, easy)
    d["R"] = lambda mi: ("easy", f"{mi} recovery", mi, f"Recovery: slower than easy, {P.recovery}/mi, HR under ~{P.hr - 12}.")
    d["GA"] = lambda mi: ("easy", f"{mi} general aerobic", mi, f"General aerobic: {P.easy}, HR at or under {P.hr}.")
    d["ML"] = lambda mi: ("ml", f"{mi} medium-long", mi, f"Medium-long at endurance pace ({P.easy}). Second key aerobic run of the week.")
    d["MP"] = lambda mi: ("mp", f"{mi} @ marathon pace", mi, f"Settle into {P.mpace}/mi. Even effort, practise race fueling on 8+.")
    d["L"] = lambda mi: ("long", f"{mi} long", mi, f"Easy pace ({P.easy}), NOT marathon pace. Gel every 45 min from 10 mi up.")
    d["PL"] = lambda mi: ("long", f"{mi} long", mi, f"Endurance pace {P.easy}. Finish the last 2-3 mi a little quicker if you feel good.")
    d["LMP"] = lambda mi, mp: ("mp", f"{mi} w/ {mp} @ MP", mi, f"{mi - mp} mi easy, then {mp} mi at marathon pace ({P.mpace}). Rehearse race fueling.")

    def tempo(n):
        wu = 1.5 if n == 3 else 1
        return ("tempo", f"Tempo {n} x 1 mi", round(wu * 2 + n + (n - 1) * 0.25, 1),
                f"{wu} mi warmup, {n} x 1 mi at {P.tempo} with 2 min jog, {wu} mi cooldown.")
    d["T"] = tempo
    d["LT"] = lambda mi, mins: ("tempo", f"LT {mi} w/ {mins} min", mi,
                                f"Warm up, {mins} min continuous at lactate-threshold pace ({P.tempo}, 15K-to-half effort), cool down to {mi} mi.")
    d["VO"] = lambda mi, reps: ("speed", f"VO2 {mi} w/ {reps}", mi,
                                f"Warm up, {reps} at 5K pace (1000 m in {P.m1000}, 1200 m in {P.m1200}) with 50-90% of rep time jogging, cool down to {mi} mi.")
    d["TUNE"] = lambda: ("speed", "Tune-up race", 10, "8K-15K race if you can find one; otherwise 10 mi with 6 mi at LT pace. Warm-up and cool-down count.")
    speed = {
        "pyrA": ("Pyramid A", 6.5, f"1.5 mi WU. 400-800-1200-800-400 m, jog half the rep distance after each. 400s {P.m400}, 800s {P.m800}, 1200 {P.m1200}. 1.5 mi CD."),
        "pyrB": ("Pyramid B", 9, f"1.5 mi WU. 400-800-1200-1600-1200-800-400 m, jog half the rep distance after each. Same rep paces as A; 1600 in {P.m1600}. 1.5 mi CD."),
        "800x6": ("6 x 800", 7.5, f"1.5 mi WU, 6 x 800 m in {P.m800} with 400 m jog, 1.5 mi CD."),
        "800x7": ("7 x 800", 8, f"1.5 mi WU, 7 x 800 m in {P.m800} with 400 m jog, 1.5 mi CD."),
        "mile4": ("4 x 1 mi", 8, f"1.5 mi WU, 4 x 1 mi at {P.mile} with 3 min jog, 1.5 mi CD."),
        "mile5": ("5 x 1 mi", 9.5, f"1.5 mi WU, 5 x 1 mi at {P.mile} with 3 min jog, 1.5 mi CD."),
    }
    d["S"] = lambda k: ("speed", speed[k][0], speed[k][1], speed[k][2])
    d["_speed"] = speed
    return d


# ------------------------------------------------------------ templates (Mon..Sun)
# Each day is [builder, *args]. The race week is built separately by countdown.
TEMPLATES = {
    "higdon_adv2": {
        "label": "Higdon Advanced 2, adapted",
        "weeks": [
            ("Easy start (recovery if you just raced)", [["E", 6], ["E", 6], ["E", 6], ["T", 3], ["REST"], ["E", 6], ["L", 10]]),
            ("", [["E", 6], ["S", "pyrA"], ["E", 7], ["T", 3], ["REST"], ["MP", 6], ["L", 12]]),
            ("", [["E", 6], ["S", "pyrA"], ["E", 7], ["T", 3], ["REST"], ["MP", 7], ["L", 13]]),
            ("Tempo builds to 4 x 1", [["E", 6], ["S", "pyrA"], ["E", 7], ["T", 4], ["REST"], ["MP", 7], ["L", 14]]),
            ("", [["E", 6], ["S", "pyrA"], ["E", 8], ["T", 4], ["REST"], ["MP", 8], ["L", 15]]),
            ("Stepback", [["E", 6], ["S", "800x6"], ["E", 6], ["T", 3], ["REST"], ["MP", 6], ["L", 12]]),
            ("", [["E", 6], ["S", "pyrA"], ["E", 8], ["T", 4], ["REST"], ["MP", 8], ["L", 16]]),
            ("Tempo builds to 5 x 1", [["E", 6], ["S", "pyrB"], ["E", 9], ["T", 5], ["REST"], ["MP", 8], ["L", 18]]),
            ("First 20", [["E", 6], ["S", "800x7"], ["E", 9], ["T", 5], ["REST"], ["MP", 8], ["L", 20]]),
            ("Stepback", [["E", 6], ["S", "pyrA"], ["E", 7], ["T", 4], ["REST"], ["MP", 7], ["L", 14]]),
            ("Second 20", [["E", 6], ["S", "mile4"], ["E", 10], ["T", 5], ["REST"], ["MP", 6], ["L", 20]]),
            ("Stepback", [["E", 6], ["S", "pyrB"], ["E", 8], ["T", 5], ["REST"], ["MP", 10], ["L", 14]]),
            ("Peak week. Last 20, 20 days out", [["E", 6], ["S", "mile5"], ["E", 10], ["T", 5], ["REST"], ["MP", 6], ["L", 20]]),
            ("Taper", [["E", 6], ["S", "800x6"], ["E", 8], ["T", 4], ["REST"], ["MP", 8], ["L", 12]]),
            ("Taper", [["E", 6], ["S", "pyrA"], ["E", 6], ["T", 3], ["REST"], ["MP", 6], ["L", 8]]),
        ],
        # days before the race (-1 = the day before); only those inside race week are used
        "countdown": {-6: ["REST"], -5: ["E", 5], -4: ["RW400"], -3: ["E", 4], -2: ["STRIDES", 3], -1: ["REST"]},
    },
    "pfitz_18_70": {
        "label": "Pfitzinger 18/70, adapted",
        "weeks": [
            ("Book wk 3 · easy start", [["REST"], ["R", 6], ["GA", 9], ["R", 6], ["GA", 8], ["R", 6], ["PL", 12]]),
            ("Endurance", [["REST"], ["LT", 9, 20], ["ML", 11], ["R", 6], ["GA", 8], ["R", 6], ["PL", 15]]),
            ("Endurance", [["REST"], ["R", 6], ["ML", 11], ["R", 6], ["LT", 10, 25], ["R", 6], ["PL", 16]]),
            ("Endurance · first MP long run", [["REST"], ["LT", 10, 25], ["ML", 12], ["R", 6], ["GA", 10], ["R", 6], ["LMP", 18, 10]]),
            ("Threshold block", [["REST"], ["R", 7], ["ML", 14], ["R", 6], ["LT", 10, 30], ["R", 6], ["PL", 16]]),
            ("Threshold", [["REST"], ["R", 7], ["ML", 15], ["R", 6], ["LT", 11, 35], ["R", 6], ["PL", 20]]),
            ("Threshold · MP long run", [["REST"], ["R", 7], ["ML", 14], ["R", 6], ["GA", 10], ["R", 6], ["LMP", 16, 12]]),
            ("Threshold", [["REST"], ["R", 7], ["ML", 15], ["R", 6], ["LT", 12, 40], ["R", 6], ["PL", 20]]),
            ("Peak long run", [["REST"], ["GA", 8], ["ML", 15], ["LT", 11, 40], ["R", 6], ["R", 6], ["PL", 22]]),
            ("Race prep · VO2 starts", [["REST"], ["VO", 10, "5 x 1000 m"], ["ML", 15], ["R", 6], ["GA", 10], ["R", 6], ["LMP", 18, 12]]),
            ("Race prep · peak week", [["REST"], ["VO", 11, "6 x 1000 m"], ["ML", 16], ["R", 7], ["GA", 10], ["R", 6], ["PL", 20]]),
            ("Race prep · tune-up Sat", [["REST"], ["GA", 8], ["ML", 14], ["R", 6], ["R", 6], ["TUNE"], ["PL", 17]]),
            ("Race prep · last 20", [["REST"], ["VO", 10, "5 x 1200 m"], ["ML", 15], ["R", 6], ["GA", 9], ["R", 6], ["PL", 20]]),
            ("Taper 1 · tune-up Sat", [["REST"], ["VO", 10, "5 x 1000 m"], ["ML", 12], ["R", 6], ["R", 6], ["TUNE"], ["PL", 16]]),
            ("Taper 2", [["REST"], ["R", 7], ["ML", 9], ["LT", 8, 20], ["R", 6], ["R", 6], ["PL", 12]]),
        ],
        "countdown": {-6: ["REST"], -5: ["REST"], -4: ["R", 6], -3: ["DRESS"], -2: ["STRIDES5"], -1: ["SHAKE"]},
    },
}


def build(cfg: dict) -> dict:
    tpl = TEMPLATES[cfg["template"]]
    P = Paces(cfg)
    D = make_days(P)
    D["RW400"] = lambda: ("speed", "5 w/ 4 x 400", 5, f"1.5 mi WU, 4 x 400 m at {clock(round((P.hp - 44) * 400 / MI))} (relaxed, not all-out) with 400 m jog, CD to 5 mi.")
    D["STRIDES"] = lambda mi: ("easy", f"{mi} easy + strides", mi, f"{mi} easy, then 4 x 20 s strides.")
    D["STRIDES5"] = lambda: ("easy", "5 recovery + strides", 5, "Easy, then 6 x 100 m strides.")
    D["DRESS"] = lambda: ("mp", "7 w/ 2 @ MP", 7, f"Dress rehearsal: race shoes and kit, 2 mi at {P.mpace} in the middle.")
    D["SHAKE"] = lambda: ("easy", "3 shakeout", 3, "Very easy, or rest if your legs feel flat.")
    call = lambda spec: D[spec[0]](*spec[1:])

    race = date.fromisoformat(cfg["race_date"])
    race_mon = race - timedelta(days=race.weekday())
    start = race_mon - timedelta(weeks=len(tpl["weeks"]))
    floor = cfg.get("min_run_mi", 0)
    overrides = cfg.get("overrides", {})
    notes = {int(k): v for k, v in cfg.get("week_notes", {}).items()}

    days, week_notes = [], []
    for w, (note, row) in enumerate(tpl["weeks"]):
        week_notes.append({"week": w + 1, "note": notes.get(w + 1, note)})
        for i, spec in enumerate(row):
            dt = start + timedelta(days=7 * w + i)
            kind, title, mi, detail = call(overrides.get(dt.isoformat(), spec))
            if kind == "easy" and mi < floor:  # minimum run length outside race week
                mi = floor
                title = title.replace(title.split()[0], f"{floor:g}", 1)
            days.append({"date": dt.isoformat(), "week": w + 1, "kind": kind, "title": title, "mi": mi, "detail": detail})

    rw = len(tpl["weeks"]) + 1
    week_notes.append({"week": rw, "note": notes.get(rw, "Race week")})
    dt = race_mon
    while dt < race:
        spec = overrides.get(dt.isoformat()) or tpl["countdown"].get((dt - race).days, ["REST"])
        kind, title, mi, detail = call(spec)
        days.append({"date": dt.isoformat(), "week": rw, "kind": kind, "title": title, "mi": mi, "detail": detail})
        dt += timedelta(days=1)
    first3 = f"{clock(r5(P.mp + 6))}-{clock(r5(P.mp + 11))}"
    days.append({"date": race.isoformat(), "week": rw, "kind": "race", "title": f"RACE: {cfg.get('race_name', 'Marathon')}",
                 "mi": cfg["race_distance_mi"],
                 "detail": f"Goal {clock(P.goal_s)} ({P.mpace}/mi). First 3 mi at {first3}, settle from there."})

    if cfg.get("start"):  # joining late: drop days before the start date
        days = [d for d in days if d["date"] >= cfg["start"]]

    key = [["Paces", f"Recovery {P.recovery} · Easy/long {P.easy} (HR ≤{P.hr}) · Marathon {P.mpace} · "
                     f"Tempo/LT {P.tempo} · Mile repeats {P.mile} · 1000 m {P.m1000} · 800 m {P.m800} · 400 m {P.m400}."]]
    if cfg["template"] == "higdon_adv2":
        sp = D["_speed"]
        key = [["Pyramid A", sp["pyrA"][2]], ["Pyramid B", sp["pyrB"][2]],
               ["Tempo", f"Thu: 3 x 1 mi, building to 4 x 1 and then 5 x 1. Tempo pace {P.tempo}."]] + key
    else:
        key = [["Shape", "Mon rest. One hard day + a midweek medium-long + Sunday long. Blocks: endurance → threshold → race prep (VO2 + tune-ups) → 3-week taper."]] + key
    key += [["Source", f"{tpl['label']}: built from the plan's documented structure, not copied from its published tables."]]

    return {"name": cfg.get("name", tpl["label"]), "template": cfg["template"],
            "start": days[0]["date"], "race": race.isoformat(),
            "weeks": week_notes, "days": days, "key": key}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    plan = build(cfg)
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent / "data" / "plan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=1), encoding="utf-8")
    wk: dict[int, float] = {}
    for d in plan["days"]:
        wk[d["week"]] = wk.get(d["week"], 0) + d["mi"]
    print(f"{plan['name']}: {len(plan['days'])} days, {plan['start']} -> {plan['race']}, "
          f"{sum(wk.values()):.0f} mi, peak week {max(wk.values()):.0f} mi")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
