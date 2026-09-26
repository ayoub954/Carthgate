"""Matching: observations → HS headings, INS country names → ISO, sellers ↔ businesses, HS suggestion.

All matches are stored with a similarity score + method; they are AI_INFERENCE / STATISTICAL
links, never presented as verified facts.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

import numpy as np
from sqlalchemy.orm import Session

from ..models import CommerceObservation, Country, CustomsRecord, HSCode, Product, ProductMatch
from . import embeddings

PRODUCT_MATCH_THRESHOLD = 0.45
# Reject anchors: observations closest to these are NOT a monitored product (food & groceries are out of scope).
REJECT_ANCHORS = ["food, groceries, dairy products, meat, fish", "snacks, biscuits, cakes, chocolate, sweets, confectionery",
                  "beverages, drinks, water, juice, soda, coffee, tea", "spices, sauces, condiments, oil, pasta, cereals, flour",
                  "aliments, épicerie, boissons, gâteaux, biscuits",
                  "tabac, cigarettes, tobacco, cigars, tabac à rouler"]
_hs_cache = None  # (codes, descriptions, embeddings) of HS headings


def norm(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _product_corpus(db: Session):
    prods = db.query(Product).filter(Product.monitored.is_(True)).all()
    from ..providers.comtrade import KEYWORDS
    texts = [f"{p.short_name}: {KEYWORDS.get(p.id, '')}. {p.name}" for p in prods]
    return prods, texts


def match_observations_to_products(db: Session, log=print) -> str:
    """Semantic match of each product observation to a monitored HS heading (Sentence Transformer)."""
    prods, texts = _product_corpus(db)
    # Food registries are outside the monitored (non-food) headings: excluded from matching.
    # keep products declared by the source itself (product_id set without an automatic match score)
    obs = db.query(CommerceObservation).filter(CommerceObservation.source_key != "openfoodfacts").filter(
        (CommerceObservation.product_id.is_(None)) | (CommerceObservation.match_score.isnot(None))).all()
    db.query(CommerceObservation).filter(CommerceObservation.source_key == "openfoodfacts").update(
        {"product_id": None, "match_score": None}, synchronize_session=False)
    if not obs or not prods:
        return "no observations/products"
    n_prod = len(texts)
    corpus_emb = embeddings.encode(texts + REJECT_ANCHORS)
    queries = [" ".join(filter(None, [o.product, o.brand, o.raw_categories or o.category]))[:300] or "unknown" for o in obs]
    db.query(ProductMatch).filter(ProductMatch.subject_type == "observation").delete()
    matched = 0
    for o, q, res in zip(obs, queries, embeddings.best_matches(queries, texts + REJECT_ANCHORS, top_k=1, corpus_emb=corpus_emb)):
        i, score = res[0]
        if i < n_prod and score >= PRODUCT_MATCH_THRESHOLD:
            o.product_id, o.match_score = prods[i].id, round(score, 4)
            db.add(ProductMatch(subject_type="observation", subject_id=o.external_id, subject_text=q[:200],
                                product_id=prods[i].id, score=score, method="sentence-transformer cosine"))
            matched += 1
        else:
            o.product_id, o.match_score = None, round(score, 4)
    db.flush()
    return f"{matched}/{len(obs)} observations matched to monitored HS headings (threshold {PRODUCT_MATCH_THRESHOLD})"


def group_observations(db: Session, log=print) -> str:
    """Duplicate / near-duplicate detection: group observations of the same product (name+brand embeddings)."""
    obs = [o for o in db.query(CommerceObservation).all() if o.product]
    if not obs:
        return "no observations"
    texts = [f"{o.brand or ''} {o.product}".strip().lower() for o in obs]
    emb = embeddings.encode(texts)
    from sklearn.cluster import DBSCAN

    labels = DBSCAN(eps=0.12, min_samples=1, metric="cosine").fit_predict(emb)
    groups: dict[int, list] = {}
    for o, lab in zip(obs, labels):
        groups.setdefault(int(lab), []).append(o)
    for lab, members in groups.items():
        rep = sorted(members, key=lambda m: (m.image_url is None, len(m.product or "")))[0]
        key = f"g{lab}:{(rep.brand or '').strip()[:40]}|{(rep.product or '')[:80]}"
        for m in members:
            m.group_key = key
    # perceptual image hash (duplicate image detection) — only for already-cached images
    db.flush()
    multi = sum(1 for g in groups.values() if len(g) > 1)
    return f"{len(groups)} product groups ({multi} with ≥2 observations)"


def match_ins_countries(db: Session, log=print) -> str:
    """INS publishes French upper-case country names → map to ISO3 (exact normalised, fuzzy, then semantic)."""
    countries = db.query(Country).all()
    if not countries:
        return "no country reference"
    by_norm = {}
    for c in countries:
        for n in (c.name_fr, c.name_en):
            if n:
                by_norm[norm(n)] = c
                by_norm[norm(re.sub(r"\(.*?\)", "", n))] = c
    names = sorted({r.partner_name for r in db.query(CustomsRecord.partner_name).filter(
        CustomsRecord.dataset == "ins_country_month").distinct() if r.partner_name})
    unresolved, mapping = [], {}
    for n in names:
        k = norm(n.replace("_", " "))
        if k in by_norm:
            mapping[n] = (by_norm[k].iso3, 1.0, "exact")
            continue
        best, bs = None, 0.0
        for kk, c in by_norm.items():
            s = SequenceMatcher(None, k, kk).ratio()
            if s > bs:
                best, bs = c, s
        contained = [c for kk, c in by_norm.items() if len(k) >= 5 and (re.search(rf"(^|\s){re.escape(k)}$", kk) or kk.startswith(k + " "))]
        if bs >= 0.86:
            mapping[n] = (best.iso3, bs, "fuzzy")
        elif len({c.iso3 for c in contained}) == 1:  # e.g. "HONG KONG" → "Chine, RAS de Hong Kong"
            mapping[n] = (contained[0].iso3, 0.9, "containment")
        else:
            unresolved.append(n)
    if unresolved:
        corpus = [f"{c.name_fr or ''} / {c.name_en}" for c in countries]
        for n, res in zip(unresolved, embeddings.best_matches([n.title() for n in unresolved], corpus, top_k=1)):
            i, s = res[0]
            if s >= 0.80 and not re.match(r"(?i)^(pays|autre|zone|union)", n):
                mapping[n] = (countries[i].iso3, s, "semantic")
    for n, (iso, s, meth) in mapping.items():
        db.query(CustomsRecord).filter(CustomsRecord.dataset == "ins_country_month", CustomsRecord.partner_name == n).update(
            {"partner_iso3": iso}, synchronize_session=False)
    db.flush()
    miss = [n for n in names if n not in mapping]
    risky = {n: v for n, v in mapping.items() if v[2] != "exact"}
    log(f"non-exact country mappings: {risky}")
    return f"{len(mapping)}/{len(names)} INS country names mapped to ISO3; unmapped kept as-is: {miss[:8]}"


def suggest_hs(db: Session, text: str, top_k: int = 4) -> list[dict]:
    """HS Classification Agent core: semantic similarity against HS 2022 headings (4-digit)."""
    heads = db.query(HSCode).filter(HSCode.level == 4).all()
    if not heads or not text.strip():
        return []
    global _hs_cache
    if _hs_cache is None or len(_hs_cache[0]) != len(heads):
        _hs_cache = ([h.code for h in heads], [h.description for h in heads], embeddings.encode([h.description for h in heads]))
    codes, descs, emb = _hs_cache
    res = embeddings.best_matches([text], descs, top_k=top_k, corpus_emb=emb)[0]
    return [{"hs_code": codes[i], "description": descs[i], "similarity": round(s, 3)} for i, s in res]


def match_question_to_product(db: Session, text: str) -> tuple[Product | None, float]:
    prods, texts = _product_corpus(db)
    if not prods:
        return None, 0.0
    i, s = embeddings.best_matches([text], texts, top_k=1)[0][0]
    return prods[i], s


def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, norm(a), norm(b)).ratio()
