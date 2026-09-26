"""NetworkX network intelligence + Trade Constellation / Sankey builders.

Edge evidence types:
  VERIFIED     official statistic or official reference (UN Comtrade, M49, HS)
  OBSERVED     observed in a public source (OSM shop location/type, Open*Facts entry)
  STATISTICAL  statistical association (co-location of category shops and product flows)
  AI_INFERENCE semantic match produced by the Sentence Transformer
Importer → seller links are NEVER inferred.
"""
from __future__ import annotations

from collections import Counter, defaultdict

import networkx as nx
from networkx.algorithms import community
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import (CommerceObservation, Country, CustomsImport, CustomsRecord, EntryPoint, NetworkEdge, NetworkNode,
                      Product, Seller)
from .entry import TYPE_TO_MODE

CONT_FR = {"Africa": "Afrique", "Europe": "Europe", "Asia": "Asie", "North America": "Amérique du Nord",
           "South America": "Amérique du Sud", "Oceania": "Océanie"}
MODE_LABEL = {"SEA": "Voie maritime", "AIR": "Voie aérienne", "LAND": "Voie terrestre"}


def latest_comtrade_year(db: Session) -> str | None:
    return db.query(func.max(CustomsRecord.period)).filter(CustomsRecord.dataset == "comtrade_hs4_partner").scalar()


def build_graph(db: Session) -> nx.DiGraph:
    G = nx.DiGraph()
    year = latest_comtrade_year(db)
    countries = {c.iso3: c for c in db.query(Country).all()}
    products = {p.id: p for p in db.query(Product).filter(Product.monitored.is_(True))}

    def node(nid, ntype, label, **attrs):
        if nid not in G:
            G.add_node(nid, node_type=ntype, label=label, **attrs)

    def edge(a, b, rel, ev, weight=1.0, conf=1.0, src=None, period=None):
        G.add_edge(a, b, relation_type=rel, evidence_type=ev, weight=weight, confidence=conf, source=src, period=period)

    for p in products.values():
        node(f"PRODUCT:{p.id}", "PRODUCT", p.short_name, category=p.category)
        node(f"CATEGORY:{p.category}", "CATEGORY", p.category)
        node(f"HS_CODE:{p.chapter}", "HS_CODE", f"Chapitre {p.chapter}")
        edge(f"CATEGORY:{p.category}", f"PRODUCT:{p.id}", "includes", "VERIFIED", src="hs_nomenclature")
        edge(f"HS_CODE:{p.chapter}", f"PRODUCT:{p.id}", "hs_parent", "VERIFIED", src="hs_nomenclature")
    if year:
        rows = db.query(CustomsRecord).filter(CustomsRecord.dataset == "comtrade_hs4_partner", CustomsRecord.period == year).all()
        for r in rows:
            c = countries.get(r.partner_iso3)
            if not c or r.hs_code not in products or not r.value:
                continue
            node(f"COUNTRY:{c.iso3}", "COUNTRY", c.name_fr or c.name_en, continent=c.continent, lat=c.lat, lon=c.lon)
            if c.continent:
                node(f"CONTINENT:{c.continent}", "CONTINENT", CONT_FR.get(c.continent, c.continent))
                if not G.has_edge(f"CONTINENT:{c.continent}", f"COUNTRY:{c.iso3}"):
                    edge(f"CONTINENT:{c.continent}", f"COUNTRY:{c.iso3}", "contains", "VERIFIED", src="un_m49")
            edge(f"COUNTRY:{c.iso3}", f"PRODUCT:{r.hs_code}", "exports_to_tunisia", "VERIFIED", weight=float(r.value),
                 src="un_comtrade", period=year)
    # declaration-level (only with authorized extract)
    eps = {e.entry_point_id: e for e in db.query(EntryPoint).all()}
    for hs, entry, n, imp in db.query(func.substr(CustomsImport.hs_code, 1, 4), CustomsImport.entry_point_id,
                                      func.count(), func.count(func.distinct(CustomsImport.importer_hash))).group_by(
            func.substr(CustomsImport.hs_code, 1, 4), CustomsImport.entry_point_id).all():
        if hs in products and entry in eps:
            e = eps[entry]
            mode = TYPE_TO_MODE.get(e.entry_type)
            node(f"ENTRY_MODE:{mode}", "ENTRY_MODE", MODE_LABEL.get(mode, mode))
            node(f"ENTRY_POINT:{entry}", "ENTRY_POINT", e.official_name, entry_type=e.entry_type)
            edge(f"PRODUCT:{hs}", f"ENTRY_MODE:{mode}", "enters_by", "VERIFIED", weight=n, src="authorized_customs_extract")
            edge(f"ENTRY_MODE:{mode}", f"ENTRY_POINT:{entry}", "through", "VERIFIED", weight=n, src="authorized_customs_extract")
    for imp, hs, n in db.query(CustomsImport.importer_hash, func.substr(CustomsImport.hs_code, 1, 4), func.count()).group_by(
            CustomsImport.importer_hash, func.substr(CustomsImport.hs_code, 1, 4)).all():
        if imp and hs in products:
            node(f"IMPORTER_HASH:{imp[:12]}", "IMPORTER_HASH", f"Importateur {imp[:6]}")
            edge(f"IMPORTER_HASH:{imp[:12]}", f"PRODUCT:{hs}", "declared", "VERIFIED", weight=n, src="authorized_customs_extract")
    # commerce: category → zone (observed shop counts), seller nodes
    zone_cat = Counter()
    for s in db.query(Seller).filter(Seller.category.isnot(None)).all():
        if s.governorate:
            zone_cat[(s.category, s.governorate)] += 1
    for (cat, gov), n in zone_cat.items():
        node(f"ZONE:{gov}", "ZONE", gov)
        if f"CATEGORY:{cat}" in G:
            edge(f"CATEGORY:{cat}", f"ZONE:{gov}", "observed_shops_in", "OBSERVED", weight=n, src="osm_shops")
    # observations → product (semantic)
    for pid, n in db.query(CommerceObservation.product_id, func.count()).filter(
            CommerceObservation.product_id.isnot(None)).group_by(CommerceObservation.product_id):
        node(f"OBS:{pid}", "OBSERVATIONS", f"{n} observations commerciales")
        edge(f"OBS:{pid}", f"PRODUCT:{pid}", "matched_to", "AI_INFERENCE", weight=n, conf=0.6, src="open_facts")
    return G


