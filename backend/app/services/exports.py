"""Exports (CSV / XLSX / JSON) — every row carries source_name, source_url, period, retrieved_at."""
from __future__ import annotations

import io
import json
from datetime import datetime

import pandas as pd
from sqlalchemy.orm import Session

from ..models import (Anomaly, CommerceObservation, CustomsRecord, DataSource, EconomicIndicator, EntryPoint, Forecast,
                      Recommendation, RiskScore, Seller)

DATASETS = {
    "customs_records": "Official aggregated trade statistics (INS, UN Comtrade)",
    "economic_indicators": "Economic indicators (INS, World Bank)",
    "observations": "Product observations (Open*Facts / authorized sources)",
    "sellers": "Public commercial locations (OpenStreetMap)",
    "entry_points": "Customs entry points referential",
    "anomalies": "Isolation Forest anomalies",
    "risk_scores": "Dynamic risk scores",
    "recommendations": "AI Customs Advisor recommendations",
    "forecasts": "Economic forecasts",
}


def _src_names(db: Session) -> dict:
    from .queries import SOURCE_FR, SOURCE_INFO
    d = {k: v[0] for k, v in SOURCE_INFO.items() if v}
    d.update(SOURCE_FR)
    return d


def dataset_frame(db: Session, name: str, filters: dict | None = None) -> pd.DataFrame:
    f = filters or {}
    names = _src_names(db)
    if name == "customs_records":
        q = db.query(CustomsRecord)
        if f.get("dataset"):
            q = q.filter(CustomsRecord.dataset == f["dataset"])
        if f.get("hs"):
            q = q.filter(CustomsRecord.hs_code.like(f"{f['hs']}%"))
        if f.get("country"):
            q = q.filter((CustomsRecord.partner_iso3 == f["country"]) | (CustomsRecord.partner_name.ilike(f"%{f['country']}%")))
        if f.get("period_from"):
            q = q.filter(CustomsRecord.period >= f["period_from"])
        if f.get("period_to"):
            q = q.filter(CustomsRecord.period <= f["period_to"])
        rows = [{"dataset": r.dataset, "flow": r.flow, "period": r.period, "hs_code": r.hs_code, "hs_description": r.hs_description,
                 "partner_iso3": r.partner_iso3, "partner": r.partner_name, "value": r.value, "value_unit": r.value_unit,
                 "net_weight_kg": r.weight_kg, "quantity": r.quantity, "quantity_unit": r.quantity_unit,
                 "source_name": names.get(r.source_key, r.source_key), "source_url": r.source_url,
                 "retrieved_at": r.retrieved_at} for r in q.limit(int(f.get("limit", 200000)))]
    elif name == "economic_indicators":
        rows = [{"indicator": e.indicator, "label": e.label, "period": e.period, "frequency": e.frequency, "value": e.value,
                 "unit": e.unit, "source_name": names.get(e.source_key, e.source_key), "source_url": e.source_url,
                 "retrieved_at": e.retrieved_at} for e in db.query(EconomicIndicator)]
    elif name == "observations":
        q = db.query(CommerceObservation)
        if f.get("hs"):
            q = q.filter(CommerceObservation.product_id == f["hs"])
        rows = [{"platform": o.platform, "page_name": o.page_name, "page_url": o.page_url, "post_url": o.post_url,
                 "product": o.product, "brand": o.brand, "category": o.category, "image_url": o.image_url, "price": o.price,
                 "currency": o.currency, "date": o.observed_at, "public_business_location": o.public_business_location,
                 "declared_manufacturing_place": o.manufacturing_place, "matched_hs": o.product_id, "match_score": o.match_score,
                 "period": o.observed_at.date().isoformat() if o.observed_at else None,
                 "source_name": names.get(o.source_key, o.source_key), "source_url": o.source_url, "retrieved_at": o.retrieved_at}
                for o in q]
    elif name == "sellers":
        q = db.query(Seller)
        if f.get("governorate"):
            q = q.filter(Seller.governorate == f["governorate"])
        if f.get("category"):
            q = q.filter(Seller.category == f["category"])
        rows = [{"name": s.name, "shop_type": s.shop_type, "category": s.category, "governorate": s.governorate, "city": s.city,
                 "lat": s.lat, "lon": s.lon, "website": s.website, "facebook": s.facebook, "instagram": s.instagram,
                 "tiktok": s.tiktok, "period": "current snapshot", "source_name": "OpenStreetMap (ODbL)", "source_url": s.source_url,
                 "retrieved_at": s.retrieved_at} for s in q]
    elif name == "entry_points":
        rows = [{"entry_point_id": e.entry_point_id, "official_name": e.official_name, "entry_type": e.entry_type,
                 "governorate": e.governorate, "latitude": e.latitude, "longitude": e.longitude, "name_source": e.name_source,
                 "period": "current", "source_name": "Entry points referential", "source_url": e.source_url,
                 "retrieved_at": e.retrieved_at} for e in db.query(EntryPoint)]
    elif name == "anomalies":
        rows = [{"type": a.subject_type, "subject": a.subject_id, "hs_code": a.hs_code, "period": a.period, "score": a.score,
                 "is_anomaly": a.is_anomaly, "reasons": "; ".join(a.reasons or []), "model": a.model, "data_coverage": a.data_coverage,
                 "confidence": a.confidence, "source_name": names.get(a.source_key, a.source_key), "source_url": None,
                 "retrieved_at": a.created_at} for a in db.query(Anomaly).filter(Anomaly.is_anomaly.is_(True))]
    elif name == "risk_scores":
        rows = [{"product_id": r.product_id, "score": r.score, "level": r.level, "data_coverage": r.data_coverage,
                 "confidence": r.confidence, "period": r.period,
                 **{f"factor_{k}": v.get("value") for k, v in (r.factors or {}).items()},
                 "source_name": "DIWANA risk engine (INS, UN Comtrade, OSM, Open*Facts)", "source_url": None,
                 "retrieved_at": r.created_at} for r in db.query(RiskScore)]
    elif name == "recommendations":
        rows = [{"rank": r.rank, "action": r.action, "what": r.what, "where": r.where, "why": " | ".join(r.why),
                 "priority_score": r.priority_score, "confidence": r.confidence, "data_coverage": r.data_coverage,
                 "period": r.period, "source_name": ", ".join(r.sources), "source_url": None, "retrieved_at": r.created_at}
                for r in db.query(Recommendation).order_by(Recommendation.rank)]
    elif name == "forecasts":
        rows = [{"indicator": f.indicator, "model": f.model, "period": f.period, "predicted": f.predicted, "lower": f.lower,
                 "upper": f.upper, "unit": f.unit, "source_name": "INS monthly series (model output)",
                 "source_url": "https://www.ins.tn/publication", "retrieved_at": f.created_at} for f in db.query(Forecast)]
    else:
        raise ValueError(f"unknown dataset {name}")
    return _frenchify(db, name, pd.DataFrame(rows))


