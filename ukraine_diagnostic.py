
import json
import os
import urllib.request
from collections import Counter
from datetime import datetime, timezone

API_URL = "https://api.ukrainealarm.com/api/v3/alerts"
DB_URL = os.environ["SUPABASE_URL"].rstrip("/")
DB_KEY = os.environ["SUPABASE_SECRET_KEY"]
API_KEY = os.environ["UKRAINE_ALARM_API_KEY"]


def fetch(url, headers):
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize(regions):
    result = {}

    for region in regions:
        rid = str(region.get("regionId") or "")
        rtype = str(region.get("regionType") or "")

        for alert in region.get("activeAlerts") or []:
            threat = str(alert.get("type") or "UNKNOWN")
            key = f"UA:{rtype}:{rid}:{threat}"

            levels = alert.get("activeAlertLevels") or []
            names = sorted({
                str(item.get("alertLevel") or "")
                for item in levels
            })
            created = [
                item["createdAt"]
                for item in levels
                if item.get("createdAt")
            ]

            result[key] = {
                "region": (
                    region.get("regionEngName")
                    or region.get("regionName")
                ),
                "level": ",".join(names) or None,
                "created": min(created) if created else None,
                "updated": alert.get("lastUpdate"),
                "raw": alert,
            }

    return result


def main():
    print("=" * 72)
    print("UKRAINE ALERT DIAGNOSTIC v0.1")
    print("Execution:", datetime.now(timezone.utc).isoformat())
    print("=" * 72)

    regions = fetch(
        API_URL,
        {
            "Authorization": API_KEY,
            "Accept": "application/json",
            "User-Agent": "EuropeConflictRadar-Diagnostic/0.1",
        }
    )

    current = normalize(regions)

    previous = {}
    offset = 0

    while True:
        batch = fetch(
            f"{DB_URL}/rest/v1/ukraine_alert_state"
            f"?select=alert_key,region_name,level,"
            f"source_created_at,source_updated_at,active"
            f"&order=alert_key.asc&limit=1000&offset={offset}",
            {
                "apikey": DB_KEY,
                "Authorization": f"Bearer {DB_KEY}",
            }
        )

        for row in batch:
            previous[row["alert_key"]] = row

        if len(batch) < 1000:
            break

        offset += 1000

    counts = Counter()
    examples = []

    for key, now in current.items():
        old = previous.get(key)

        if old is None:
            counts["NEW"] += 1
            continue

        if not old.get("active"):
            counts["REACTIVATED"] += 1
            continue

        level_changed = old.get("level") != now["level"]

        created_changed = (
            old.get("source_created_at") != now["created"]
        )

        updated_changed = (
            old.get("source_updated_at") != now["updated"]
        )

        if level_changed and created_changed:
            category = "LEVEL_AND_CREATED"
        elif level_changed:
            category = "LEVEL_ONLY"
        elif created_changed:
            category = "CREATED_ONLY"
        elif updated_changed:
            category = "UPDATED_TIMESTAMP_ONLY"
        else:
            category = "UNCHANGED"

        counts[category] += 1

        if category != "UNCHANGED" and len(examples) < 12:
            examples.append({
                "region": now["region"],
                "type": key.split(":")[-1],
                "category": category,
                "old_level": old.get("level"),
                "new_level": now["level"],
                "old_created": old.get("source_created_at"),
                "new_created": now["created"],
                "old_updated": old.get("source_updated_at"),
                "new_updated": now["updated"],
            })

    missing = [
        key for key, old in previous.items()
        if old.get("active") and key not in current
    ]

    print("\nSUMMARY")
    print("API regions:", len(regions))
    print("API active states:", len(current))
    print("DB states:", len(previous))

    for category, count in counts.most_common():
        print(f"{category}: {count}")

    print("MISSING ACTIVE STATES:", len(missing))

    print("\nEXAMPLES")
    for example in examples:
        print(json.dumps(
            example,
            ensure_ascii=False,
            indent=2
        ))

    print("\nUKRAINE DIAGNOSTIC COMPLETED")


if __name__ == "__main__":
    main()