def analyze_network(db: Session, log=print) -> str:
    G = build_graph(db)
    if G.number_of_nodes() == 0:
        return "INSUFFICIENT DATA"
    U = G.to_undirected()
    deg = nx.degree_centrality(U)
    btw = nx.betweenness_centrality(U, k=min(200, len(U)), seed=42)
    comms = community.greedy_modularity_communities(U) if U.number_of_edges() else []
    cid = {n: i for i, c in enumerate(comms) for n in c}
    db.query(NetworkEdge).delete()
    db.query(NetworkNode).delete()
    for n, a in G.nodes(data=True):
        db.add(NetworkNode(id=n[:128], node_type=a["node_type"], label=str(a["label"])[:255],
                           attrs={k: v for k, v in a.items() if k not in ("node_type", "label")} |
                                 {"degree_centrality": round(deg.get(n, 0), 4), "betweenness": round(btw.get(n, 0), 4),
                                  "community": cid.get(n)}))
    for u, v, a in G.edges(data=True):
        db.add(NetworkEdge(source=u[:128], target=v[:128], relation_type=a["relation_type"], evidence_type=a["evidence_type"],
                           weight=a.get("weight"), confidence=a.get("confidence"), source_key=a.get("source"),
                           period=a.get("period")))
    db.flush()
    return f"{G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(comms)} communities"


