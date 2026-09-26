"""« Expliquer avec l'IA » — explanation of a chart from the rows the chart displays.

The explanation is computed from the numbers (total, leader, concentration, trend, peak); when a language model is
configured it only rewrites those computed facts in plain French. It never adds figures.
"""
from __future__ import annotations

import numpy as np

from .cases import _n


def _fmt(v: float, unit: str | None) -> str:
    u = unit or ""
    if unit in ("USD", "TND"):
        return f"{_n(v / 1e6, 2)} M {'$' if unit == 'USD' else 'DT'}" if abs(v) >= 1e6 else f"{_n(v, 0)} {'$' if unit == 'USD' else 'DT'}"
    if unit == "%":
        return f"{_n(v, 1)} %"
    return f"{_n(v, 0)} {u}".strip()


def explain_rows(title: str, rows: list[dict], unit: str | None = None, kind: str = "category", question: str | None = None) -> dict:
    pts = [(str(r.get("label")), float(r.get("value") or 0)) for r in rows if r.get("label") is not None][:200]
    facts: list[str] = []
    if not pts:
        return {"text": "Ce graphique ne contient pas encore de données : aucune explication ne peut être produite.", "facts": []}
    vals = np.array([v for _, v in pts])
    total = float(vals.sum())
    if kind == "time":
        first, last = pts[0], pts[-1]
        peak = max(pts, key=lambda p: p[1])
        facts.append(f"La série couvre {len(pts)} période(s), de {first[0]} à {last[0]}.")
        facts.append(f"Valeur la plus élevée : {_fmt(peak[1], unit)} ({peak[0]}).")
        if len(pts) >= 2 and first[1]:
            ch = last[1] / first[1] - 1
            facts.append(f"Entre la première et la dernière période, l'évolution est de {ch * 100:+.0f} %.")
        if len(pts) >= 6:
            recent, before = vals[-3:].mean(), vals[:-3].mean()
            if before:
                facts.append(f"La moyenne des 3 dernières périodes est {'supérieure' if recent > before else 'inférieure'} de "
                             f"{abs(recent / before - 1) * 100:.0f} % à celle des périodes précédentes.")
            z = (vals[-1] - vals[:-1].mean()) / (vals[:-1].std() or 1)
            if abs(z) >= 2:
                facts.append("La dernière période sort nettement de la plage habituelle : elle mérite une attention particulière.")
        else:
            facts.append("L'historique est encore court : les tendances doivent être interprétées avec prudence.")
    else:
        srt = sorted(pts, key=lambda p: -p[1])
        lead = srt[0]
        if total:
            facts.append(f"« {lead[0]} » arrive en tête avec {_fmt(lead[1], unit)}, soit {lead[1] / total * 100:.0f} % du total.")
            top3 = sum(v for _, v in srt[:3]) / total
            if len(srt) > 3:
                facts.append(f"Les trois premiers éléments représentent {top3 * 100:.0f} % du total"
                             + (" : la répartition est très concentrée." if top3 >= 0.75 else " : la répartition reste diversifiée." if top3 < 0.5 else "."))
        facts.append(f"{len(srt)} élément(s) affiché(s) ; total : {_fmt(total, unit)}.")
        if len(srt) >= 2 and srt[1][1]:
            facts.append(f"Le premier élément est {lead[1] / srt[1][1]:.1f} fois plus important que le deuxième (« {srt[1][0]} »).".replace(".", ",", 1))
    text = "Selon les données affichées :\n" + "\n".join(f"• {f}" for f in facts) + \
           "\nCes constats décrivent les données ; ils ne constituent pas des conclusions."
    try:
        from ..llm.explain import explain
        r = explain(f"Explique simplement le graphique « {title} »" + (f" qui répond à la question : {question}" if question else "") + ".",
                    {"agents": [{"agent_name": title, "status": "OK", "findings": facts, "warnings": []}], "cards": []})
        if r.get("llm"):
            text = r["text"]
    except Exception:
        pass
    return {"text": text, "facts": facts}
