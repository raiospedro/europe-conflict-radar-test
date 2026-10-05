import json
import math
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SECRET_KEY"]

USER_AGENT = "EuropeConflictRadar-Matcher/0.1"

# ============================================================
# EXPERIMENTAL RELEVANCE WORDS
# ============================================================

RELEVANT_WORDS = {
    "explosion",
    "explosive",
    "bomb",
    "bombing",
    "missile",
    "rocket",
    "drone",
    "air raid",
    "airstrike",
    "air strike",
    "attack",
    "armed",
    "shooting",
    "terror",
    "terrorism",
    "terrorist",
    "evacuation",
    "chemical",
    "radiological",
    "nuclear",
    "ammunition",
    "munition",
    "military",
    "artillery",
    "shelling",
    "war",
    "large-scale fire",
    "large scale fire",
}

# Algumas equivalências alemãs/francesas úteis.
RELEVANT_WORDS.update({
    "bombe",
    "bomben",
    "bombenentschärfung",
    "explosion",
    "anschlag",
    "terror",
    "terrorismus",
    "evakuierung",
    "großbrand",
    "grossbrand",
    "incendie",
    "attentat",
    "attaque",
    "évacuation",
    "evacuation",
})


# ============================================================
# SUPABASE
# ============================================================

def supabase_get(table, params=""):

    url = f"{SUPABASE_URL}/rest/v1/{table}"

    if params:
        url += "?" + params

    request = urllib.request.Request(
        url,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "User-Agent": USER_AGENT,
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:

        return json.loads(
            response.read().decode("utf-8")
        )


def supabase_insert(table, payload):

    url = f"{SUPABASE_URL}/rest/v1/{table}"

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": (
                "resolution=ignore-duplicates,"
                "return=minimal"
            ),
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:

        return response.status


# ============================================================
# TIME
# ============================================================

def parse_time(value):

    if not value:
        return None

    try:

        dt = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        return dt.astimezone(
            timezone.utc
        )

    except Exception:
        return None


def parse_gdelt_time(value):

    if not value:
        return None

    try:

        dt = datetime.strptime(
            value,
            "%Y%m%d%H%M%S"
        )

        return dt.replace(
            tzinfo=timezone.utc
        )

    except Exception:
        return None


# ============================================================
# GEO
# ============================================================

def haversine(
    lat1,
    lon1,
    lat2,
    lon2
):

    radius = 6371.0

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)

    dlat = math.radians(
        lat2 - lat1
    )

    dlon = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(dlat / 2) ** 2
        +
        math.cos(p1)
        * math.cos(p2)
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return radius * c


def collect_coordinates(value, result):

    if isinstance(value, dict):

        # GeoJSON coordinates
        if "coordinates" in value:

            collect_coordinates(
                value["coordinates"],
                result
            )

        # LU-Alert custom storage
        if "polygons" in value:

            polygons = value.get(
                "polygons",
                []
            )

            for polygon in polygons:

                if not isinstance(
                    polygon,
                    str
                ):
                    continue

                for pair in polygon.split():

                    try:

                        lat, lon = pair.split(
                            ","
                        )

                        result.append(
                            (
                                float(lat),
                                float(lon)
                            )
                        )

                    except Exception:
                        pass

        for key, item in value.items():

            if key not in (
                "coordinates",
                "polygons"
            ):
                collect_coordinates(
                    item,
                    result
                )

    elif isinstance(value, list):

        # GeoJSON coordinate pair:
        # [longitude, latitude]
        if (
            len(value) >= 2
            and isinstance(
                value[0],
                (int, float)
            )
            and isinstance(
                value[1],
                (int, float)
            )
        ):

            lon = float(value[0])
            lat = float(value[1])

            if (
                -90 <= lat <= 90
                and -180 <= lon <= 180
            ):
                result.append(
                    (lat, lon)
                )

        else:

            for item in value:

                collect_coordinates(
                    item,
                    result
                )


def representative_point(geometry):

    if not geometry:
        return None

    coordinates = []

    collect_coordinates(
        geometry,
        coordinates
    )

    if not coordinates:
        return None

    latitude = sum(
        item[0]
        for item in coordinates
    ) / len(coordinates)

    longitude = sum(
        item[1]
        for item in coordinates
    ) / len(coordinates)

    return (
        latitude,
        longitude
    )


# ============================================================
# TEXT
# ============================================================

