import csv
import io
import urllib.request
import zipfile
from datetime import datetime, timezone
from urllib.parse import urlparse

# ============================================================
# EUROPE CONFLICT RADAR
# GDELT 2.0 Event Feed Test v0.4
#
# Objetivo:
# - ler corretamente o schema GDELT 2.0
# - limitar à Europa
# - procurar violência/conflito potencialmente relevante
# - reduzir ruído
# - deduplicar artigos
# - NÃO gravar ainda no Supabase
# ============================================================

LAST_UPDATE_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"

# ------------------------------------------------------------
# FIPS GEO country codes usados pelo GDELT.
# Europa operacional do nosso projeto.
# ------------------------------------------------------------

EUROPE_FIPS = {
    "AL": "Albania",
    "AN": "Andorra",
    "AU": "Austria",
    "BE": "Belgium",
    "BK": "Bosnia and Herzegovina",
    "BU": "Bulgaria",
    "BO": "Belarus",
    "HR": "Croatia",
    "CY": "Cyprus",
    "EZ": "Czechia",
    "DA": "Denmark",
    "EN": "Estonia",
    "FI": "Finland",
    "FR": "France",
    "GM": "Germany",
    "GR": "Greece",
    "HU": "Hungary",
    "IC": "Iceland",
    "EI": "Ireland",
    "IT": "Italy",
    "LG": "Latvia",
    "LH": "Lithuania",
    "LU": "Luxembourg",
    "MK": "North Macedonia",
    "MT": "Malta",
    "MD": "Moldova",
    "MJ": "Montenegro",
    "NL": "Netherlands",
    "NO": "Norway",
    "PL": "Poland",
    "PO": "Portugal",
    "RO": "Romania",
    "RI": "Serbia",
    "LO": "Slovakia",
    "SI": "Slovenia",
    "SP": "Spain",
    "SW": "Sweden",
    "SZ": "Switzerland",
    "UK": "United Kingdom",
    "UP": "Ukraine",
    "VT": "Vatican City",
    "SM": "San Marino",
    "MN": "Monaco",
    "LS": "Liechtenstein",
    "KV": "Kosovo",
}

# ------------------------------------------------------------
# CAMEO codes
#
# Não usamos simplesmente root 18/19/20.
#
# Procuramos inicialmente:
# 190 = use conventional military force
# 191 = impose blockade
# 192 = occupy territory
# 193 = fight with small arms/light weapons
# 194 = fight with artillery/tanks
# 195 = employ aerial weapons
# 196 = violate ceasefire
#
# 20x = mass violence / unconventional mass violence
#
# Alguns códigos podem continuar a produzir ruído.
# É precisamente isso que este teste pretende medir.
# ------------------------------------------------------------

HIGH_RELEVANCE_PREFIXES = (
    "190",
    "191",
    "192",
    "193",
    "194",
    "195",
    "196",
    "20",
)

# 15 = exhibit military/police force.
# Não é necessariamente ataque, mas pode ser útil como sinal.
WATCH_PREFIXES = (
    "152",  # increase military alert status
    "154",  # mobilize/increase armed forces
)

print("=" * 76)
print("EUROPE CONFLICT RADAR - GDELT EVENT FEED v0.4")
print("Execution time:", datetime.now(timezone.utc).isoformat())
print("=" * 76)

# ============================================================
# 1. DESCOBRIR O FICHEIRO MAIS RECENTE
# ============================================================

print("\n[1/5] Looking for latest GDELT dataset...")

request = urllib.request.Request(
    LAST_UPDATE_URL,
    headers={"User-Agent": "EuropeConflictRadar-Test/0.4"},
)

with urllib.request.urlopen(request, timeout=60) as response:
    last_update = response.read().decode("utf-8")

export_url = None

for line in last_update.splitlines():
    parts = line.split()

    if len(parts) >= 3 and parts[2].endswith(".export.CSV.zip"):
        export_url = parts[2]
        break

if not export_url:
    raise RuntimeError("Could not find latest GDELT export file.")

print("Latest export:")
print(export_url)

# ============================================================
# 2. DOWNLOAD
# ============================================================

print("\n[2/5] Downloading latest 15-minute dataset...")

request = urllib.request.Request(
    export_url,
    headers={"User-Agent": "EuropeConflictRadar-Test/0.4"},
)

with urllib.request.urlopen(request, timeout=120) as response:
    zip_data = response.read()

print(f"Downloaded: {len(zip_data):,} bytes")

# ============================================================
# 3. PROCESSAMENTO
# ============================================================

print("\n[3/5] Processing events...")

total_events = 0
europe_events = 0
material_conflict_events = 0
candidate_events = []

