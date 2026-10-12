
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

# EUROPE CONFLICT RADAR
# POLAND IMGW OFFICIAL API PROBE v0.1
# Read-only: no Supabase writes

SOURCES = {
    "METEO": (
        "https://danepubliczne.imgw.pl"
        "/api/data/warningsmeteo"
    ),
    "HYDRO": (
        "https://danepubliczne.imgw.pl"
        "/api/data/warningshydro"
    ),
}

print("=" * 70)
print("EUROPE CONFLICT RADAR - POLAND IMGW PROBE v0.1")
print("Execution:", datetime.now(timezone.utc).isoformat())
print("=" * 70)

for name, url in SOURCES.items():
    print("\n" + "-" * 70)
    print("SOURCE:", name)
    print("URL:", url)

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "EuropeConflictRadar/0.1"
        }
    )

    try:
        with urllib.request.urlopen(
            request, timeout=45
        ) as response:
            raw = response.read()
            print("HTTP STATUS:", response.status)
            print("BYTES:", len(raw))

        data = json.loads(raw.decode("utf-8"))

        print("RESPONSE TYPE:", type(data).__name__)

        if isinstance(data, list):
            print("RECORDS:", len(data))
            examples = data[:2]

        elif isinstance(data, dict):
            print("ROOT FIELDS:", list(data.keys()))
            examples = [data]

        else:
            examples = []

        print("\nSAMPLE DATA")

        for index, item in enumerate(examples, 1):
            print("RECORD:", index)
            print(
                json.dumps(
                    item,
                    ensure_ascii=False,
                    indent=2
                )[:5000]
            )

    except urllib.error.HTTPError as error:
        print("HTTP ERROR:", error.code)

    except Exception as error:
        print(
            "ERROR:",
            type(error).__name__,
            str(error)
        )

print("\n" + "=" * 70)
print("POLAND IMGW PROBE COMPLETED")
print("=" * 70)
