import json
import os
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

DATASET_API = (
    "https://data.public.lu/api/1/datasets/"
    "alertes-du-systeme-lu-alert/"
)

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SECRET_KEY"]

USER_AGENT = "EuropeConflictRadar-Luxembourg/0.3"


def download(url):

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=60
    ) as response:

        return response.read()


def parse_date(value):

    if not value:
        return datetime.min.replace(
            tzinfo=timezone.utc
        )

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

    except Exception:
        return datetime.min.replace(
            tzinfo=timezone.utc
        )


def supabase_insert(payload):

    endpoint = (
        f"{SUPABASE_URL}/rest/v1/"
        "official_alerts?on_conflict=external_id"
    )

    request = urllib.request.Request(
        endpoint,
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


print("=" * 76)
print("LUXEMBOURG LU-ALERT COLLECTOR")
print("Execution:", datetime.now(timezone.utc).isoformat())
print("=" * 76)

# ============================================================
# DATASET METADATA
# ============================================================

dataset = json.loads(
    download(DATASET_API).decode("utf-8")
)

resources = dataset.get(
    "resources",
    []
)

xml_resources = []

for resource in resources:

    url = resource.get(
        "url",
        ""
    )

    fmt = (
        resource.get("format")
        or ""
    ).lower()

    if (
        fmt == "xml"
        or url.lower().endswith(".xml")
    ):
        xml_resources.append(
            resource
        )


def resource_datetime(resource):

    dates = []

    for field in (
        "last_modified",
        "created_at"
    ):

        value = resource.get(field)

        if value:
            dates.append(
                parse_date(value)
            )

    if not dates:
        return datetime.min.replace(
            tzinfo=timezone.utc
        )

    return max(dates)


xml_resources.sort(
    key=resource_datetime,
    reverse=True
)

print(
    "Total CAP-LU resources:",
    len(xml_resources)
)

# Para o primeiro carregamento:
# últimos 50 recursos.
#
# Depois os IDs UNIQUE impedem duplicados.

resources_to_process = xml_resources[:50]

accepted = 0
failed = 0
parsed = 0

for resource in reversed(
    resources_to_process
):

    url = resource.get("url")

    try:

        xml_raw = download(url)

        root = ET.fromstring(
            xml_raw
        )

    except Exception as error:

        print(
            "XML ERROR:",
            url,
            error
        )

        failed += 1
        continue

    # Namespace CAP-LU real
    if root.tag.startswith("{"):

        namespace_uri = (
            root.tag
            .split("}")[0]
            .strip("{")
        )

    else:
        namespace_uri = ""

    def tag(name):

        if namespace_uri:
            return (
                f"{{{namespace_uri}}}{name}"
            )

        return name

    def text(element, name):

        if element is None:
            return None

        found = element.find(
            tag(name)
        )

        if found is None:
            return None

        return found.text

    identifier = text(
        root,
        "identifier"
    )

    if not identifier:
        continue

    parsed += 1

    sender = text(
        root,
        "sender"
    )

    sent = text(
        root,
        "sent"
    )

    cap_status = text(
        root,
        "status"
    )

    msg_type = text(
        root,
        "msgType"
    )

    # ========================================================
    # ESCOLHER INFO
    #
    # Preferimos inglês.
    # Se não existir: francês.
    # Depois: primeiro disponível.
    # ========================================================

    infos = root.findall(
        tag("info")
    )

    selected_info = None

    for info in infos:

        language = (
            text(info, "language")
            or ""
        ).lower()

        if language.startswith("en"):
            selected_info = info
            break

    if selected_info is None:

        for info in infos:

            language = (
                text(info, "language")
                or ""
            ).lower()

            if language.startswith("fr"):
                selected_info = info
                break

    if (
        selected_info is None
        and infos
    ):
        selected_info = infos[0]

    if selected_info is None:
        continue

    language = text(
        selected_info,
        "language"
    )

    category = text(
        selected_info,
        "category"
    )

    event = text(
        selected_info,
        "event"
    )

    urgency = text(
        selected_info,
        "urgency"
    )

    severity = text(
        selected_info,
        "severity"
    )

    certainty = text(
        selected_info,
        "certainty"
    )

    effective = text(
        selected_info,
        "effective"
    )

    expires = text(
        selected_info,
        "expires"
    )

    headline = text(
        selected_info,
        "headline"
    )

    description = text(
        selected_info,
        "description"
    )

    instruction = text(
        selected_info,
        "instruction"
    )

    # ========================================================
    # ÁREAS / POLÍGONOS
    # ========================================================

    area_descriptions = []
    polygons = []
    circles = []

    areas = selected_info.findall(
        tag("area")
    )

    for area in areas:

        area_description = text(
            area,
            "areaDesc"
        )

        if area_description:
            area_descriptions.append(
                area_description
            )

        for polygon in area.findall(
            tag("polygon")
        ):

            if polygon.text:
                polygons.append(
                    polygon.text
                )

        for circle in area.findall(
            tag("circle")
        ):

            if circle.text:
                circles.append(
                    circle.text
                )

    geometry = {
        "polygons": polygons,
        "circles": circles,
    }

    payload = {

        "country": "Luxembourg",

        "authority": (
            f"LU-Alert / {sender}"
            if sender
            else "LU-Alert"
        ),

        "external_id": identifier,

        "alert_type": msg_type,
        "status": cap_status,

        "region": None,

        "area_description": (
            " | ".join(
                area_descriptions
            )
            if area_descriptions
            else None
        ),

        "issued_at": sent,

        "expires_at": expires,

        "headline": (
            headline
            or event
        ),

        "description": description,

        "source_url": url,

        "source_type": (
            "official_CAP_LU"
        ),

        "severity": severity,

        "urgency": urgency,

        "event_code": event,

        "geometry": geometry,

        "raw_data": {
            "sender": sender,
            "status": cap_status,
            "msg_type": msg_type,
            "scope": text(
                root,
                "scope"
            ),
            "language": language,
            "category": category,
            "event": event,
            "certainty": certainty,
            "effective": effective,
            "instruction": instruction,
            "resource_created": (
                resource.get(
                    "created_at"
                )
            ),
            "resource_modified": (
                resource.get(
                    "last_modified"
                )
            ),
        },
    }

    try:

        status_code = supabase_insert(
            payload
        )

        if status_code in (
            200,
            201,
            204
        ):

            accepted += 1

            print(
                "OK",
                sent,
                msg_type,
                event,
                "|",
                headline,
            )

    except urllib.error.HTTPError as error:

        failed += 1

        print(
            "SUPABASE ERROR",
            identifier,
            error.code,
            error.read().decode(
                "utf-8",
                errors="replace"
            ),
        )

print()
print("=" * 76)
print("RESOURCES CHECKED:", len(resources_to_process))
print("CAP ALERTS PARSED:", parsed)
print("SUPABASE ACCEPTED:", accepted)
print("FAILED:", failed)
print("=" * 76)
