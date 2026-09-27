# Daily refresh: pull whatever is new from Garmin, then rebuild dashboard.html.
# The cache is incremental, so a short window is enough -- it only fetches days
# it doesn't already have. Wellness reaches back 14 days because sleep and HRV
# for a given night can land in Garmin Connect a day or two late.

$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path "refresh.log" -Value "`n===== $stamp =====" -Encoding utf8

python garmin_pull.py --days 30 --wellness-days 14 2>&1 |
  Add-Content -Path "refresh.log" -Encoding utf8

python build_dashboard.py 2>&1 |
  Add-Content -Path "refresh.log" -Encoding utf8
