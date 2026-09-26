"""Fragmentation detector + entry anomaly detection on DECLARATION-LEVEL customs data.

Requires an authorized SINDA extract (customs_imports). Without it every function returns an
explicit INSUFFICIENT DATA / SINDA CONNECTION REQUIRED result — nothing is simulated.

Signals (per HS heading, window 7/30/90 days):
  many small imports + similar products + short period + multiple importers
  + multiple entry points + significant cumulative volume.
Methods: temporal DBSCAN (declaration dates), rules, low-value ratio, Isolation Forest (entries).
Outcome: NORMAL / MONITOR / POSSIBLE FRAGMENTATION PATTERN — never "fraud".
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.ensemble import IsolationForest
from sqlalchemy.orm import Session

from ..models import Anomaly, CustomsImport, FragmentationPattern

NO_DATA = {
    "status": "INSUFFICIENT DATA",
    "message": "SINDA CONNECTION REQUIRED — fragmentation analysis needs declaration-level customs data "
               "(date, HS code, declared value, importer, entry point). Load an authorized extract via "
               "POST /api/customs/import.",
}


def customs_frame(db: Session) -> pd.DataFrame:
    rows = db.query(CustomsImport).all()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([{
        "date": r.declaration_date, "hs": r.hs_code, "hs4": r.hs_code[:4], "importer": r.importer_hash,
        "entry": r.entry_point_id, "mode": r.transport_mode, "value": r.declared_value, "qty": r.quantity,
        "origin": r.origin_iso3, "provenance": r.provenance_iso3, "gov": r.destination_governorate,
        "desc": r.description} for r in rows])


def score_window(g: pd.DataFrame, hist: pd.DataFrame, window_days: int) -> dict:
    n = len(g)
    low_thr = hist["value"].quantile(0.25) if len(hist) >= 20 else g["value"].quantile(0.25)
    low_ratio = float((g["value"] <= low_thr).mean()) if n else 0.0
    days = (g["date"].astype("int64") // 86_400_000_000_000).values.reshape(-1, 1)
    dens = 0.0
    if n >= 3:
        lab = DBSCAN(eps=1.0, min_samples=3).fit_predict(days)
        dens = float((lab >= 0).mean())
    importers = g["importer"].nunique(dropna=True)
    entries = g["entry"].nunique(dropna=True)
    # baseline: average count per window over history
    span_days = max((hist["date"].max() - hist["date"].min()).days, window_days) if len(hist) else window_days
    baseline = len(hist) / span_days * window_days if len(hist) else 0
    growth = (n / baseline - 1) if baseline else None
    cum_value = float(g["value"].sum())
    hist_windows = (hist.set_index("date")["value"].resample(f"{window_days}D").sum()) if len(hist) else pd.Series(dtype=float)
    cum_pct = float((hist_windows < cum_value).mean()) if len(hist_windows) >= 3 else None
    similarity = None
    if g["desc"].notna().sum() >= 3:
        try:
            from . import embeddings
            e = embeddings.encode(g["desc"].dropna().astype(str).tolist()[:200])
            sims = e @ e.T
            similarity = float((sims.sum() - len(e)) / (len(e) * (len(e) - 1)))
        except Exception:
            similarity = None
    points, reasons = 0.0, []
    if n >= 10 and low_ratio >= 0.6:
        points += 25; reasons.append(f"{low_ratio*100:.0f} % des {n} déclarations sont de faible valeur")
    if dens >= 0.6:
        points += 20; reasons.append(f"{dens*100:.0f} % des opérations sont très rapprochées dans le temps")
    if importers >= 5:
        points += 15; reasons.append(f"{importers} importateurs différents")
    if entries >= 2:
        points += 10; reasons.append(f"{entries} points d'entrée utilisés")
    if growth is not None and growth >= 0.5:
        points += 15; reasons.append(f"Nombre de déclarations +{growth*100:.0f} % par rapport au rythme habituel")
    if cum_pct is not None and cum_pct >= 0.9:
        points += 10; reasons.append("Volume cumulé parmi les plus élevés observés historiquement")
    if similarity is not None and similarity >= 0.75:
        points += 5; reasons.append("Produits très similaires d'une déclaration à l'autre")
    status = "POSSIBLE FRAGMENTATION PATTERN" if points >= 60 else "MONITOR" if points >= 35 else "NORMAL"
    return {"status": status, "score": min(points, 100.0), "reasons": reasons[:5], "features": {
        "declarations": n, "low_value_ratio": low_ratio, "low_value_threshold": float(low_thr) if pd.notna(low_thr) else None,
        "temporal_density": dens, "unique_importers": int(importers), "entry_points": int(entries),
        "growth_vs_baseline": growth, "cumulative_value": cum_value, "cumulative_value_percentile": cum_pct,
        "product_similarity": similarity}}


def detect_fragmentation(db: Session, log=print) -> str:
    df = customs_frame(db)
    db.query(FragmentationPattern).delete()
    if df.empty:
        return NO_DATA["message"]
    end = df["date"].max()
    n = 0
    for window in (7, 30, 90):
        start = end - timedelta(days=window)
        for hs4, g in df[df["date"] > start].groupby("hs4"):
            hist = df[(df["hs4"] == hs4) & (df["date"] <= start)]
            res = score_window(g, hist, window)
            db.add(FragmentationPattern(hs_code=hs4, window_days=window, status=res["status"], score=res["score"],
                                        features={**res["features"], "reasons": res["reasons"]},
                                        period=f"{start.date()} → {end.date()}"))
            n += 1
    db.flush()
    return f"{n} (heading × window) fragmentation assessments"


def detect_entry_anomalies(db: Session, log=print) -> str:
    df = customs_frame(db)
    db.query(Anomaly).filter(Anomaly.subject_type == "ENTRY").delete()
    if df.empty or df["entry"].isna().all():
        return NO_DATA["message"]
    df["week"] = df["date"].dt.to_period("W").dt.start_time
    agg = df.groupby(["hs4", "entry", "week"]).agg(n=("value", "size"), value=("value", "sum"),
                                                   low=("value", lambda v: float((v <= v.quantile(0.25)).mean())),
                                                   importers=("importer", "nunique")).reset_index()
    first_seen = df.groupby(["hs4", "entry"])["date"].min()
    agg["new_pair"] = agg.apply(lambda r: int((r.week - first_seen[(r.hs4, r.entry)]).days <= 7), axis=1)
    agg["mode_share"] = agg.groupby(["hs4", "week"])["n"].transform(lambda s: s / s.sum())
    if len(agg) < 30:
        return "INSUFFICIENT DATA for Isolation Forest on entries"
    X = np.column_stack([np.log1p(agg.n), np.log1p(agg.value), agg.low, agg.importers, agg.new_pair, agg.mode_share])
    iso = IsolationForest(n_estimators=200, contamination=0.05, random_state=42).fit(X)
    pct = pd.Series(-iso.score_samples(X)).rank(pct=True).values * 100
    pred = iso.predict(X) == -1
    for (_, r), s, a in zip(agg.iterrows(), pct, pred):
        reasons = []
        if r.new_pair:
            reasons.append("Nouveau point d'entrée pour ce produit")
        if r.low >= 0.6:
            reasons.append("Concentration de déclarations de faible valeur")
        db.add(Anomaly(subject_type="ENTRY", subject_id=f"{r.hs4}:{r.entry}:{r.week.date()}", hs_code=r.hs4,
                       period=str(r.week.date()), score=round(float(s), 1), is_anomaly=bool(a), reasons=reasons,
                       features={"declarations": int(r.n), "value": float(r.value), "entry_point_id": r.entry,
                                 "importers": int(r.importers), "mode_share": float(r.mode_share)},
                       model="IsolationForest(n=200)", source_key="customs_declarations", data_coverage=1.0,
                       confidence="MEDIUM"))
    db.flush()
    return f"{len(agg)} (heading × entry point × week) scored"


def detect_declared_values(db: Session, log=print) -> str:
    """Declared unit value (value / quantity) of each recent declaration vs the heading's own history."""
    df = customs_frame(db)
    db.query(Anomaly).filter(Anomaly.subject_type == "DECLARED_VALUE").delete()
    if df.empty or df["qty"].isna().all():
        return NO_DATA["message"]
    df = df[df["qty"].fillna(0) > 0].copy()
    df["uv"] = df["value"] / df["qty"]
    end = df["date"].max()
    n = 0
    for hs4, g in df.groupby("hs4"):
        hist = g[g["date"] <= end - timedelta(days=30)]
        rec = g[g["date"] > end - timedelta(days=30)]
        if len(hist) < 5 or rec.empty:
            continue
        med = hist["uv"].median()
        low = rec[rec["uv"] < 0.5 * med]
        if len(low) >= 3:
            db.add(Anomaly(subject_type="DECLARED_VALUE", subject_id=f"{hs4}:{end.date()}", hs_code=hs4, period=f"{(end - timedelta(days=30)).date()} → {end.date()}",
                           score=round(min(100.0, 50 + 50 * len(low) / len(rec)), 1), is_anomaly=True,
                           reasons=[f"{len(low)} déclaration(s) récente(s) avec une valeur unitaire inférieure à la moitié de la valeur habituelle",
                                    f"Valeur unitaire habituelle : {med:,.0f} TND ; récente : {low['uv'].median():,.0f} TND".replace(",", " ")],
                           features={"declarations": int(len(rec)), "low_value_count": int(len(low)), "median_uv_hist": float(med),
                                     "median_uv_recent_low": float(low["uv"].median())},
                           model="rule: unit value < 50% of historical median", source_key="customs_declarations",
                           data_coverage=1.0, confidence="MEDIUM"))
            n += 1
    db.flush()
    return f"{n} declared-value patterns"


