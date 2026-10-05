import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE_URL = "https://warnung.bund.de/api31"
MAP_URL = f"{BASE_URL}/mowas/mapData.json"

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SECRET_KEY"]

USER_AGENT = "EuropeConflictRadar-Germany/0.2"


def download_json(url, attempts=3):

    last_error = None

    for attempt in range(1, attempts + 1):

        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                },
            )

            with urllib.request.urlopen(
                request,
                timeout=60
            ) as response:

                return json.loads(
                    response.read().decode("utf-8")
                )

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
                time.sleep(attempt * 10)

    raise RuntimeError(last_error)


def supabase_insert(payload):

    endpoint = (
        f"{SUPABASE_URL}/rest/v1/"
        "official_alerts?on_conflict=external_id"
    )

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        endpoint,
        data=data,
        method="POST",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=ignore-duplicates,return=minimal",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:

        return response.status


print("=" * 76)
print("GERMANY NINA / MOWAS COLLECTOR")
print("Execution:", datetime.now(timezone.utc).isoformat())
print("=" * 76)

alerts = download_json(MAP_URL)

print("Current MoWaS records:", len(alerts))

accepted = 0
failed = 0

for alert in alerts:

    alert_id = alert.get("id")

    if not alert_id:
        continue

    detail_url = f"{BASE_URL}/warnings/{alert_id}.json"
    geo_url = f"{BASE_URL}/warnings/{alert_id}.geojson"

    # --------------------------------------------------
    # DETAIL
    # --------------------------------------------------

    try:
        detail = download_json(detail_url)

    except Exception as error:
        print("Detail failed:", alert_id, error)
        detail = {}

    # --------------------------------------------------
    # GEOJSON
    # --------------------------------------------------

    try:
        geometry = download_json(geo_url)

    except Exception as error:
        print("GeoJSON failed:", alert_id, error)
        geometry = None

    title_de = (
        alert.get("i18nTitle", {}).get("de")
        or alert.get("i18nTitle", {}).get("en")
        or ""
    )

    title_en = (
        alert.get("i18nTitle", {}).get("en")
        or title_de
    )

    alert_type = alert.get("type")

    # Mapear estado
    if alert_type == "Cancel":
        status = "cancelled"

    elif alert_type == "Update":
        status = "updated"

    else:
        status = "active"

    payload = {
        "country": "Germany",
        "authority": "MoWaS / NINA",
        "external_id": alert_id,

        "alert_type": alert_type,
        "status": status,

        "region": None,
        "area_description": title_de,

        "issued_at": alert.get("startDate"),
        "expires_at": alert.get("expiresDate"),

        "headline": title_en,
        "description": title_de,

        "source_url": detail_url,
        "source_type": "official",

        "severity": alert.get("severity"),
        "urgency": alert.get("urgency"),

        "event_code": (
            alert.get("transKeys", {}).get("event")
        ),

        "geometry": geometry,

        "raw_data": {
            "summary": alert,
            "detail": detail,
        },
    }

    try:

        status_code = supabase_insert(payload)

        if status_code in (200, 201, 204):
            accepted += 1

            print(
                "OK",
                alert_type,
                alert.get("startDate"),
                title_de,
            )

    except urllib.error.HTTPError as error:

        failed += 1

        print(
            "SUPABASE ERROR",
            alert_id,
            error.code,
            error.read().decode(
                "utf-8",
                errors="replace"
            ),
        )

print()
print("=" * 76)
print("MOWAS RECORDS:", len(alerts))
print("SUPABASE ACCEPTED:", accepted)
print("SUPABASE FAILED:", failed)
print("=" * 76)
