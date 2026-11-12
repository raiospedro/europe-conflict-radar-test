
import json
import math
import os
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# ============================================================
# EUROPE CONFLICT RADAR MATCHER v0.5.1
# EGRESS OPTIMIZATION
#
# Preserves v0.5 matching thresholds.
# Limits Supabase reads to recent data.
# Re-evaluates recent official alerts.
# Fixes undefined latency variables.
# Does not delete historical records.
# ============================================================

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SECRET_KEY"]
UA = "EuropeConflictRadar-Matcher/0.5.1"

NOW = datetime.now(timezone.utc)

OFFICIAL_HOURS = 24
GDELT_HOURS = 30
PAGE_SIZE = 500

RELEVANT = {
    "explosion", "explosive", "bomb", "bombing",
    "missile", "rocket", "drone", "air raid",
    "airstrike", "air strike", "attack", "armed",
    "shooting", "terror", "terrorism", "terrorist",
    "evacuation", "chemical", "radiological",
    "nuclear", "ammunition", "munition",
    "artillery", "shelling", "large scale fire",
    "major fire", "world war bomb", "bombe",
    "bomben", "bombenentscharfung", "anschlag",
    "terrorismus", "evakuierung", "grossbrand",
    "sprengstoff", "attentat", "attaque",
    "incendie majeur", "incendie important"
}

TEST = {
    "test", "testing", "exercise", "drill",
    "probealarm", "ubung", "uebung",
    "essai", "exercice"
}

CONCEPTS = {
    "bomb": {
        "bomb", "bombing", "bombe", "bomben",
        "bombenentscharfung", "munition",
        "ammunition", "explosive", "sprengstoff",
        "world war bomb"
    },
    "explosion": {
        "explosion", "blast", "detonation", "explosive"
    },
    "missile": {
        "missile", "rocket", "airstrike",
        "air strike", "shelling", "artillery"
    },
    "drone": {
        "drone", "uav", "unmanned aerial"
    },
    "attack": {
        "attack", "attacked", "attentat",
        "attaque", "anschlag", "armed", "shooting"
    },
    "terror": {
        "terror", "terrorism", "terrorist",
        "anschlag", "attentat"
    },
    "evacuation": {
        "evacuation", "evacuate",
        "evacuated", "evakuierung"
    },
    "fire": {
        "large scale fire", "major fire",
        "grossbrand", "incendie majeur",
        "incendie important"
    },
    "chemical": {
        "chemical", "hazardous substance",
        "toxic", "radiological", "nuclear"
    },
    "military": {
        "artillery", "shelling"
    }
}

STOP = {
    "alert", "warning", "official", "update",
    "cancel", "cancelled", "public", "immediate",
    "unknown", "actual", "germany", "luxembourg",
    "united", "kingdom", "city", "district",
    "area", "region", "state", "from", "with",
    "this", "that", "into", "near", "over",
    "under", "after", "before", "during",
    "large", "scale"
}


def norm(value):
    if not value:
        return ""

    value = re.sub(r"<[^>]+>", " ", str(value))
    value = unicodedata.normalize("NFKD", value)

    value = "".join(
        char for char in value
        if not unicodedata.combining(char)
    ).lower()

    return re.sub(
        r"\s+", " ",
        re.sub(r"[^a-z0-9\s\-]", " ", value)
    ).strip()


def official_text(alert):
    return norm(" ".join(
        str(alert.get(key) or "")
        for key in (
            "headline", "description",
            "event_code", "area_description"
        )
    ))


def gdelt_text(event):
    return norm(" ".join(
        str(event.get(key) or "")
        for key in (
            "headline", "description", "city",
            "region", "country", "source_domain",
            "source_url"
        )
    ))


def concepts(text):
    return {
        concept
        for concept, terms in CONCEPTS.items()
        if any(term in text for term in terms)
    }


def tokens(text):
    return {
        word
        for word in re.findall(
            r"\b[a-z][a-z0-9\-]{3,}\b", text
        )
        if word not in STOP
    }


