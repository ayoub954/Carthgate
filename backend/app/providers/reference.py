"""Reference data providers: countries/continents, HS nomenclature, governorates, entry points.

All reference rows come from published sources:
- UN M49 standard (unstats.un.org) — continents / regions, French + English names
- World Bank country API — capital city coordinates (used as map anchors for country flows)
- UN Comtrade HS reference (H6) — HS nomenclature descriptions
- geoBoundaries (OSM-derived, ODbL) — Tunisian governorate polygons
- OMMP (ommp.nat.tn) — official list of Tunisian commercial seaports
- Wikidata (CC0) — airport / port coordinates
- OpenStreetMap Overpass (ODbL) — land border control posts
"""
from __future__ import annotations

import io
import re
import unicodedata
from datetime import datetime

import httpx
import pandas as pd
from sqlalchemy.orm import Session

from .. import cache
from ..config import settings
from ..models import Country, EntryPoint, HSCode, Location
from .base import CONNECTED, ERROR, DataProvider, ProviderStatus
from .geo import find_governorate, haversine_km, centroid

OVERPASS = "https://overpass-api.de/api/interpreter"
WIKIDATA = "https://query.wikidata.org/sparql"


# French forms of official names published only in Arabic in the open source (translation, not a new entity)
ARABIC_FR = {"معبر راس اجدير": "Poste frontalier de Ras Jedir"}