def detect_mode_shifts(db: Session, log=print) -> str:
    """Entry-mode change: share of each transport mode in the last 30 days vs before."""
    df = customs_frame(db)
    db.query(Anomaly).filter(Anomaly.subject_type == "MODE_SHIFT").delete()
    if df.empty or df["mode"].isna().all():
        return NO_DATA["message"]
    end = df["date"].max()
    n = 0
    labels = {"SEA": "maritime", "AIR": "aérienne", "LAND": "terrestre"}
    for hs4, g in df.dropna(subset=["mode"]).groupby("hs4"):
        hist, rec = g[g["date"] <= end - timedelta(days=30)], g[g["date"] > end - timedelta(days=30)]
        if len(hist) < 5 or len(rec) < 3:
            continue
        hs_, rs_ = hist["mode"].value_counts(normalize=True), rec["mode"].value_counts(normalize=True)
        for mode, share in rs_.items():
            before = float(hs_.get(mode, 0.0))
            if share - before >= 0.3:
                db.add(Anomaly(subject_type="MODE_SHIFT", subject_id=f"{hs4}:{mode}:{end.date()}", hs_code=hs4,
                               period=f"{(end - timedelta(days=30)).date()} → {end.date()}", score=round(min(100.0, 50 + 100 * (share - before)), 1),
                               is_anomaly=True, reasons=[f"Voie {labels.get(mode, mode)} : {share*100:.0f} % des déclarations récentes contre {before*100:.0f} % auparavant"],
                               features={"mode": mode, "share_recent": float(share), "share_before": before},
                               model="rule: mode share change ≥ 30 pts", source_key="customs_declarations", data_coverage=1.0, confidence="MEDIUM"))
                n += 1
    db.flush()
    return f"{n} entry-mode changes"
