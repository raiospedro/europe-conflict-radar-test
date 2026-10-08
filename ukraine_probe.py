
import json
import os
import urllib.request
from collections import Counter
from datetime import datetime, timezone, timedelta

URL = "https://api.ukrainealarm.com/api/v3/alerts"
KEY = os.environ["UKRAINE_ALARM_API_KEY"]
NOW = datetime.now(timezone.utc)

def date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError:
        return None

request = urllib.request.Request(
    URL,
    headers={
        "Authorization": KEY,
        "Accept": "application/json",
        "User-Agent": "EuropeConflictRadar/0.2"
    }
)

with urllib.request.urlopen(request, timeout=45) as response:
    data = json.load(response)

types = Counter()
levels = Counter()
regions_with_alerts = 0
recent_24h = 0
recent_7d = 0
old_alerts = 0
total_alerts = 0

print("=" * 65)
print("UKRAINE ALARM API - COVERAGE TEST v0.2")
print("Execution:", NOW.isoformat())
print("Regions:", len(data))
print("=" * 65)

for region in data:
    alerts = region.get("activeAlerts") or []

    if alerts:
        regions_with_alerts += 1

    for alert in alerts:
        total_alerts += 1
        types[alert.get("type", "UNKNOWN")] += 1

        updated = date(alert.get("lastUpdate"))

        if updated:
            age = NOW - updated

            if timedelta(0) <= age <= timedelta(hours=24):
                recent_24h += 1
            if timedelta(0) <= age <= timedelta(days=7):
                recent_7d += 1
            if age > timedelta(days=30):
                old_alerts += 1

        for level in alert.get("activeAlertLevels") or []:
            levels[level.get("alertLevel", "UNKNOWN")] += 1

print("\nSUMMARY")
print("Regions with alerts:", regions_with_alerts)
print("Total active alert records:", total_alerts)
print("Updated within 24h:", recent_24h)
print("Updated within 7 days:", recent_7d)
print("Last updated over 30 days ago:", old_alerts)

print("\nTHREAT TYPES")
for name, count in types.most_common():
    print(name, count)

print("\nALERT LEVELS")
for name, count in levels.most_common():
    print(name, count)

print("\nMOST RECENT ALERTS")
records = []

for region in data:
    for alert in region.get("activeAlerts") or []:
        updated = date(alert.get("lastUpdate"))
        if updated:
            records.append((
                updated,
                region.get("regionEngName")
                or region.get("regionName"),
                alert.get("type")
            ))

for updated, region, kind in sorted(
    records, reverse=True
)[:15]:
    print(updated.isoformat(), "|", region, "|", kind)

print("\nUKRAINE COVERAGE TEST COMPLETED")
