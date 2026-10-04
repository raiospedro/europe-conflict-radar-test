import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SECRET_KEY"]

endpoint = f"{SUPABASE_URL}/rest/v1/events"

test_event = {
    "event_key": "CONNECTION_TEST_001",
    "event_type": "connection_test",
    "status": "test",
    "country": "Portugal",
    "country_code": "PT",
    "city": "TEST",
    "latitude": 0,
    "longitude": 0,
    "confidence": 0,
    "headline": "GitHub to Supabase connection test",
    "description": "Temporary test record. Safe to delete."
}

data = json.dumps(test_event).encode("utf-8")

request = urllib.request.Request(
    endpoint,
    data=data,
    method="POST",
    headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
)

print("=" * 60)
print("SUPABASE CONNECTION TEST")
print("Time:", datetime.now(timezone.utc).isoformat())
print("=" * 60)

try:
    with urllib.request.urlopen(request, timeout=30) as response:
        result = response.read().decode("utf-8")

        print("HTTP status:", response.status)
        print("SUCCESS - GitHub can write to Supabase.")
        print("Response:")
        print(result)

except urllib.error.HTTPError as error:
    print("HTTP ERROR:", error.code)
    print(error.read().decode("utf-8"))
    raise

print("=" * 60)
print("TEST FINISHED")
print("=" * 60)
