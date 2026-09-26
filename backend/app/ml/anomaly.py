"""Isolation Forest anomaly detection on REAL official statistics.

A) HS chapter × month imports (INS monthly series): value, YoY change, change vs trailing
   3-month mean, unit value (TND/kg) vs the chapter's own history, share of total imports.
B) Partner × HS heading unit values (UN Comtrade, latest year): declared unit value (USD/kg)
   vs the median across partners — a declared-value pattern signal.
ANOMALY ≠ FRAUD: results are signals for human review.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sqlalchemy.orm import Session

from ..models import Anomaly, CustomsRecord


def _robust_z(s: pd.Series, x: float) -> float:
    s = s.dropna()
    if len(s) < 6 or pd.isna(x):
        return 0.0
    med = s.median()
    mad = (s - med).abs().median() * 1.4826
    if not mad:
        return 0.0
    return float((x - med) / mad)


def _confidence(n_hist: int, coverage: float) -> str:
    if n_hist >= 36 and coverage >= 0.8:
        return "HIGH"
    if n_hist >= 18 and coverage >= 0.6:
        return "MEDIUM"
    return "LOW"


def chapter_month_frame(db: Session) -> pd.DataFrame:
    rows = db.query(CustomsRecord.hs_code, CustomsRecord.hs_description, CustomsRecord.period, CustomsRecord.value,
                    CustomsRecord.weight_kg).filter(CustomsRecord.dataset == "ins_chapter_month", CustomsRecord.flow == "M").all()
    df = pd.DataFrame(rows, columns=["hs", "desc", "period", "value", "weight"])
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["period"] + "-01")
    df = df.sort_values(["hs", "date"])
    tot = df.groupby("date")["value"].sum().rename("total")
    df = df.join(tot, on="date")
    df["share"] = df["value"] / df["total"]
    df["uv"] = np.where(df["weight"] > 0, df["value"] / df["weight"], np.nan)
    g = df.groupby("hs")
    df["value_lag12"] = g["value"].shift(12)
    df["yoy"] = np.where(df["value_lag12"] > 0, df["value"] / df["value_lag12"] - 1, np.nan)
    df["trail3"] = g["value"].transform(lambda s: s.shift(1).rolling(3, min_periods=2).mean())
    df["vs_trail3"] = np.where(df["trail3"] > 0, df["value"] / df["trail3"] - 1, np.nan)
    df["share_lag12"] = g["share"].shift(12)
    df["share_chg"] = df["share"] - df["share_lag12"]
    return df


def detect_chapter_anomalies(db: Session, log=print) -> str:
    df = chapter_month_frame(db)
    if df.empty:
        return "INSUFFICIENT DATA: no INS chapter series"
    db.query(Anomaly).filter(Anomaly.subject_type == "HS_CHAPTER_MONTH").delete()
    feat = df.dropna(subset=["yoy", "vs_trail3"]).copy()
    feat = feat[(feat["value"] > 0) & (feat["value_lag12"] > 0)]
    if len(feat) < 50:
        return "INSUFFICIENT DATA for Isolation Forest"
    feat["log_value"] = np.log1p(feat["value"])
    feat["log_yoy"] = np.sign(feat["yoy"]) * np.log1p(np.abs(feat["yoy"]))
    feat["log_trail"] = np.sign(feat["vs_trail3"]) * np.log1p(np.abs(feat["vs_trail3"]))
    feat["uv_z"] = feat.apply(lambda r: _robust_z(df.loc[(df.hs == r.hs) & (df.date < r.date), "uv"], r.uv), axis=1).clip(-10, 10)
    feat["share_chg_pp"] = (feat["share_chg"] * 100).fillna(0)
    cols = ["log_value", "log_yoy", "log_trail", "uv_z", "share_chg_pp"]
    X = feat[cols].fillna(0).values
    iso = IsolationForest(n_estimators=300, contamination=0.04, random_state=42).fit(X)
    raw = -iso.score_samples(X)
    pct = pd.Series(raw).rank(pct=True).values * 100
    pred = iso.predict(X) == -1
    n_months = df.groupby("hs")["date"].nunique()
    months_total = df["date"].nunique()
    n_anom = 0
    for (idx, r), score, is_a in zip(feat.iterrows(), pct, pred):
        reasons = []
        if abs(r.yoy) >= 0.3:
            reasons.append(f"Importations {'+' if r.yoy > 0 else ''}{r.yoy*100:.0f} % par rapport au même mois de l'année précédente")
        if abs(r.vs_trail3) >= 0.3:
            reasons.append(f"{'+' if r.vs_trail3 > 0 else ''}{r.vs_trail3*100:.0f} % par rapport à la moyenne des 3 mois précédents")
        if abs(r.uv_z) >= 3:
            reasons.append(f"Valeur unitaire (TND/kg) {'au-dessus' if r.uv_z > 0 else 'en dessous'} de sa plage historique habituelle")
        if abs(r.share_chg_pp) >= 0.5:
            reasons.append(f"Part dans les importations totales {'+' if r.share_chg_pp > 0 else ''}{r.share_chg_pp:.1f} point(s) sur un an")
        cov = n_months.get(r.hs, 0) / max(months_total, 1)
        db.add(Anomaly(subject_type="HS_CHAPTER_MONTH", subject_id=f"{r.hs}:{r.period}", hs_code=r.hs, period=r.period,
                       score=round(float(score), 1), is_anomaly=bool(is_a), reasons=reasons[:4],
                       features={"value_tnd": float(r.value), "yoy": float(r.yoy), "vs_trailing_3m": float(r.vs_trail3),
                                 "unit_value_tnd_kg": None if pd.isna(r.uv) else float(r.uv), "unit_value_robust_z": float(r.uv_z),
                                 "share_change_pp": float(r.share_chg_pp), "description": r.desc},
                       model="IsolationForest(n=300, contamination=0.04)", source_key="ins_trade",
                       data_coverage=round(cov, 3), confidence=_confidence(int(n_months.get(r.hs, 0)), cov)))
        n_anom += int(is_a)
    db.flush()
    return f"{len(feat)} chapter-months scored, {n_anom} flagged (latest month {feat['period'].max()})"


def detect_unit_value_anomalies(db: Session, log=print) -> str:
    rows = db.query(CustomsRecord).filter(CustomsRecord.dataset == "comtrade_hs4_partner").all()
    if not rows:
        return "INSUFFICIENT DATA: no Comtrade partner detail"
    from ..models import Country
    fr_names = {c.iso3: c.name_fr or c.name_en for c in db.query(Country)}
    df = pd.DataFrame([{"hs": r.hs_code, "period": r.period, "iso": r.partner_iso3, "partner": fr_names.get(r.partner_iso3, r.partner_name),
                        "value": r.value, "kg": r.weight_kg} for r in rows])
    df = df[(df["kg"].fillna(0) > 0) & (df["value"] > 0)]
    df = df[df["iso"].fillna("").str.fullmatch(r"[A-Z]{3}")]  # drop pseudo-partners (bunkers, areas n.e.s.)
    latest = df["period"].max()
    df = df[df["period"] == latest].copy()
    if len(df) < 40:
        return "INSUFFICIENT DATA"
    df["uv"] = df["value"] / df["kg"]
    df["med_uv"] = df.groupby("hs")["uv"].transform("median")
    df["uv_ratio"] = np.log(df["uv"] / df["med_uv"])
    df["share"] = df["value"] / df.groupby("hs")["value"].transform("sum")
    df["log_value"] = np.log1p(df["value"])
    df = df[df.groupby("hs")["uv"].transform("count") >= 5]
    X = df[["uv_ratio", "log_value", "share"]].values
    iso = IsolationForest(n_estimators=300, contamination=0.05, random_state=42).fit(X)
    pct = pd.Series(-iso.score_samples(X)).rank(pct=True).values * 100
    pred = iso.predict(X) == -1
    db.query(Anomaly).filter(Anomaly.subject_type == "PARTNER_HS_UNIT_VALUE").delete()
    n = 0
    for (_, r), sc, a in zip(df.iterrows(), pct, pred):
        ratio = float(np.exp(r.uv_ratio))
        reasons = []
        if ratio <= 0.33:
            reasons.append(f"Valeur unitaire déclarée {ratio:.2f} fois la médiane des autres pays (basse)")
        elif ratio >= 3:
            reasons.append(f"Valeur unitaire déclarée {ratio:.1f} fois la médiane des autres pays (élevée)")
        if r.share >= 0.25:
            reasons.append(f"Ce pays fournit {r.share*100:.0f} % des importations de ce produit")
        db.add(Anomaly(subject_type="PARTNER_HS_UNIT_VALUE", subject_id=f"{r.hs}:{r.iso}:{latest}", hs_code=r.hs,
                       period=str(latest), score=round(float(sc), 1), is_anomaly=bool(a) and bool(reasons), reasons=reasons,
                       features={"partner": r.partner, "partner_iso3": r.iso, "value_usd": float(r.value), "net_weight_kg": float(r.kg),
                                 "unit_value_usd_kg": float(r.uv), "median_unit_value_usd_kg": float(r.med_uv), "uv_ratio": ratio,
                                 "share": float(r.share)},
                       model="IsolationForest(n=300, contamination=0.05)", source_key="un_comtrade",
                       data_coverage=1.0, confidence="MEDIUM"))
        n += int(bool(a) and bool(reasons))
    db.flush()
    return f"{len(df)} partner×heading unit values scored for {latest}, {n} flagged"
