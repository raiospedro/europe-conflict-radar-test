import csv
import io
import urllib.request
import zipfile
from datetime import datetime, timezone

# ============================================================
# EUROPE CONFLICT RADAR
# GDELT 2.0 Event Feed Test v0.3
# ============================================================

LAST_UPDATE_URL = (
    "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"
)

print("=" * 70)
print("EUROPE CONFLICT RADAR - GDELT EVENT FEED TEST v0.3")
print("Execution time:", datetime.now(timezone.utc).isoformat())
print("=" * 70)

# ------------------------------------------------------------
# 1. Discover latest GDELT files
# ------------------------------------------------------------

print("\nLooking for latest GDELT dataset...")

request = urllib.request.Request(
    LAST_UPDATE_URL,
    headers={"User-Agent": "EuropeConflictRadar-Test/0.3"}
)

with urllib.request.urlopen(request, timeout=60) as response:
    last_update = response.read().decode("utf-8")

export_url = None

for line in last_update.splitlines():
    parts = line.split()

    if len(parts) >= 3:
        file_url = parts[2]

        if file_url.endswith(".export.CSV.zip"):
            export_url = file_url
            break

if not export_url:
    raise RuntimeError("Could not find latest GDELT export file.")

print("Latest export:")
print(export_url)

# ------------------------------------------------------------
# 2. Download latest 15-minute event file
# ------------------------------------------------------------

print("\nDownloading latest event dataset...")

request = urllib.request.Request(
    export_url,
    headers={"User-Agent": "EuropeConflictRadar-Test/0.3"}
)

with urllib.request.urlopen(request, timeout=120) as response:
    zip_data = response.read()

print(f"Downloaded {len(zip_data):,} bytes.")

# ------------------------------------------------------------
# 3. Open ZIP and inspect events
# ------------------------------------------------------------

with zipfile.ZipFile(io.BytesIO(zip_data)) as archive:

    filename = archive.namelist()[0]

    print("Dataset inside ZIP:")
    print(filename)

    with archive.open(filename) as csv_file:

        text_stream = io.TextIOWrapper(
            csv_file,
            encoding="utf-8",
            errors="replace"
        )

        reader = csv.reader(text_stream, delimiter="\t")

        total_events = 0
        potential_conflict_events = []

        for row in reader:

            total_events += 1

            # GDELT Event 2.0 has many columns.
            # We initially use only a few stable fields.

            if len(row) < 61:
                continue

            global_event_id = row[0]

            event_code = row[26]
            event_base_code = row[27]
            event_root_code = row[28]

            action_geo_type = row[49]
            action_geo_fullname = row[50]
            action_geo_country = row[51]
            action_geo_adm1 = row[52]

            latitude = row[56]
            longitude = row[57]

            date_added = row[59]
            source_url = row[60]

            # CAMEO root codes:
            # 18 = assault
            # 19 = fight
            # 20 = unconventional mass violence
            #
            # For this first test we deliberately keep
            # the filter broad.

            if event_root_code in {"18", "19", "20"}:

                potential_conflict_events.append({
                    "id": global_event_id,
                    "event_code": event_code,
                    "root_code": event_root_code,
                    "location": action_geo_fullname,
                    "country": action_geo_country,
                    "adm1": action_geo_adm1,
                    "latitude": latitude,
                    "longitude": longitude,
                    "date_added": date_added,
                    "source_url": source_url,
                })

print()
print("=" * 70)
print(f"TOTAL EVENTS IN LATEST 15-MINUTE FILE: {total_events}")
print(
    "POTENTIAL CONFLICT EVENTS:",
    len(potential_conflict_events)
)
print("=" * 70)

# Show maximum 30 events in GitHub log

for number, event in enumerate(
    potential_conflict_events[:30],
    start=1
):

    print()
    print("-" * 70)
    print(f"EVENT {number}")
    print("GDELT ID:", event["id"])
    print("CAMEO code:", event["event_code"])
    print("Root code:", event["root_code"])
    print("Location:", event["location"])
    print("Country:", event["country"])
    print("ADM1:", event["adm1"])
    print("Latitude:", event["latitude"])
    print("Longitude:", event["longitude"])
    print("GDELT DATEADDED:", event["date_added"])
    print("Source:", event["source_url"])

print()
print("=" * 70)
print("GDELT EVENT FEED TEST COMPLETED")
print("=" * 70)
