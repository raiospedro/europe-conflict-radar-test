
import os
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

# EUROPE CONFLICT RADAR - UKRAINE COLLECTOR v0.4
# Historical audit and source timestamp tracking.
# No public alerts. No Matcher integration.

API_URL = "https://api.ukrainealarm.com/api/v3/alerts"
DB_URL = os.environ["SUPABASE_URL"].rstrip("/")
DB_KEY = os.environ["SUPABASE_SECRET_KEY"]
API_KEY = os.environ["UKRAINE_ALARM_API_KEY"]


def now():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        return None


def request_json(url, headers, method="GET", payload=None):
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

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
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            ConnectionResetError
        ) as error:
            if isinstance(error, urllib.error.HTTPError):
                if error.code not in (429, 500, 502, 503, 504):
                    raise
            if attempt == 2:
                raise
            time.sleep(3 * (2 ** attempt))


def headers(prefer=None):
    result = {
        "apikey": DB_KEY,
        "Authorization": f"Bearer {DB_KEY}"
    }
    if prefer:
        result["Prefer"] = prefer
    return result


def db_get(table, query):
    return request_json(
        f"{DB_URL}/rest/v1/{table}?{query}",
        headers()
    )


def db_write(table, rows, upsert=False):
    if not rows:
        return
    url = f"{DB_URL}/rest/v1/{table}"
    prefer = "return=minimal"
    if upsert:
        url += "?on_conflict=alert_key"
        prefer = "resolution=merge-duplicates,return=minimal"
    request_json(url, headers(prefer), "POST", rows)


def normalize(regions, observed):
    result = {}

    for region in regions:
        rid = str(region.get("regionId") or "")
        rtype = str(region.get("regionType") or "")
        if not rid:
            continue

        for alert in region.get("activeAlerts") or []:
            threat = str(alert.get("type") or "UNKNOWN")
            key = f"UA:{rtype}:{rid}:{threat}"
            levels = alert.get("activeAlertLevels") or []

            names = sorted({
                str(x.get("alertLevel") or "")
                for x in levels
            })

            dates = [
                timestamp(x.get("createdAt"))
                for x in levels
            ]
            dates = [x for x in dates if x]

            result[key] = {
                "alert_key": key,
                "region_id": rid,
                "region_type": rtype,
                "region_name": (
                    region.get("regionEngName")
                    or region.get("regionName")
                ),
                "alert_type": threat,
                "level": ",".join(names) or None,
                "source_created_at": min(dates) if dates else None,
                "source_updated_at": timestamp(
                    alert.get("lastUpdate")
                ),
                "last_seen_at": observed,
                "active": True,
                "raw_data": alert
            }

    return result


def missing_count(raw):
    if not isinstance(raw, dict):
        return 0
    meta = raw.get("_radar_meta") or {}
    if not isinstance(meta, dict):
        return 0
    try:
        return max(0, int(meta.get("consecutive_missing", 0)))
    except (ValueError, TypeError):
        return 0


def main():
    observed = now()
    print("=" * 68)
    print("EUROPE CONFLICT RADAR - UKRAINE COLLECTOR v0.4")
    print("Execution:", observed)
    print("=" * 68)

    regions = request_json(API_URL, {
        "Authorization": API_KEY,
        "Accept": "application/json",
        "User-Agent": "EuropeConflictRadar-Ukraine/0.4"
    })

    if not isinstance(regions, list) or not regions:
        raise RuntimeError("Invalid Ukraine API snapshot")

    current = normalize(regions, observed)
    if not current:
        raise RuntimeError("Empty snapshot - no changes saved")

    previous = {}
    offset = 0

    while True:
        batch = db_get(
            "ukraine_alert_state",
            f"select=*&order=alert_key.asc&limit=1000&offset={offset}"
        )
        if not isinstance(batch, list):
            raise RuntimeError("Invalid Supabase response")
        for row in batch:
            previous[row["alert_key"]] = row
        if len(batch) < 1000:
            break
        offset += 1000

    counts = {
        "baseline": 0,
        "activated": 0,
        "updated": 0,
        "ended": 0,
        "unchanged": 0,
        "metadata_only": 0,
        "pending_end": 0
    }

    transitions = []
    upserts = []
    initial = len(previous) == 0

    def record(key, kind, row, old=None, extra=None):
        details = {
            "collector_version": "0.4",
            "region_name": row.get("region_name"),
            "type": row.get("alert_type"),
            "level": row.get("level"),
            "source_created_at": row.get("source_created_at"),
            "source_updated_at": row.get("source_updated_at"),
            "previous_level": (
                old.get("level") if old else None
            ),
            "previous_source_created_at": (
                old.get("source_created_at") if old else None
            ),
            "previous_source_updated_at": (
                old.get("source_updated_at") if old else None
            )
        }

        if extra:
            details.update(extra)

        transitions.append({
            "alert_key": key,
            "transition_type": kind,
            "observed_at": observed,
            "source_updated_at": row.get("source_updated_at"),
            "details": details
        })
        counts[kind] += 1

    # Compare active states.
    for key, row in current.items():
        old = previous.get(key)
        row["raw_data"] = dict(row["raw_data"])
        row["raw_data"]["_radar_meta"] = {
            "consecutive_missing": 0
        }

        if old is None:
            row["first_seen_at"] = observed
            record(
                key,
                "baseline" if initial else "activated",
                row
            )

        else:
            row["first_seen_at"] = old["first_seen_at"]

            if not old.get("active"):
                record(key, "activated", row, old)

            else:
                level_changed = (
                    old.get("level") != row["level"]
                )
                created_changed = (
                    timestamp(old.get("source_created_at"))
                    != row["source_created_at"]
                )
                updated_changed = (
                    timestamp(old.get("source_updated_at"))
                    != row["source_updated_at"]
                )

                if level_changed or created_changed:
                    record(key, "updated", row, old)
                else:
                    counts["unchanged"] += 1
                    if updated_changed:
                        counts["metadata_only"] += 1

        upserts.append(row)

    # Confirm absence across consecutive snapshots.
    for key, old in previous.items():
        if not old.get("active") or key in current:
            continue

        missing = missing_count(old.get("raw_data")) + 1
        old["raw_data"] = dict(old.get("raw_data") or {})
        old["raw_data"]["_radar_meta"] = {
            "consecutive_missing": missing
        }

        if missing >= 2:
            old["active"] = False
            record(
                key, "ended", old,
                extra={
                    "end_observed_at": observed,
                    "end_time_source": "inferred_from_absence",
                    "consecutive_missing": missing
                }
            )
        else:
            counts["pending_end"] += 1

        upserts.append(old)

    # Save states first, then transitions.
    # These two requests are not one atomic transaction.
    db_write("ukraine_alert_state", upserts, upsert=True)
    db_write("ukraine_alert_transitions", transitions)

    print("Regions:", len(regions))
    print("Active alert states:", len(current))

    for key, value in counts.items():
        print(f"{key.upper()}: {value}")

    print("Transitions saved:", len(transitions))
    print("=" * 68)
    print("UKRAINE COLLECTOR v0.4 COMPLETED")
    print("=" * 68)


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
