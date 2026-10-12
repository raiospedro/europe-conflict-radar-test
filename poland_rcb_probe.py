
import json
import re
import urllib.request
import urllib.error
from html.parser import HTMLParser
from datetime import datetime, timezone

# EUROPE CONFLICT RADAR
# POLAND RCB METADATA PROBE v0.3
# Read-only. No Supabase writes.

BASE = "https://www.gov.pl/web/rcb/"

PAGES = {
    "AIR_THREAT": "alert-rcb---zagrozenie-z-powietrza-0810",
    "RUSSIAN_AIR_ATTACK": (
        "alert-rcb---rosyjski-atak-powietrzny-"
        "na-terenie-ukrainy-1010"
    ),
    "STRONG_WIND": "alert-rcb---silny-wiatr-0810",
}


class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = []
        self.times = []
        self.current_time = None
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "meta":
            self.meta.append(attrs)

        if tag == "time":
            self.current_time = attrs
            self.current_text = []

    def handle_data(self, data):
        if self.current_time is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag):
        if tag == "time" and self.current_time is not None:
            self.times.append({
                "attributes": self.current_time,
                "text": " ".join(self.current_text).strip()
            })
            self.current_time = None


def fetch(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 EuropeConflictRadar/0.3",
            "Accept": "text/html,application/xhtml+xml"
        }
    )

    with urllib.request.urlopen(
        request, timeout=45
    ) as response:
        raw = response.read()
        return (
            response.status,
            response.headers,
            raw.decode("utf-8", errors="replace")
        )


def extract_json_ld(html):
    blocks = re.findall(
        r'<script[^>]+type=["\']application/ld\+json'
        r'["\'][^>]*>(.*?)</script>',
        html,
        flags=re.I | re.S
    )

    results = []

    for block in blocks:
        try:
            results.append(json.loads(block.strip()))
        except json.JSONDecodeError:
            pass

    return results


def extract_date_candidates(html):
    patterns = {
        "ISO_DATETIME": (
            r'\b20\d{2}-\d{2}-\d{2}'
            r'[T ]\d{2}:\d{2}:\d{2}'
            r'(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?'
        ),
        "ISO_DATE": r'\b20\d{2}-\d{2}-\d{2}\b',
        "POLISH_DATE": r'\b\d{2}\.\d{2}\.20\d{2}\b',
        "UNIX_MS": r'\b1[5-9]\d{11}\b'
    }

    results = {}

    for name, pattern in patterns.items():
        matches = re.findall(pattern, html)
        results[name] = list(dict.fromkeys(matches))[:15]

    return results


print("=" * 72)
print("EUROPE CONFLICT RADAR - POLAND RCB METADATA PROBE v0.3")
print("Execution:", datetime.now(timezone.utc).isoformat())
print("=" * 72)

for category, path in PAGES.items():
    url = BASE + path

    print("\n" + "-" * 72)
    print("CATEGORY:", category)
    print("URL:", url)

    try:
        status, headers, html = fetch(url)

        print("HTTP STATUS:", status)
        print("HTML LENGTH:", len(html))

        print("\nHTTP HEADERS")
        for name in (
            "Date",
            "Last-Modified",
            "ETag",
            "Cache-Control",
            "Age"
        ):
            print(name + ":", headers.get(name))

        parser = MetadataParser()
        parser.feed(html)

        print("\nRELEVANT META TAGS")

        for item in parser.meta:
            combined = " ".join(
                str(value)
                for value in item.values()
            ).lower()

            if any(term in combined for term in (
                "date", "time", "publish",
                "modif", "article", "update"
            )):
                print(json.dumps(
                    item,
                    ensure_ascii=False
                )[:700])

        print("\nHTML TIME ELEMENTS")
        print(json.dumps(
            parser.times[:10],
            ensure_ascii=False,
            indent=2
        ))

        print("\nJSON-LD")
        structured = extract_json_ld(html)
        print(json.dumps(
            structured[:3],
            ensure_ascii=False,
            indent=2
        )[:4000])

        print("\nDATE CANDIDATES")
        dates = extract_date_candidates(html)

        for name, values in dates.items():
            print(name + ":", values)

        print("\nDATE-RELATED HTML SNIPPETS")

        patterns = [
            r".{0,100}data publikacji.{0,150}",
            r".{0,100}opublikowano.{0,150}",
            r".{0,100}data modyfikacji.{0,150}",
            r".{0,100}datePublished.{0,150}",
            r".{0,100}dateModified.{0,150}"
        ]

        for pattern in patterns:
            snippets = re.findall(
                pattern,
                html,
                flags=re.I | re.S
            )

            for snippet in snippets[:3]:
                cleaned = re.sub(
                    r"\s+",
                    " ",
                    snippet
                )
                print(cleaned[:350])

    except Exception as error:
        print(
            "PROBE ERROR:",
            type(error).__name__,
            str(error)
        )

print("\n" + "=" * 72)
print("POLAND RCB METADATA PROBE COMPLETED")
print("=" * 72)
