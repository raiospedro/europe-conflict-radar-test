
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# ============================================================
# EUROPE CONFLICT RADAR - UKRAINE COLLECTOR v0.3
#
# - Normalize UTC timestamps before comparison
# - Ignore timestamp formatting differences
# - Separate metadata changes from threat changes
# - Require 2 consecutive absences before ending alerts
# - Preserve historical state and baseline
# ============================================================

API_URL = "https://api.ukrainealarm.com/api/v3/alerts"
DB_URL = os.environ["SUPABASE_URL"].rstrip("/")
DB_KEY = os.environ["SUPABASE_SECRET_KEY"]
API_KEY = os.environ["UKRAINE_ALARM_API_KEY"]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def parse_timestamp(value):
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except (ValueError, TypeError):
        return None


def timestamps_equal(a, b):
    if not a and not b:
        return True

    da = parse_timestamp(a)
    db = parse_timestamp(b)

    if da is not None and db is not None:
        return da == db

    return a == b


def request_json(url, headers, method="GET", payload=None):
    body = None

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    headers = dict(headers)

    if body is not None:
        headers["Content-Type"] = "application/json"

    for attempt in range(3):
        try:
            request = urllib.request.Request(
                url,
                data=body,
                headers=headers,
                method=method
            )

            with urllib.request.urlopen(
                request,
                timeout=45
            ) as response:

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


def db_post(table, rows):
    if rows:
        request_json(
            f"{DB_URL}/rest/v1/{table}",
            db_headers("return=minimal"),
            "POST",
            rows
        )


def db_upsert(rows):
    if rows:
        request_json(
            f"{DB_URL}/rest/v1/ukraine_alert_state"
            "?on_conflict=alert_key",
            db_headers(
                "resolution=merge-duplicates,return=minimal"
            ),
            "POST",
            rows
        )


def normalize(regions, observed):
    result = {}

    for region in regions:
        region_id = str(region.get("regionId") or "")
        region_type = str(region.get("regionType") or "")

        if not region_id:
            continue

        for alert in region.get("activeAlerts") or []:
            threat = str(alert.get("type") or "UNKNOWN")

            key = (
                f"UA:{region_type}:{region_id}:{threat}"
            )

            levels = alert.get("activeAlertLevels") or []

            level_names = sorted({
                str(item.get("alertLevel") or "")
                for item in levels
            })

            created_dates = [
                item["createdAt"]
                for item in levels
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
                "level": ",".join(level_names) or None,
                "source_created_at": (
                    min(created_dates)
                    if created_dates else None
                ),
                "source_updated_at": alert.get("lastUpdate"),
                "last_seen_at": observed,
                "active": True,
                "raw_data": alert
            }

    return result


def missing_count(raw):
    if not isinstance(raw, dict):
        return 0

    metadata = raw.get("_radar_meta")

    if not isinstance(metadata, dict):
        return 0

    try:
        return max(
            0,
            int(metadata.get("consecutive_missing", 0))
        )

    except (ValueError, TypeError):
        return 0


def main():
    observed = utc_now()

    print("=" * 70)
    print("EUROPE CONFLICT RADAR - UKRAINE COLLECTOR v0.3")
    print("Execution:", observed)
    print("=" * 70)

    regions = request_json(
        API_URL,
        {
            "Authorization": API_KEY,
            "Accept": "application/json",
            "User-Agent": "EuropeConflictRadar-Ukraine/0.3"
        }
    )

    if not isinstance(regions, list) or not regions:
        raise RuntimeError(
            "Invalid or empty Ukraine API response"
        )

    current = normalize(regions, observed)

    if not current:
        raise RuntimeError(
            "Empty snapshot: refusing to end stored alerts"
        )

    previous = {}
    offset = 0

    while True:
        batch = db_get(
            "ukraine_alert_state",
            "select=*&order=alert_key.asc"
            f"&limit=1000&offset={offset}"
        )

        for item in batch:
            previous[item["alert_key"]] = item

        if len(batch) < 1000:
            break

        offset += 1000

    initial_snapshot = len(previous) == 0

    changes = []
    upserts = []

    counts = {
        "baseline": 0,
        "activated": 0,
        "updated": 0,
        "ended": 0,
        "unchanged": 0,
        "metadata_only": 0,
        "pending_end": 0
    }

    def transition(key, kind, row):
        changes.append({
            "alert_key": key,
            "transition_type": kind,
            "observed_at": observed,
            "source_updated_at": row.get(
                "source_updated_at"
            ),
            "details": {
                "region_name": row.get("region_name"),
                "type": row.get("alert_type"),
                "level": row.get("level")
            }
        })

        counts[kind] += 1

    # ========================================================
    # COMPARE CURRENT ALERTS
    # ========================================================

    for key, row in current.items():
        old = previous.get(key)

        row["raw_data"] = dict(row["raw_data"])

        row["raw_data"]["_radar_meta"] = {
            "consecutive_missing": 0
        }

        if old is None:
            row["first_seen_at"] = observed

            kind = (
                "baseline"
                if initial_snapshot
                else "activated"
            )

            transition(key, kind, row)

        else:
            row["first_seen_at"] = old["first_seen_at"]

            if not old.get("active"):
                transition(key, "activated", row)

            else:
                level_changed = (
                    old.get("level") != row["level"]
                )

                created_changed = not timestamps_equal(
                    old.get("source_created_at"),
                    row.get("source_created_at")
                )

                updated_changed = not timestamps_equal(
                    old.get("source_updated_at"),
                    row.get("source_updated_at")
                )

                if level_changed or created_changed:
                    transition(key, "updated", row)

                else:
                    counts["unchanged"] += 1

                    if updated_changed:
                        counts["metadata_only"] += 1

        upserts.append(row)

    # ========================================================
    # DETECT MISSING ALERTS
    # ========================================================

    for key, old in previous.items():
        if not old.get("active"):
            continue

        if key in current:
            continue

        missing = missing_count(
            old.get("raw_data")
        ) + 1

        old["last_seen_at"] = observed

        old["raw_data"] = dict(
            old.get("raw_data") or {}
        )

        old["raw_data"]["_radar_meta"] = {
            "consecutive_missing": missing
        }

        if missing >= 2:
            old["active"] = False
            transition(key, "ended", old)

        else:
            counts["pending_end"] += 1

        upserts.append(old)

    # ========================================================
    # SAVE
    # ========================================================

    db_upsert(upserts)
    db_post(
        "ukraine_alert_transitions",
        changes
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    print("Regions:", len(regions))
    print("Active alert states:", len(current))

    for key, value in counts.items():
        print(f"{key.upper()}: {value}")

    print("=" * 70)
    print("UKRAINE COLLECTOR v0.3 COMPLETED")
    print("=" * 70)


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
