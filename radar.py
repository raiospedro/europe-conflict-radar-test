import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# ============================================================
# EUROPE CONFLICT RADAR - TEST v0.1
# Primeiro teste: consultar GDELT
# ============================================================

GDELT_API = "https://api.gdeltproject.org/api/v2/doc/doc"

# Pesquisa inicial deliberadamente ampla.
# Depois vamos medir o ruído e melhorar os filtros.
QUERY = (
    '(missile OR drone OR explosion OR "air raid" OR '
    '"air strike" OR shelling OR bombardment)'
)

params = {
    "query": QUERY,
    "mode": "ArtList",
    "maxrecords": "50",
    "format": "json",
    "sort": "DateDesc",
    "timespan": "1h",
}

url = GDELT_API + "?" + urllib.parse.urlencode(params)

print("=" * 70)
print("EUROPE CONFLICT RADAR - GDELT TEST")
print("Execution time:", datetime.now(timezone.utc).isoformat())
print("=" * 70)
print()
print("Querying GDELT...")
print()

try:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "EuropeConflictRadar/0.1"}
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

except Exception as error:
    print("ERROR contacting GDELT:")
    print(error)
    raise

articles = data.get("articles", [])

print(f"GDELT returned {len(articles)} articles.")
print()

if not articles:
    print("No articles found in the selected period.")

for number, article in enumerate(articles, start=1):

    title = article.get("title", "")
    domain = article.get("domain", "")
    country = article.get("sourcecountry", "")
    language = article.get("language", "")
    seen = article.get("seendate", "")
    article_url = article.get("url", "")

    print("-" * 70)
    print(f"ARTICLE {number}")
    print(f"Title: {title}")
    print(f"Source: {domain}")
    print(f"Source country: {country}")
    print(f"Language: {language}")
    print(f"GDELT seen date: {seen}")
    print(f"URL: {article_url}")

print()
print("=" * 70)
print("END OF TEST")
print("=" * 70)
