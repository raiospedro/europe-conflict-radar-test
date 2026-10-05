import json
import urllib.request
from datetime import datetime, timezone

URL = (
    "https://get.data.gov.lt/"
    "datasets/gov/pagd/pranesimai/:all/:format/json"
)

print("=" * 70)
print("LITHUANIA OFFICIAL ALERT DATA TEST")
print("Execution time:", datetime.now(timezone.utc).isoformat())
print("=" * 70)

request = urllib.request.Request(
    URL,
    headers={
        "User-Agent": "EuropeConflictRadar-Test/0.1",
        "Accept": "application/json",
    },
)

with urllib.request.urlopen(request, timeout=60) as response:
    raw = response.read().decode("utf-8")
    data = json.loads(raw)

print("HTTP request successful.")
print("Response type:", type(data).__name__)

# Descobrir automaticamente a estrutura antes de programarmos
# a ingestão definitiva.

if isinstance(data, list):

    print("Records:", len(data))

    sample = data[-10:] if len(data) > 10 else data

elif isinstance(data, dict):

    print("Top-level keys:", list(data.keys()))

    # Alguns endpoints devolvem os registos dentro de _data.
    if "_data" in data and isinstance(data["_data"], list):
        sample = data["_data"][-10:]
        print("Records in _data:", len(data["_data"]))

    else:
        sample = [data]

else:
    sample = []

print()
print("=" * 70)
print("LAST/SAMPLE RECORDS")
print("=" * 70)

for number, record in enumerate(sample, start=1):

    print()
    print("-" * 70)
    print("RECORD", number)

    if isinstance(record, dict):

        for key, value in record.items():
            print(f"{key}: {value}")

    else:
        print(record)

print()
print("=" * 70)
print("LITHUANIA TEST COMPLETED")
print("=" * 70)