def is_test(alert):
    words = set(re.findall(
        r"\b[a-z0-9\-]+\b",
        official_text(alert)
    ))
    return bool(words & TEST)


def relevant(alert):
    text = official_text(alert)
    return any(term in text for term in RELEVANT)


def api_request(table, params="", payload=None, method="GET",
                prefer=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    if params:
        url += "?" + params

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "User-Agent": UA
    }

    if prefer:
        headers["Prefer"] = prefer

    body = None

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method
    )

    with urllib.request.urlopen(
        request, timeout=45
    ) as response:
        raw = response.read()
        return (
            json.loads(raw.decode("utf-8"))
            if raw else None
        )


def get_pages(table, filters, columns, page_size=PAGE_SIZE):
    rows = []
    offset = 0

    while True:
        params = urllib.parse.urlencode({
            "select": ",".join(columns),
            **filters,
            "order": "id.asc",
            "limit": page_size,
            "offset": offset
        })

        batch = api_request(table, params)

        if not isinstance(batch, list):
            raise RuntimeError(
                f"Invalid response from {table}"
            )

        rows.extend(batch)

        if len(batch) < page_size:
            break

        offset += page_size

    return rows


def fetch_official():
    cutoff = (
        NOW - timedelta(hours=OFFICIAL_HOURS)
    ).isoformat()

    columns = [
        "id", "country", "headline", "description",
        "event_code", "area_description",
        "issued_at", "geometry"
    ]

    return get_pages(
        "official_alerts",
        {"issued_at": "gte." + cutoff},
        columns
    )


def fetch_gdelt():
    cutoff = (
        NOW - timedelta(hours=GDELT_HOURS)
    ).isoformat()

    columns = [
        "id", "country", "headline", "description",
        "city", "region", "source_domain",
        "source_url", "latitude", "longitude",
        "gdelt_date_added", "first_detected_at"
    ]

    return get_pages(
        "events",
        {
            "event_type": "eq.gdelt_candidate",
            "first_detected_at": "gte." + cutoff
        },
        columns
    )


def existing_matches():
    cutoff = (
        NOW - timedelta(hours=OFFICIAL_HOURS)
    ).isoformat()

    return get_pages(
        "event_matches",
        {"official_time": "gte." + cutoff},
        [
            "id", "official_alert_id",
            "gdelt_event_id", "classification"
        ]
    )


def insert_match(payload):
    params = ""

    if payload.get("gdelt_event_id") is not None:
        params = (
            "on_conflict=official_alert_id,gdelt_event_id"
        )

    return api_request(
        "event_matches",
        params=params,
        payload=payload,
        method="POST",
        prefer=(
            "resolution=ignore-duplicates,return=minimal"
            if params else "return=minimal"
        )
    )


