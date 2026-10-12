
import re
import urllib.request
import urllib.error
from html import unescape
from urllib.parse import urljoin
from datetime import datetime, timezone

URL = "https://www.gov.pl/web/rcb/komunikaty"

print("=" * 70)
print("EUROPE CONFLICT RADAR - POLAND RCB PROBE v0.1")
print("Execution:", datetime.now(timezone.utc).isoformat())
print("=" * 70)

request = urllib.request.Request(
    URL,
    headers={
        "User-Agent": "Mozilla/5.0 EuropeConflictRadar/0.1",
        "Accept": "text/html,application/xhtml+xml"
    }
)

try:
    with urllib.request.urlopen(
        request, timeout=45
    ) as response:
        html = response.read().decode(
            "utf-8", errors="replace"
        )
        print("HTTP STATUS:", response.status)

    print("HTML BYTES:", len(html.encode("utf-8")))

    links = re.findall(
        r'''href=["']([^"']+)["']''',
        html,
        flags=re.IGNORECASE
    )

    candidates = []

    for link in links:
        absolute = urljoin(URL, unescape(link))

        if "/web/rcb/" not in absolute:
            continue

        if any(term in absolute.lower() for term in (
            "alert", "atak", "zagrozenie",
            "komunikat", "ostrzeg"
        )):
            candidates.append(absolute)

    unique = sorted(set(candidates))

    print("\nCANDIDATE LINKS:", len(unique))

    for link in unique[:40]:
        print(link)

    print("\nCONTENT KEYWORDS")

    for word in (
        "atak powietrzny",
        "zagrożenie",
        "alert rcb",
        "ukrain",
        "dron"
    ):
        print(
            word,
            html.lower().count(word.lower())
        )

    print("\nPOLAND RCB PROBE COMPLETED")

except Exception as error:
    print(
        "PROBE ERROR:",
        type(error).__name__,
        str(error)
    )
    raise
