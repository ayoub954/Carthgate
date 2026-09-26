"""ECONOMIC SCENARIO ENGINE — separate from the forecast.

FORECAST  = statistical projection of official series (ml/forecast.py).
SCENARIO  = "what if" arithmetic on top of the baseline forecast, driven by explicit ASSUMPTIONS.
Presets are ILLUSTRATIVE assumptions (editable), not estimates of the informal economy.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import EconomicIndicator, Forecast, ScenarioResult

SCENARIO_FR = {"BASELINE": "Tendance actuelle", "CONSERVATIVE": "Scénario prudent", "MODERATE": "Scénario intermédiaire",
               "AMBITIOUS": "Scénario renforcé"}

PRESETS = {
    "BASELINE": {"unreported_commerce_share_pct": 0.0, "formalization_improvement_pct": 0.0,
                 "compliance_improvement_pct": 0.0, "detection_improvement_pct": 0.0},
    "CONSERVATIVE": {"unreported_commerce_share_pct": 1.0, "formalization_improvement_pct": 5.0,
                     "compliance_improvement_pct": 5.0, "detection_improvement_pct": 5.0},
    "MODERATE": {"unreported_commerce_share_pct": 2.0, "formalization_improvement_pct": 10.0,
                 "compliance_improvement_pct": 10.0, "detection_improvement_pct": 10.0},
    "AMBITIOUS": {"unreported_commerce_share_pct": 3.0, "formalization_improvement_pct": 20.0,
                  "compliance_improvement_pct": 15.0, "detection_improvement_pct": 20.0},
}


def effective_duty_rate(db: Session) -> dict:
    """Customs & import duties / imports of goods & services (World Bank, latest common year)."""
    duties = {e.period: e.value for e in db.query(EconomicIndicator).filter_by(indicator="wb_customs_duties")}
    imports = {e.period: e.value for e in db.query(EconomicIndicator).filter_by(indicator="wb_imports_gs")}
    common = sorted(set(duties) & set(imports))
    if not common:
        return {"rate_pct": None, "year": None, "note": "Donnée indisponible — saisir un taux supposé"}
    y = common[-1]
    return {"rate_pct": round(duties[y] / imports[y] * 100, 2), "year": y,
            "note": f"Droits de douane rapportés aux importations (Banque mondiale, {y}, dernière année publiée)."}


def run_scenario(db: Session, preset: str = "MODERATE", overrides: dict | None = None) -> dict:
    preset = preset.upper()
    a = dict(PRESETS.get(preset, PRESETS["MODERATE"]))
    duty = effective_duty_rate(db)
    a["effective_duty_rate_pct"] = duty["rate_pct"]
    labels_fr = {"unreported_commerce_share_pct": "Part des importations insuffisamment déclarées (%)",
                 "formalization_improvement_pct": "Amélioration de la formalisation (%)",
                 "compliance_improvement_pct": "Amélioration de la conformité (%)",
                 "detection_improvement_pct": "Amélioration de la détection (%)", "effective_duty_rate_pct": "Taux moyen de droits (%)"}
    for k, v in (overrides or {}).items():
        if k in a and v is not None:
            a[k] = float(v)
    fc = db.query(Forecast).filter_by(indicator="ins_imports").order_by(Forecast.period).all()
    if not fc:
        return {"status": "INSUFFICIENT DATA", "message": "Projection de référence indisponible"}
    if a["effective_duty_rate_pct"] is None:
        return {"status": "ASSUMPTION REQUIRED", "message": "Indiquez un taux de droits supposé", "assumptions": a}
    combined = 1 - (1 - a["formalization_improvement_pct"] / 100) * (1 - a["compliance_improvement_pct"] / 100) * \
        (1 - a["detection_improvement_pct"] / 100)
    rows, cum = [], 0.0
    for f in fc:
        base = a["unreported_commerce_share_pct"] / 100 * f.predicted
        recovered = base * combined
        rev = recovered * a["effective_duty_rate_pct"] / 100
        cum += rev
        rows.append({"year": int(f.period), "baseline_imports_mtnd": f.predicted, "baseline_lower": f.lower, "baseline_upper": f.upper,
                     "assumed_unreported_base_mtnd": base, "recovered_base_mtnd": recovered,
                     "potential_additional_customs_revenue_mtnd": rev,
                     "revenue_lower_mtnd": rev * (f.lower / f.predicted) if f.predicted else None,
                     "revenue_upper_mtnd": rev * (f.upper / f.predicted) if f.predicted else None,
                     "cumulative_mtnd": cum})
    res = {"scenario": preset, "assumptions": a, "names": labels_fr, "assumption_labels": {
        "unreported_commerce_share_pct": "Hypothèse — part des importations supposée insuffisamment déclarée (aucune statistique officielle n'existe)",
        "formalization_improvement_pct": "Hypothèse — part de cette base qui serait formalisée",
        "compliance_improvement_pct": "Hypothèse — amélioration de la conformité",
        "detection_improvement_pct": "Hypothèse — amélioration de la détection analytique",
        "effective_duty_rate_pct": duty["note"]},
        "combined_capture_rate": combined, "results": rows,
        "statement": f"Selon ce scénario et ces hypothèses, les recettes douanières supplémentaires potentielles atteindraient environ "
                     f"{rows[-1]['cumulative_mtnd']:,.0f} millions de dinars en cumulé d'ici {rows[-1]['year']}. Il s'agit d'une simulation fondée sur des "
                     f"hypothèses, et non d'une prévision de l'impact de la plateforme.".replace(",", " "),
        "scenario_label": SCENARIO_FR.get(preset, preset)}
    db.add(ScenarioResult(name=preset, assumptions=a, results=rows))
    db.commit()
    return res
