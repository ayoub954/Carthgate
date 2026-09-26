"""UN Comtrade provider — official customs trade statistics REPORTED BY TUNISIA (reporter 788).

Uses the public (keyless) preview endpoint, limited to 500 rows per call, so queries are
kept small: HS chapters x World per year, and a watch-list of consumer-goods headings x all
partners for recent years. Values are USD (primaryValue = CIF for imports).
Tunisia does not report mode of transport to Comtrade (motCode = 0 only), so this source
CANNOT be used to compute AIR/SEA/LAND shares — the app says so explicitly.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .. import cache
from ..models import Country, CustomsRecord, Product
from .base import CONNECTED, ERROR, DataProvider, ProviderStatus

API = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
AVAIL = "https://comtradeapi.un.org/public/v1/getDA/C/A/HS"

# Consumer goods frequently traded through small / cross-border e-commerce flows.
# This is a monitoring scope (which HS headings to query), not data.
WATCHLIST = {
    "8517": ("Smartphones et téléphones", "Électronique"),
    "8471": ("Ordinateurs portables et PC", "Électronique"),
    "8473": ("Accessoires informatiques", "Électronique"),
    "8528": ("Écrans et téléviseurs", "Électronique"),
    "8518": ("Écouteurs, casques et haut-parleurs", "Électronique"),
    "8525": ("Caméras", "Électronique"),
    "8504": ("Chargeurs et alimentations", "Électronique"),
    "8507": ("Batteries", "Électronique"),
    "8523": ("Cartes mémoire et clés USB", "Électronique"),
    "8544": ("Câbles", "Électronique"),
    "8543": ("Autres appareils électriques (dont cigarettes électroniques)", "Électronique"),
    "8509": ("Petit électroménager de cuisine", "Électroménager"),
    "8516": ("Sèche-cheveux et appareils électrothermiques", "Électroménager"),
    "8510": ("Rasoirs et tondeuses", "Électroménager"),
    "9504": ("Consoles et jeux vidéo", "Jouets et jeux"),
    "9503": ("Jouets", "Jouets et jeux"),
    "9506": ("Articles de sport", "Sport"),
    "3303": ("Parfums", "Cosmétiques"),
    "3304": ("Maquillage et soins de la peau", "Cosmétiques"),
    "3305": ("Produits capillaires", "Cosmétiques"),
    "3306": ("Hygiène bucco-dentaire", "Cosmétiques"),
    "3307": ("Déodorants et produits de rasage", "Cosmétiques"),
    "6109": ("T-shirts", "Textile et habillement"),
    "6110": ("Pulls et sweat-shirts", "Textile et habillement"),
    "6204": ("Vêtements pour femmes", "Textile et habillement"),
    "6203": ("Vêtements pour hommes", "Textile et habillement"),
    "6402": ("Chaussures en caoutchouc ou plastique", "Chaussures"),
    "6403": ("Chaussures en cuir", "Chaussures"),
    "6404": ("Baskets et chaussures textiles", "Chaussures"),
    "4202": ("Sacs et maroquinerie", "Maroquinerie"),
    "7117": ("Bijoux fantaisie", "Bijoux et montres"),
    "9102": ("Montres et montres connectées", "Bijoux et montres"),
    "9004": ("Lunettes de soleil", "Optique"),
    "8711": ("Motos et trottinettes électriques", "Véhicules"),
    "8712": ("Vélos", "Véhicules"),
}

# Common product names (FR/EN) per heading — vocabulary used by the semantic matcher, not data.
KEYWORDS = {
    "8517": "smartphone, téléphone portable, mobile phone, iPhone, Samsung Galaxy, router, modem",
    "8471": "laptop, ordinateur portable, PC, computer, notebook, tablet PC",
    "8473": "computer accessories, keyboard, mouse, souris, clavier, computer parts",
    "8528": "TV, télévision, écran, monitor, smart TV",
    "8518": "écouteurs, casque audio, headphones, earbuds, speaker, haut-parleur, microphone",
    "8525": "caméra, camera, webcam, dashcam, action camera",
    "8504": "chargeur, charger, power adapter, adaptateur secteur",
    "8507": "batterie, battery, power bank, accumulateur",
    "8523": "carte mémoire, clé USB, memory card, USB flash drive, SSD",
    "8544": "câble, cable USB, HDMI cable, fil électrique",
    "8543": "cigarette électronique, vape, e-cigarette, electronic device",
    "8509": "mixeur, blender, robot de cuisine, kitchen appliance",
    "8516": "sèche-cheveux, hair dryer, fer à lisser, bouilloire électrique, kettle, micro-ondes",
    "8510": "rasoir électrique, tondeuse, shaver, hair clipper, épilateur",
    "9504": "console de jeux, PlayStation, Xbox, Nintendo, video game",
    "9503": "jouet, toy, poupée, doll, puzzle, jeu pour enfants",
    "9506": "équipement sportif, sports equipment, ballon, raquette, fitness",
    "3303": "parfum, perfume, eau de toilette, eau de parfum, fragrance",
    "3304": "crème visage, maquillage, make-up, soin de la peau, skin care, crème solaire, sunscreen, after sun, lotion, moisturiser, sérum",
    "3305": "shampooing, shampoo, après-shampooing, conditioner, masque capillaire, hair mask, soin cheveux, coloration",
    "3306": "dentifrice, toothpaste, bain de bouche, mouthwash, fil dentaire",
    "3307": "déodorant, deodorant, gel douche, bain, mousse à raser, shaving foam, antiperspirant",
    "6109": "t-shirt, tee shirt, maillot de corps",
    "6110": "pull, sweater, pullover, sweat-shirt, cardigan",
    "6204": "robe, dress, jupe, tailleur femme, women's clothing",
    "6203": "pantalon, jean, costume homme, men's trousers, suit",
    "6402": "sandales, claquettes, baskets plastique, rubber shoes, flip flops",
    "6403": "chaussures en cuir, leather shoes, bottes, boots",
    "6404": "baskets, sneakers, chaussures de sport, textile shoes",
    "4202": "sac à main, handbag, sac à dos, backpack, portefeuille, wallet, valise",
    "7117": "bijoux fantaisie, costume jewellery, bracelet, collier, boucles d'oreilles",
    "9102": "montre, watch, smartwatch, montre connectée",
    "9004": "lunettes de soleil, sunglasses, lunettes",
    "8711": "moto, scooter, trottinette électrique, e-scooter, motorcycle",
    "8712": "vélo, bicycle, bicyclette",
}

CHAPTER_CATEGORY = {
    **{c: "Alimentation et agriculture" for c in [f"{i:02d}" for i in range(1, 25)]},
    **{c: "Minéraux et énergie" for c in ["25", "26", "27"]},
    **{c: "Chimie et pharmacie" for c in [f"{i:02d}" for i in range(28, 33)] + ["34", "35", "36", "37", "38"]},
    "33": "Cosmétiques", "39": "Plastiques et caoutchouc", "40": "Plastiques et caoutchouc",
    "41": "Maroquinerie", "42": "Maroquinerie", "43": "Maroquinerie",
    **{c: "Bois et papier" for c in [f"{i:02d}" for i in range(44, 50)]},
    **{c: "Textile et habillement" for c in [f"{i:02d}" for i in range(50, 64)]},
    **{c: "Chaussures" for c in ["64", "65", "66", "67"]},
    **{c: "Matériaux de construction" for c in ["68", "69", "70"]},
    "71": "Bijoux et montres", "91": "Bijoux et montres",
    **{c: "Métaux" for c in [f"{i:02d}" for i in range(72, 84)]},
    "84": "Machines et informatique", "85": "Électronique",
    **{c: "Véhicules" for c in ["86", "87", "88", "89"]},
    "90": "Optique", "92": "Autres produits manufacturés", "93": "Autres produits manufacturés",
    "94": "Mobilier", "95": "Jouets et jeux", "96": "Autres produits manufacturés", "97": "Autres produits manufacturés",
}


class ComtradeProvider(DataProvider):
    key = "un_comtrade"
    name = "UN Comtrade — Tunisia imports by HS and partner (reported by Tunisia)"
    provider = "CustomsProvider"
    url = "https://comtradeplus.un.org/"
    access_type = "PUBLIC_OFFICIAL_STATISTICS"
    license = "UN Comtrade public preview API"

    def health(self):
        try:
            cache.fetch(AVAIL, params={"reporterCode": 788}, max_age_hours=24)
            return ProviderStatus(self.key, CONNECTED, "Comtrade API reachable")
        except Exception as e:
            return ProviderStatus(self.key, ERROR, str(e))

    def available_years(self) -> list[int]:
        d = cache.fetch(AVAIL, params={"reporterCode": 788}, max_age_hours=24).json()
        return sorted({int(r["period"]) for r in d.get("data", [])})

    def _q(self, **params):
        p = {"reporterCode": 788, "flowCode": "M", "includeDesc": "true", **params}
        return cache.fetch(API, params=p, max_age_hours=24 * 30, min_interval=1.5).json()

    def ingest(self, db: Session, log) -> ProviderStatus:
        years = self.available_years()
        if not years:
            st = ProviderStatus(self.key, ERROR, "No Comtrade availability for Tunisia")
            self.save_status(db, st)
            return st
        latest = years[-1]
        recent = [y for y in years if y >= latest - 2]
        chapter_years = [y for y in years if y >= latest - 9]
        import json as _json
        ref = cache.fetch("https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json", max_age_hours=24 * 90)
        partners = {str(p["PartnerCode"]).zfill(3): (p.get("PartnerCodeIsoAlpha3"), p["PartnerDesc"].strip())
                    for p in _json.loads(ref.content.decode("utf-8-sig"))["results"]}
        db.query(CustomsRecord).filter(CustomsRecord.source_key == self.key).delete()
        now = datetime.utcnow()
        n = 0

        def add(r, dataset):
            nonlocal n
            if r.get("primaryValue") is None:
                return
            code = str(r["partnerCode"]).zfill(3)
            db.add(CustomsRecord(
                dataset=dataset, flow="M", period=str(r["period"]), period_type="A", hs_code=r["cmdCode"],
                hs_description=r.get("cmdDesc"),
                partner_iso3=(partners.get(code, (None,))[0]) if r["partnerCode"] else "WLD",
                partner_name=r.get("partnerDesc") or ("World" if r["partnerCode"] == 0 else partners.get(code, (None, f"M49 {code}"))[1]),
                value=float(r["primaryValue"]), value_unit="USD", weight_kg=r.get("netWgt"),
                quantity=r.get("qty"), quantity_unit=r.get("qtyUnitAbbr"), source_key=self.key,
                source_url=f"{API}?reporterCode=788&period={r['period']}&cmdCode={r['cmdCode']}&flowCode=M",
                retrieved_at=now))
            n += 1

        for y in chapter_years:
            try:
                for r in self._q(period=y, partnerCode=0, cmdCode="AG2").get("data", []):
                    add(r, "comtrade_chapter_world")
            except Exception as e:
                log(f"Comtrade chapters {y}: {e}")
        for y in recent:
            try:
                for r in self._q(period=y, cmdCode="TOTAL").get("data", []):
                    if r["partnerCode"] != 0:
                        add(r, "comtrade_total_partner")
            except Exception as e:
                log(f"Comtrade partners {y}: {e}")
            for hs in WATCHLIST:
                try:
                    for r in self._q(period=y, cmdCode=hs).get("data", []):
                        add(r, "comtrade_hs4_partner" if r["partnerCode"] != 0 else "comtrade_hs4_world")
                except Exception as e:
                    log(f"Comtrade {hs} {y}: {e}")
        db.flush()
        st = ProviderStatus(self.key, CONNECTED if n else ERROR,
                            f"Annual data; latest year available: {latest}. Mode of transport NOT reported by Tunisia.",
                            n, period=f"{chapter_years[0]}–{latest}", last_updated=now)
        self.save_status(db, st)
        return st


def seed_products(db: Session) -> int:
    """Monitored products = watch-list HS headings (descriptions from the HS nomenclature)."""
    from ..models import HSCode

    n = 0
    for hs, (short, cat) in WATCHLIST.items():
        h = db.get(HSCode, hs)
        p = db.get(Product, hs) or Product(id=hs, hs_code=hs)
        p.name = h.description if h else short
        p.short_name, p.category, p.chapter, p.monitored = short, cat, hs[:2], True
        p.source_key, p.source_url = "hs_nomenclature", "https://comtradeapi.un.org/files/v1/app/reference/HS.json"
        db.merge(p)
        n += 1
    db.flush()
    return n
