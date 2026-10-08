
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

API_URL = "https://api.ukrainealarm.com/api/v3/alerts"
API_KEY = os.environ["UKRAINE_ALARM_API_KEY"]

print("=" * 65)
print("EUROPE CONFLICT RADAR - UKRAINE API PROBE v0.1")
print("Execution:", datetime.now(timezone.utc).isoformat())
print("=" * 65)

request = urllib.request.Request(
    API_URL,
    headers={
        "Authorization": API_KEY,
        "Accept": "application/json",
        "User-Agent": "EuropeConflictRadar/0.1",
    },
)

try:
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read()
        print("HTTP STATUS:", response.status)
        print("Downloaded bytes:", len(raw))

    data = json.loads(raw.decode("utf-8"))

    print("Response type:", type(data).__name__)

    if isinstance(data, list):
        print("Regions returned:", len(data))
        records = data[:3]
    elif isinstance(data, dict):
        print("Response fields:", list(data.keys()))
        records = [data]
    else:
        records = []

    print("\nSAMPLE DATA")
    for index, record in enumerate(records, 1):
        print("-" * 65)
        print("Record:", index)
        print(json.dumps(record, ensure_ascii=False, indent=2)[:4000])

    print("\nUKRAINE API TEST COMPLETED")

except urllib.error.HTTPError as error:
    print("HTTP ERROR:", error.code)
    print(error.read().decode("utf-8", errors="replace")[:1000])
    raise SystemExit(1)

except Exception as error:
    print("CONNECTION ERROR:", type(error).__name__, str(error))
    raise SystemExit(1)