def product_constellation(db: Session, product_id: str, top_countries: int = 8, top_zones: int = 6, top_sellers: int = 12) -> dict:
    """Subgraph CONTINENT → COUNTRY → CATEGORY/PRODUCT → ENTRY MODE → ENTRY POINT → SELLER → ZONE for one product."""
    p = db.get(Product, product_id)
    if not p:
        return {"nodes": [], "edges": []}
    pid = f"PRODUCT:{product_id}"
    nodes, edges = {}, []

    def add_node(nid):
        n = db.get(NetworkNode, nid)
        if n and nid not in nodes:
            nodes[nid] = {"id": nid, "type": n.node_type, "label": n.label, **(n.attrs or {})}
        return n is not None

    add_node(pid)
    cat = f"CATEGORY:{p.category}"
    add_node(cat)
    edges.append({"source": cat, "target": pid, "relation_type": "includes", "evidence_type": "VERIFIED", "source_key": "hs_nomenclature"})
    inc = db.query(NetworkEdge).filter(NetworkEdge.target == pid, NetworkEdge.relation_type == "exports_to_tunisia").order_by(
        NetworkEdge.weight.desc()).limit(top_countries).all()
    for e in inc:
        add_node(e.source)
        edges.append({"source": e.source, "target": pid, "relation_type": e.relation_type, "evidence_type": e.evidence_type,
                      "weight": e.weight, "source_key": e.source_key, "period": e.period})
        for ce in db.query(NetworkEdge).filter(NetworkEdge.target == e.source, NetworkEdge.relation_type == "contains"):
            add_node(ce.source)
            edges.append({"source": ce.source, "target": e.source, "relation_type": "contains", "evidence_type": "VERIFIED",
                          "source_key": "un_m49"})
    modes = db.query(NetworkEdge).filter(NetworkEdge.source == pid, NetworkEdge.relation_type == "enters_by").all()
    if modes:
        for e in modes:
            add_node(e.target)
            edges.append({"source": pid, "target": e.target, "relation_type": e.relation_type, "evidence_type": e.evidence_type,
                          "weight": e.weight, "source_key": e.source_key})
            for e2 in db.query(NetworkEdge).filter(NetworkEdge.source == e.target, NetworkEdge.relation_type == "through"):
                add_node(e2.target)
                edges.append({"source": e.target, "target": e2.target, "relation_type": "through", "evidence_type": "VERIFIED",
                              "weight": e2.weight, "source_key": e2.source_key})
    else:
        nodes["ENTRY_MODE:NA"] = {"id": "ENTRY_MODE:NA", "type": "ENTRY_MODE", "label": "Mode d'entrée : données détaillées non connectées",
                                  "unavailable": True}
        edges.append({"source": pid, "target": "ENTRY_MODE:NA", "relation_type": "enters_by", "evidence_type": "UNAVAILABLE",
                      "source_key": None})
    zones = db.query(NetworkEdge).filter(NetworkEdge.source == cat, NetworkEdge.relation_type == "observed_shops_in").order_by(
        NetworkEdge.weight.desc()).limit(top_zones).all()
    for z in zones:
        add_node(z.target)
        edges.append({"source": pid, "target": z.target, "relation_type": "association statistique (commerces de la catégorie dans la zone)",
                      "evidence_type": "STATISTICAL", "weight": z.weight, "source_key": "osm_shops"})
    zone_names = [z.target.split(":", 1)[1] for z in zones]
    sellers = db.query(Seller).filter(Seller.category == p.category, Seller.governorate.in_(zone_names),
                                      Seller.name.isnot(None)).limit(top_sellers).all()
    for s in sellers:
        sid = f"SELLER:{s.id}"
        nodes[sid] = {"id": sid, "type": "SELLER", "label": s.name, "seller_id": s.id}
        edges.append({"source": cat, "target": sid, "relation_type": "observed_shop_type", "evidence_type": "OBSERVED",
                      "source_key": "osm_shops"})
        edges.append({"source": sid, "target": f"ZONE:{s.governorate}", "relation_type": "located_in", "evidence_type": "OBSERVED",
                      "source_key": "osm_shops"})
    obs = f"OBS:{product_id}"
    if add_node(obs):
        edges.append({"source": obs, "target": pid, "relation_type": "matched_to", "evidence_type": "AI_INFERENCE",
                      "source_key": "open_facts", "confidence": 0.6})
    edges = [e for e in edges if e["source"] in nodes and e["target"] in nodes]
    return {"nodes": list(nodes.values()), "edges": edges}


