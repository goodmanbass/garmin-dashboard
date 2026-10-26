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

## 6. Training plan card (optional)

Drop a `data\plan.json` in and the dashboard adds a day-by-day plan card. Each past day shows what you actually ran next to what was planned (green when you hit 90%+). Without the file, the card stays hidden.

```json
{
  "name": "My marathon plan",
  "weeks": [{"week": 1, "note": "Recovery week"}],
  "key": [["Tempo", "3 x 1 mi at half-marathon pace, 2 min jog"]],
  "days": [
    {"date": "2027-01-04", "week": 1, "kind": "easy", "title": "6 easy", "mi": 6, "detail": "HR under 150"},
    {"date": "2027-01-05", "week": 1, "kind": "speed", "title": "6 x 800", "mi": 7.5, "detail": "400 m jog between"}
  ]
}
```

`kind` sets the colour stripe: `easy`, `speed`, `tempo`, `mp` (marathon pace), `long`, `rest`, `race`. Hover a day to see its `detail`.

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
