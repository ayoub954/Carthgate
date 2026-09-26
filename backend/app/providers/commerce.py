"""Commerce providers.

AuthorizedCommerceProvider
  * OpenStreetMap public commercial locations (shops) in Tunisia — name, type, public
    location, website / Facebook / Instagram links ONLY when tagged in OSM (ODbL).
  * Open Food / Beauty / Products Facts — open product registries: products recorded as
    sold in Tunisia, with real images, brands, categories, declared manufacturing places.
  * Optional: e-commerce domains listed in AUTHORIZED_COMMERCE_SITES (operator-authorised),
    read through sitemap + schema.org Product JSON-LD, robots.txt always enforced.
SocialCommerceProvider
  * Facebook/Instagram via Meta Graph API and TikTok via Research API — ONLY with official
    tokens. Without tokens the status is "AUTHORIZED API REQUIRED"; nothing is scraped.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from .. import cache
from ..config import settings
from ..models import CommerceObservation, Location, Seller
from .base import ACCESS_REQUIRED, CONNECTED, ERROR, NOT_AVAILABLE, DataProvider, ProviderStatus
from .geo import find_governorate
from .reference import overpass

SHOP_CATEGORY = {
    "mobile_phone": "Électronique", "electronics": "Électronique", "computer": "Électronique",
    "hifi": "Électronique", "video_games": "Jouets et jeux", "appliance": "Électroménager",
    "clothes": "Textile et habillement", "fashion_accessories": "Textile et habillement", "shoes": "Chaussures",
    "bag": "Maroquinerie", "cosmetics": "Cosmétiques", "perfumery": "Cosmétiques", "beauty": "Cosmétiques",
    "watches": "Bijoux et montres", "jewelry": "Bijoux et montres", "toys": "Jouets et jeux",
    "sports": "Sport", "optician": "Optique",
}

OFF_SITES = {
    "openbeautyfacts": ("Open Beauty Facts", "https://world.openbeautyfacts.org", None),
    "openproductsfacts": ("Open Products Facts", "https://world.openproductsfacts.org", None),
    "openfoodfacts": ("Open Food Facts", "https://world.openfoodfacts.org", 10),  # cap pages (food is out of core scope)
}


def _social(tags: dict, *keys) -> str | None:
    for k in keys:
        v = tags.get(k)
        if v:
            v = v.split(";")[0].strip()
            if k.endswith("facebook") and not v.startswith("http"):
                v = "https://www.facebook.com/" + v.lstrip("@/")
            if k.endswith("instagram") and not v.startswith("http"):
                v = "https://www.instagram.com/" + v.lstrip("@/")
            if k.endswith("tiktok") and not v.startswith("http"):
                v = "https://www.tiktok.com/@" + v.lstrip("@/")
            if k in ("website", "contact:website") and not v.startswith("http"):
                v = "https://" + v
            return v
    return None


class AuthorizedCommerceProvider(DataProvider):
    key = "commerce_public"
    name = "Public commerce observations (OpenStreetMap shops + Open*Facts registries)"
    provider = "AuthorizedCommerceProvider"
    url = "https://www.openstreetmap.org/"
    access_type = "PUBLIC_OPEN_DATA"
    license = "ODbL 1.0"

    def health(self):
        ok = cache.exists("https://overpass-api.de/api/status")
        return ProviderStatus(self.key, CONNECTED if ok else ERROR)

    # ---------------------------------------------------------------- OSM
    def ingest_shops(self, db: Session, log) -> int:
        types = "|".join(sorted(SHOP_CATEGORY))
        q = f"""[out:json][timeout:180];
        area["ISO3166-1"="TN"][admin_level=2]->.tn;
        nwr["shop"~"^({types})$"](area.tn);
        out center tags;"""
        data = overpass(q, max_age_hours=24 * 3)
        govs = db.query(Location).filter(Location.level == "governorate").all()
        now = datetime.utcnow()
        n = 0
        existing = {s.external_id: s for s in db.query(Seller).filter(Seller.source_key == "osm_shops")}
        for e in data["elements"]:
            c = e.get("center", e)
            if "lat" not in c:
                continue
            t = e.get("tags", {})
            ext = f"osm:{e['type']}/{e['id']}"
            s = existing.get(ext) or Seller(external_id=ext)
            s.name = t.get("name:fr") or t.get("name") or t.get("name:en") or t.get("brand")
            s.shop_type = t.get("shop")
            s.category = SHOP_CATEGORY.get(s.shop_type)
            s.lat, s.lon = c["lat"], c["lon"]
            s.city = t.get("addr:city")
            s.governorate = find_governorate(govs, s.lat, s.lon)
            s.website = _social(t, "website", "contact:website")
            s.facebook = _social(t, "contact:facebook", "facebook")
            s.instagram = _social(t, "contact:instagram", "instagram")
            s.tiktok = _social(t, "contact:tiktok", "tiktok")
            s.brand = t.get("brand")
            # keep only non-personal public tags (no phone / email / house number)
            s.tags = {k: v for k, v in t.items() if k in ("shop", "brand", "brand:wikidata", "opening_hours", "operator", "second_hand")}
            s.source_key = "osm_shops"
            s.source_url = f"https://www.openstreetmap.org/{e['type']}/{e['id']}"
            s.retrieved_at = now
            db.add(s)
            n += 1
        db.flush()
        return n

    # ---------------------------------------------------------------- Open*Facts
    def ingest_open_facts(self, db: Session, log) -> dict:
        fields = ("code,product_name,product_name_fr,brands,categories,categories_tags,image_front_url,"
                  "stores,manufacturing_places,origins,created_t,last_modified_t,purchase_places")
        counts = {}
        for key, (label, base, cap) in OFF_SITES.items():
            page, n = 1, 0
            while True:
                try:
                    d = cache.fetch(f"{base}/api/v2/search", params={
                        "countries_tags_en": "tunisia", "page_size": 100, "page": page, "fields": fields,
                        "sort_by": "last_modified_t"}, max_age_hours=24 * 3, min_interval=6.5).json()
                except Exception as e:
                    log(f"{label} page {page}: {e}")
                    break
                prods = d.get("products", [])
                for p in prods:
                    name = (p.get("product_name_fr") or p.get("product_name") or "").strip()
                    if not name and not p.get("brands"):
                        continue
                    ext = f"{key}:{p['code']}"
                    o = db.query(CommerceObservation).filter_by(external_id=ext).first() or CommerceObservation(external_id=ext)
                    o.platform = label
                    o.page_name = label
                    o.page_url = f"{base}/product/{p['code']}"
                    o.post_url = o.page_url
                    o.product = name or None
                    o.brand = (p.get("brands") or "").split(",")[0].strip() or None
                    cats = [c.split(":", 1)[-1].replace("-", " ") for c in p.get("categories_tags") or []]
                    o.category = cats[-1] if cats else None
                    o.raw_categories = ", ".join(cats) or None
                    o.image_url = p.get("image_front_url") or None
                    o.observed_at = datetime.utcfromtimestamp(p["created_t"]) if p.get("created_t") else None
                    o.public_business_location = (p.get("stores") or p.get("purchase_places") or None)
                    o.manufacturing_place = p.get("manufacturing_places") or None
                    o.origin = p.get("origins") or None
                    o.source_key = key
                    o.source_url = o.page_url
                    o.retrieved_at = datetime.utcnow()
                    db.add(o)
                    n += 1
                if not prods or page * 100 >= d.get("count", 0) or (cap and page >= cap):  # "page_count" = items on page
                    break
                page += 1
            counts[label] = n
            db.flush()
        return counts

    # ---------------------------------------------------------------- authorized sites
    def ingest_authorized_sites(self, db: Session, log) -> int:
        n = 0
        for domain in settings.authorized_commerce_sites:
            base = domain if domain.startswith("http") else "https://" + domain
            try:
                sm = cache.fetch(base.rstrip("/") + "/sitemap.xml", check_robots=True, max_age_hours=24, min_interval=2)
            except Exception as e:
                log(f"{domain}: sitemap unavailable or disallowed ({e})")
                continue
            urls = re.findall(r"<loc>([^<]+)</loc>", sm.text())
            for u in [u for u in urls if re.search(r"produ|/p/|item", u, re.I)][:200]:
                try:
                    page = cache.fetch(u, check_robots=True, max_age_hours=24, min_interval=2).text()
                except Exception:
                    continue
                for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S | re.I):
                    try:
                        data = json.loads(block.strip())
                    except Exception:
                        continue
                    items = data if isinstance(data, list) else data.get("@graph", [data])
                    for it in items:
                        if not isinstance(it, dict) or "Product" not in str(it.get("@type")):
                            continue
                        offers = it.get("offers") or {}
                        offers = offers[0] if isinstance(offers, list) and offers else offers
                        brand = it.get("brand")
                        brand = brand.get("name") if isinstance(brand, dict) else brand
                        img = it.get("image")
                        img = img[0] if isinstance(img, list) and img else (img.get("url") if isinstance(img, dict) else img)
                        ext = f"web:{urlparse(u).netloc}:{u}"[:128]
                        o = db.query(CommerceObservation).filter_by(external_id=ext).first() or CommerceObservation(external_id=ext)
                        o.platform, o.page_name, o.page_url, o.post_url = "Website", urlparse(u).netloc, base, u
                        o.product, o.brand, o.image_url = it.get("name"), brand, img
                        o.category = it.get("category") if isinstance(it.get("category"), str) else None
                        try:
                            o.price = float(offers.get("price")) if offers.get("price") else None
                        except (TypeError, ValueError):
                            o.price = None
                        o.currency = offers.get("priceCurrency")
                        o.observed_at = datetime.utcnow()
                        o.source_key, o.source_url, o.retrieved_at = "authorized_sites", u, datetime.utcnow()
                        db.add(o)
                        n += 1
        db.flush()
        return n

    def ingest(self, db: Session, log) -> ProviderStatus:
        now = datetime.utcnow()
        parts, total = [], 0
        try:
            s = self.ingest_shops(db, log)
            parts.append(f"OSM shops: {s}")
            total += s
            self.save_status(db, ProviderStatus("osm_shops", CONNECTED, "Public commercial locations (shop=*)", s,
                                                period="instantané actuel", last_updated=now),
                             name="OpenStreetMap — public commercial locations in Tunisia (shop=*)", url="https://www.openstreetmap.org/")
        except Exception as e:
            log(f"OSM shops: {e}")
            self.save_status(db, ProviderStatus("osm_shops", ERROR, str(e)), name="OpenStreetMap — public commercial locations in Tunisia (shop=*)")
        try:
            counts = self.ingest_open_facts(db, log)
            for label, c in counts.items():
                parts.append(f"{label}: {c}")
                total += c
            self.save_status(db, ProviderStatus("open_facts", CONNECTED if counts else ERROR,
                                                "; ".join(f"{k}: {v}" for k, v in counts.items()) + " (food capped at 1,000 most recently updated)",
                                                sum(counts.values()), period="instantané actuel", last_updated=now),
                             name="Open Beauty / Products / Food Facts — products recorded in Tunisia", url="https://world.openbeautyfacts.org/")
        except Exception as e:
            log(f"Open*Facts: {e}")
        if settings.authorized_commerce_sites:
            w = self.ingest_authorized_sites(db, log)
            self.save_status(db, ProviderStatus("authorized_sites", CONNECTED if w else ERROR,
                                                f"{len(settings.authorized_commerce_sites)} authorized domains", w, last_updated=now),
                             name="Authorized e-commerce websites (schema.org JSON-LD, robots.txt enforced)")
        else:
            self.save_status(db, ProviderStatus("authorized_sites", NOT_AVAILABLE,
                                                "No authorized e-commerce domain configured (AUTHORIZED_COMMERCE_SITES)."),
                             name="Authorized e-commerce websites (schema.org JSON-LD, robots.txt enforced)")
        st = ProviderStatus(self.key, CONNECTED if total else ERROR, "; ".join(parts), total, last_updated=now)
        self.save_status(db, st)
        return st


class SocialCommerceProvider(DataProvider):
    key = "social_commerce"
    name = "Social commerce — Facebook / Instagram / TikTok (official APIs only)"
    provider = "SocialCommerceProvider"
    url = "https://developers.facebook.com/docs/graph-api/"
    access_type = "AUTHORIZED_API"

    def health(self):
        if not settings.meta_token and not settings.tiktok_token:
            return ProviderStatus(self.key, ACCESS_REQUIRED, "AUTHORIZED API REQUIRED — no Meta/TikTok token configured")
        return ProviderStatus(self.key, CONNECTED, "Token configured")

    def ingest(self, db: Session, log) -> ProviderStatus:
        if not settings.meta_token:
            st = ProviderStatus(self.key, ACCESS_REQUIRED,
                                "AUTHORIZED API REQUIRED — set META_GRAPH_ACCESS_TOKEN + META_PAGE_IDS (Meta Content Library / Pages API). "
                                "No scraping is performed.")
            self.save_status(db, st)
            return st
        n = 0
        for pid in settings.meta_page_ids:
            try:
                page = cache.fetch(f"https://graph.facebook.com/v19.0/{pid}", params={
                    "fields": "name,link,category,location,website", "access_token": settings.meta_token}, max_age_hours=12).json()
                posts = cache.fetch(f"https://graph.facebook.com/v19.0/{pid}/posts", params={
                    "fields": "message,permalink_url,created_time,full_picture", "limit": 50,
                    "access_token": settings.meta_token}, max_age_hours=12).json().get("data", [])
            except Exception as e:
                log(f"Meta page {pid}: {e.__class__.__name__}")  # never log the token
                continue
            for p in posts:
                ext = f"facebook:{p.get('id')}"
                o = db.query(CommerceObservation).filter_by(external_id=ext).first() or CommerceObservation(external_id=ext)
                o.platform, o.page_name, o.page_url, o.post_url = "Facebook", page.get("name"), page.get("link"), p.get("permalink_url")
                o.product = (p.get("message") or "")[:500] or None
                o.image_url = p.get("full_picture")
                o.observed_at = datetime.fromisoformat(p["created_time"].replace("+0000", "+00:00")).replace(tzinfo=None) if p.get("created_time") else None
                loc = page.get("location") or {}
                o.public_business_location = loc.get("city")
                o.source_key, o.source_url, o.retrieved_at = self.key, p.get("permalink_url"), datetime.utcnow()
                db.add(o)
                n += 1
        st = ProviderStatus(self.key, CONNECTED if n else ERROR, f"{len(settings.meta_page_ids)} pages", n, last_updated=datetime.utcnow())
        self.save_status(db, st)
        return st
