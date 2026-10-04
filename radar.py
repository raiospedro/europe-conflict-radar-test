import csv
import io
import json
import os
import socket
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from urllib.parse import urlparse

# ============================================================
# EUROPE CONFLICT RADAR v0.5
# Experimental 7-day collection
#
# GDELT -> Europe -> STRICT/WATCH -> Supabase
# ============================================================

LAST_UPDATE_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SECRET_KEY"]

EUROPE_FIPS = {
    "AL": "Albania",
    "AN": "Andorra",
    "AU": "Austria",
    "BE": "Belgium",
    "BK": "Bosnia and Herzegovina",
    "BO": "Belarus",
    "BU": "Bulgaria",
    "CY": "Cyprus",
    "DA": "Denmark",
    "EI": "Ireland",
    "EN": "Estonia",
    "EZ": "Czechia",
    "FI": "Finland",
    "FR": "France",
    "GM": "Germany",
    "GR": "Greece",
    "HR": "Croatia",
    "HU": "Hungary",
    "IC": "Iceland",
    "IT": "Italy",
    "KV": "Kosovo",
    "LG": "Latvia",
    "LH": "Lithuania",
    "LO": "Slovakia",
    "LS": "Liechtenstein",
    "LU": "Luxembourg",
    "MD": "Moldova",
    "MJ": "Montenegro",
    "MK": "North Macedonia",
    "MN": "Monaco",
    "MT": "Malta",
    "NL": "Netherlands",
    "NO": "Norway",
    "PL": "Poland",
    "PO": "Portugal",
    "RI": "Serbia",
    "RO": "Romania",
    "SI": "Slovenia",
    "SM": "San Marino",
    "SP": "Spain",
    "SW": "Sweden",
    "SZ": "Switzerland",
    "UK": "United Kingdom",
    "UP": "Ukraine",
    "VT": "Vatican City",
}

# High-interest CAMEO codes for the experiment.
STRICT_PREFIXES = (
    "190",  # conventional military force
    "191",  # blockade
    "192",  # occupy territory
    "193",  # small arms/light weapons
    "194",  # artillery/tanks
    "195",  # aerial weapons
    "196",  # ceasefire violation
    "20",   # unconventional mass violence
)

# Signals worth keeping for evaluation even when not STRICT.
WATCH_PREFIXES = (
    "152",  # increase military alert status
    "154",  # mobilize/increase armed forces
)

USER_AGENT = "EuropeConflictRadar-Test/0.5"

# ============================================================
# NETWORK HELPERS
# ============================================================

def download(url, attempts=4, timeout=60):
    """Download with retry/backoff for temporary GDELT/network failures."""

    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT},
            )

            with urllib.request.urlopen(
                request,
                timeout=timeout
            ) as response:
                return response.read()

        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            ConnectionResetError,
            TimeoutError,
            socket.timeout,
        ) as error:

            last_error = error

            print(
                f"Download attempt {attempt}/{attempts} failed:",
                repr(error)
            )

            if attempt < attempts:
                wait_seconds = attempt * 15
                print(f"Retrying in {wait_seconds}s...")
                time.sleep(wait_seconds)

    raise RuntimeError(
        f"Download failed after {attempts} attempts: {last_error}"
    )


def supabase_request(method, path, payload=None, prefer=None):
    url = f"{SUPABASE_URL}/rest/v1/{path}"

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }

    if prefer:
        headers["Prefer"] = prefer

    data = None

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers=headers,
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, response.read().decode("utf-8")


# ============================================================
# START
# ============================================================

run_started = datetime.now(timezone.utc)

print("=" * 78)
print("EUROPE CONFLICT RADAR v0.5")
print("Run started:", run_started.isoformat())
print("=" * 78)

# ============================================================
# 1. FIND LATEST GDELT EXPORT
# ============================================================

print("\n[1/6] Finding latest GDELT export...")

last_update = download(
    LAST_UPDATE_URL,
    attempts=4,
    timeout=60
).decode("utf-8")

export_url = None

for line in last_update.splitlines():
    parts = line.split()

    if len(parts) >= 3 and parts[2].endswith(".export.CSV.zip"):
        export_url = parts[2]
        break

if not export_url:
    raise RuntimeError("Latest GDELT export not found.")

print("Export:", export_url)

# ============================================================
# 2. DOWNLOAD DATASET
# ============================================================

print("\n[2/6] Downloading dataset...")

zip_data = download(
    export_url,
    attempts=4,
    timeout=120
)

print(f"Downloaded {len(zip_data):,} bytes")

# ============================================================
# 3. PROCESS
# ============================================================

print("\n[3/6] Processing Europe...")

total_events = 0
europe_events = 0
material_conflict_events = 0
candidates = []

