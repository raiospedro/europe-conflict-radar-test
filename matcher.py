import json, math, os, re, unicodedata, urllib.error, urllib.request
from datetime import datetime, timezone

SUPABASE_URL=os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY=os.environ["SUPABASE_SECRET_KEY"]
UA="EuropeConflictRadar-Matcher/0.3"

RELEVANT={"explosion","explosive","bomb","bombing","missile","rocket","drone","air raid","airstrike","air strike","attack","armed","shooting","terror","terrorism","terrorist","evacuation","chemical","radiological","nuclear","ammunition","munition","military","artillery","shelling","war","large scale fire","major fire","world war bomb","bombe","bomben","bombenentscharfung","anschlag","terrorismus","evakuierung","grossbrand","sprengstoff","attentat","attaque","incendie majeur","incendie important"}
TEST={"test","testing","exercise","drill","probealarm","ubung","uebung","essai","exercice"}
CONCEPTS={
"bomb":{"bomb","bombing","bombe","bomben","bombenentscharfung","munition","ammunition","explosive","sprengstoff","world war bomb"},
"explosion":{"explosion","blast","detonation","explosive"},
"missile":{"missile","rocket","airstrike","air strike","shelling","artillery"},
"drone":{"drone","uav","unmanned aerial"},
"attack":{"attack","attacked","attentat","attaque","anschlag","armed","shooting"},
"terror":{"terror","terrorism","terrorist","anschlag","attentat"},
"evacuation":{"evacuation","evacuate","evacuated","evakuierung"},
"fire":{"large scale fire","major fire","grossbrand","incendie majeur","incendie important"},
"chemical":{"chemical","hazardous substance","toxic","radiological","nuclear"},
"military":{"military","armed forces","troops","artillery","war"}}
STOP={"alert","warning","official","update","cancel","cancelled","public","immediate","unknown","actual","germany","luxembourg","united","kingdom","city","district","area","region","state","from","with","this","that","into","near","over","under","after","before","during","large","scale"}

def norm(v):
    if not v:return ""
    v=re.sub(r"<[^>]+>"," ",str(v)); v=unicodedata.normalize("NFKD",v)
    v="".join(c for c in v if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9\s\-]"," ",v)).strip()

def otext(a): return norm(" ".join(str(a.get(k) or "") for k in ("headline","description","event_code","area_description")))
def gtext(e): return norm(" ".join(str(e.get(k) or "") for k in ("headline","description","city","region","country","source_domain","source_url")))
def concepts(t): return {c for c,terms in CONCEPTS.items() if any(x in t for x in terms)}
def tokens(t): return {x for x in re.findall(r"\b[a-z][a-z0-9\-]{3,}\b",t) if x not in STOP}
def is_test(a): return bool(set(re.findall(r"\b[a-z0-9\-]+\b",otext(a))) & TEST)
def relevant(a): return any(x in otext(a) for x in RELEVANT)

def get(table,params=""):
    u=f"{SUPABASE_URL}/rest/v1/{table}"+(("?"+params) if params else "")
    r=urllib.request.Request(u,headers={"apikey":SUPABASE_KEY,"Authorization":f"Bearer {SUPABASE_KEY}","User-Agent":UA})
    with urllib.request.urlopen(r,timeout=30) as x:return json.loads(x.read().decode())

def insert(payload):
    u=f"{SUPABASE_URL}/rest/v1/event_matches"
    h={"apikey":SUPABASE_KEY,"Authorization":f"Bearer {SUPABASE_KEY}","Content-Type":"application/json"}
    if payload.get("gdelt_event_id") is not None:
        u+="?on_conflict=official_alert_id,gdelt_event_id"; h["Prefer"]="resolution=ignore-duplicates,return=minimal"
    else:h["Prefer"]="return=minimal"
    r=urllib.request.Request(u,data=json.dumps(payload).encode(),method="POST",headers=h)
    with urllib.request.urlopen(r,timeout=30) as x:return x.status

def ptime(v):
    try:return datetime.fromisoformat(v.replace("Z","+00:00")).astimezone(timezone.utc)
    except:return None
