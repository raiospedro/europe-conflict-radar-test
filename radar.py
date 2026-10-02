import json
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone

GDELT_API = "https://api.gdeltproject.org/api/v2/doc/doc"

# Começamos deliberadamente com uma consulta pequena.
QUERY = '(missile OR "air raid" OR shelling)'

params = {
    "query": QUERY,
    "mode": "ArtList",
    "maxrecords": "10",
    "format": "json",
    "sort": "DateDesc",
    "timespan": "1h",
}

url = GDELT_API + "?" + urllib.parse.urlencode(params)

print("=" * 70)
print("EUROPE CONFLICT RADAR - GDELT TEST v0.2")
print("Execution time:", datetime.now(timezone.utc).isoformat())
print("=" * 70)

max_attempts = 3

for attempt in range(1, max_attempts + 1):

    print(f"\nGDELT request - attempt {attempt}/{max_attempts}")

    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "EuropeConflictRadar-Test/0.2"
            }
        )

        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
            data = json.loads(raw)

        print("GDELT request successful.")
        break

    except urllib.error.HTTPError as error:

        if error.code == 429:
            print("GDELT rate limit (HTTP 429).")

            if attempt < max_attempts:
                wait_seconds = attempt * 30
                print(f"Waiting {wait_seconds} seconds before retry...")
                time.sleep(wait_seconds)
                continue

        raise

else:
    raise RuntimeError("GDELT did not respond successfully.")

articles = data.get("articles", [])

print(f"\nGDELT returned {len(articles)} articles.\n")

for number, article in enumerate(articles, start=1):

    print("-" * 70)
    print(f"ARTICLE {number}")
    print("Title:", article.get("title", ""))
    print("Source:", article.get("domain", ""))
    print("Source country:", article.get("sourcecountry", ""))
    print("Language:", article.get("language", ""))
    print("GDELT seen:", article.get("seendate", ""))
    print("URL:", article.get("url", ""))

print("\n" + "=" * 70)
print("TEST COMPLETED SUCCESSFULLY")
print("=" * 70)
