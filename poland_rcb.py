
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

BASE = "https://www.gov.pl/web/rcb/komunikaty"
DB = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SECRET_KEY"]
NOW = datetime.now(timezone.utc).isoformat()


class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.text = []
        self.skip = 0
        self.in_main = 0
        self.title = ""
        self.h1 = False

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        if tag == "a" and d.get("href"):
            self.links.append(d["href"])
        if tag == "h1":
            self.h1 = True
        if tag == "main":
            self.in_main += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)
        if tag == "h1":
            self.h1 = False
        if tag == "main":
            self.in_main = max(0, self.in_main - 1)

    def handle_data(self, data):
        s = " ".join(data.split())
        if self.skip or not s:
            return
        if self.h1:
            self.title += (" " if self.title else "") + s
        if self.in_main:
            self.text.append(s)


def fetch(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "EuropeConflictRadar/RCB-research-0.1",
            "Accept": "text/html"
        }
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", errors="replace")


def api(table, method="GET", payload=None, query=""):
    url = f"{DB}/rest/v1/{table}"
    if query:
        url += "?" + query

    headers = {
        "apikey": KEY,
        "Authorization": f"Bearer {KEY}",
        "Content-Type": "application/json",
        "Prefer": (
            "return=representation"
            if method == "GET"
            else "return=minimal"
        )
    }

    data = (
        None if payload is None
        else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    )

    req = urllib.request.Request(
        url, headers=headers, data=data, method=method
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        raw = r.read()
        return json.loads(raw) if raw else []


def normalize(url):
    parsed = urllib.parse.urlsplit(
        urllib.parse.urljoin(BASE, url)
    )
    if (
        parsed.netloc != "www.gov.pl"
        or not parsed.path.startswith("/web/rcb/")
    ):
        return None
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, "", "")
    )


def main():
    print("POLAND RCB COLLECTOR v0.1", NOW)

    listing = Parser()
    listing.feed(fetch(BASE))

    links = set()
    for raw in listing.links:
        url = normalize(raw)
        if url and "/alert-rcb-" in url:
            links.add(url)

    print("Alert links discovered:", len(links))
    if not links:
        raise RuntimeError("No RCB alert links found")

    added = changed = unchanged = errors = 0

    for url in sorted(links):
        try:
            page = Parser()
            page.feed(fetch(url))

            body = re.sub(
                r"\s+", " ", " ".join(page.text)
            ).strip()
            title = page.title.strip() or url.rsplit("/", 1)[-1]

            if len(body) < 40:
                print("SKIP short content:", url)
                errors += 1
                continue

            digest = hashlib.sha256(
                (title + "\n" + body).encode("utf-8")
            ).hexdigest()

            filter_url = (
                "url=eq." +
                urllib.parse.quote(url, safe="")
            )

            existing = api(
                "poland_rcb_posts",
                query="select=url,content_hash&" + filter_url
            )

            if not existing:
                api("poland_rcb_posts", "POST", [{
                    "url": url,
                    "title": title,
                    "body_text": body,
                    "content_hash": digest,
                    "first_seen_at": NOW,
                    "last_seen_at": NOW
                }])
                api("poland_rcb_changes", "POST", [{
                    "url": url,
                    "change_type": "first_seen",
                    "observed_at": NOW,
                    "content_hash": digest
                }])
                added += 1

            elif existing[0]["content_hash"] != digest:
                api("poland_rcb_posts", "PATCH", {
                    "title": title,
                    "body_text": body,
                    "content_hash": digest,
                    "last_seen_at": NOW
                }, filter_url)
                api("poland_rcb_changes", "POST", [{
                    "url": url,
                    "change_type": "content_changed",
                    "observed_at": NOW,
                    "content_hash": digest
                }])
                changed += 1

            else:
                api("poland_rcb_posts", "PATCH", {
                    "last_seen_at": NOW
                }, filter_url)
                unchanged += 1

        except Exception as exc:
            print("ERROR:", url, type(exc).__name__, str(exc))
            errors += 1

    print(
        "NEW:", added,
        "CHANGED:", changed,
        "UNCHANGED:", unchanged,
        "ERRORS:", errors
    )

    if errors:
        raise RuntimeError(f"{errors} pages failed")

    print("POLAND RCB COLLECTOR COMPLETED")


if __name__ == "__main__":
    main()