with zipfile.ZipFile(io.BytesIO(zip_data)) as archive:

    filename = archive.namelist()[0]

    with archive.open(filename) as csv_file:

        text_stream = io.TextIOWrapper(
            csv_file,
            encoding="utf-8",
            errors="replace",
        )

        reader = csv.reader(text_stream, delimiter="\t")

        for row in reader:

            total_events += 1

            # GDELT 2.0 export tem 61 colunas.
            if len(row) < 61:
                continue

            # ------------------------------------------------
            # SCHEMA GDELT 2.0 - índices Python (zero based)
            # ------------------------------------------------

            global_event_id = row[0]

            is_root_event = row[25]

            event_code = row[26]
            event_base_code = row[27]
            event_root_code = row[28]

            quad_class = row[29]
            goldstein_scale = row[30]

            num_mentions = row[31]
            num_sources = row[32]
            num_articles = row[33]
            avg_tone = row[34]

            action_geo_type = row[51]
            action_geo_fullname = row[52]
            action_geo_country = row[53]
            action_geo_adm1 = row[54]
            action_geo_lat = row[56]
            action_geo_long = row[57]
            action_geo_feature_id = row[58]

            date_added = row[59]
            source_url = row[60]

            # -----------------------------------------------
            # EUROPA
            # -----------------------------------------------

            if action_geo_country not in EUROPE_FIPS:
                continue

            europe_events += 1

            # -----------------------------------------------
            # MATERIAL CONFLICT
            # QuadClass 4 = Material Conflict
            # -----------------------------------------------

            if quad_class == "4":
                material_conflict_events += 1

            # -----------------------------------------------
            # RELEVÂNCIA PARA O NOSSO RADAR
            # -----------------------------------------------

            relevance = None

            if event_code.startswith(HIGH_RELEVANCE_PREFIXES):
                relevance = "HIGH"

            elif event_code.startswith(WATCH_PREFIXES):
                relevance = "WATCH"

            if relevance is None:
                continue

            # Queremos localização utilizável.
            if not action_geo_lat or not action_geo_long:
                continue

            # Conversão segura dos números.
            try:
                sources_int = int(num_sources or 0)
            except ValueError:
                sources_int = 0

            try:
                articles_int = int(num_articles or 0)
            except ValueError:
                articles_int = 0

            try:
                mentions_int = int(num_mentions or 0)
            except ValueError:
                mentions_int = 0

            try:
                goldstein_float = float(goldstein_scale or 0)
            except ValueError:
                goldstein_float = 0.0

            # -----------------------------------------------
            # SCORE EXPERIMENTAL
            #
            # NÃO significa "confirmado".
            # Serve apenas para ordenar o que merece análise.
            # -----------------------------------------------

            score = 0

            if relevance == "HIGH":
                score += 40
            else:
                score += 15

            if quad_class == "4":
                score += 15

            if is_root_event == "1":
                score += 5

            if sources_int >= 2:
                score += 10

            if sources_int >= 3:
                score += 10

            if articles_int >= 3:
                score += 5

            if mentions_int >= 5:
                score += 5

            if goldstein_float <= -7:
                score += 10

            candidate_events.append({
                "gdelt_id": global_event_id,
                "event_code": event_code,
                "base_code": event_base_code,
                "root_code": event_root_code,
                "quad_class": quad_class,
                "goldstein": goldstein_float,
                "is_root": is_root_event,
                "num_mentions": mentions_int,
                "num_sources": sources_int,
                "num_articles": articles_int,
                "avg_tone": avg_tone,
                "location": action_geo_fullname,
                "country_code": action_geo_country,
                "country": EUROPE_FIPS[action_geo_country],
                "adm1": action_geo_adm1,
                "geo_type": action_geo_type,
                "latitude": action_geo_lat,
                "longitude": action_geo_long,
                "feature_id": action_geo_feature_id,
                "date_added": date_added,
                "source_url": source_url,
                "relevance": relevance,
                "score": score,
            })

# ============================================================
# 4. DEDUPLICAÇÃO BÁSICA
# ============================================================

print("\n[4/5] Deduplicating...")

# O mesmo artigo pode originar vários eventos GDELT.
# Nesta primeira versão mantemos apenas o evento com maior
# score por URL + localização + event code.

deduplicated = {}

for event in candidate_events:

    key = (
        event["source_url"],
        event["location"],
        event["event_code"],
    )

    existing = deduplicated.get(key)

    if existing is None or event["score"] > existing["score"]:
        deduplicated[key] = event

final_events = list(deduplicated.values())

# Ordenar:
# score -> fontes -> artigos
final_events.sort(
    key=lambda x: (
        x["score"],
        x["num_sources"],
        x["num_articles"],
    ),
    reverse=True,
)

# ============================================================
# 5. RESULTADOS
# ============================================================

print("\n[5/5] Results")

print()
print("=" * 76)
print(f"TOTAL GDELT EVENTS:              {total_events}")
print(f"EVENTS LOCATED IN EUROPE:        {europe_events}")
print(f"EUROPE MATERIAL CONFLICT:        {material_conflict_events}")
print(f"CANDIDATES BEFORE DEDUP:         {len(candidate_events)}")
print(f"CANDIDATES AFTER DEDUP:          {len(final_events)}")
print("=" * 76)

if not final_events:
    print("\nNo candidate armed-conflict events found in this 15-minute window.")

for number, event in enumerate(final_events[:50], start=1):

    print()
    print("-" * 76)

    print(
        f"EVENT {number} | "
        f"{event['relevance']} | "
        f"SCORE {event['score']}"
    )

    print("GDELT ID:", event["gdelt_id"])

    print(
        "CAMEO:",
        event["event_code"],
        "| Base:",
        event["base_code"],
        "| Root:",
        event["root_code"],
    )

    print(
        "QuadClass:",
        event["quad_class"],
        "| Goldstein:",
        event["goldstein"],
        "| Root event:",
        event["is_root"],
    )

    print("Country:", event["country"])
    print("Location:", event["location"])
    print("ADM1:", event["adm1"])

    print(
        "Coordinates:",
        event["latitude"],
        event["longitude"],
    )

    print(
        "Mentions:",
        event["num_mentions"],
        "| Sources:",
        event["num_sources"],
        "| Articles:",
        event["num_articles"],
    )

    print("GDELT DATEADDED:", event["date_added"])

    try:
        domain = urlparse(event["source_url"]).netloc
    except Exception:
        domain = ""

    print("Source domain:", domain)
    print("Source URL:", event["source_url"])

print()
print("=" * 76)
print("EUROPE CONFLICT RADAR v0.4 COMPLETED")
print("=" * 76)
