"""Business verification (formalization) + activity consistency + 'Vendeurs à vérifier'.

Formalization statuses (never an accusation):
  VERIFIED / PROBABLE_MATCH / NOT_FOUND / UNKNOWN / INSTITUTIONAL_ACCESS_REQUIRED
NOT_FOUND ≠ ILLEGAL → shown as "Non retrouvée dans les données disponibles".
Seller ↔ customs activity is linked ONLY through an official registry link (Business.importer_hash);
it is never inferred from names or locations.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy.orm import Session

from ..models import (Business, BusinessMatch, CommerceObservation, CustomsImport, Product, Seller, SellerReview)
from . import embeddings
from .matching import name_similarity

FORMALIZATION_FR = {
    "VERIFIED": "Vérifiée",
    "PROBABLE_MATCH": "À confirmer",
    "NOT_FOUND": "Non retrouvée dans les données disponibles",
    "UNKNOWN": "Information indisponible",
    "INSTITUTIONAL_ACCESS_REQUIRED": "Information indisponible",
}
LEVELS = [(75, "Prioritaire"), (55, "Élevé"), (35, "Modéré"), (0, "Faible")]
WINDOWS = {"today": 1, "7d": 7, "30d": 30, "90d": 90}


def verify_businesses(db: Session, log=print) -> str:
    businesses = db.query(Business).all()
    sellers = db.query(Seller).filter(Seller.name.isnot(None)).all()
    db.query(BusinessMatch).delete()
    if not businesses:
        for s in sellers:
            db.add(BusinessMatch(seller_id=s.id, status="INSTITUTIONAL_ACCESS_REQUIRED", method="registre non connecté"))
        db.flush()
        return f"{len(sellers)} sellers: INSTITUTIONAL_ACCESS_REQUIRED (no registry data)"
    counts = Counter()
    for s in sellers:
        best, bs = None, 0.0
        for b in businesses:
            sc = name_similarity(s.name, b.name)
            if sc > bs:
                best, bs = b, sc
        status = "VERIFIED" if bs >= 0.92 else "PROBABLE_MATCH" if bs >= 0.75 else "NOT_FOUND"
        db.add(BusinessMatch(seller_id=s.id, business_id=best.id if best and status != "NOT_FOUND" else None, status=status,
                             score=round(bs, 3), method="similarité des raisons sociales"))
        counts[status] += 1
    db.flush()
    return f"business verification: {dict(counts)}"


def activity_consistency(db: Session, seller: Seller, business: Business | None) -> tuple[float | None, str]:
    """Declared activity vs observed category (semantic similarity). Returns (score 0-1, label)."""
    if not business or not business.declared_activity or not seller.category:
        return None, "Information indisponible"
    obs = [o.product for o in db.query(CommerceObservation).filter_by(page_name=seller.name).limit(30) if o.product]
    observed = f"{seller.category}: " + ", ".join(sorted(set(obs))[:6])
    try:
        e = embeddings.encode([business.declared_activity, observed])
        sim = float(e[0] @ e[1])
    except Exception:
        return None, "Information indisponible"
    label = "Cohérente" if sim >= 0.55 else "Partiellement cohérente" if sim >= 0.4 else "Écart entre activité déclarée et activité observée"
    return sim, label


def review_sellers(db: Session, window: str = "30d", emit=None, log=print) -> dict:
    """'Vendeurs à vérifier' — ranks sellers for VERIFICATION using observed digital activity,
    formalization, activity consistency and customs activity observable through official links."""
    def step(label):
        if emit:
            emit(label)

    days = WINDOWS.get(window, 30)
    now = datetime.utcnow()
    since = now - timedelta(days=days)
    step("Recherche des activités commerciales observées")
    obs_all = db.query(CommerceObservation).filter(CommerceObservation.page_name.isnot(None)).all()
    by_seller: dict[str, list] = {}
    for o in obs_all:
        by_seller.setdefault(o.page_name, []).append(o)
    sellers = db.query(Seller).filter(Seller.name.in_(list(by_seller))).all() if by_seller else []
    db.query(SellerReview).filter(SellerReview.window == window).delete()
    if not sellers:
        db.flush()
        return {"available": False, "window": window, "items": [],
                "message": "Données insuffisantes pour cette analyse : aucune activité commerciale nominative n'est "
                           "observable dans les sources connectées, et les registres des entreprises ainsi que les "
                           "déclarations douanières ne sont pas connectés. Aucun vendeur n'est signalé sans élément vérifiable."}
    step("Analyse des vendeurs")
    matches = {m.seller_id: m for m in db.query(BusinessMatch)}
    businesses = {b.id: b for b in db.query(Business)}
    products = {p.id: p for p in db.query(Product)}
    step("Vérification des informations disponibles")
    decl = db.query(CustomsImport).all()
    decl_by_imp: dict[str, list] = {}
    for d in decl:
        decl_by_imp.setdefault(d.importer_hash, []).append(d)
    step("Analyse des produits commercialisés")
    imported_hs = {d.hs_code[:4] for d in decl}
    recent_counts = {s.name: sum(1 for o in by_seller[s.name] if o.observed_at and o.observed_at >= since) for s in sellers}
    vol = np.array(list(recent_counts.values()) or [0])
    step("Croisement avec les flux douaniers disponibles")
    items = []
    for s in sellers:
        obs = by_seller[s.name]
        recent = [o for o in obs if o.observed_at and o.observed_at >= since]
        prev = [o for o in obs if o.observed_at and since - timedelta(days=days) <= o.observed_at < since]
        prods = Counter(o.product for o in obs if o.product)
        hs = Counter(o.product_id for o in obs if o.product_id)
        prices = [o.price for o in recent if o.price]
        m = matches.get(s.id)
        status = m.status if m else "INSTITUTIONAL_ACCESS_REQUIRED"
        b = businesses.get(m.business_id) if m and m.business_id else None
        cons_score, cons_label = activity_consistency(db, s, b)
        linked = decl_by_imp.get(b.importer_hash, []) if b and b.importer_hash else []
        linked_recent = [d for d in linked if d.declaration_date >= since]
        declared_value = sum(d.declared_value or 0 for d in linked_recent)
        observed_value = sum(prices) if prices else 0.0
        if linked:
            customs_txt = f"{len(linked_recent)} déclaration(s) sur la période via le lien officiel entreprise ↔ importateur ({declared_value:,.0f} TND déclarés)".replace(",", " ")
        elif b:
            customs_txt = "Aucun flux douanier rattaché à cette entreprise dans les données disponibles"
        else:
            customs_txt = "Informations douanières insuffisantes (aucun lien officiel avec un importateur)"
        # --- score components (0..1)
        c_activity = float((vol < len(recent)).mean()) if len(vol) > 1 else 0.5
        growth = (len(recent) / len(prev) - 1) if prev else (1.0 if recent else 0.0)
        c_growth = float(min(1.0, max(0.0, growth / 2)))
        c_imported = sum(v for k, v in hs.items() if k in imported_hs) / max(1, sum(hs.values()))
        c_formal = {"VERIFIED": 0.0, "PROBABLE_MATCH": 0.4, "NOT_FOUND": 1.0}.get(status, None)
        c_cons = None if cons_score is None else float(min(1.0, max(0.0, (0.6 - cons_score) / 0.3)))
        gap_ratio = None
        if observed_value and (b is not None or status == "NOT_FOUND"):
            gap_ratio = 1.0 if declared_value <= 0 else float(min(1.0, max(0.0, 1 - declared_value / (observed_value * 3))))
        comps = {"activité": (c_activity, 0.25), "hausse": (c_growth, 0.10), "produits importés": (c_imported, 0.15),
                 "formalisation": (c_formal, 0.20), "cohérence": (c_cons, 0.10), "écart": (gap_ratio, 0.20)}
        av = {k: v for k, v in comps.items() if v[0] is not None}
        wsum = sum(w for _, w in av.values())
        score = round(100 * sum(v * w for v, w in av.values()) / wsum, 1) if wsum else 0.0
        coverage = wsum / sum(w for _, w in comps.values())
        level = next(l for t, l in LEVELS if score >= t)
        reasons = []
        if c_activity >= 0.7:
            reasons.append(f"Activité commerciale numérique importante ({len(recent)} publications sur la période)")
        if growth >= 0.5 and len(recent) >= 5:
            reasons.append(f"Activité en hausse de {growth*100:.0f} % par rapport à la période précédente")
        if c_imported >= 0.6:
            reasons.append("Produits importés fortement représentés dans l'offre observée")
        if status == "NOT_FOUND":
            reasons.append("Formalisation non retrouvée dans les données disponibles")
        if c_cons is not None and c_cons >= 0.5:
            reasons.append("Écart entre l'activité déclarée et l'activité observée")
        if gap_ratio is not None and gap_ratio >= 0.6:
            reasons.append("Écart potentiel entre activité observée et informations douanières disponibles")
        items.append(dict(seller=s, score=score, level=level, status=status, customs_txt=customs_txt, cons_label=cons_label,
                          reasons=reasons[:4], facts={
                              "public_name": s.name, "platform": s.platform or "Carte publique", "products": [p for p, _ in prods.most_common(6)],
                              "main_product": prods.most_common(1)[0][0] if prods else None,
                              "main_hs": hs.most_common(1)[0][0] if hs else None,
                              "main_category": products[hs.most_common(1)[0][0]].category if hs and hs.most_common(1)[0][0] in products else s.category,
                              "observations_period": len(recent), "observations_total": len(obs),
                              "price_min": min(prices) if prices else None, "price_max": max(prices) if prices else None,
                              "location": s.governorate, "lat": s.lat, "lon": s.lon,
                              "declared_activity": b.declared_activity if b else None,
                              "declared_value_period": declared_value if linked else None,
                              "observed_offer_value": observed_value, "data_coverage": round(coverage, 2),
                              "confidence": "Élevé" if coverage >= 0.8 else "Moyen" if coverage >= 0.5 else "Faible",
                              "period": f"{since:%d/%m/%Y} → {now:%d/%m/%Y}"}))
    step("Recherche d'écarts")
    step("Évaluation des niveaux de priorité")
    items.sort(key=lambda i: -i["score"])
    for it in items:
        db.add(SellerReview(seller_id=it["seller"].id, score=it["score"], level=it["level"],
                            formalization=FORMALIZATION_FR.get(it["status"], "Information indisponible"),
                            customs_activity=it["customs_txt"], consistency=it["cons_label"], reasons=it["reasons"],
                            facts=it["facts"], window=window))
    db.flush()
    step("Génération des recommandations")
    return {"available": True, "window": window, "items": [review_dict(r) for r in
                                                           db.query(SellerReview).filter_by(window=window).order_by(SellerReview.score.desc())]}


def review_dict(r: SellerReview) -> dict:
    return {"id": r.id, "seller_id": r.seller_id, "score": r.score, "level": r.level, "formalization": r.formalization,
            "customs_activity": r.customs_activity, "consistency": r.consistency, "reasons": r.reasons, **(r.facts or {})}