with zipfile.ZipFile(io.BytesIO(zip_data)) as archive:

    filename = archive.namelist()[0]

    with archive.open(filename) as csv_file:

        text_stream = io.TextIOWrapper(
            csv_file,
            encoding="utf-8",
            errors="replace",
        )

        reader = csv.reader(text_stream, delimiter="\t")

        for row in reader:

            total_events += 1

            if len(row) < 61:
                continue

            gdelt_id = row[0]
            is_root_event = row[25]

            event_code = row[26]
            base_code = row[27]
            root_code = row[28]

            quad_class = row[29]
            goldstein = row[30]

            num_mentions = row[31]
            num_sources = row[32]
            num_articles = row[33]
            avg_tone = row[34]

            geo_type = row[51]
            location = row[52]
            country_code = row[53]
            adm1 = row[54]
            latitude = row[56]
            longitude = row[57]

            gdelt_date_added = row[59]
            source_url = row[60]

            if country_code not in EUROPE_FIPS:
                continue

            europe_events += 1

            if quad_class == "4":
                material_conflict_events += 1

            radar_class = None

            if event_code.startswith(STRICT_PREFIXES):
                radar_class = "STRICT"

            elif event_code.startswith(WATCH_PREFIXES):
                radar_class = "WATCH"

            # IMPORTANT:
            # During the experiment we also retain European
            # Material Conflict events that did not match STRICT.
            elif quad_class == "4":
                radar_class = "WATCH"

            if radar_class is None:
                continue

            if not latitude or not longitude:
                continue

            def to_int(value):
                try:
                    return int(value or 0)
                except ValueError:
                    return 0

            def to_float(value):
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return None

            mentions = to_int(num_mentions)
            sources = to_int(num_sources)
            articles = to_int(num_articles)

            goldstein_value = to_float(goldstein)
            tone_value = to_float(avg_tone)
            lat_value = to_float(latitude)
            lon_value = to_float(longitude)

            if lat_value is None or lon_value is None:
                continue

            # Experimental ranking only.
            confidence = 0

            if radar_class == "STRICT":
                confidence += 40
            else:
                confidence += 15

            if quad_class == "4":
                confidence += 15

            if is_root_event == "1":
                confidence += 5

            if sources >= 2:
                confidence += 10

            if sources >= 3:
                confidence += 10

            if articles >= 3:
                confidence += 5

            if mentions >= 5:
                confidence += 5

            if goldstein_value is not None and goldstein_value <= -7:
                confidence += 10

            try:
                source_domain = urlparse(source_url).netloc
            except Exception:
                source_domain = ""

            candidates.append({
                "gdelt_id": gdelt_id,
                "event_key": f"GDELT_{gdelt_id}",
                "event_type": "gdelt_candidate",
                "status": "unverified",
                "country": EUROPE_FIPS[country_code],
                "country_code": country_code,
                "region": adm1 or None,
                "city": location or None,
                "latitude": lat_value,
                "longitude": lon_value,
                "geo_precision": f"GDELT_TYPE_{geo_type}",
                "confidence": confidence,
                "headline": None,
                "description": (
                    "Automatically detected GDELT candidate. "
                    "Location/event may be incorrect. "
                    "Not an official warning."
                ),
                "official_confirmed": False,
                "cameo_code": event_code,
                "cameo_base_code": base_code,
                "cameo_root_code": root_code,
                "quad_class": to_int(quad_class),
                "goldstein_scale": goldstein_value,
                "num_mentions": mentions,
                "num_sources": sources,
                "num_articles": articles,
                "avg_tone": tone_value,
                "source_url": source_url,
                "source_domain": source_domain,
                "radar_class": radar_class,
                "gdelt_date_added": gdelt_date_added,
            })

print("Total GDELT events:", total_events)
print("Europe:", europe_events)
print("European Material Conflict:", material_conflict_events)
print("Candidates:", len(candidates))

# ============================================================
# 4. DEDUPLICATE CURRENT FILE
# ============================================================

print("\n[4/6] Deduplicating current run...")

unique_candidates = {}

for event in candidates:
    unique_candidates[event["gdelt_id"]] = event

candidates = list(unique_candidates.values())

print("Unique candidates:", len(candidates))

# ============================================================
# 5. STORE IN SUPABASE
# ============================================================

print("\n[5/6] Writing candidates to Supabase...")

inserted = 0
already_present = 0
failed = 0

for event in candidates:

    try:
        status, body = supabase_request(
            "POST",
            "events?on_conflict=gdelt_id",
            payload=event,
            prefer="resolution=ignore-duplicates,return=minimal",
        )

        if status in (200, 201, 204):
            inserted += 1

    except urllib.error.HTTPError as error:

        error_body = error.read().decode("utf-8", errors="replace")

        print(
            "Supabase error for",
            event["gdelt_id"],
            error.code,
            error_body,
        )

        failed += 1

# ============================================================
# 6. SUMMARY
# ============================================================

print("\n[6/6] Summary")

print("=" * 78)
print("TOTAL:", total_events)
print("EUROPE:", europe_events)
print("MATERIAL CONFLICT:", material_conflict_events)
print("CANDIDATES:", len(candidates))
print("SUPABASE ACCEPTED:", inserted)
print("SUPABASE FAILED:", failed)
print("=" * 78)

for event in sorted(
    candidates,
    key=lambda item: item["confidence"],
    reverse=True
)[:20]:

    print()
    print(
        event["radar_class"],
        "| score",
        event["confidence"],
        "|",
        event["country"],
        "|",
        event["city"],
        "| CAMEO",
        event["cameo_code"],
    )

    print(
        "Sources:",
        event["num_sources"],
        "| Articles:",
        event["num_articles"],
        "|",
        event["source_domain"],
    )

    print(event["source_url"])

print()
print("RUN COMPLETED:", datetime.now(timezone.utc).isoformat())
