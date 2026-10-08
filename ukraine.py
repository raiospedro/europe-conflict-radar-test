
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API_URL = "https://api.ukrainealarm.com/api/v3/alerts"
DB_URL = os.environ["SUPABASE_URL"].rstrip("/")
DB_KEY = os.environ["SUPABASE_SECRET_KEY"]
API_KEY = os.environ["UKRAINE_ALARM_API_KEY"]

def request_json(url, headers, method="GET", payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    headers = dict(headers)

    if body is not None:
        headers["Content-Type"] = "application/json"

    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url, data=body, headers=headers, method=method
            )
            with urllib.request.urlopen(req, timeout=45) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except (urllib.error.HTTPError, urllib.error.URLError,
                TimeoutError, ConnectionResetError) as error:
            if isinstance(error, urllib.error.HTTPError):
                if error.code not in (429, 500, 502, 503, 504):
                    raise
            if attempt == 2:
                raise
            time.sleep(3 * (2 ** attempt))

def db_headers(prefer=None):
    headers = {
        "apikey": DB_KEY,
        "Authorization": f"Bearer {DB_KEY}"
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers

def db_get(table, query):
    return request_json(
        f"{DB_URL}/rest/v1/{table}?{query}",
        db_headers()
    )

def db_post(table, rows, prefer="return=minimal"):
    if rows:
        return request_json(
            f"{DB_URL}/rest/v1/{table}",
            db_headers(prefer),
            "POST", rows
        )

def db_upsert(rows):
    if rows:
        return request_json(
            f"{DB_URL}/rest/v1/ukraine_alert_state"
            "?on_conflict=alert_key",
            db_headers("resolution=merge-duplicates,return=minimal"),
            "POST", rows
        )

def now_utc():
    return datetime.now(timezone.utc).isoformat()

def normalize(regions, observed):
    result = {}

    for region in regions:
        region_id = str(region.get("regionId") or "")
        region_type = str(region.get("regionType") or "")

        for alert in region.get("activeAlerts") or []:
            threat = str(alert.get("type") or "UNKNOWN")
            key = f"UA:{region_type}:{region_id}:{threat}"

            levels = alert.get("activeAlertLevels") or []
            names = sorted({
                str(item.get("alertLevel") or "")
                for item in levels
            })
            created = [
                item["createdAt"] for item in levels
                if item.get("createdAt")
            ]

            result[key] = {
                "alert_key": key,
                "region_id": region_id,
                "region_type": region_type,
                "region_name": (
                    region.get("regionEngName")
                    or region.get("regionName")
                ),
                "alert_type": threat,
                "level": ",".join(names) or None,
                "source_created_at": min(created) if created else None,
                "source_updated_at": alert.get("lastUpdate"),
                "last_seen_at": observed,
                "active": True,
                "raw_data": alert
            }

    return result

def main():
    print("EUROPE CONFLICT RADAR - UKRAINE COLLECTOR v0.1")
    observed = now_utc()

    regions = request_json(
        API_URL,
        {
            "Authorization": API_KEY,
            "Accept": "application/json",
            "User-Agent": "EuropeConflictRadar-Ukraine/0.1"
        }
    )

    if not isinstance(regions, list) or not regions:
        raise RuntimeError("Invalid Ukraine API response")

    current = normalize(regions, observed)

    if not current:
        raise RuntimeError("Empty snapshot; refusing to end alerts")

    previous = {}
    offset = 0

    while True:
        batch = db_get(
            "ukraine_alert_state",
            f"select=*&order=alert_key.asc"
            f"&limit=1000&offset={offset}"
        )
        for item in batch:
            previous[item["alert_key"]] = item

        if len(batch) < 1000:
            break
        offset += 1000

    changes = []
    upserts = []
    counts = {
        "baseline": 0,
        "activated": 0,
        "updated": 0,
        "ended": 0,
        "unchanged": 0
    }

    initial_snapshot = len(previous) == 0

    for key, row in current.items():
        old = previous.get(key)

        if old is None:
            kind = "baseline" if initial_snapshot else "activated"
            row["first_seen_at"] = observed

        else:
            row["first_seen_at"] = old["first_seen_at"]

            if not old.get("active"):
                kind = "activated"
            elif (
                old.get("level") != row["level"]
                or old.get("source_updated_at")
                   != row["source_updated_at"]
                or old.get("source_created_at")
                   != row["source_created_at"]
            ):
                kind = "updated"
            else:
                kind = None

        if kind:
            counts[kind] += 1
            changes.append({
                "alert_key": key,
                "transition_type": kind,
                "observed_at": observed,
                "source_updated_at": row["source_updated_at"],
                "details": {
                    "region_name": row["region_name"],
                    "type": row["alert_type"],
                    "level": row["level"]
                }
            })
        else:
            counts["unchanged"] += 1

        upserts.append(row)

    for key, old in previous.items():
        if old.get("active") and key not in current:
            counts["ended"] += 1
            old["active"] = False
            old["last_seen_at"] = observed
            upserts.append(old)

            changes.append({
                "alert_key": key,
                "transition_type": "ended",
                "observed_at": observed,
                "source_updated_at": old.get("source_updated_at"),
                "details": {
                    "region_name": old.get("region_name"),
                    "type": old.get("alert_type")
                }
            })

    db_upsert(upserts)
    db_post("ukraine_alert_transitions", changes)

    print("Regions:", len(regions))
    print("Active alert states:", len(current))

    for key, value in counts.items():
        print(f"{key.upper()}: {value}")

    print("UKRAINE COLLECTOR COMPLETED")

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            "COLLECTOR ERROR:",
            type(error).__name__,
            str(error),
            file=sys.stderr
        )
        raise
