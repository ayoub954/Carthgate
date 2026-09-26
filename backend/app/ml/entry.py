"""AI ENTRY-POINT INTELLIGENCE — SEA / AIR / LAND shares computed ONLY from customs data.

REAL CUSTOMS DATA → PANDAS AGGREGATION → ENTRY MODE CALCULATION → STATISTICS → (LLM explanation elsewhere)
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
from sqlalchemy.orm import Session

from ..models import CustomsImport, EntryPoint

INSUFFICIENT_FR = ("Les données actuellement connectées ne permettent pas de déterminer de manière fiable si ce produit "
                   "entre principalement par voie maritime, aérienne ou terrestre. Une connexion aux données douanières "
                   "détaillées est nécessaire.")
INSUFFICIENT_EN = "Insufficient customs data to determine entry mode."

TYPE_TO_MODE = {"SEAPORT": "SEA", "AIRPORT": "AIR", "LAND_BORDER": "LAND"}


def _confidence(n: int, coverage: float, age_days: float) -> str:
    if n >= 1000 and coverage >= 0.85 and age_days <= 60:
        return "HIGH"
    if n >= 100 and coverage >= 0.6 and age_days <= 180:
        return "MEDIUM"
    return "LOW"


def entry_analysis(db: Session, hs_prefix: str | None = None, period_from: str | None = None,
                   period_to: str | None = None) -> dict:
    q = db.query(CustomsImport)
    if hs_prefix:
        q = q.filter(CustomsImport.hs_code.like(f"{hs_prefix}%"))
    rows = q.all()
    base = {"hs_prefix": hs_prefix, "data_used": "customs_imports (authorized declaration-level extract)",
            "source": "SINDA / authorized customs extract"}
    if not rows:
        return {**base, "available": False, "message_en": INSUFFICIENT_EN, "message_fr": INSUFFICIENT_FR,
                "records_analyzed": 0, "data_coverage": 0.0, "confidence": None,
                "why": "Public sources (INS, UN Comtrade) do not publish transport mode or entry point for Tunisia. "
                       "UN Comtrade motCode for Tunisia = 0 (not reported)."}
    eps = {e.entry_point_id: e for e in db.query(EntryPoint).all()}
    df = pd.DataFrame([{"date": r.declaration_date, "mode": r.transport_mode or TYPE_TO_MODE.get(
        getattr(eps.get(r.entry_point_id), "entry_type", None)), "entry": r.entry_point_id, "value": r.declared_value,
        "qty": r.quantity, "origin": r.provenance_iso3 or r.origin_iso3, "gov": r.destination_governorate} for r in rows])
    if period_from:
        df = df[df.date >= pd.to_datetime(period_from)]
    if period_to:
        df = df[df.date <= pd.to_datetime(period_to)]
    total = len(df)
    known = df.dropna(subset=["mode"])
    coverage = len(known) / total if total else 0
    if len(known) < 15:
        return {**base, "available": False, "message_en": INSUFFICIENT_EN, "message_fr": INSUFFICIENT_FR,
                "records_analyzed": total, "data_coverage": round(coverage, 3), "confidence": "LOW"}
    by_mode = known.groupby("mode").agg(records=("value", "size"), value=("value", "sum"), quantity=("qty", "sum"))
    by_mode["share_records"] = by_mode.records / by_mode.records.sum()
    by_mode["share_value"] = by_mode.value / by_mode.value.sum()
    main = by_mode.share_value.idxmax()
    by_entry = known.dropna(subset=["entry"]).groupby("entry").agg(records=("value", "size"), value=("value", "sum"),
                                                                  quantity=("qty", "sum"))
    by_entry["share"] = by_entry.value / by_entry.value.sum()
    top = []
    for eid, r in by_entry.sort_values("value", ascending=False).head(5).iterrows():
        e = eps.get(eid)
        top.append({"entry_point_id": eid, "name": e.official_name if e else eid, "type": TYPE_TO_MODE.get(e.entry_type) if e else None,
                    "records": int(r.records), "quantity": float(r.quantity or 0), "value": float(r.value), "share": float(r.share)})
    # yearly evolution
    known = known.assign(year=known.date.dt.year)
    evo = known.pivot_table(index="year", columns="mode", values="value", aggfunc="sum").fillna(0)
    evo = (evo.div(evo.sum(axis=1), axis=0)).round(4).reset_index().to_dict("records")
    age = (datetime.utcnow() - known.date.max()).days
    return {**base, "available": True, "main_entry_mode": main,
            "modes": {m: {"share_value": float(r.share_value), "share_records": float(r.share_records),
                          "records": int(r.records), "value": float(r.value)} for m, r in by_mode.iterrows()},
            "top_entry_points": top, "evolution": evo, "records_analyzed": total,
            "period": f"{known.date.min().date()} → {known.date.max().date()}",
            "data_coverage": round(coverage, 3), "confidence": _confidence(total, coverage, age)}
