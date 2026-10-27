# Garmin Training Dashboard

Builds a single-page training dashboard (`dashboard.html`) from **your own** Garmin Connect data. It covers runs, rides and swims, the weekly load, sleep, HRV, VO2max, Garmin's race predictions and a countdown to your target race.

Everything runs on your computer. Your Garmin password is only used once, to get sign-in tokens, and is never saved. Your data stays in the `data/` folder and is never uploaded anywhere.

---

## 1. One-time setup (Windows)

1. **Install Python 3.10+** from <https://www.python.org/downloads/>.
   On the first installer screen, tick **"Add python.exe to PATH"**.
2. **Download this repo.** Use the green **Code** button, then **Download ZIP**, and unzip it somewhere like `Documents\garmin-dashboard`. Or run `git clone` if you use git.
3. **Install the Garmin library.** Open PowerShell and run:
   ```powershell
   pip install garminconnect
   ```

## 2. Log in to Garmin (once)

Double-click **`LOGIN.bat`**. Enter your Garmin Connect email and password, plus an MFA code if your account uses one.

This saves sign-in tokens to `C:\Users\<you>\.garminconnect`. They last about a year. When they expire, run `LOGIN.bat` again.

## 3. Pull your data and build the dashboard

Open PowerShell in the project folder and run:

```powershell
python garmin_pull.py          # first run: about 1 year of activities and 90 days of sleep/HRV
python build_dashboard.py
```

The first pull takes several minutes because it backfills your history. After that, open **`dashboard.html`** in your browser.

To pull more history: `python garmin_pull.py --days 730 --wellness-days 180`

## 4. Daily refresh

For later updates, run **`refresh.ps1`**. It only fetches what's new and then rebuilds the page:

```powershell
powershell -ExecutionPolicy Bypass -File refresh.ps1
```

Output goes to `refresh.log`.

**To automate it:** open Task Scheduler, choose **Create Basic Task**, set it to run **Daily** (for example at 6:30 AM), and choose **Start a program**:
- Program: `powershell.exe`
- Arguments: `-ExecutionPolicy Bypass -File "C:\path\to\garmin-dashboard\refresh.ps1"`

Run only one refresher per Garmin account. Two machines logging in with the same account can get you rate-limited.

## 5. Set your race goal (optional)

The race card stays empty until you create `data\goal.json`. For example:

```json
{
  "name": "My Half Marathon",
  "date": "2027-03-14",
  "goal_time_s": 6300,
  "distance_m": 21097.5,
  "easy_hr_max": 150,
  "long_run_mi": 12
}
```

| Field | Meaning |
|---|---|
| `date` | Race day (YYYY-MM-DD) |
| `goal_time_s` | Goal finish time in seconds (6300 = 1:45:00) |
| `distance_m` | Race distance in meters (half 21097.5, full 42195) |
| `easy_hr_max` | Top of your easy heart-rate zone, used to flag easy runs |
| `long_run_mi` | Long-run target distance in miles |

Then run `python build_dashboard.py` again.

## 6. Training plan cards (optional)

`plans/make_plan.py` builds a day-by-day marathon plan with **your** paces, race date and goal, and the dashboard shows it as a card. Each past day shows what you actually ran next to what was planned (green at 90%+).

1. Copy `plans/example.json` into your own folder, e.g. `plans/my-plans/higdon.json`, and edit it:

| Field | Meaning |
|---|---|
| `template` | `higdon_adv2` (Hal Higdon Advanced 2, adapted) or `pfitz_18_70` (Pfitzinger 18/70, adapted) |
| `race_date`, `race_distance_mi`, `race_name` | Your race. Plans are 16 weeks ending on race day |
| `goal_time` | Sets marathon pace |
| `recent_race` | A recent race (distance in miles + time). Sets easy, tempo and interval paces. Leave it out to derive them from the goal |
| `easy_hr_max` | Top of your easy heart-rate zone |
| `min_run_mi` | Shortest run allowed outside race week (0 = no minimum) |
| `start` | Optional. Join late: drop plan days before this date |
| `overrides` | Swap any date's workout: `"2027-03-02": ["TRIP", "Work trip", "No run."]`, `["REST"]`, `["E", 6]`, `["L", 14]`, `["T", 4]` (tempo miles), `["S", "pyrA"]`, `["MP", 8]` |
| `week_notes` | Notes shown on a week's header, by week number |

2. Generate it, then rebuild:

```powershell
python plans\make_plan.py plans\my-plans\higdon.json data\plan.json
python plans\make_plan.py plans\my-plans\pfitz.json data\plan2.json   # optional second card
python build_dashboard.py
```

`data\plan.json` is the main card and `data\plan2.json` the optional alternate. Without them the cards stay hidden. `plans/beans-plans/` holds the original author's two plans as worked examples.

The templates are built from each plan's published structure, not copied from the books' or site's daily tables.

---

## Mac / Linux

The steps are the same, using a terminal instead of the `.bat` and `.ps1` files:

```bash
python3 -m venv venv && source venv/bin/activate
pip install garminconnect
python garmin_login.py
python garmin_pull.py && python build_dashboard.py
```

For a daily refresh, add a cron job that runs
`python garmin_pull.py --days 30 --wellness-days 14 && python build_dashboard.py`.

Ignore `deploy/linux/`. It's specific to the original author's home server.

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` isn't recognized | Reinstall Python with "Add to PATH" ticked, or use `py` instead of `python` |
| `No saved tokens` | Run `LOGIN.bat` (or `garmin_login.py`) first |
| Login fails / 401 / 429 | Wait 15 to 30 minutes (Garmin rate-limits logins), then try again |
| Last night's sleep/HRV is missing | Garmin sometimes posts it late. The next refresh fills it in |
| Dashboard looks stale | Check `refresh.log` and re-run `refresh.ps1` |

## Privacy

`.gitignore` keeps `data/`, `dashboard.html`, logs and tokens out of git. If you fork this repo, don't remove those lines. Also don't share `dashboard.html` itself, because your health data is embedded in it.
