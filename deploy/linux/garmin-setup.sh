#!/bin/bash
# Move the Garmin dashboard refresh onto the Linux box: its own folder, its own Python
# environment, the saved Garmin tokens, and a daily timer that republishes to the home hub.
# Safe to re-run.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this with sudo:  sudo bash ~/garmin-stage/garmin-setup.sh" >&2
  exit 1
fi

BASE=/var/lib/bassbudget
GARMIN="$BASE/garmin"
STAGE="${STAGE:-/home/zach/garmin-stage}"
say() { printf '\n== %s\n' "$1"; }

say "Project folder (not web-served: the code and tokens stay out of the hub)"
install -d -o bassbudget -g bassbudget -m 2770 "$GARMIN" "$GARMIN/data"
cp "$STAGE"/project/*.py "$STAGE"/project/template.html "$GARMIN/"
cp "$STAGE"/project/data/*.json "$GARMIN/data/" 2>/dev/null || true
install -o bassbudget -g bassbudget -m 770 "$STAGE/refresh.sh" "$GARMIN/refresh.sh"
chown -R bassbudget:bassbudget "$GARMIN"
chmod 660 "$GARMIN"/*.py "$GARMIN"/template.html "$GARMIN"/data/*.json 2>/dev/null || true

say "Garmin sign-in tokens (readable only by the service account)"
install -d -o bassbudget -g bassbudget -m 700 "$BASE/.garminconnect"
install -o bassbudget -g bassbudget -m 600 "$STAGE/garmin_tokens.json" "$BASE/.garminconnect/"

say "Python environment (this downloads the Garmin library, give it a minute)"
if [ ! -x "$GARMIN/venv/bin/python" ]; then
  sudo -u bassbudget -H python3 -m venv "$GARMIN/venv"
fi
sudo -u bassbudget -H "$GARMIN/venv/bin/pip" install --quiet --upgrade pip
sudo -u bassbudget -H "$GARMIN/venv/bin/pip" install --quiet garminconnect

say "Daily refresh at 06:45"
install -m 644 "$STAGE/garmin-dashboard.service" "$STAGE/garmin-dashboard.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now garmin-dashboard.timer

say "Running it once now to prove the tokens still work"
if systemctl start garmin-dashboard.service; then
  echo "refresh ran"
else
  echo "!! refresh failed - see: journalctl -u garmin-dashboard -n 40" >&2
fi
journalctl -u garmin-dashboard -n 12 --no-pager | tail -10

say "Cleaning up the staged copy of the tokens"
shred -u "$STAGE/garmin_tokens.json" 2>/dev/null || rm -f "$STAGE/garmin_tokens.json"

cat <<'DONE'

===========================================================
 Done. Tell Claude it finished.
===========================================================
DONE