def normalize_text(value):

    if not value:
        return ""

    value = value.lower()

    value = re.sub(
        r"<[^>]+>",
        " ",
        value
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def official_text(alert):

    values = [
        alert.get("headline"),
        alert.get("description"),
        alert.get("event_code"),
        alert.get("area_description"),
    ]

    return normalize_text(
        " ".join(
            str(value or "")
            for value in values
        )
    )


def is_relevant(alert):

    text = official_text(alert)

    return any(
        word in text
        for word in RELEVANT_WORDS
    )


def text_score(
    official_alert,
    gdelt_event
):

    official = official_text(
        official_alert
    )

    gdelt = normalize_text(
        " ".join([
            gdelt_event.get("city") or "",
            gdelt_event.get("region") or "",
            gdelt_event.get("country") or "",
            gdelt_event.get("source_domain") or "",
        ])
    )

    score = 0

    # Country agreement
    official_country = normalize_text(
        official_alert.get("country")
    )

    gdelt_country = normalize_text(
        gdelt_event.get("country")
    )

    if (
        official_country
        and official_country == gdelt_country
    ):
        score += 20

    # Region/location terms
    tokens = set(
        re.findall(
            r"\b[a-zA-ZÀ-ÿ]{4,}\b",
            official
        )
    )

    matches = sum(
        1
        for token in tokens
        if token in gdelt
    )

    score += min(
        matches * 5,
        20
    )

    return score


# ============================================================
# MATCH
# ============================================================

print("=" * 78)
print("EUROPE CONFLICT RADAR MATCHER v0.1")
print(
    "Execution:",
    datetime.now(
        timezone.utc
    ).isoformat()
)
print("=" * 78)

# Official alerts currently stored.
official_alerts = supabase_get(
    "official_alerts",
    "select=*"
)

# GDELT candidates.
gdelt_events = supabase_get(
    "events",
    (
        "select=*"
        "&event_type=eq.gdelt_candidate"
    )
)

print(
    "Official alerts:",
    len(official_alerts)
)

print(
    "GDELT candidates:",
    len(gdelt_events)
)

relevant_official = [
    alert
    for alert in official_alerts
    if is_relevant(alert)
]

print(
    "Relevant official alerts:",
    len(relevant_official)
)

matches_created = 0
unmatched_created = 0

for official in relevant_official:

    official_time = parse_time(
        official.get("issued_at")
    )

    if official_time is None:
        continue

    official_point = representative_point(
        official.get("geometry")
    )

    candidates = []

    for gdelt in gdelt_events:

        # Same country first.
        if (
            normalize_text(
                official.get("country")
            )
            !=
            normalize_text(
                gdelt.get("country")
            )
        ):
            continue

        gdelt_time = parse_gdelt_time(
            gdelt.get(
                "gdelt_date_added"
            )
        )

        if gdelt_time is None:
            continue

        latency = (
            gdelt_time
            - official_time
        ).total_seconds() / 60

        # Compare from 2h before official alert
        # to 6h afterwards.
        if (
            latency < -120
            or latency > 360
        ):
            continue

        # ----------------------------------------
        # TIME SCORE
        # ----------------------------------------

        abs_latency = abs(
            latency
        )

        if abs_latency <= 15:
            time_points = 35

        elif abs_latency <= 30:
            time_points = 30

        elif abs_latency <= 60:
            time_points = 20

        elif abs_latency <= 120:
            time_points = 10

        else:
            time_points = 5

        # ----------------------------------------
        # DISTANCE
        # ----------------------------------------

        distance = None
        distance_points = 0

        if (
            official_point
            and gdelt.get("latitude") is not None
            and gdelt.get("longitude") is not None
        ):

            try:

                distance = haversine(
                    official_point[0],
                    official_point[1],
                    float(
                        gdelt["latitude"]
                    ),
                    float(
                        gdelt["longitude"]
                    ),
                )

                if distance <= 10:
                    distance_points = 35

                elif distance <= 25:
                    distance_points = 30

                elif distance <= 50:
                    distance_points = 20

                elif distance <= 100:
                    distance_points = 10

            except Exception:
                distance = None

        # ----------------------------------------
        # TEXT
        # ----------------------------------------

        text_points = text_score(
            official,
            gdelt
        )

        total_score = (
            time_points
            + distance_points
            + text_points
        )

        candidates.append({
            "event": gdelt,
            "latency": latency,
            "distance": distance,
            "time_score": time_points,
            "distance_score": distance_points,
            "text_score": text_points,
            "score": total_score,
        })

    candidates.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    # Keep best candidate only in v0.1.
    if candidates:

        best = candidates[0]

        if best["score"] >= 50:

            classification = (
                "probable_match"
            )

        elif best["score"] >= 30:

            classification = (
                "possible_match"
            )

        else:

            classification = (
                "weak_match"
            )

        payload = {
            "official_alert_id": official["id"],
            "gdelt_event_id": best["event"]["id"],

            "official_country": official.get(
                "country"
            ),

            "official_time": official.get(
                "issued_at"
            ),

            "gdelt_time": (
                best["event"].get(
                    "first_detected_at"
                )
            ),

            "latency_minutes": round(
                best["latency"],
                2
            ),

            "distance_km": (
                round(
                    best["distance"],
                    2
                )
                if best["distance"] is not None
                else None
            ),

            "time_score": best[
                "time_score"
            ],

            "distance_score": best[
                "distance_score"
            ],

            "text_score": best[
                "text_score"
            ],

            "match_score": best[
                "score"
            ],

            "classification": classification,

            "notes": (
                "Experimental automatic match. "
                "Not manually verified."
            ),
        }

        try:

            supabase_insert(
                "event_matches",
                payload
            )

            matches_created += 1

            print()
            print(
                classification.upper(),
                "|",
                official.get(
                    "headline"
                )
            )

            print(
                "Latency:",
                round(
                    best["latency"],
                    1
                ),
                "minutes"
            )

            print(
                "Distance:",
                (
                    round(
                        best["distance"],
                        1
                    )
                    if best["distance"]
                    is not None
                    else "unknown"
                ),
                "km"
            )

            print(
                "Score:",
                best["score"]
            )

        except Exception as error:

            print(
                "MATCH INSERT ERROR:",
                error
            )

    else:

        payload = {
            "official_alert_id": official["id"],

            "gdelt_event_id": None,

            "official_country": official.get(
                "country"
            ),

            "official_time": official.get(
                "issued_at"
            ),

            "classification": (
                "no_candidate"
            ),

            "notes": (
                "No GDELT candidate found "
                "within -120/+360 minutes."
            ),
        }

        try:

            supabase_insert(
                "event_matches",
                payload
            )

            unmatched_created += 1

        except Exception as error:

            print(
                "UNMATCHED INSERT ERROR:",
                error
            )

print()
print("=" * 78)
print(
    "MATCHES CREATED:",
    matches_created
)
print(
    "NO-CANDIDATE RECORDS:",
    unmatched_created
)
print("=" * 78)
