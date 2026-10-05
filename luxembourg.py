import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

DATASET_API = (
    "https://data.public.lu/api/1/datasets/"
    "alertes-du-systeme-lu-alert/"
)

USER_AGENT = "EuropeConflictRadar-Luxembourg/0.1"

print("=" * 76)
print("LUXEMBOURG LU-ALERT OFFICIAL DATA TEST")
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


# ============================================================
# 1. DATASET METADATA
# ============================================================

print("\n[1/3] Downloading official dataset metadata...")

raw = download(DATASET_API)
dataset = json.loads(raw.decode("utf-8"))

print("Dataset title:", dataset.get("title"))
print("Last modified:", dataset.get("last_modified"))

resources = dataset.get("resources", [])

print("Resources:", len(resources))

# ============================================================
# 2. FIND XML RESOURCES
# ============================================================

print("\n[2/3] Finding XML CAP-LU resources...")

xml_resources = []

for resource in resources:

    url = resource.get("url", "")
    fmt = (resource.get("format") or "").lower()

    if (
        fmt == "xml"
        or url.lower().endswith(".xml")
    ):

        xml_resources.append(resource)


def resource_date(resource):

    return (
        resource.get("latest")
        or resource.get("last_modified")
        or resource.get("created_at")
        or ""
    )


xml_resources.sort(
    key=resource_date,
    reverse=True
)

print("XML resources:", len(xml_resources))

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
# 3. PARSE LATEST CAP-LU XML
# ============================================================

if not xml_resources:

    raise RuntimeError(
        "No XML resources found."
    )

latest = xml_resources[0]
latest_url = latest.get("url")

print()
print("=" * 76)
print("[3/3] PARSING LATEST CAP-LU FILE")
print("=" * 76)

print("Latest URL:", latest_url)

xml_raw = download(latest_url)

print("Downloaded bytes:", len(xml_raw))

root = ET.fromstring(xml_raw)

print("Root tag:", root.tag)

# CAP normally uses:
# urn:oasis:names:tc:emergency:cap:1.2

namespace = {
    "cap": "urn:oasis:names:tc:emergency:cap:1.2"
}


def cap_text(element, path):

    found = element.find(
        path,
        namespace
    )

    if found is not None:
        return found.text

    return None


# Alguns dumps podem conter vários <alert>.
if root.tag.endswith("alert"):
    alerts = [root]
else:
    alerts = root.findall(
        ".//cap:alert",
        namespace
    )

print("CAP alerts found:", len(alerts))

for number, alert in enumerate(
    alerts[:20],
    start=1
):

    print()
    print("-" * 76)
    print("ALERT", number)

    print(
        "Identifier:",
        cap_text(
            alert,
            "cap:identifier"
        )
    )

    print(
        "Sender:",
        cap_text(
            alert,
            "cap:sender"
        )
    )

    print(
        "Sent:",
        cap_text(
            alert,
            "cap:sent"
        )
    )

    print(
        "Status:",
        cap_text(
            alert,
            "cap:status"
        )
    )

    print(
        "Message type:",
        cap_text(
            alert,
            "cap:msgType"
        )
    )

    info = alert.find(
        "cap:info",
        namespace
    )

    if info is not None:

        print(
            "Language:",
            cap_text(
                info,
                "cap:language"
            )
        )

        print(
            "Category:",
            cap_text(
                info,
                "cap:category"
            )
        )

        print(
            "Event:",
            cap_text(
                info,
                "cap:event"
            )
        )

        print(
            "Urgency:",
            cap_text(
                info,
                "cap:urgency"
            )
        )

        print(
            "Severity:",
            cap_text(
                info,
                "cap:severity"
            )
        )

        print(
            "Certainty:",
            cap_text(
                info,
                "cap:certainty"
            )
        )

        print(
            "Headline:",
            cap_text(
                info,
                "cap:headline"
            )
        )

        area = info.find(
            "cap:area",
            namespace
        )

        if area is not None:

            print(
                "Area:",
                cap_text(
                    area,
                    "cap:areaDesc"
                )
            )

            polygons = area.findall(
                "cap:polygon",
                namespace
            )

            print(
                "Polygons:",
                len(polygons)
            )

print()
print("=" * 76)
print("LUXEMBOURG TEST COMPLETED")
print("=" * 76)
