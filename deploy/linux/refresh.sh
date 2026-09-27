#!/bin/bash
# Pull whatever is new from Garmin, rebuild the dashboard, and publish it to the home hub.
# The cache is incremental, so the short windows below are enough; wellness reaches back further
# because sleep and HRV for a night can land in Garmin Connect a day or two late.
set -uo pipefail

HERE=/var/lib/bassbudget/garmin
PUBLISH=/var/lib/bassbudget/apps/garmin/index.html
cd "$HERE" || exit 1

"$HERE/venv/bin/python" garmin_pull.py --days 30 --wellness-days 14 || exit 1
"$HERE/venv/bin/python" build_dashboard.py || exit 1

# Publish only a dashboard that actually built, so a bad run cannot blank the page.
if [ -s "$HERE/dashboard.html" ]; then
  install -m 660 "$HERE/dashboard.html" "$PUBLISH"
  echo "published -> $PUBLISH ($(du -h "$PUBLISH" | cut -f1))"
else
  echo "dashboard.html missing or empty - kept the previous published copy" >&2
  exit 1
fi