def parse_time(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def gdelt_time(value):
    try:
        return datetime.strptime(
            value, "%Y%m%d%H%M%S"
        ).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def haversine(a, b, c, d):
    radius = 6371.0

    p1 = math.radians(a)
    p2 = math.radians(c)

    da = math.radians(c - a)
    db = math.radians(d - b)

    z = (
        math.sin(da / 2) ** 2
        + math.cos(p1) * math.cos(p2)
        * math.sin(db / 2) ** 2
    )

    return radius * 2 * math.atan2(
        math.sqrt(z),
        math.sqrt(max(0, 1 - z))
    )


def collect_coords(value, output):
    if isinstance(value, dict):
        if "coordinates" in value:
            collect_coords(value["coordinates"], output)

        for polygon in value.get("polygons", []):
            if isinstance(polygon, str):
                for pair in polygon.split():
                    try:
                        lat, lon = pair.split(",")
                        output.append(
                            (float(lat), float(lon))
                        )
                    except (ValueError, TypeError):
                        pass

        for key, item in value.items():
            if key not in ("coordinates", "polygons"):
                collect_coords(item, output)

    elif isinstance(value, list):
        if (
            len(value) >= 2
            and isinstance(value[0], (int, float))
            and isinstance(value[1], (int, float))
        ):
            lon, lat = float(value[0]), float(value[1])

            if -90 <= lat <= 90 and -180 <= lon <= 180:
                output.append((lat, lon))
        else:
            for item in value:
                collect_coords(item, output)


def point(geometry):
    output = []
    collect_coords(geometry, output)

    if not output:
        return None

    return (
        sum(lat for lat, _ in output) / len(output),
        sum(lon for _, lon in output) / len(output)
    )


def semantic(alert, event):
    ot = official_text(alert)
    gt = gdelt_text(event)

    common_concepts = concepts(ot) & concepts(gt)
    common_tokens = tokens(ot) & tokens(gt)

    location_text = norm(
        (alert.get("area_description") or "")
        + " "
        + (alert.get("headline") or "")
    )

    common_locations = (
        tokens(location_text) & tokens(gt)
    )

    score = (
        (40 if common_concepts else 0)
        + min(len(common_locations) * 15, 30)
        + min(
            len(common_tokens - common_locations) * 5,
            15
        )
    )

    return (
        score,
        bool(common_concepts),
        sorted(common_concepts),
        sorted(common_locations)
    )


def main():
    print("=" * 72)
    print("EUROPE CONFLICT RADAR MATCHER v0.5.1")
    print("Execution:", NOW.isoformat())
    print("=" * 72)

    official = fetch_official()
    events = fetch_gdelt()
    matches = existing_matches()

    relevant_alerts = [
        alert for alert in official
        if not is_test(alert) and relevant(alert)
    ]

    print("Official window hours:", OFFICIAL_HOURS)
    print("GDELT window hours:", GDELT_HOURS)
    print("Official alerts loaded:", len(official))
    print("GDELT candidates loaded:", len(events))
    print("Relevant official alerts:", len(relevant_alerts))

    existing_pairs = {
        (
            row["official_alert_id"],
            row["gdelt_event_id"]
        )
        for row in matches
        if row.get("gdelt_event_id") is not None
    }

    existing_no_candidate = {
        row["official_alert_id"]
        for row in matches
        if row.get("classification") == "no_candidate"
    }

    events_by_country = {}

    for event in events:
        country = norm(event.get("country"))
        events_by_country.setdefault(
            country, []
        ).append(event)

    counts = {
        "probable": 0,
        "possible": 0,
        "accepted": 0,
        "no_candidate": 0,
        "already_recorded": 0,
        "rejected_time": 0,
        "rejected_distance": 0,
        "rejected_semantics": 0
    }

    for alert in relevant_alerts:
        official_time = parse_time(
            alert.get("issued_at")
        )

        if not official_time:
            continue

        official_point = point(
            alert.get("geometry")
        )

        candidates = []

        country_events = events_by_country.get(
            norm(alert.get("country")), []
        )

        for event in country_events:
            event_time = gdelt_time(
                event.get("gdelt_date_added")
            )

            if not event_time:
                continue

            latency = (
                event_time - official_time
            ).total_seconds() / 60

            if latency < -90 or latency > 240:
                counts["rejected_time"] += 1
                continue

            distance = None

            if (
                official_point
                and event.get("latitude") is not None
                and event.get("longitude") is not None
            ):
                try:
                    distance = haversine(
                        official_point[0],
                        official_point[1],
                        float(event["latitude"]),
                        float(event["longitude"])
                    )
                except (ValueError, TypeError):
                    pass

            if distance is not None and distance > 200:
                counts["rejected_distance"] += 1
                continue

            (
                semantic_score,
                strong,
                common_concepts,
                common_locations
            ) = semantic(alert, event)

            if not strong:
                counts["rejected_semantics"] += 1
                continue

            absolute_latency = abs(latency)

            time_score = (
                25 if absolute_latency <= 15
                else 20 if absolute_latency <= 30
                else 15 if absolute_latency <= 60
                else 8 if absolute_latency <= 120
                else 3
            )

            distance_score = (
                0 if distance is None
                else 25 if distance <= 10
                else 20 if distance <= 25
                else 15 if distance <= 50
                else 8 if distance <= 100
                else 2
            )

            total_score = (
                semantic_score
                + time_score
                + distance_score
            )

            candidates.append((
                total_score,
                event,
                latency,
                distance,
                time_score,
                distance_score,
                semantic_score,
                common_concepts,
                common_locations
            ))

        candidates.sort(
            key=lambda item: item[0],
            reverse=True
        )

        best = candidates[0] if candidates else None
        classification = None

        if best:
            score = best[0]
            distance = best[3]
            common_concepts = best[7]
            common_locations = best[8]

            same_concept = bool(common_concepts)
            same_location = bool(common_locations)

            close_25 = (
                distance is not None
                and distance <= 25
            )

            within_100 = (
                distance is None
                or distance <= 100
            )

            if (
                score >= 75
                and within_100
                and same_concept
                and (same_location or close_25)
            ):
                classification = "probable_match"
                counts["probable"] += 1

            elif (
                score >= 60
                and same_concept
                and within_100
                and (same_location or close_25)
            ):
                classification = "possible_match"
                counts["possible"] += 1

        print("-" * 72)
        print("OFFICIAL:", alert.get("headline"))
        print("COUNTRY:", alert.get("country"))

        if classification:
            (
                score, event, latency, distance,
                time_score, distance_score,
                semantic_score, common_concepts,
                common_locations
            ) = best

            pair = (alert["id"], event["id"])

            first_detected = parse_time(
                event.get("first_detected_at")
            )

            radar_latency = (
                (
                    first_detected - official_time
                ).total_seconds() / 60
                if first_detected else None
            )

            overhead = (
                (
                    first_detected
                    - gdelt_time(event.get("gdelt_date_added"))
                ).total_seconds() / 60
                if first_detected else None
            )

            if pair in existing_pairs:
                counts["already_recorded"] += 1

            else:
                payload = {
                    "official_alert_id": alert["id"],
                    "gdelt_event_id": event["id"],
                    "official_country": alert.get("country"),
                    "official_time": alert.get("issued_at"),
                    "gdelt_time": event.get("first_detected_at"),
                    "latency_minutes": round(latency, 2),
                    "distance_km": (
                        round(distance, 2)
                        if distance is not None else None
                    ),
                    "time_score": time_score,
                    "distance_score": distance_score,
                    "text_score": semantic_score,
                    "match_score": score,
                    "classification": classification,
                    "notes": (
                        "Matcher v0.5.1; "
                        f"concepts={common_concepts}; "
                        f"locations={common_locations}; "
                        "manual validation required."
                    )
                }

                insert_match(payload)
                counts["accepted"] += 1
                existing_pairs.add(pair)

            print("RESULT:", classification.upper())
            print("Score:", score)
            print("GDELT LATENCY:", round(latency, 1))
            print(
                "RADAR LATENCY:",
                round(radar_latency, 1)
                if radar_latency is not None
                else "unknown"
            )
            print(
                "OUR OVERHEAD:",
                round(overhead, 1)
                if overhead is not None
                else "unknown"
            )

        else:
            print("RESULT: NO VALID MATCH")

            # Re-evaluate throughout the observation window.
            # Only record no_candidate after the maximum
            # positive GDELT latency has elapsed,
            # with an additional polling allowance.

            mature = (
                NOW - official_time
                >= timedelta(minutes=255)
            )

            if not mature:
                print("STATUS: WAITING FOR GDELT")
                continue

            if alert["id"] in existing_no_candidate:
                counts["already_recorded"] += 1
                continue

            payload = {
                "official_alert_id": alert["id"],
                "gdelt_event_id": None,
                "official_country": alert.get("country"),
                "official_time": alert.get("issued_at"),
                "classification": "no_candidate",
                "match_score": 0,
                "notes": (
                    "Matcher v0.5.1: no valid candidate "
                    "after observation window."
                )
            }

            insert_match(payload)
            counts["no_candidate"] += 1
            existing_no_candidate.add(alert["id"])

    print("=" * 72)
    print("MATCHER v0.5.1 SUMMARY")
    print("=" * 72)

    for name, value in counts.items():
        print(name.upper() + ":", value)

    print("MATCHER COMPLETED:", datetime.now(timezone.utc).isoformat())


if __name__ == "__main__":
    main()
