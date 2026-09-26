"""DOSSIERS — from analysis results to cases requiring human verification.

Every analysed subject (chapter × month, product × supplier country, product × window of declarations,
product × entry point × week…) is classified:

    COMPORTEMENT HABITUEL · À SURVEILLER · ANOMALIE À VÉRIFIER · PRIORITAIRE

Only "ANOMALIE À VÉRIFIER" and "PRIORITAIRE" subjects become dossiers, and only those can be transmitted to
Finance — after a human verification by a customs agent. Nothing is ever labelled as fraud.

Indice de priorité (0–100) = 55 % intensity of the signal (how unusual the subject is versus its own history
or its peers) + 25 % economic exposure (value concerned, percentile among comparable subjects)
+ 20 % recency, + 5 points per corroborating signal on the same product (max +15).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy.orm import Session

from ..models import (Anomaly, Case, CaseEvent, CommerceObservation, Country, CustomsImport, CustomsRecord, DataSource,
                      EntryPoint, FragmentationPattern, Product, Seller)

CLASS_FR = {"HABITUEL": "Comportement habituel", "A_SURVEILLER": "À surveiller", "A_VERIFIER": "Anomalie à vérifier",
            "PRIORITAIRE": "Prioritaire"}
STATUS_FR = {"A_ANALYSER": "À analyser", "EN_COURS": "En cours", "A_VERIFIER": "À vérifier",
             "TRANSMIS": "Transmis à Finance", "CLASSE": "Classé"}
FIN_STATUS_FR = {"TRANSMIS": "Transmis", "RECU": "Reçu", "EN_ANALYSE": "En analyse", "TRAITE": "Traité"}
KIND_FR = {"FRAGMENTATION": "Fragmentation possible", "VALEUR": "Valeur déclarée à vérifier",
           "CONCENTRATION": "Concentration inhabituelle d'un fournisseur", "HAUSSE": "Hausse inhabituelle des importations",
           "BAISSE": "Baisse inhabituelle des importations déclarées", "POINT_ENTREE": "Point d'entrée inhabituel",
           "MODE_ENTREE": "Changement de mode d'entrée", "PETITS_FLUX": "Multiplication des petits flux"}
CONF_FR = {"HIGH": "Élevé", "MEDIUM": "Moyen", "LOW": "Faible"}
CONTINENT_FR = {"Africa": "Afrique", "Europe": "Europe", "Asia": "Asie", "North America": "Amérique du Nord",
                "South America": "Amérique du Sud", "Oceania": "Océanie", "Americas": "Amérique"}
MODE_FR = {"SEA": "Mer", "AIR": "Air", "LAND": "Terre"}
SOURCE_NAMES = {"ins_trade": "INS — Commerce extérieur (publication mensuelle officielle)",
                "un_comtrade": "Nations unies — statistiques du commerce (importations de la Tunisie)",
                "open_facts": "Registres ouverts de produits (observations publiques)",
                "osm_shops": "Localisations commerciales publiques",
                "entry_points_ref": "Référentiel des points d'entrée",
                "customs_declarations": "Déclarations douanières détaillées (extrait autorisé)"}
OPEN_STATUSES = ("A_ANALYSER", "EN_COURS", "A_VERIFIER")


def _n(v, d: int = 1) -> str:
    """French number formatting: 1 234,5"""
    if v is None:
        return "—"
    return f"{v:,.{d}f}".replace(",", " ").replace(".", ",")


MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


def month_fr(period: str) -> str:
    try:
        y, m = period.split("-")[:2]
        return f"{MONTHS[int(m) - 1]} {y}"
    except (ValueError, IndexError):
        return period


def classify(score: float) -> str:
    return "PRIORITAIRE" if score >= 75 else "A_VERIFIER" if score >= 55 else "A_SURVEILLER" if score >= 35 else "HABITUEL"


def _pct_rank(values: list[float], v: float | None) -> float:
    if v is None or not values:
        return 0.0
    arr = np.array(values)
    return float((arr < v).mean() * 100)


def _recency(end: datetime | None, now: datetime) -> float:
    if not end:
        return 0.3
    days = max(0, (now - end).days)
    return float(np.clip(1 - days / 730, 0.15, 1.0))


def _source(db: Session, key: str, observations: int | None = None) -> dict:
    d = db.query(DataSource).filter_by(key=key).first()
    return {"name": SOURCE_NAMES.get(key, key), "url": d.url if d else None, "period": d.period if d else None,
            "updated": d.last_updated.strftime("%d/%m/%Y") if d and d.last_updated else None,
            "observations": observations}


class _Ctx:
    """Shared lookups for one build."""

    def __init__(self, db: Session):
        self.db = db
        self.now = datetime.utcnow()
        self.products = {p.id: p for p in db.query(Product).filter(Product.monitored.is_(True))}
        self.chapters = defaultdict(list)
        for p in self.products.values():
            self.chapters[p.chapter].append(p)
        self.countries = {c.iso3: c for c in db.query(Country)}
        self.eps = {e.entry_point_id: e for e in db.query(EntryPoint)}
        zones = defaultdict(Counter)
        for s in db.query(Seller.category, Seller.governorate):
            if s[0] and s[1]:
                zones[s[0]][s[1]] += 1
        self.zones = zones
        obs = defaultdict(list)
        for o in db.query(CommerceObservation).filter(CommerceObservation.product_id.isnot(None)):
            obs[o.product_id].append(o)
        self.obs = obs

    def country(self, iso: str | None, fallback: str | None = None) -> tuple[str | None, str | None]:
        c = self.countries.get(iso) if iso else None
        if not c:
            return fallback, None
        return c.name_fr or c.name_en, CONTINENT_FR.get(c.continent, c.continent)

    def zone(self, category: str | None) -> tuple[str | None, dict | None]:
        cnt = self.zones.get(category)
        if not cnt:
            return None, None
        g, n = cnt.most_common(1)[0]
        tot = sum(cnt.values())
        return g, {"zone": g, "shops": n, "share": n / tot, "relation": "CORRÉLATION STATISTIQUE",
                   "detail": f"{n} commerce(s) de la catégorie sur {tot} référencés publiquement ({n / tot * 100:.0f} %)"}

    def online(self, pid: str | None) -> dict:
        lst = self.obs.get(pid, []) if pid else []
        if not lst:
            return {"available": False, "count": 0, "message": "Aucune observation commerciale publique rattachée à ce produit."}
        lst = sorted(lst, key=lambda o: o.observed_at or datetime.min, reverse=True)
        prices = [o.price for o in lst if o.price]
        return {"available": True, "count": len(lst), "platforms": dict(Counter(o.platform for o in lst)),
                "brands": dict(Counter(o.brand for o in lst if o.brand).most_common(5)),
                "price_min": min(prices) if prices else None, "price_max": max(prices) if prices else None,
                "note": "Une observation n'est pas une vente.",
                "items": [{"product": o.product, "brand": o.brand, "platform": o.platform, "image_url": o.image_url,
                           "link": o.post_url or o.page_url, "date": o.observed_at.date().isoformat() if o.observed_at else None,
                           "price": o.price, "location": o.public_business_location} for o in lst[:8]]}


def _score(signal: float, exposure: float, recency: float, corroboration: int) -> float:
    return round(min(100.0, 0.55 * signal + 0.25 * exposure + 20 * recency + min(15, 5 * corroboration)), 1)


# ------------------------------------------------------------------------------------------------ subjects
def _chapter_subjects(ctx: _Ctx) -> list[dict]:
    db = ctx.db
    rows = db.query(Anomaly).filter(Anomaly.subject_type == "HS_CHAPTER_MONTH", Anomaly.hs_code.in_(list(ctx.chapters))).all()
    if not rows:
        return []
    latest = max(a.period for a in rows)
    ly, lm = map(int, latest.split("-"))
    cutoff = f"{ly - 1}-{lm:02d}"
    values = [(a.features or {}).get("value_tnd") or 0 for a in rows]
    out = []
    for a in rows:
        if a.period <= cutoff:  # last 12 published months only
            continue
        f = a.features or {}
        signal = a.score if a.is_anomaly else min(a.score, 50.0)
        y, m = map(int, a.period.split("-"))
        end = datetime(y, m, 28)
        prods = ctx.chapters[a.hs_code]
        up = (f.get("yoy") or 0) > 0 or (f.get("vs_trailing_3m") or 0) > 0
        out.append({"type": "chapter", "anomaly": a, "signal": signal, "is_anomaly": a.is_anomaly,
                    "exposure": _pct_rank(values, f.get("value_tnd")), "end": end, "products": prods,
                    "kind": "HAUSSE" if up else "BAISSE", "key": f"chap:{a.hs_code}:{a.period}"})
    return out


def _unit_value_subjects(ctx: _Ctx) -> list[dict]:
    rows = ctx.db.query(Anomaly).filter(Anomaly.subject_type == "PARTNER_HS_UNIT_VALUE", Anomaly.hs_code.in_(list(ctx.products))).all()
    values = [(a.features or {}).get("value_usd") or 0 for a in rows]
    out = []
    for a in rows:
        f = a.features or {}
        ratio = f.get("uv_ratio") or 1
        kind = "VALEUR" if ratio < 0.67 or ratio > 1.5 else "CONCENTRATION"
        signal = a.score if a.is_anomaly else min(a.score, 50.0)
        if kind == "CONCENTRATION":
            signal *= 0.6  # supplier concentration alone is a weaker signal than a value gap
        out.append({"type": "unit_value", "anomaly": a, "signal": signal, "is_anomaly": a.is_anomaly,
                    "exposure": _pct_rank(values, f.get("value_usd")), "end": datetime(int(a.period), 12, 31),
                    "products": [ctx.products[a.hs_code]], "kind": kind, "key": f"uv:{a.hs_code}:{f.get('partner_iso3')}:{a.period}"})
    return out


def _declaration_subjects(ctx: _Ctx) -> list[dict]:
    db = ctx.db
    out = []
    frag = db.query(FragmentationPattern).all()
    fvals = [(f.features or {}).get("cumulative_value") or 0 for f in frag]
    for f in frag:
        p = ctx.products.get(f.hs_code)
        if not p:
            continue
        end = datetime.fromisoformat(f.period.split(" → ")[1]) if f.period and " → " in f.period else None
        kind = "FRAGMENTATION" if f.status.startswith("POSSIBLE") else "PETITS_FLUX"
        out.append({"type": "fragmentation", "pattern": f, "signal": f.score, "is_anomaly": f.status != "NORMAL",
                    "exposure": _pct_rank(fvals, (f.features or {}).get("cumulative_value")), "end": end, "products": [p],
                    "kind": kind, "key": f"frag:{f.hs_code}:{f.window_days}:{end.date() if end else ''}"})
    for a in db.query(Anomaly).filter(Anomaly.subject_type.in_(["ENTRY", "DECLARED_VALUE", "MODE_SHIFT"])):
        p = ctx.products.get(a.hs_code)
        if not p:
            continue
        kind = {"ENTRY": "POINT_ENTREE", "DECLARED_VALUE": "VALEUR", "MODE_SHIFT": "MODE_ENTREE"}[a.subject_type]
        try:
            end = datetime.fromisoformat((a.period or "").split(" → ")[-1])
        except ValueError:
            end = None
        out.append({"type": "declaration_anomaly", "anomaly": a, "signal": a.score if a.is_anomaly else min(a.score, 50.0),
                    "is_anomaly": a.is_anomaly, "exposure": 50.0, "end": end, "products": [p], "kind": kind,
                    "key": f"decl:{a.subject_type}:{a.subject_id}"})
    return out


# ------------------------------------------------------------------------------------------------ details per subject
def _decl_rows(db: Session, hs4: str, start: datetime | None, end: datetime | None) -> list[CustomsImport]:
    q = db.query(CustomsImport).filter(CustomsImport.hs_code.like(f"{hs4}%"))
    if start:
        q = q.filter(CustomsImport.declaration_date > start)
    if end:
        q = q.filter(CustomsImport.declaration_date <= end + timedelta(days=1))
    return q.order_by(CustomsImport.declaration_date).all()


def _decl_details(ctx: _Ctx, rows: list[CustomsImport]) -> dict:
    ops = [{"date": r.declaration_date.date().isoformat(), "value": r.declared_value, "quantity": r.quantity,
            "unit": r.currency or "TND", "country": ctx.country(r.provenance_iso3 or r.origin_iso3, r.provenance_iso3)[0],
            "entry_point": ctx.eps[r.entry_point_id].official_name if r.entry_point_id in ctx.eps else None,
            "mode": MODE_FR.get(r.transport_mode), "importer": (r.importer_hash or "")[:8] or None,
            "zone": r.destination_governorate} for r in rows[:300]]
    eps = Counter(r.entry_point_id for r in rows if r.entry_point_id)
    tot = sum(eps.values())
    entry_points = [{"id": k, "name": ctx.eps[k].official_name if k in ctx.eps else k,
                     "type": ctx.eps[k].entry_type if k in ctx.eps else None, "operations": n, "share": n / tot}
                    for k, n in eps.most_common(5)]
    modes = Counter(r.transport_mode for r in rows if r.transport_mode)
    origins = Counter(r.provenance_iso3 or r.origin_iso3 for r in rows if (r.provenance_iso3 or r.origin_iso3))
    govs = Counter(r.destination_governorate for r in rows if r.destination_governorate)
    return {"operations": ops, "entry_points": entry_points, "mode": modes.most_common(1)[0][0] if modes else None,
            "origin": origins.most_common(1)[0][0] if origins else None, "zone": govs.most_common(1)[0][0] if govs else None,
            "value": float(sum(r.declared_value or 0 for r in rows)), "importers": len({r.importer_hash for r in rows if r.importer_hash})}


def _materialize(ctx: _Ctx, s: dict, score: float, corroboration: list[str]) -> dict:
    db = ctx.db
    p = s["products"][0]
    names = ", ".join(x.short_name for x in s["products"][:4])
    base = {"product_id": p.id if len(s["products"]) == 1 else None, "product": p.short_name if len(s["products"]) == 1 else names,
            "category": p.category, "kind": s["kind"], "period_end": s["end"], "priority_score": score,
            "classification": classify(score)}
    zone, zone_ev = ctx.zone(p.category)
    indicators: list[dict] = []
    sources: list[dict] = []
    info_used: list[str] = []
    if s["type"] == "chapter":
        a = s["anomaly"]
        f = a.features or {}
        hist = ctx.db.query(CustomsRecord).filter(CustomsRecord.dataset == "ins_chapter_month", CustomsRecord.flow == "M",
                                                  CustomsRecord.hs_code == a.hs_code, CustomsRecord.period <= a.period
                                                  ).order_by(CustomsRecord.period.desc()).limit(13).all()
        ops = [{"date": r.period, "value": r.value, "quantity": r.weight_kg, "quantity_unit": "kg", "unit": "TND",
                "label": f"Importations du chapitre {a.hs_code} — {r.period}"} for r in reversed(hist)]
        yoy, v3 = f.get("yoy"), f.get("vs_trailing_3m")
        baseline = (f.get("value_tnd") or 0) / (1 + v3) if v3 not in (None, -1) else None
        direction = "hausse" if s["kind"] == "HAUSSE" else "baisse"
        motif = f"{'Hausse' if direction == 'hausse' else 'Baisse'} inhabituelle des importations — chapitre {a.hs_code} ({f.get('description', '')})"
        expl = (f"Selon la publication officielle de l'INS, les importations du chapitre {a.hs_code} ({f.get('description', '').lower()}) "
                f"atteignent {_n((f.get('value_tnd') or 0) / 1e6)} millions de dinars en {month_fr(a.period)}"
                + (f", soit {yoy * 100:+.0f} % par rapport au même mois de l'année précédente" if yoy is not None else "")
                + (f" et {v3 * 100:+.0f} % par rapport à la moyenne des trois mois précédents" if v3 is not None else "")
                + f". Ce niveau sort de la plage habituellement observée pour ce chapitre, qui couvre notamment : {names}. "
                  + ("Une hausse rapide peut traduire l'arrivée de volumes importants à répartir ensuite sur le marché, "
                     "éventuellement sous forme de nombreux petits flux." if direction == "hausse" else
                     "Une baisse brutale des importations déclarées, alors que ces produits restent présents sur le marché, "
                     "peut signaler un déplacement des flux vers des canaux moins visibles (petits envois, autres points d'entrée).")
                + " Il s'agit d'un signal statistique à vérifier, pas d'une conclusion.")
        indicators += [{"label": r, "source": "INS", "relation": "OBSERVÉ"} for r in (a.reasons or [])]
        sources.append(_source(db, "ins_trade", len(hist)))
        info_used += ["Valeurs mensuelles importées par chapitre", "Poids importés", "Comparaison avec le même mois de l'année précédente",
                      "Comparaison avec les trois mois précédents"]
        base.update(period=month_fr(a.period), operations=ops, entry_points=[], value_concerned=f.get("value_tnd"),
                    gap_to_verify=abs((f.get("value_tnd") or 0) - baseline) if baseline else None, amount_unit="TND",
                    confidence=CONF_FR.get(a.confidence, "Moyen"), motif=motif, explanation=expl)
    elif s["type"] == "unit_value":
        a = s["anomaly"]
        f = a.features or {}
        cname, cont = ctx.country(f.get("partner_iso3"), f.get("partner"))
        rows = ctx.db.query(CustomsRecord).filter(CustomsRecord.dataset == "comtrade_hs4_partner", CustomsRecord.hs_code == p.id,
                                                  CustomsRecord.partner_iso3 == f.get("partner_iso3")).order_by(CustomsRecord.period).all()
        ops = [{"date": r.period, "value": r.value, "quantity": r.weight_kg, "quantity_unit": "kg", "unit": "USD",
                "label": f"{p.short_name} — importations annuelles depuis {cname}"} for r in rows]
        ratio, uv, med = f.get("uv_ratio") or 1, f.get("unit_value_usd_kg"), f.get("median_unit_value_usd_kg")
        gap = max(0.0, (med - uv) * f.get("net_weight_kg", 0)) if uv is not None and med and uv < med else None
        if s["kind"] == "VALEUR" and ratio < 1:
            motif = f"Valeur unitaire basse — {p.short_name} en provenance de {cname}"
            core = (f"la valeur unitaire déclarée ({_n(uv)} USD/kg) représente {_n(ratio, 2)} fois la médiane des autres pays fournisseurs "
                    f"({_n(med)} USD/kg). Si ce flux avait été valorisé au niveau médian, sa valeur aurait été supérieure d'environ "
                    f"{_n((gap or 0) / 1e6, 2)} million(s) de dollars.")
        elif s["kind"] == "VALEUR":
            motif = f"Valeur unitaire élevée — {p.short_name} en provenance de {cname}"
            core = (f"la valeur unitaire déclarée ({_n(uv)} USD/kg) représente {_n(ratio)} fois la médiane des autres pays fournisseurs "
                    f"({_n(med)} USD/kg).")
        else:
            motif = f"Concentration inhabituelle sur un fournisseur — {p.short_name} ({cname})"
            core = f"ce pays concentre {f.get('share', 0) * 100:.0f} % des importations du produit, un niveau inhabituel parmi les flux analysés."
        expl = (f"Selon les statistiques du commerce publiées par les Nations unies pour {a.period}, les importations tunisiennes de "
                f"{p.short_name.lower()} en provenance de {cname} s'élèvent à {_n((f.get('value_usd') or 0) / 1e6)} millions de dollars "
                f"({f.get('share', 0) * 100:.0f} % des importations du produit) ; " + core +
                " Un tel écart peut avoir des causes légitimes (gamme, qualité, conditionnement) ; il justifie une vérification "
                "des valeurs déclarées, pas une conclusion.")
        indicators += [{"label": r, "source": "Nations unies", "relation": "OBSERVÉ"} for r in (a.reasons or [])]
        sources.append(_source(db, "un_comtrade", len(rows)))
        info_used += ["Valeur importée par produit et pays", "Poids net", "Valeur unitaire comparée aux autres pays fournisseurs"]
        base.update(period=a.period, operations=ops, entry_points=[], country=cname, country_iso3=f.get("partner_iso3"), continent=cont,
                    value_concerned=f.get("value_usd"), gap_to_verify=gap, amount_unit="USD", confidence=CONF_FR.get(a.confidence, "Moyen"),
                    motif=motif, explanation=expl)
    else:
        if s["type"] == "fragmentation":
            fp = s["pattern"]
            start, end = [datetime.fromisoformat(x) for x in fp.period.split(" → ")]
            rows = _decl_rows(db, fp.hs_code, start, end)
            ff = fp.features or {}
            reasons = ff.get("reasons", [])
            motif = f"{KIND_FR[s['kind']]} — {p.short_name} ({fp.window_days} jours)"
            expl = (f"Selon les déclarations disponibles, {ff.get('declarations', len(rows))} petites opérations concernant {p.short_name.lower()} "
                    f"ont été enregistrées entre le {start:%d/%m/%Y} et le {end:%d/%m/%Y}"
                    + (f", par {ff.get('unique_importers')} importateurs différents" if ff.get("unique_importers") else "")
                    + (f" et via {ff.get('entry_points')} points d'entrée" if ff.get("entry_points", 0) >= 2 else "")
                    + ". Leur fréquence est supérieure au comportement habituellement observé dans les données disponibles"
                    + (f" : {'; '.join(r[0].lower() + r[1:] for r in reasons[:3])}" if reasons else "")
                    + ". Prises ensemble, ces opérations peuvent correspondre à une activité commerciale plus importante fragmentée "
                      "en petits flux. Une vérification humaine est nécessaire.")
            indicators += [{"label": r, "source": "Déclarations", "relation": "OBSERVÉ"} for r in reasons]
            period = fp.period.replace(" → ", " au ")
        else:
            a = s["anomaly"]
            start = s["end"] - timedelta(days=30) if s["end"] else None
            rows = _decl_rows(db, a.hs_code, start, s["end"])
            if a.subject_type == "ENTRY":
                ep = (a.features or {}).get("entry_point_id")
                rows = [r for r in rows if r.entry_point_id == ep] or rows
            motif = f"{KIND_FR[s['kind']]} — {p.short_name}"
            expl = (f"Selon les déclarations disponibles, {p.short_name.lower()} présente un comportement inhabituel : "
                    + "; ".join((r[0].lower() + r[1:]) for r in (a.reasons or ["écart par rapport à l'historique"]))
                    + ". Ce signal mérite une vérification humaine.")
            indicators += [{"label": r, "source": "Déclarations", "relation": "OBSERVÉ"} for r in (a.reasons or [])]
            period = a.period
        d = _decl_details(ctx, rows)
        cname, cont = ctx.country(d["origin"])
        sources.append(_source(db, "customs_declarations", len(rows)))
        info_used += ["Dates des déclarations", "Codes produits", "Valeurs et quantités déclarées", "Points d'entrée", "Modes de transport",
                      "Importateurs (identifiants anonymisés)"]
        if d["zone"]:
            zone, zone_ev = d["zone"], {"zone": d["zone"], "relation": "OBSERVÉ", "detail": "Gouvernorat de destination déclaré"}
        base.update(period=period, operations=d["operations"], entry_points=d["entry_points"], entry_mode=d["mode"],
                    country=cname, country_iso3=d["origin"], continent=cont, value_concerned=d["value"], gap_to_verify=None,
                    amount_unit="TND", confidence="Moyen", motif=motif, explanation=expl)
    online = ctx.online(p.id if len(s["products"]) == 1 else None)
    if online["available"]:
        sources.append(_source(db, "open_facts", online["count"]))
        indicators.append({"label": f"{online['count']} observation(s) commerciale(s) publique(s) du produit", "source": "Commerce observé",
                           "relation": "OBSERVÉ", "detail": "Une observation n'est pas une vente."})
    if zone_ev:
        sources.append(_source(db, "osm_shops"))
        indicators.append({"label": f"Zone commerciale la plus représentée : {zone}", "source": "Localisations commerciales publiques",
                           "relation": zone_ev["relation"], "detail": zone_ev["detail"]})
    for c in corroboration:
        indicators.append({"label": c, "source": "Analyse croisée", "relation": "CORRÉLATION STATISTIQUE"})
    base.update(geographic_zone=zone, online_observations=online, risk_indicators=indicators,
                evidence={"sources": sources, "information_used": info_used, "zone": zone_ev,
                          "method": "Indice de priorité = intensité du signal (55 %) + exposition économique (25 %) + actualité (20 %) "
                                    "+ signaux concordants sur le même produit. Un indice élevé signifie une priorité de vérification humaine.",
                          "computed_at": ctx.now.strftime("%d/%m/%Y %H:%M")})
    return base


# ------------------------------------------------------------------------------------------------ build
def _scored(ctx: _Ctx):
    """Yield (subject, score, classification, corroborating signals) — single scoring path for build and summary."""
    subjects = _chapter_subjects(ctx) + _unit_value_subjects(ctx) + _declaration_subjects(ctx)
    by_product = defaultdict(set)
    for s in subjects:
        if s["is_anomaly"]:
            for p in s["products"]:
                by_product[p.id].add(s["kind"])
    for s in subjects:
        corro = []
        if len(s["products"]) == 1:
            others = by_product[s["products"][0].id] - {s["kind"]}
            corro = [f"Autre signal sur le même produit : {KIND_FR[k].lower()}" for k in sorted(others)]
        score = _score(s["signal"], s["exposure"], _recency(s["end"], ctx.now), len(corro))
        if not s["is_anomaly"]:
            score = min(score, 54.0)  # a subject without a detected anomaly is never proposed for transmission
        yield s, score, classify(score), corro


def build_cases(db: Session, log=print) -> dict:
    ctx = _Ctx(db)
    summary = Counter()
    created = updated = 0
    existing = {c.signature: c for c in db.query(Case)}
    for s, score, cls, corro in _scored(ctx):
        summary[cls] += 1
        if cls not in ("A_VERIFIER", "PRIORITAIRE"):
            continue
        data = _materialize(ctx, s, score, corro)
        c = existing.get(s["key"])
        if c is None:
            c = Case(signature=s["key"], case_ref=f"TMP-{s['key']}"[:32], status="A_ANALYSER", created_by="Analyse IA", **data)
            db.add(c)
            db.flush()
            c.case_ref = f"DT-{ctx.now.year}-{c.id:05d}"
            db.add(CaseEvent(case_id=c.id, actor="Analyse IA", institution="DOUANE", action="Dossier créé",
                             detail=f"{CLASS_FR[cls]} — indice de priorité {score:.0f}/100", visibility="DOUANE"))
            created += 1
        elif c.status == "A_ANALYSER":
            for k, v in data.items():
                setattr(c, k, v)
            c.updated_at = ctx.now
            updated += 1
    db.flush()
    total = sum(summary.values())
    log(f"cases: {total} subjects classified, {created} created, {updated} refreshed")
    return {"subjects": total, "classification": {CLASS_FR[k]: summary.get(k, 0) for k in CLASS_FR},
            "created": created, "updated": updated}


def classification_summary(db: Session) -> dict:
    """Classification of every analysed subject (read only, same scoring as the dossiers)."""
    summary = Counter(cls for _, _, cls, _ in _scored(_Ctx(db)))
    return {CLASS_FR[k]: summary.get(k, 0) for k in CLASS_FR}


# ------------------------------------------------------------------------------------------------ views
def case_row(c: Case) -> dict:
    eps = c.entry_points or []
    return {"id": c.id, "ref": c.case_ref, "product": c.product, "product_id": c.product_id, "category": c.category,
            "zone": c.geographic_zone, "entry_point": eps[0]["name"] if eps else None, "date": c.period,
            "created_at": c.created_at.isoformat() if c.created_at else None, "motif": c.motif, "kind": KIND_FR.get(c.kind, c.kind),
            "priority_score": c.priority_score, "classification": CLASS_FR.get(c.classification), "status": c.status,
            "status_label": STATUS_FR.get(c.status, c.status), "finance_status": FIN_STATUS_FR.get(c.finance_status) if c.finance_status else None,
            "country": c.country, "continent": c.continent, "value_concerned": c.value_concerned, "gap_to_verify": c.gap_to_verify,
            "amount_unit": c.amount_unit}


def case_full(db: Session, c: Case, visibility: str = "DOUANE") -> dict:
    events = db.query(CaseEvent).filter(CaseEvent.case_id == c.id, CaseEvent.visibility.in_(["ALL", visibility])).order_by(CaseEvent.at).all()
    return {**case_row(c), "period": c.period, "operations": c.operations or [], "entry_points": c.entry_points or [],
            "entry_mode": MODE_FR.get(c.entry_mode) if c.entry_mode else None, "online": c.online_observations or {},
            "indicators": c.risk_indicators or [], "confidence": c.confidence, "explanation": c.explanation,
            "evidence": c.evidence or {}, "country_iso3": c.country_iso3,
            "transferable": c.status in ("EN_COURS", "A_VERIFIER") and c.classification in ("A_VERIFIER", "PRIORITAIRE"),
            "history": [{"at": e.at.isoformat(), "actor": e.actor, "institution": e.institution, "action": e.action, "detail": e.detail}
                        for e in events]}
