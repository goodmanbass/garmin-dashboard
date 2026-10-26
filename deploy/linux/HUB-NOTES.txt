This folder is the SOURCE copy of the Garmin dashboard. It is no longer the live one.

Since September 22, 2026 the daily refresh runs on the home hub (192.168.50.56) at about 6:45 AM,
and the up-to-date page is published there, under the Garmin app on the hub.

That means:
  - dashboard.html in this folder stopped updating on September 22. Opening it shows old data.
  - The Windows scheduled task "Garmin Dashboard Refresh" is switched off ON PURPOSE.
    Don't turn it back on - two refreshers would both log into Garmin with the same account.
  - Changes to the dashboard are made here, then copied to /var/lib/bassbudget/garmin on the hub.