def gtime(v):
    try:return datetime.strptime(v,"%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except:return None
def hav(a,b,c,d):
    R=6371.; p1,p2=math.radians(a),math.radians(c); da=math.radians(c-a); db=math.radians(d-b)
    z=math.sin(da/2)**2+math.cos(p1)*math.cos(p2)*math.sin(db/2)**2
    return R*2*math.atan2(math.sqrt(z),math.sqrt(1-z))

def coords(v,out):
    if isinstance(v,dict):
        if "coordinates" in v: coords(v["coordinates"],out)
        for poly in v.get("polygons",[]):
            if isinstance(poly,str):
                for pair in poly.split():
                    try:
                        lat,lon=pair.split(","); out.append((float(lat),float(lon)))
                    except:pass
        for k,x in v.items():
            if k not in ("coordinates","polygons"):coords(x,out)
    elif isinstance(v,list):
        if len(v)>=2 and isinstance(v[0],(int,float)) and isinstance(v[1],(int,float)):
            lon,lat=float(v[0]),float(v[1])
            if -90<=lat<=90 and -180<=lon<=180:out.append((lat,lon))
        else:
            for x in v:coords(x,out)

def point(g):
    out=[]; coords(g,out)
    if not out:return None
    return sum(x for x,_ in out)/len(out),sum(y for _,y in out)/len(out)

def semantic(a,e):
    ot,gt=otext(a),gtext(e); cc=concepts(ot)&concepts(gt); ct=tokens(ot)&tokens(gt)
    lt=tokens(norm((a.get("area_description") or "")+" "+(a.get("headline") or ""))); cl=lt&tokens(gt)
    score=(40 if cc else 0)+min(len(cl)*15,30)+min(len(ct-cl)*5,15)
    return score,bool(cc or cl),sorted(cc),sorted(cl)

def no_candidate_exists(i):
    return bool(get("event_matches",f"select=id&official_alert_id=eq.{i}&gdelt_event_id=is.null&limit=1"))

print("="*78); print("EUROPE CONFLICT RADAR MATCHER v0.3"); print("Execution:",datetime.now(timezone.utc).isoformat()); print("="*78)
official=get("official_alerts","select=*"); events=get("events","select=*&event_type=eq.gdelt_candidate")
rel=[a for a in official if not is_test(a) and relevant(a)]
print("Official alerts:",len(official)); print("GDELT candidates:",len(events)); print("Relevant official alerts:",len(rel)); print("Test/exercise alerts excluded:",sum(is_test(a) for a in official))

accepted=no_new=existing=probable=possible=rej_dist=rej_sem=rej_time=0

for a in rel:
    ot=ptime(a.get("issued_at"))
    if not ot:continue
    op=point(a.get("geometry")); valid=[]
    for e in events:
        if norm(a.get("country"))!=norm(e.get("country")):continue
        gt=gtime(e.get("gdelt_date_added"))
        if not gt:continue
        latency=(gt-ot).total_seconds()/60
        if latency < -90 or latency > 240: rej_time+=1; continue
        distance=None
        if op and e.get("latitude") is not None and e.get("longitude") is not None:
            try:distance=hav(op[0],op[1],float(e["latitude"]),float(e["longitude"]))
            except:pass
        if distance is not None and distance>200: rej_dist+=1; continue
        ss,strong,cc,cl=semantic(a,e)
        if not strong: rej_sem+=1; continue
        al=abs(latency); ts=25 if al<=15 else 20 if al<=30 else 15 if al<=60 else 8 if al<=120 else 3
        ds=0 if distance is None else 25 if distance<=10 else 20 if distance<=25 else 15 if distance<=50 else 8 if distance<=100 else 2
        valid.append((ss+ts+ds,e,latency,distance,ts,ds,ss,cc,cl))
    valid.sort(key=lambda x:x[0],reverse=True)

    classification=None; best=valid[0] if valid else None
    if best:
        if best[0]>=75 and (best[3] is None or best[3]<=100):classification="probable_match"; probable+=1
        elif best[0]>=55:classification="possible_match"; possible+=1

    print("\n"+"-"*78); print("OFFICIAL:",a.get("headline"))
    if classification:
        score,e,latency,distance,ts,ds,ss,cc,cl=best
        payload={"official_alert_id":a["id"],"gdelt_event_id":e["id"],"official_country":a.get("country"),"official_time":a.get("issued_at"),"gdelt_time":e.get("first_detected_at"),"latency_minutes":round(latency,2),"distance_km":round(distance,2) if distance is not None else None,"time_score":ts,"distance_score":ds,"text_score":ss,"match_score":score,"classification":classification,"notes":f"Matcher v0.3; concepts={cc}; locations={cl}; manual validation required."}
        try:
            if insert(payload) in (200,201,204):accepted+=1
            print("RESULT:",classification.upper()); print("Score:",score); print("Latency:",round(latency,1),"minutes"); print("Distance:",round(distance,1) if distance is not None else "unknown","km"); print("Common concepts:",cc); print("Common locations:",cl); print("GDELT source:",e.get("source_url"))
        except Exception as ex:print("MATCH INSERT ERROR:",ex)
    else:
        print("RESULT: NO VALID MATCH")
        if best:print("Best rejected score:",best[0])
        try:
            if no_candidate_exists(a["id"]): existing+=1
            else:
                payload={"official_alert_id":a["id"],"gdelt_event_id":None,"official_country":a.get("country"),"official_time":a.get("issued_at"),"classification":"no_candidate","match_score":0,"notes":"Matcher v0.3: no candidate passed conservative semantic/geographic rules."}
                if insert(payload) in (200,201,204):no_new+=1
        except Exception as ex:print("NO-CANDIDATE ERROR:",ex)

print("\n"+"="*78); print("MATCHER v0.3 SUMMARY"); print("="*78)
print("OFFICIAL ALERTS:",len(official)); print("GDELT CANDIDATES:",len(events)); print("RELEVANT OFFICIAL ALERTS:",len(rel))
print("PROBABLE MATCHES:",probable); print("POSSIBLE MATCHES:",possible); print("MATCHES ACCEPTED:",accepted)
print("NO-CANDIDATES CREATED:",no_new); print("ALREADY RECORDED:",existing)
print("REJECTED BY TIME:",rej_time); print("REJECTED BY DISTANCE:",rej_dist); print("REJECTED BY SEMANTICS:",rej_sem)
print("MATCHER v0.3 COMPLETED:",datetime.now(timezone.utc).isoformat()); print("="*78)
