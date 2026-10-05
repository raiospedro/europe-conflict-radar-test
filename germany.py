import json
import urllib.request
from datetime import datetime, timezone

BASE_URL = "https://warnung.bund.de/api31"
MAP_URL = f"{BASE_URL}/mowas/mapData.json"

print("=" * 72)
print("GERMANY NINA / MOWAS OFFICIAL ALERT TEST")
print("Execution:", datetime.now(timezone.utc).isoformat())
print("=" * 72)

request = urllib.request.Request(
    MAP_URL,
    headers={
        "User-Agent": "EuropeConflictRadar-Test/0.1",
        "Accept": "application/json",
    },
)

with urllib.request.urlopen(request, timeout=60) as response:
    alerts = json.loads(response.read().decode("utf-8"))

print(f"\nCurrent MoWaS alerts: {len(alerts)}")

# Mais recentes primeiro
alerts.sort(
    key=lambda x: x.get("startDate", ""),
    reverse=True
)

for number, alert in enumerate(alerts[:20], start=1):

    alert_id = alert.get("id")
    title = alert.get("i18nTitle", {}).get("en")
    title_de = alert.get("i18nTitle", {}).get("de")

    print()
    print("-" * 72)
    print(f"ALERT {number}")
    print("ID:", alert_id)
    print("Start:", alert.get("startDate"))
    print("Expires:", alert.get("expiresDate"))
    print("Type:", alert.get("type"))
    print("Severity:", alert.get("severity"))
    print("Urgency:", alert.get("urgency"))
    print("Event code:", alert.get("transKeys", {}).get("event"))
    print("Title DE:", title_de)
    print("Title EN:", title)

    if alert_id:
        print(
            "Detail:",
            f"{BASE_URL}/warnings/{alert_id}.json"
        )
        print(
            "GeoJSON:",
            f"{BASE_URL}/warnings/{alert_id}.geojson"
        )

print()
print("=" * 72)
print("GERMANY TEST COMPLETED")
print("=" * 72)