COLS_FR = {
    "dataset": "jeu de données", "flow": "flux", "period": "période", "hs_code": "position tarifaire", "hs_description": "produit",
    "partner_iso3": "code pays", "partner": "pays", "value": "valeur", "value_unit": "unité de valeur", "net_weight_kg": "poids net (kg)",
    "quantity": "quantité", "quantity_unit": "unité de quantité", "source_name": "source", "source_url": "lien source",
    "retrieved_at": "date de récupération", "indicator": "indicateur", "label": "libellé", "frequency": "fréquence", "unit": "unité",
    "platform": "plateforme", "page_name": "page / vendeur", "page_url": "lien page", "post_url": "lien publication", "product": "produit",
    "brand": "marque", "category": "catégorie", "image_url": "image", "price": "prix", "currency": "devise", "date": "date",
    "public_business_location": "localisation commerciale", "declared_manufacturing_place": "lieu de fabrication déclaré",
    "matched_hs": "position rapprochée", "match_score": "similarité", "name": "nom", "shop_type": "type de commerce",
    "governorate": "gouvernorat", "city": "ville", "lat": "latitude", "lon": "longitude", "website": "site web",
    "facebook": "facebook", "instagram": "instagram", "tiktok": "tiktok", "entry_point_id": "identifiant", "official_name": "nom officiel",
    "entry_type": "type", "latitude": "latitude", "longitude": "longitude", "name_source": "origine du nom", "type": "type d'analyse",
    "subject": "objet", "score": "score", "is_anomaly": "inhabituel", "reasons": "pourquoi", "model": "méthode",
    "data_coverage": "couverture des données", "confidence": "confiance", "product_id": "position tarifaire", "level": "niveau",
    "rank": "rang", "action": "action", "what": "quoi", "where": "où", "why": "pourquoi", "priority_score": "indice de priorité",
    "predicted": "projection", "lower": "borne basse", "upper": "borne haute", "data_mode": "nature des données",
}
DATASET_FR = {"ins_chapter_month": "INS — mensuel par chapitre", "ins_country_month": "INS — mensuel par pays",
              "ins_country_month_agg": "INS — mensuel par zone", "comtrade_hs4_partner": "Annuel par produit et pays",
              "comtrade_hs4_world": "Annuel par produit", "comtrade_chapter_world": "Annuel par chapitre",
              "comtrade_total_partner": "Annuel par pays"}
