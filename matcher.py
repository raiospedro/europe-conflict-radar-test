import json
import math
import os
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SECRET_KEY"]

USER_AGENT = "EuropeConflictRadar-Matcher/0.3"

# ============================================================
# MATCHER v0.3
#
# Philosophy:
#
# - Conservative matching.
# - Geographic proximity alone is NOT enough.
# - Time proximity alone is NOT enough.
# - Semantic evidence is mandatory.
# - Test/exercise alerts are excluded.
# - Candidates > 200 km are rejected.
# - Candidates > 100 km can never be probable.
#
# This script does NOT confirm real-world events.
# It only measures possible correspondence between
# official alerts and GDELT candidates.
# ============================================================


# ============================================================
# RELEVANT OFFICIAL ALERT VOCABULARY
# ============================================================

RELEVANT_TERMS = {

    # English
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
    "large scale fire",
    "major fire",
    "world war bomb",

    # German
    "bombe",
    "bomben",
    "bombenentscharfung",
    "anschlag",
    "terrorismus",
    "evakuierung",
    "grossbrand",
    "munition",
    "sprengstoff",

    # French
    "bombe",
    "explosion",
    "attentat",
    "attaque",
    "evacuation",
    "incendie majeur",
    "incendie important",
}


# ============================================================
# ALERTS THAT MUST NOT BE MATCHED
# ============================================================

TEST_TERMS = {
    "test",
    "testing",
    "exercise",
    "drill",
    "probealarm",
    "ubung",
    "uebung",
    "essai",
    "exercice",
}


# ============================================================
# EVENT CONCEPT GROUPS
#
# At least one common concept is strong semantic evidence.
# ============================================================

CONCEPTS = {

    "bomb": {
        "bomb",
        "bombing",
        "bombe",
        "bomben",
        "bombenentscharfung",
        "munition",
        "ammunition",
        "explosive",
        "explosives",
        "sprengstoff",
        "world war bomb",
    },

    "explosion": {
        "explosion",
        "blast",
        "detonation",
        "explosive",
    },

    "missile": {
        "missile",
        "rocket",
        "airstrike",
        "air strike",
        "shelling",
        "artillery",
    },

    "drone": {
        "drone",
        "uav",
        "unmanned aerial",
    },

    "attack": {
        "attack",
        "attacked",
        "attentat",
        "attaque",
        "anschlag",
        "armed",
        "shooting",
    },

    "terror": {
        "terror",
        "terrorism",
        "terrorist",
        "anschlag",
        "attentat",
    },

    "evacuation": {
        "evacuation",
        "evacuate",
        "evacuated",
        "evakuierung",
    },

    "fire": {
        "large scale fire",
        "major fire",
        "grossbrand",
        "incendie majeur",
        "incendie important",
    },

    "chemical": {
        "chemical",
        "hazardous substance",
        "toxic",
        "radiological",
        "nuclear",
    },

    "military": {
        "military",
        "armed forces",
        "troops",
        "artillery",
        "war",
    },
}


# ============================================================
# GENERIC WORDS THAT SHOULD NOT CREATE A MATCH
# ============================================================

STOPWORDS = {
    "alert",
    "warning",
    "official",
    "update",
    "cancel",
    "cancelled",
    "public",
    "immediate",
    "unknown",
    "actual",
    "germany",
    "luxembourg",
    "united",
    "kingdom",
    "city",
    "district",
    "area",
    "region",
    "state",
    "from",
    "with",
    "this",
    "that",
    "into",
    "near",
    "over",
    "under",
    "after",
    "before",
    "during",
    "large",
    "scale",
}


# ============================================================
# TEXT HELPERS
# ============================================================

def normalize_text(value):

    if not value:
        return ""

    value = str(value)

    # Remove HTML
    value = re.sub(
        r"<[^>]+>",
        " ",
        value
    )

    # Remove accents for comparison
    value = unicodedata.normalize(
        "NFKD",
        value
    )

    value = "".join(
        char
        for char in value
        if not unicodedata.combining(char)
    )

    value = value.lower()

    value = re.sub(
        r"[^a-z0-9\s\-]",
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


def gdelt_text(event):

    values = [
        event.get("headline"),
        event.get("description"),
        event.get("city"),
        event.get("region"),
        event.get("country"),
        event.get("source_domain"),
        event.get("source_url"),
    ]

    return normalize_text(
        " ".join(
            str(value or "")
            for value in values
        )
    )


def contains_test_language(alert):

    text = official_text(alert)

    tokens = set(
        re.findall(
            r"\b[a-z0-9\-]+\b",
            text
        )
    )

    return any(
        term in tokens
        for term in TEST_TERMS
    )


def is_relevant(alert):

    text = official_text(alert)

    return any(
        term in text
        for term in RELEVANT_TERMS
    )


def detected_concepts(text):

    found = set()

    for concept, terms in CONCEPTS.items():

        if any(
            term in text
            for term in terms
        ):
            found.add(concept)

    return found


def meaningful_tokens(text):

    tokens = re.findall(
        r"\b[a-z][a-z0-9\-]{3,}\b",
        text
    )

    return {
        token
        for token in tokens
        if token not in STOPWORDS
    }


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

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }

    if (
        table == "event_matches"
        and payload.get("gdelt_event_id") is not None
    ):

        url += (
            "?on_conflict="
            "official_alert_id,gdelt_event_id"
        )

        headers["Prefer"] = (
            "resolution=ignore-duplicates,"
            "return=minimal"
        )

    else:

        headers["Prefer"] = "return=minimal"

    request = urllib.request.Request(
        url,
        data=json.dumps(
            payload
        ).encode("utf-8"),
        method="POST",
        headers=headers,
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
            value.replace(
                "Z",
                "+00:00"
            )
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


def collect_coordinates(
    value,
    result
):

    if isinstance(value, dict):

        if "coordinates" in value:

            collect_coordinates(
                value["coordinates"],
                result
            )

        # LU-Alert CAP polygons:
        # "latitude,longitude latitude,longitude..."
        if "polygons" in value:

            for polygon in value.get(
                "polygons",
                []
            ):

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

        # Standard GeoJSON:
        # longitude, latitude
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
                and
                -180 <= lon <= 180
            ):

                result.append(
                    (
                        lat,
                        lon
                    )
                )

        else:

            for item in value:

                collect_coordinates(
                    item,
                    result
                )


