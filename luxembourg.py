import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

DATASET_API = (
    "https://data.public.lu/api/1/datasets/"
    "alertes-du-systeme-lu-alert/"
)

USER_AGENT = "EuropeConflictRadar-Luxembourg/0.2"

print("=" * 76)
print("LUXEMBOURG LU-ALERT OFFICIAL DATA TEST v0.2")
print("Execution:", datetime.now(timezone.utc).isoformat())
print("=" * 76)


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


# ============================================================
# 1. DATASET
# ============================================================

print("\n[1/3] Downloading dataset metadata...")

raw = download(DATASET_API)

dataset = json.loads(
    raw.decode("utf-8")
)

print(
    "Dataset:",
    dataset.get("title")
)

print(
    "Dataset last modified:",
    dataset.get("last_modified")
)

resources = dataset.get(
    "resources",
    []
)

print(
    "Total resources:",
    len(resources)
)

# ============================================================
# 2. XML RESOURCES
# ============================================================

print("\n[2/3] Finding CAP-LU XML resources...")

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

    values = [
        resource.get("last_modified"),
        resource.get("created_at"),
    ]

    dates = [
        parse_date(value)
        for value in values
        if value
    ]

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
    "XML resources:",
    len(xml_resources)
)

print()
print("10 MOST RECENT XML RESOURCES")
print("-" * 76)

for resource in xml_resources[:10]:

    print()
    print(
        resource.get("title")
        or resource.get("url")
    )

    print(
        "Created:",
        resource.get("created_at")
    )

    print(
        "Modified:",
        resource.get("last_modified")
    )

    print(
        "URL:",
        resource.get("url")
    )

# ============================================================
# 3. PARSE LATEST XML
# ============================================================

if not xml_resources:

    raise RuntimeError(
        "No XML resources found."
    )

latest = xml_resources[0]

latest_url = latest.get("url")

print()
print("=" * 76)
print("[3/3] PARSING LATEST CAP-LU")
print("=" * 76)

print(
    "Resource created:",
    latest.get("created_at")
)

print(
    "Resource modified:",
    latest.get("last_modified")
)

print(
    "URL:",
    latest_url
)

xml_raw = download(
    latest_url
)

print(
    "Downloaded bytes:",
    len(xml_raw)
)

root = ET.fromstring(
    xml_raw
)

print(
    "Root tag:",
    root.tag
)

# ------------------------------------------------------------
# Descobrir namespace REAL diretamente do XML
# ------------------------------------------------------------

if root.tag.startswith("{"):

    namespace_uri = (
        root.tag
        .split("}")[0]
        .strip("{")
    )

else:
    namespace_uri = ""

print(
    "Detected namespace:",
    namespace_uri
)


def tag(name):

    if namespace_uri:
        return f"{{{namespace_uri}}}{name}"

    return name


def child_text(
    element,
    name
):

    if element is None:
        return None

    found = element.find(
        tag(name)
    )

    if found is None:
        return None

    return found.text


# ------------------------------------------------------------
# CAP ALERT
# ------------------------------------------------------------

alerts = []

if root.tag.endswith("alert"):

    alerts = [root]

else:

    alerts = root.findall(
        f".//{tag('alert')}"
    )

print(
    "CAP alerts found:",
    len(alerts)
)

for number, alert in enumerate(
    alerts[:20],
    start=1
):

    print()
    print("-" * 76)
    print(
        "ALERT",
        number
    )

    print(
        "Identifier:",
        child_text(
            alert,
            "identifier"
        )
    )

    print(
        "Sender:",
        child_text(
            alert,
            "sender"
        )
    )

    print(
        "Sent:",
        child_text(
            alert,
            "sent"
        )
    )

    print(
        "Status:",
        child_text(
            alert,
            "status"
        )
    )

    print(
        "Message type:",
        child_text(
            alert,
            "msgType"
        )
    )

    print(
        "Scope:",
        child_text(
            alert,
            "scope"
        )
    )

    infos = alert.findall(
        tag("info")
    )

    print(
        "Info blocks:",
        len(infos)
    )

    for info_number, info in enumerate(
        infos,
        start=1
    ):

        print()
        print(
            f"  INFO {info_number}"
        )

        print(
            "  Language:",
            child_text(
                info,
                "language"
            )
        )

        print(
            "  Category:",
            child_text(
                info,
                "category"
            )
        )

        print(
            "  Event:",
            child_text(
                info,
                "event"
            )
        )

        print(
            "  Urgency:",
            child_text(
                info,
                "urgency"
            )
        )

        print(
            "  Severity:",
            child_text(
                info,
                "severity"
            )
        )

        print(
            "  Certainty:",
            child_text(
                info,
                "certainty"
            )
        )

        print(
            "  Effective:",
            child_text(
                info,
                "effective"
            )
        )

        print(
            "  Expires:",
            child_text(
                info,
                "expires"
            )
        )

        print(
            "  Headline:",
            child_text(
                info,
                "headline"
            )
        )

        print(
            "  Description:",
            child_text(
                info,
                "description"
            )
        )

        print(
            "  Instruction:",
            child_text(
                info,
                "instruction"
            )
        )

        areas = info.findall(
            tag("area")
        )

        print(
            "  Areas:",
            len(areas)
        )

        for area_number, area in enumerate(
            areas,
            start=1
        ):

            print(
                f"    AREA {area_number}:",
                child_text(
                    area,
                    "areaDesc"
                )
            )

            polygons = area.findall(
                tag("polygon")
            )

            circles = area.findall(
                tag("circle")
            )

            print(
                "    Polygons:",
                len(polygons)
            )

            print(
                "    Circles:",
                len(circles)
            )

            for polygon in polygons[:2]:

                value = polygon.text or ""

                print(
                    "    Polygon sample:",
                    value[:300]
                )

print()
print("=" * 76)
print("LUXEMBOURG TEST v0.2 COMPLETED")
print("=" * 76)
