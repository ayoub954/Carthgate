"""Explanation layer — the language model only EXPLAINS computed results; it never computes or invents.

Without an available language model, a deterministic French narrative is produced from the same facts.
Model names are never returned to the user interface.
"""
from __future__ import annotations

import json

from . import router
from .provider import LLMUnavailable

SYSTEM = """Tu es l'assistant d'analyse de DIWANA TRACE AI pour les agents de la Douane tunisienne.
RÈGLES STRICTES :
- Réponds TOUJOURS en français, dans un style professionnel et clair.
- Utilise UNIQUEMENT les faits du JSON fourni. N'invente jamais de chiffres, noms, liens, périodes ou sources.
- Si une information manque ou est indisponible, dis-le simplement ("Données insuffisantes pour cette analyse").
- Commence par "Selon les données disponibles".
- N'emploie jamais de termes techniques (modèle, algorithme, API, base de données, etc.).
- Règles : anomalie ≠ fraude ; non retrouvé dans un registre ≠ illégal ; observation ≠ vente ; projection ≠ certitude ;
  une priorité élevée est une priorité de vérification, jamais une accusation. Ne recommande jamais de sanction.
- Si les faits indiquent des données simulées de démonstration, précise-le en une phrase.
- 170 mots maximum, paragraphes courts ou puces."""


def fallback_summary(question: str, facts: dict) -> str:
    cards = facts.get("cards") or []
    agents = facts.get("agents") or []
    lines = ["Selon les données disponibles,"]
    if facts.get("mode", "").startswith("données simulées"):
        lines[0] = "Selon les données simulées de démonstration,"
    if cards:
        lines[0] += f" {len(cards)} priorité(s) de vérification ressortent de l'analyse :"
        for c in cards:
            parts = [f"**{c['product']}**"]
            if c.get("priority_score") is not None:
                parts.append(f"indice de priorité {c['priority_score']:.0f}/100")
            if c.get("entry_point"):
                parts.append(f"principalement via {c['entry_point']}")
            if c.get("country"):
                parts.append(f"provenance principale : {c['country']}")
            lines.append("• " + ", ".join(parts) + ".")
            if c.get("why"):
                lines.append("  Pourquoi : " + " ; ".join(w[0].lower() + w[1:] if w else w for w in c["why"][:3]) + ".")
    else:
        found = [f for a in agents if a["status"] in ("OK", "PARTIAL") for f in a["findings"][:2]]
        lines[0] += " voici les principaux résultats :" if found else " l'analyse ne permet pas de conclure."
        lines += [f"• {f}" for f in found[:6]]
    missing = [a["agent_name"] for a in agents if a["status"] in ("INSUFFICIENT_DATA", "ACCESS_REQUIRED")]
    notes = [f for a in agents if a["status"] in ("INSUFFICIENT_DATA", "ACCESS_REQUIRED") for f in a["findings"][:1]]
    if notes:
        lines.append(notes[0])
    elif missing:
        lines.append(f"Données insuffisantes pour : {', '.join(missing).lower()}.")
    lines.append("Ces éléments constituent des priorités de vérification pour l'agent, et non des conclusions.")
    return "\n".join(lines)


def explain(question: str, facts: dict, task: str = "reasoning") -> dict:
    payload = json.dumps(facts, ensure_ascii=False, default=str)[:14000]
    try:
        res = router.complete(task, SYSTEM, f"QUESTION : {question}\n\nFAITS CALCULÉS (JSON) :\n{payload}", max_tokens=700)
        return {"text": res.text.strip(), "llm": res.model, "mode": "AI"}
    except LLMUnavailable:
        return {"text": fallback_summary(question, facts), "llm": None, "mode": "GENERATED"}
    except Exception:
        return {"text": fallback_summary(question, facts), "llm": None, "mode": "GENERATED"}


def classify(question: str, schema_hint: str) -> dict | None:
    try:
        res = router.complete("fast", "Extract structured intent. Reply with JSON only.",
                              f"{schema_hint}\n\nQUESTION: {question}", json_mode=True, max_tokens=300)
        return json.loads(res.text)
    except Exception:
        return None
