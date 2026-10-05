import re
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urljoin

URL = "https://www.fr-alert.gouv.fr/les-alertes"

print("=" * 76)
print("FRANCE FR-ALERT TECHNICAL PROBE")
print("Execution:", datetime.now(timezone.utc).isoformat())
print("=" * 76)

request = urllib.request.Request(
    URL,
    headers={
        "User-Agent": "Mozilla/5.0 EuropeConflictRadar-Test/0.1",
        "Accept": "text/html,application/xhtml+xml",
    },
)

with urllib.request.urlopen(request, timeout=60) as response:
    html = response.read().decode("utf-8", errors="replace")

print("HTTP OK")
print("HTML bytes:", len(html.encode("utf-8")))

# ------------------------------------------------------------
# Procurar links presentes na página
# ------------------------------------------------------------

links = re.findall(
    r'''(?:href|action)=["']([^"']+)["']''',
    html,
    flags=re.IGNORECASE,
)

interesting = []

keywords = (
    "export",
    "csv",
    "json",
    "xml",
    "alert",
    "download",
    "telecharg",
)

for link in links:

    absolute = urljoin(URL, link)

    if any(word in absolute.lower() for word in keywords):
        interesting.append(absolute)

print()
print("=" * 76)
print("INTERESTING LINKS")
print("=" * 76)

for link in sorted(set(interesting)):
    print(link)

# ------------------------------------------------------------
# Procurar contexto textual relacionado com export
# ------------------------------------------------------------

print()
print("=" * 76)
print("EXPORT CONTEXT")
print("=" * 76)

lower_html = html.lower()

for keyword in ("export", "csv", "json", "xml"):

    start = 0

    while True:

        position = lower_html.find(keyword, start)

        if position == -1:
            break

        begin = max(0, position - 300)
        end = min(len(html), position + 500)

        snippet = html[begin:end]

        # tornar o log mais legível
        snippet = re.sub(r"\s+", " ", snippet)

        print()
        print(f"--- {keyword.upper()} ---")
        print(snippet)

        start = position + len(keyword)

print()
print("=" * 76)
print("FRANCE PROBE COMPLETED")
print("=" * 76)
