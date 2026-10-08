
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API_URL = 'https://api.ukrainealarm.com/api/v3/alerts'
DB_URL = os.environ['SUPABASE_URL'].rstrip('/')
DB_KEY = os.environ['SUPABASE_SECRET_KEY']
API_KEY = os.environ['UKRAINE_ALARM_API_KEY']


def request_json(url, headers, method='GET', payload=None):
    body = None if payload is None else json.dumps(payload).encode('utf-8')
    headers = dict(headers)
    if body is not None:
        headers['Content-Type'] = 'application/json'
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=45) as response:
                data = response.read()
                return json.loads(data) if data else None
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ConnectionResetError) as exc:
            if isinstance(exc, urllib.error.HTTPError) and exc.code not in (429, 500, 502, 503, 504):
                raise
            if attempt == 2:
                raise
            time.sleep(3 * 2 ** attempt)


def headers(prefer=None):
    result = {'apikey': DB_KEY, 'Authorization': f'Bearer {DB_KEY}'}
    if prefer:
        result['Prefer'] = prefer
    return result


def db_get(table, query):
    return request_json(f'{DB_URL}/rest/v1/{table}?{query}', headers())


def db_post(table, rows):
    if rows:
        request_json(f'{DB_URL}/rest/v1/{table}', headers('return=minimal'), 'POST', rows)


def db_upsert(rows):
    if rows:
        request_json(
            f'{DB_URL}/rest/v1/ukraine_alert_state?on_conflict=alert_key',
            headers('resolution=merge-duplicates,return=minimal'), 'POST', rows
        )


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def normalize(regions, observed):
    result = {}
    for region in regions:
        rid = str(region.get('regionId') or '')
        rtype = str(region.get('regionType') or '')
        if not rid:
            continue
        for alert in region.get('activeAlerts') or []:
            threat = str(alert.get('type') or 'UNKNOWN')
            key = f'UA:{rtype}:{rid}:{threat}'
            levels = alert.get('activeAlertLevels') or []
            names = sorted({str(level.get('alertLevel') or '') for level in levels})
            created = [level['createdAt'] for level in levels if level.get('createdAt')]
            result[key] = {
                'alert_key': key,
                'region_id': rid,
                'region_type': rtype,
                'region_name': region.get('regionEngName') or region.get('regionName'),
                'alert_type': threat,
                'level': ','.join(names) or None,
                'source_created_at': min(created) if created else None,
                'source_updated_at': alert.get('lastUpdate'),
                'last_seen_at': observed,
                'active': True,
                'raw_data': alert,
            }
    return result


def missing_count(raw):
    # Internal experimental bookkeeping in raw_data, not a new SQL column.
    if not isinstance(raw, dict):
        return 0
    meta = raw.get('_radar_meta')
    if not isinstance(meta, dict):
        return 0
    try:
        return max(0, int(meta.get('consecutive_missing', 0)))
    except (ValueError, TypeError):
        return 0


def main():
    observed = utc_now()
    print('EUROPE CONFLICT RADAR - UKRAINE COLLECTOR v0.2')
    print('Execution:', observed)
    regions = request_json(API_URL, {
        'Authorization': API_KEY,
        'Accept': 'application/json',
        'User-Agent': 'EuropeConflictRadar-Ukraine/0.2',
    })
    if not isinstance(regions, list) or not regions:
        raise RuntimeError('Invalid or empty Ukraine API response')
    current = normalize(regions, observed)
    if not current:
        raise RuntimeError('No active alerts in snapshot; refusing to end stored alerts')

    previous = {}
    offset = 0
    while True:
        batch = db_get('ukraine_alert_state', f'select=*&order=alert_key.asc&limit=1000&offset={offset}')
        for item in batch:
            previous[item['alert_key']] = item
        if len(batch) < 1000:
            break
        offset += 1000

    baseline = not previous
    changes = []
    upserts = []
    counts = {k: 0 for k in ('baseline', 'activated', 'updated', 'ended', 'unchanged', 'metadata_only', 'pending_end')}

    def transition(key, kind, row):
        changes.append({
            'alert_key': key,
            'transition_type': kind,
            'observed_at': observed,
            'source_updated_at': row.get('source_updated_at'),
            'details': {
                'region_name': row.get('region_name'),
                'type': row.get('alert_type'),
                'level': row.get('level'),
            },
        })
        counts[kind] += 1

    for key, row in current.items():
        old = previous.get(key)
        row['raw_data'] = dict(row['raw_data'])
        row['raw_data']['_radar_meta'] = {'consecutive_missing': 0}
        if old is None:
            row['first_seen_at'] = observed
            transition(key, 'baseline' if baseline else 'activated', row)
        else:
            row['first_seen_at'] = old['first_seen_at']
            if not old.get('active'):
                transition(key, 'activated', row)
            elif old.get('level') != row['level'] or old.get('source_created_at') != row['source_created_at']:
                transition(key, 'updated', row)
            else:
                counts['unchanged'] += 1
                if old.get('source_updated_at') != row['source_updated_at']:
                    counts['metadata_only'] += 1
        upserts.append(row)

    for key, old in previous.items():
        if not old.get('active') or key in current:
            continue
        count = missing_count(old.get('raw_data')) + 1
        old['last_seen_at'] = observed
        old['raw_data'] = dict(old.get('raw_data') or {})
        old['raw_data']['_radar_meta'] = {'consecutive_missing': count}
        if count >= 2:
            old['active'] = False
            transition(key, 'ended', old)
        else:
            counts['pending_end'] += 1
        upserts.append(old)

    # Writes are not atomic across tables; do not publish alerts from this collector.
    db_upsert(upserts)
    db_post('ukraine_alert_transitions', changes)
    print('Regions:', len(regions))
    print('Active alert states:', len(current))
    for key, value in counts.items():
        print(f'{key.upper()}: {value}')
    print('UKRAINE COLLECTOR v0.2 COMPLETED')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('COLLECTOR ERROR:', type(exc).__name__, str(exc), file=sys.stderr)
        raise