def sankey(db: Session, metric: str = "value", category: str | None = None, top_countries: int = 12) -> dict:
    """CONTINENT → COUNTRY → PRODUCT → TRANSPORT MODE → ENTRY POINT → ZONE (layers only where data exists)."""
    year = latest_comtrade_year(db)
    q = db.query(CustomsRecord).filter(CustomsRecord.dataset == "comtrade_hs4_partner", CustomsRecord.period == year)
    prods = {p.id: p for p in db.query(Product)}
    countries = {c.iso3: c for c in db.query(Country).all()}
    flows = defaultdict(float)
    by_country = Counter()
    rows = []
    for r in q.all():
        p = prods.get(r.hs_code)
        c = countries.get(r.partner_iso3)
        if not p or not c or (category and p.category != category):
            continue
        v = r.value if metric == "value" else (r.weight_kg or 0) if metric == "weight" else 1
        rows.append((c, p, v))
        by_country[c.iso3] += v
    keep = {k for k, _ in by_country.most_common(top_countries)}
    for c, p, v in rows:
        cname = (c.name_fr or c.name_en) if c.iso3 in keep else "Autres pays"
        cont = c.continent or "Unknown"
        flows[(CONT_FR.get(cont, cont), cname)] += v
        flows[(cname, p.short_name)] += v
    has_decl = db.query(CustomsImport).count() > 0
    layers = ["CONTINENT", "COUNTRY", "PRODUCT"] + (["TRANSPORT MODE", "ENTRY POINT", "TUNISIAN ZONE"] if has_decl else [])
    if has_decl:
        # one coherent flow (same unit) built entirely from declarations: CONTINENT → … → ZONE
        flows = defaultdict(float)
        eps = {e.entry_point_id: e for e in db.query(EntryPoint).all()}
        for r in db.query(CustomsImport).all():
            p = prods.get(r.hs_code[:4])
            e = eps.get(r.entry_point_id)
            if not p or not e or (category and p.category != category):
                continue
            mode = r.transport_mode or TYPE_TO_MODE.get(e.entry_type)
            v = r.declared_value if metric == "value" else (r.quantity or 0) if metric == "weight" else 1
            c = countries.get(r.provenance_iso3 or r.origin_iso3)
            cname = (c.name_fr or c.name_en) if c else "Pays non précisé"
            flows[(CONT_FR.get(c.continent, "Autre") if c else "Autre", cname)] += v
            flows[(cname, p.short_name)] += v
            flows[(p.short_name, MODE_LABEL.get(mode, mode))] += v
            flows[(MODE_LABEL.get(mode, mode), e.official_name)] += v
            if r.destination_governorate:
                flows[(e.official_name, r.destination_governorate)] += v
    names = []
    for a, b in flows:
        for n in (a, b):
            if n not in names:
                names.append(n)
    return {"period": year, "metric": metric, "layers": layers, "nodes": [{"name": n} for n in names],
            "links": [{"source": names.index(a), "target": names.index(b), "value": v} for (a, b), v in flows.items() if v > 0],
            "missing_layers": [] if has_decl else ["TRANSPORT MODE", "ENTRY POINT", "TUNISIAN ZONE"],
            "missing_reason": None if has_decl else "Mode de transport, point d'entrée et zone de destination : source institutionnelle non connectée.",
            "source": "Statistiques douanières" + (" et déclarations détaillées" if has_decl else ""),
            "unit": {"value": "TND" if has_decl else "USD", "weight": "unités" if has_decl else "kg", "records": "enregistrements"}[metric]}