TYPE_FR = {"AIRPORT": "Aéroport", "SEAPORT": "Port", "LAND_BORDER": "Frontière terrestre", "HS_CHAPTER_MONTH": "Importations mensuelles",
           "PARTNER_HS_UNIT_VALUE": "Valeurs déclarées par pays", "ENTRY": "Points d'entrée", "DECLARED_VALUE": "Valeurs déclarées",
           "MODE_SHIFT": "Mode d'entrée"}


def _frenchify(db: Session, name: str, df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    from ..models import Country, Product
    from .queries import SOURCE_INFO
    if name == "customs_records":
        fr = {p.id: p.short_name for p in db.query(Product)}
        fr.update({hs: d for hs, d in db.query(CustomsRecord.hs_code, CustomsRecord.hs_description).filter(
            CustomsRecord.dataset == "ins_chapter_month").distinct() if d})
        ctry = {c.iso3: c.name_fr or c.name_en for c in db.query(Country)}
        df["hs_description"] = [fr.get(h, d) for h, d in zip(df["hs_code"], df["hs_description"])]
        df["partner"] = ["Monde" if i == "WLD" else ctry.get(i, p) if i else p for i, p in zip(df["partner_iso3"], df["partner"])]
        df["dataset"] = df["dataset"].map(lambda d: DATASET_FR.get(d, d))
        df["flow"] = df["flow"].map({"M": "Importation", "X": "Exportation"})
    for col in ("entry_type", "type"):
        if col in df:
            df[col] = df[col].map(lambda v: TYPE_FR.get(v, v))
    if "source_name" in df:
        names = {v[0].lower(): v[0] for v in SOURCE_INFO.values() if v}
        df["source_name"] = df["source_name"].map(lambda v: v if not isinstance(v, str) else v.replace("UN Comtrade", "Nations unies").replace("OpenStreetMap (ODbL)", "Localisations commerciales publiques"))
    df = df.replace({"N/A": None, "n/a": None})
    df = df.drop(columns=[c for c in ("model",) if c in df])  # internal method names are not shown to users
    from ..ml.risk import LABELS
    df = df.rename(columns={f"factor_{k}": v.lower() for k, v in LABELS.items()})
    return df.rename(columns={c: COLS_FR.get(c, c) for c in df.columns})


def export(db: Session, name: str, fmt: str, filters: dict | None = None) -> tuple[bytes, str, str]:
    df = dataset_frame(db, name, filters)
    mode = db.info.get("data_mode", "REAL")
    df["nature des données"] = "Données réelles"
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
    fname = f"diwana_{name}_{stamp}.{fmt}"
    if fmt == "csv":
        return df.to_csv(index=False).encode("utf-8-sig"), "text/csv", fname
    if fmt == "json":
        payload = {"dataset": name, "description": DATASETS.get(name), "exported_at": datetime.utcnow().isoformat(),
                   "rows": json.loads(df.to_json(orient="records", date_format="iso"))}
        return json.dumps(payload, ensure_ascii=False, indent=1).encode(), "application/json", fname
    if fmt == "xlsx":
        buf = io.BytesIO()
        for c in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[c]):
                df[c] = df[c].dt.tz_localize(None) if getattr(df[c].dt, "tz", None) else df[c]
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name=name[:31])
            pd.DataFrame([{"dataset": name, "description": DATASETS.get(name), "exported_at": datetime.utcnow().isoformat(),
                           "note": "Each row carries source_name / source_url / period / retrieved_at"}]).to_excel(w, index=False, sheet_name="provenance")
        return buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", fname
    raise ValueError("format must be csv, xlsx or json")
