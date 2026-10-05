import re
import ssl
import urllib.request
import certifi
from datetime import datetime, timezone
from urllib.parse import urljoin

URL = "https://www.fr-alert.gouv.fr/les-alertes"

print("=" * 76)
print("FRANCE FR-ALERT TECHNICAL PROBE v0.2")
print("Execution:", datetime.now(timezone.utc).isoformat())
print("=" * 76)

ssl_context = ssl.create_default_context(
    cafile=certifi.where()
)

print("Certificate bundle:", certifi.where())

request = urllib.request.Request(
    URL,
    headers={
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 Chrome/120 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
    },
)

with urllib.request.urlopen(
    request,
    timeout=60,
    context=ssl_context
) as response:

    print("HTTP status:", response.status)

    html = response.read().decode(
        "utf-8",
        errors="replace"
    )

print("HTML bytes:", len(html.encode("utf-8")))

links = re.findall(
    r'''(?:href|action)=["']([^"']+)["']''',
    html,
    flags=re.IGNORECASE,
)

keywords = (
    "export",
    "csv",
    "json",
    "xml",
    "alert",
    "download",
    "telecharg",
)

interesting = []

for link in links:

    absolute = urljoin(URL, link)

    if any(
        word in absolute.lower()
        for word in keywords
    ):
        interesting.append(absolute)

print()
print("=" * 76)
print("INTERESTING LINKS")
print("=" * 76)

for link in sorted(set(interesting)):
    print(link)

print()
print("=" * 76)
print("EXPORT CONTEXT")
print("=" * 76)

lower_html = html.lower()

for keyword in ("export", "csv", "json", "xml"):

    start = 0
    count = 0

    while True:

        position = lower_html.find(
            keyword,
            start
        )

        if position == -1:
            break

        count += 1

        # evitar logs gigantes
        if count > 10:
            break

        begin = max(0, position - 300)
        end = min(
            len(html),
            position + 500
        )

        snippet = html[begin:end]
        snippet = re.sub(
            r"\s+",
            " ",
            snippet
        )

        print()
        print(f"--- {keyword.upper()} ---")
        print(snippet)

        start = position + len(keyword)

print()
print("=" * 76)
print("FRANCE PROBE v0.2 COMPLETED")
print("=" * 76)