def norm(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


_overpass_down: set[str] = set()
OVERPASS_MIRRORS = [OVERPASS, "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
                    "https://overpass.kumi.systems/api/interpreter", "https://overpass.private.coffee/api/interpreter"]


def overpass(query: str, max_age_hours: float = 24 * 7):
    """Overpass API with public-mirror fallback (same OSM data, different operators)."""
    last = None
    for url in OVERPASS_MIRRORS:
        if url in _overpass_down:
            continue
        try:
            return cache.fetch(url, data={"data": query}, max_age_hours=max_age_hours, min_interval=4, timeout=180).json()
        except Exception as e:
            last = e
            if isinstance(e, (httpx.TransportError,)):
                _overpass_down.add(url)  # skip an unreachable mirror for the rest of this run
    raise last or RuntimeError("all Overpass mirrors unavailable")


def wikidata(query: str):
    return cache.fetch(WIKIDATA, params={"query": query, "format": "json"}, max_age_hours=24 * 7,
                       headers={"Accept": "application/sparql-results+json"}).json()


# ======================================================================
class CountryReferenceProvider(DataProvider):
    key = "un_m49"
    name = "UN M49 — Standard country or area codes (continents)"
    provider = "ReferenceProvider"
    url = "https://unstats.un.org/unsd/methodology/m49/overview/"
    access_type = "PUBLIC_OFFICIAL_REFERENCE"
    license = "United Nations Statistics Division"

    def health(self):
        return ProviderStatus(self.key, CONNECTED if cache.exists(self.url) else ERROR)

    @staticmethod
    def continent(region: str, subregion: str, intermediate: str) -> str | None:
        if region == "Americas":
            return "South America" if intermediate == "South America" else "North America"
        return {"Africa": "Africa", "Europe": "Europe", "Asia": "Asia", "Oceania": "Oceania"}.get(region)

    def ingest(self, db: Session, log) -> ProviderStatus:
        resp = cache.fetch(self.url, max_age_hours=24 * 90)
        self.register_raw(db, resp, period="current standard")
        html = io.StringIO(resp.text())
        en = pd.read_html(html, attrs={"id": "downloadTableEN"})[0]
        html.seek(0)
        fr = pd.read_html(html, attrs={"id": "downloadTableFR"})[0]
        fr_names = dict(zip(fr["ISO-alpha3 Code"], fr["Country or Area"]))
        wb = cache.fetch("https://api.worldbank.org/v2/country", params={"format": "json", "per_page": 400},
                         max_age_hours=24 * 90).json()[1]
        caps = {c["id"]: c for c in wb}
        n = 0
        for _, r in en.iterrows():
            iso3 = r["ISO-alpha3 Code"]
            if not isinstance(iso3, str):
                continue
            c = db.get(Country, iso3) or Country(iso3=iso3, name_en=r["Country or Area"])
            c.m49 = str(int(r["M49 Code"])).zfill(3)
            c.iso2 = r["ISO-alpha2 Code"] if isinstance(r["ISO-alpha2 Code"], str) else None
            c.name_en = r["Country or Area"]
            c.name_fr = fr_names.get(iso3)
            c.region = r["Sub-region Name"] if isinstance(r["Sub-region Name"], str) else None
            c.continent = self.continent(str(r["Region Name"]), str(r["Sub-region Name"]), str(r["Intermediate Region Name"]))
            cap = caps.get(iso3)
            if cap and cap.get("latitude"):
                c.capital, c.lat, c.lon = cap["capitalCity"], float(cap["latitude"]), float(cap["longitude"])
            c.source_key, c.source_url, c.retrieved_at = self.key, self.url, resp.retrieved_at
            db.merge(c)
            n += 1
        db.flush()
        st = ProviderStatus(self.key, CONNECTED, "M49 + World Bank capitals", n, period="current", last_updated=datetime.utcnow())
        self.save_status(db, st)
        return st


# ======================================================================
class HSNomenclatureProvider(DataProvider):
    key = "hs_nomenclature"
    name = "Harmonized System nomenclature (HS 2022, UN Comtrade reference)"
    provider = "TariffProvider"
    url = "https://comtradeapi.un.org/files/v1/app/reference/HS.json"
    access_type = "PUBLIC_OFFICIAL_REFERENCE"
    license = "UN Comtrade reference tables"

    def health(self):
        return ProviderStatus(self.key, CONNECTED if cache.exists(self.url) else ERROR)

    def ingest(self, db: Session, log) -> ProviderStatus:
        resp = cache.fetch(self.url, max_age_hours=24 * 90)
        self.register_raw(db, resp, period="HS 2022 (H6)")
        import json
        data = json.loads(resp.content.decode("utf-8-sig"))["results"]
        db.query(HSCode).delete()
        n = 0
        for r in data:
            code = r["id"]
            if code == "TOTAL" or not code.isdigit():
                continue
            desc = re.sub(r"^\d+\s*-\s*", "", r["text"])
            db.add(HSCode(code=code, description=desc, parent=None if r["parent"] == "TOTAL" else r["parent"],
                          level=len(code), source_key=self.key, source_url=self.url, retrieved_at=resp.retrieved_at))
            n += 1
        db.flush()
        st = ProviderStatus(self.key, CONNECTED, "HS chapters, headings and subheadings", n, period="HS 2022",
                            last_updated=datetime.utcnow())
        self.save_status(db, st)
        return st


# ======================================================================
class GovernorateProvider(DataProvider):
    key = "geoboundaries_tun_adm1"
    name = "geoBoundaries — Tunisia governorates (ADM1)"
    provider = "ReferenceProvider"
    url = "https://www.geoboundaries.org/api/current/gbOpen/TUN/ADM1/"
    access_type = "PUBLIC_OPEN_DATA"
    license = "ODbL 1.0 (OpenStreetMap-derived)"

    def health(self):
        return ProviderStatus(self.key, CONNECTED if cache.exists(self.url) else ERROR)

    def ingest(self, db: Session, log) -> ProviderStatus:
        meta = cache.fetch(self.url, max_age_hours=24 * 90).json()
        gj_url = meta["simplifiedGeometryGeoJSON"]
        resp = cache.fetch(gj_url, max_age_hours=24 * 90)
        self.register_raw(db, resp, period=meta.get("boundaryYearRepresented"), last_updated=meta.get("sourceDataUpdateDate"))
        gj = resp.json()
        db.query(Location).filter(Location.level == "governorate").delete()
        for f in gj["features"]:
            name = f["properties"].get("shapeName")
            c = centroid(f["geometry"])
            db.add(Location(id="gov:" + norm(name).replace(" ", "_"), name=name, level="governorate",
                            centroid_lat=c[0] if c else None, centroid_lon=c[1] if c else None,
                            geometry=f["geometry"], source_key=self.key, source_url=gj_url,
                            retrieved_at=resp.retrieved_at))
        db.flush()
        st = ProviderStatus(self.key, CONNECTED, "24 governorate polygons expected", len(gj["features"]),
                            period=str(meta.get("boundaryYearRepresented")), last_updated=datetime.utcnow())
        self.save_status(db, st)
        return st


# ======================================================================
class EntryPointProvider(DataProvider):
    key = "entry_points_ref"
    name = "Customs entry points referential (OMMP + Wikidata + OpenStreetMap)"
    provider = "CustomsProvider"
    url = "https://www.ommp.nat.tn/"
    access_type = "PUBLIC_OPEN_DATA"
    license = "OMMP (official list) / Wikidata CC0 / OSM ODbL"

    def health(self):
        return ProviderStatus(self.key, CONNECTED if cache.exists(OVERPASS.replace("interpreter", "status")) else ERROR)

    def _airports(self):
        if not settings.http_contact:
            return self._airports_osm()
        q = """SELECT ?item ?itemLabel ?coord ?iata WHERE {
          VALUES ?type { wd:Q644371 wd:Q1248784 }
          ?item wdt:P31 ?type ; wdt:P17 wd:Q948 ; wdt:P625 ?coord .
          OPTIONAL { ?item wdt:P238 ?iata }
          FILTER NOT EXISTS { ?item wdt:P31 wd:Q695850 }
          SERVICE wikibase:label { bd:serviceParam wikibase:language "fr,en". } }"""
        out = {}
        for b in wikidata(q)["results"]["bindings"]:
            qid = b["item"]["value"].rsplit("/", 1)[-1]
            lon, lat = map(float, re.findall(r"[-\d.]+", b["coord"]["value"])[:2])
            name = b["itemLabel"]["value"]
            if "base" in name.lower() and "aérienne" in name.lower():
                continue
            out[qid] = dict(id=f"AIR-{b.get('iata', {}).get('value') or qid}", name=name[0].upper() + name[1:],
                            type="AIRPORT", lat=lat, lon=lon, iata=b.get("iata", {}).get("value"),
                            url=f"https://www.wikidata.org/wiki/{qid}", name_source="Wikidata label")
        return list(out.values())

    def _airports_osm(self):
        q = """[out:json][timeout:90];
        area["ISO3166-1"="TN"][admin_level=2]->.tn;
        nwr["aeroway"="aerodrome"]["iata"](area.tn);
        out center tags;"""
        out = []
        for e in overpass(q)["elements"]:
            t, c = e.get("tags", {}), e.get("center", e)
            name = t.get("name:fr") or t.get("name") or t.get("name:en")
            if not name or t.get("military") or "air base" in name.lower() or "قاعدة" in name or t.get("landuse") == "military":
                continue
            out.append(dict(id=f"AIR-{t['iata']}", name=name, type="AIRPORT", lat=c["lat"], lon=c["lon"], iata=t["iata"],
                            url=f"https://www.openstreetmap.org/{e['type']}/{e['id']}", name_source="OpenStreetMap name tag"))
        return out

    def _port_candidates(self):
        if settings.http_contact:
            q = """SELECT ?item ?itemLabel ?coord WHERE { ?item wdt:P31 wd:Q44782 ; wdt:P17 wd:Q948 ; wdt:P625 ?coord .
                   SERVICE wikibase:label { bd:serviceParam wikibase:language "fr,en". } }"""
            wd = []
            for b in wikidata(q)["results"]["bindings"]:
                lon, lat = map(float, re.findall(r"[-\d.]+", b["coord"]["value"])[:2])
                wd.append((b["itemLabel"]["value"], lat, lon, b["item"]["value"], "Wikidata"))
            return wd
        q = """[out:json][timeout:120];
        area["ISO3166-1"="TN"][admin_level=2]->.tn;
        ( nwr["landuse"="port"](area.tn); nwr["industrial"="port"](area.tn); nwr["harbour"="yes"](area.tn);
          nwr["seamark:type"="harbour"](area.tn); );
        out center tags;"""
        out = []
        for e in overpass(q)["elements"]:
            t, c = e.get("tags", {}), e.get("center", e)
            if "lat" not in c:
                continue
            for nm in {t.get("name:fr"), t.get("name"), t.get("name:en"), t.get("seamark:name")} - {None}:
                out.append((nm, c["lat"], c["lon"], f"https://www.openstreetmap.org/{e['type']}/{e['id']}", "OpenStreetMap"))
        return out

    def _seaports(self, log):
        # 1) official commercial ports list from the port authority (OMMP)
        names = []
        try:
            html = cache.fetch("http://www.ommp.nat.tn/", max_age_hours=24 * 30).text()
            names = sorted(set(m.strip() for m in re.findall(r"PORT DE COMMERCE (?:DE |D')?((?:[A-ZÉÈÀ']{2,}[ -]?)+)", html)))
        except Exception as e:
            log(f"OMMP unreachable: {e}")
        if not names:
            return []
        # 2) coordinates from Wikidata (if contact configured) or OpenStreetMap
        wd = self._port_candidates()
        out = []
        for raw in names:
            nm = norm(raw).replace("menzel bourguiba", "").replace(" m", "").strip()
            first = nm.split()[0] if nm else ""
            cands = [w for w in wd if first and re.search(rf"\b{first}\b", norm(w[0])) and "port" in norm(w[0])
                     and not re.search(r"peche|ancien|vieux|plaisance|marina|punique|fatimide", norm(w[0]))]
            cands.sort(key=lambda w: len(w[0]))
            official = "Port de commerce de " + raw.title().replace("Rades", "Radès").replace("Gabes", "Gabès")
            if cands:
                w = cands[0]
                out.append(dict(id="SEA-" + first.upper(), name=official, type="SEAPORT", lat=w[1], lon=w[2],
                                url=w[3], name_source=f"OMMP official list; coordinates {w[4]} ({w[0]})"))
            else:
                # targeted OSM name search for this official port
                try:
                    q = f"""[out:json][timeout:60];area["ISO3166-1"="TN"][admin_level=2]->.tn;
                    nwr[~"^name(:fr|:en)?$"~"^port.*{first}",i](area.tn);out center tags 5;"""
                    hits = [e for e in overpass(q)["elements"] if "lat" in e.get("center", e)]
                except Exception:
                    hits = []
                if hits:
                    hits.sort(key=lambda e: bool(re.search(r"peche|pêche", (e.get("tags", {}).get("name:fr") or e.get("tags", {}).get("name") or "").lower())))
                    e = hits[0]
                    c, t = e.get("center", e), e.get("tags", {})
                    feat = t.get("name:fr") or t.get("name")
                    approx = bool(re.search(r"peche|pêche", (feat or "").lower()))
                    out.append(dict(id="SEA-" + first.upper(), name=official, type="SEAPORT", lat=c["lat"], lon=c["lon"],
                                    url=f"https://www.openstreetmap.org/{e['type']}/{e['id']}",
                                    name_source=f"OMMP official list; coordinates OpenStreetMap ({feat})" +
                                                (" — APPROXIMATE: adjacent harbour feature" if approx else "")))
                    continue
                out.append(dict(id="SEA-" + first.upper(), name=official, type="SEAPORT", lat=None, lon=None,
                                url="http://www.ommp.nat.tn/", name_source="OMMP official list; coordinates not published"))
        return out

    def _borders(self):
        q = """[out:json][timeout:120];
        area["ISO3166-1"="TN"][admin_level=2]->.tn;
        nwr["barrier"="border_control"](area.tn);
        out center tags;"""
        els = overpass(q)["elements"]
        pts = []
        for e in els:
            c = e.get("center", e)
            if "lat" not in c:
                continue
            t = e.get("tags", {})
            nm = t.get("name:fr") or t.get("name") or t.get("name:en")
            pts.append(dict(osm=f"{e['type']}/{e['id']}", lat=c["lat"], lon=c["lon"], name=nm))
        # group posts within 3 km (one crossing = many nodes)
        groups = []
        for p in pts:
            for g in groups:
                if haversine_km(p["lat"], p["lon"], g["lat"], g["lon"]) < 3:
                    g["members"].append(p)
                    if p["name"] and not g["name"]:
                        g["name"] = p["name"]
                    break
            else:
                groups.append(dict(lat=p["lat"], lon=p["lon"], name=p["name"], members=[p]))
        out = []
        for g in groups:
            name, src = g["name"], "OpenStreetMap name tag"
            if not name:
                nq = f"""[out:json][timeout:60];node(around:15000,{g['lat']},{g['lon']})["place"~"town|village|city"];out tags 1;"""
                try:
                    near = overpass(nq)["elements"]
                    if near:
                        t = near[0]["tags"]
                        name = f"Border control near {t.get('name:fr') or t.get('name')}"
                        src = "Unnamed OSM border control; label = nearest OSM place (derived)"
                except Exception:
                    pass
            if not name:
                continue
            lat, lon = g["lat"], g["lon"]
            neighbor = "Libya" if (lon > 10.2 or lat < 32.5) else "Algeria"
            if name in ARABIC_FR:
                name, src = ARABIC_FR[name], src + " (nom arabe traduit)"
            out.append(dict(id="LAND-" + g["members"][0]["osm"].replace("/", "-"), name=name, type="LAND_BORDER",
                            lat=lat, lon=lon, neighbor=neighbor,
                            url=f"https://www.openstreetmap.org/{g['members'][0]['osm']}", name_source=src))
        return out

    def ingest(self, db: Session, log) -> ProviderStatus:
        now = datetime.utcnow()
        govs = db.query(Location).filter(Location.level == "governorate").all()
        rows = []
        for fn in (self._airports, lambda: self._seaports(log), self._borders):
            try:
                rows.extend(fn())
            except Exception as e:
                log(f"entry points: {e}")
        if not rows:
            st = ProviderStatus(self.key, ERROR, "No entry point source reachable")
            self.save_status(db, st)
            return st
        # a border_control node at an airport/seaport is not a land border crossing
        hubs = [r for r in rows if r["type"] in ("AIRPORT", "SEAPORT") and r.get("lat") is not None]
        rows = [r for r in rows if r["type"] != "LAND_BORDER" or not any(
            haversine_km(r["lat"], r["lon"], h["lat"], h["lon"]) < 10 for h in hubs)]
        db.query(EntryPoint).delete()
        seen = set()
        for r in rows:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            db.add(EntryPoint(entry_point_id=r["id"], official_name=r["name"], entry_type=r["type"],
                              governorate=find_governorate(govs, r.get("lat"), r.get("lon")),
                              latitude=r.get("lat"), longitude=r.get("lon"), iata=r.get("iata"),
                              neighbor_country=r.get("neighbor"), name_source=r["name_source"],
                              source_key=self.key, source_url=r["url"], retrieved_at=now))
        db.flush()
        counts = pd.Series([r["type"] for r in rows]).value_counts().to_dict()
        st = ProviderStatus(self.key, CONNECTED, ", ".join(f"{k}: {v}" for k, v in counts.items()), len(seen),
                            period="current", last_updated=now)
        self.save_status(db, st)
        return st