def representative_point(
    geometry
):

    if not geometry:
        return None

    coordinates = []

    collect_coordinates(
        geometry,
        coordinates
    )

    if not coordinates:
        return None

    latitude = (
        sum(
            point[0]
            for point in coordinates
        )
        /
        len(coordinates)
    )

    longitude = (
        sum(
            point[1]
            for point in coordinates
        )
        /
        len(coordinates)
    )

    return (
        latitude,
        longitude
    )


# ============================================================
# SEMANTIC COMPARISON
# ============================================================

def semantic_analysis(
    official,
    gdelt
):

    official_content = official_text(
        official
    )

    gdelt_content = gdelt_text(
        gdelt
    )

    official_concepts = detected_concepts(
        official_content
    )

    gdelt_concepts = detected_concepts(
        gdelt_content
    )

    common_concepts = (
        official_concepts
        &
        gdelt_concepts
    )

    official_tokens = meaningful_tokens(
        official_content
    )

    gdelt_tokens = meaningful_tokens(
        gdelt_content
    )

    common_tokens = (
        official_tokens
        &
        gdelt_tokens
    )

    # Location terms are especially useful.
    location_text = normalize_text(
        " ".join([
            official.get(
                "area_description"
            ) or "",
            official.get(
                "headline"
            ) or "",
        ])
    )

    location_tokens = meaningful_tokens(
        location_text
    )

    common_location_tokens = (
        location_tokens
        &
        gdelt_tokens
    )

    semantic_score = 0

    if common_concepts:
        semantic_score += 35

    if common_location_tokens:
        semantic_score += min(
            len(
                common_location_tokens
            ) * 15,
            30
        )

    # Other meaningful overlap.
    other_common = (
        common_tokens
        -
        common_location_tokens
    )

    semantic_score += min(
        len(other_common) * 5,
        15
    )

    strong_semantic = (
        bool(common_concepts)
        or
        bool(common_location_tokens)
    )

    return {
        "score": semantic_score,
        "strong": strong_semantic,
        "common_concepts": sorted(
            common_concepts
        ),
        "common_location_tokens": sorted(
            common_location_tokens
        ),
        "common_tokens": sorted(
            common_tokens
        ),
    }


# ============================================================
# START
# ============================================================

print("=" * 78)
print("EUROPE CONFLICT RADAR MATCHER v0.3")
print(
    "Execution:",
    datetime.now(
        timezone.utc
    ).isoformat()
)
print("=" * 78)


# ============================================================
# LOAD DATA
# ============================================================

official_alerts = supabase_get(
    "official_alerts",
    "select=*"
)

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


# ============================================================
# OFFICIAL FILTERING
# ============================================================

relevant_official = []

test_alerts_excluded = 0

for alert in official_alerts:

    if contains_test_language(
        alert
    ):

        test_alerts_excluded += 1
        continue

    if is_relevant(
        alert
    ):

        relevant_official.append(
            alert
        )

print(
    "Relevant official alerts:",
    len(relevant_official)
)

print(
    "Test/exercise alerts excluded:",
    test_alerts_excluded
)


# ============================================================
# COUNTERS
# ============================================================

matches_accepted = 0
no_candidates_created = 0
already_recorded = 0

rejected_distance = 0
rejected_semantic = 0
rejected_time = 0

probable_matches = 0
possible_matches = 0


# ============================================================
# MATCHING
# ============================================================

for official in relevant_official:

    official_time = parse_time(
        official.get(
            "issued_at"
        )
    )

    if official_time is None:
        continue

    official_point = representative_point(
        official.get(
            "geometry"
        )
    )

    evaluated = []

    rejection_samples = []

    for gdelt in gdelt_events:

        # ====================================================
        # COUNTRY GATE
        # ====================================================

        official_country = normalize_text(
            official.get(
                "country"
            )
        )

        gdelt_country = normalize_text(
            gdelt.get(
                "country"
            )
        )

        if (
            not official_country
            or
            official_country != gdelt_country
        ):
            continue

        # ====================================================
        # TIME GATE
        # ====================================================

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

        # v0.3:
        # max 90 min before official alert,
        # max 240 min after.

        if (
            latency < -90
            or
            latency > 240
        ):

            rejected_time += 1
            continue

        # ====================================================
        # DISTANCE
        # ====================================================

        distance = None

        if (
            official_point
            and
            gdelt.get(
                "latitude"
            ) is not None
            and
            gdelt.get(
                "longitude"
            ) is not None
        ):

            try:

                distance = haversine(
                    official_point[0],
                    official_point[1],
                    float(
                        gdelt[
                            "latitude"
                        ]
                    ),
                    float(
                        gdelt[
                            "longitude"
                        ]
                    ),
                )

            except Exception:
                distance
