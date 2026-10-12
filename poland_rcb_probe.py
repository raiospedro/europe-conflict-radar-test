
import re
import json
import html
import urllib.request
from html.parser import HTMLParser
from datetime import datetime, timezone

BASE = "https://www.gov.pl/web/rcb/"

PAGES = {
    "AIR_THREAT": "alert-rcb---zagrozenie-z-powietrza-0810",
    "RUSSIAN_AIR_ATTACK": "alert-rcb---rosyjski-atak-powietrzny-na-terenie-ukrainy-1010",
    "STRONG_WIND": "alert-rcb---silny-wiatr-0810",
}

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.headings = []
        self.texts = []
        self.meta = {}
        self.tag = None
        self.ignore = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style"):
            self.ignore += 1
        if tag in ("h1", "h2", "time"):
            self.tag = tag
        if tag == "meta":
            key = attrs.get("property") or attrs.get("name")
            if key:
                self.meta[key] = attrs.get("content", "")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.ignore = max(0, self.ignore - 1)
        if tag == self.tag:
            self.tag = None

    def handle_data(self, data):
        value = " ".join(data.split())
        if not value or self.ignore:
            return
        if self.tag == "h1":
            self.title += " " + value
        if self.tag in ("h1", "h2", "time"):
            self.headings.append(value)
        self.texts.append(value)

print("=" * 70)
print("POLAND RCB CONTENT PROBE v0.2")
print("Execution:", datetime.now(timezone.utc).isoformat())
print("=" * 70)

for category, path in PAGES.items():
    url = BASE + path
    print("\n" + "-" * 70)
    print("CATEGORY:", category)
    print("URL:", url)

    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/html"
            }
        )

        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            page = raw.decode(charset, errors="replace")
            print("HTTP:", response.status)

        parser = PageParser()
        parser.feed(page)

        print("TITLE:", parser.title.strip())
        print("META:", json.dumps(
            {k: v for k, v in parser.meta.items()
             if any(x in k.lower() for x in
                    ("date", "time", "publish", "title"))},
            ensure_ascii=False
        ))

        dates = re.findall(
            r'<time\b[^>]*>.*?</time>',
            page, flags=re.I | re.S
        )
        print("TIME ELEMENTS:", [
            re.sub(r"<[^>]+>", " ", x).strip()
            for x in dates[:5]
        ])

        print("TEXT SAMPLE:")
        for line in parser.texts[:100]:
            if len(line) > 15:
                print(line[:350])

        print("TOTAL TEXT ELEMENTS:", len(parser.texts))

    except Exception as error:
        print("ERROR:", type(error).__name__, str(error))

print("\nPOLAND RCB CONTENT PROBE COMPLETED")
