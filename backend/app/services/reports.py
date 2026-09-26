"""Rapports IA (PDF) — one report per institution, built only from computed / sourced facts.

Douane  : analysis summary, classification, priority dossiers, advisor priorities, transmissions, sources, limits.
Finance : received dossiers, amounts to verify, concentrations, trends, priority dossiers.
Dossier : a single case (synthesis, operations, values, sources, history).
"""
from __future__ import annotations

from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from ..config import BASE_DIR, REPORT_DIR
from ..models import Case, DataSource, Report
from .cases import _n as _n_fr


def _n(v, d: int = 1) -> str:
    # PDF fonts lack the narrow no-break space used as the French thousands separator
    return _n_fr(v, d).replace(" ", " ")

# ---- CarthaGate visual identity (presentation only) ----
INK, MUTED = colors.HexColor("#0c2a4d"), colors.HexColor("#6b7f99")
BLUE, SKY, SKY_ROW, GOLD, LINE = (colors.HexColor("#0b4f9c"), colors.HexColor("#e4f1fc"), colors.HexColor("#f3f8fd"),
                                  colors.HexColor("#c8a24a"), colors.HexColor("#d6e4f2"))
ACCENT = BLUE
PUBLIC = BASE_DIR.parent / "frontend" / "public"
BRAND = {
    "douane": {"logo": "diw.png", "name": "DOUANE TUNISIENNE", "footer": "Douane Tunisienne • CarthaGate",
               "title": "RAPPORT D'ANALYSE DOUANIÈRE"},
    "finance": {"logo": "min.png", "name": "MINISTÈRE DES FINANCES", "footer": "Ministère des Finances • CarthaGate",
                "title": "RAPPORT D'ANALYSE FINANCIÈRE"},
}
styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Heading1"], textColor=BLUE, fontName="Helvetica-Bold", fontSize=17, leading=21, spaceAfter=4)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=BLUE, fontName="Helvetica-Bold", fontSize=11.5, leading=15,
                    spaceBefore=16, spaceAfter=6, borderPadding=(0, 0, 3, 0))
P = ParagraphStyle("P", parent=styles["BodyText"], fontSize=9, leading=13, textColor=INK)
SMALL = ParagraphStyle("S", parent=P, fontSize=7.5, leading=10, textColor=MUTED)
INST = ParagraphStyle("INST", parent=P, fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=BLUE)
BRANDLINE = ParagraphStyle("BRAND", parent=P, fontSize=8.5, leading=11, textColor=MUTED)


def _p(text, style=P):
    return Paragraph(str(text if text is not None else "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                     .replace("\n", "<br/>").replace("**", "").replace(" ", " "), style)


def _table(rows, widths):
    t = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 7.8), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.8),
                           ("BACKGROUND", (0, 0), (-1, 0), BLUE), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SKY_ROW]),
                           ("LINEBELOW", (0, 0), (-1, -1), 0.25, LINE), ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return t


def _money(v, unit):
    if v is None:
        return "—"
    return f"{_n(v / 1e6, 2)} M {unit or ''}" if abs(v) >= 1e6 else f"{_n(v, 0)} {unit or ''}"


def _section(n: int, title: str):
    """Numbered section heading « 01 — TITRE » with a gold rule."""
    t = Table([[Paragraph(f'<font color="#c8a24a">{n:02d}</font>&nbsp;&nbsp;—&nbsp;&nbsp;{title.upper()}', H2)]], colWidths=[17.8 * cm])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.8, GOLD), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 8)]))
    t.keepWithNext = True  # never leave a heading alone at the bottom of a page
    return t


def _logo(name: str, height: float):
    f = PUBLIC / name
    if not f.exists():
        return None
    try:
        from reportlab.lib.utils import ImageReader
        w, h = ImageReader(str(f)).getSize()
        return Image(str(f), width=height * w / h, height=height)
    except Exception:
        return None


def flag(country: str | None, iso3: str | None = None, height: float = 0.32 * cm):
    """Country flag drawing (from the same flag set as the interface), or None."""
    try:
        from svglib.svglib import svg2rlg
        from ..models import Country
        from ..db import SessionLocal
        s_ = SessionLocal()
        try:
            c = s_.get(Country, iso3) if iso3 else s_.query(Country).filter((Country.name_fr == country) | (Country.name_en == country)).first()
            code = (c.iso2 or "").lower() if c else None
        finally:
            s_.close()
        f = PUBLIC / "flags" / f"{code}.svg" if code else None
        if not f or not f.exists():
            return None
        d = svg2rlg(str(f))
        k = height / d.height
        d.scale(k, k)
        d.width, d.height = d.width * k, d.height * k
        return d
    except Exception:
        return None


def _country_cell(country, iso3=None):
    if not country:
        return "Information non disponible"
    fl = flag(country, iso3)
    if not fl:
        return country
    t = Table([[fl, _p(country)]], colWidths=[0.6 * cm, None])
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _header(space: str, now, ref: str, kind: str, title: str | None = None):
    """Institutional header block: logo · institution · CarthaGate, then report title and available metadata."""
    b = BRAND[space]
    logo = _logo(b["logo"], 1.9 * cm)
    ident = [_p(b["name"], INST), Paragraph('<font name="Helvetica-Bold" color="#0b4f9c">Cartha</font><font name="Helvetica-Bold" color="#c8a24a">Gate</font>'
                                            '&nbsp;&nbsp;<font color="#6b7f99">Intelligence financière &amp; douanière</font>', BRANDLINE)]
    head = Table([[logo or "", ident]], colWidths=[3.2 * cm if logo else 0.1 * cm, None])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("LINEBELOW", (0, 0), (-1, -1), 1.2, GOLD), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
    meta = Table([["Référence", ref], ["Date", f"{now:%d/%m/%Y à %H:%M} (UTC)"], ["Type d'analyse", kind]],
                 colWidths=[3.2 * cm, 14.6 * cm], hAlign="LEFT")
    meta.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 8), ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 8),
                              ("TEXTCOLOR", (0, 0), (-1, -1), INK), ("TEXTCOLOR", (0, 0), (0, -1), BLUE),
                              ("BACKGROUND", (0, 0), (-1, -1), SKY), ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                              ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]))
    return [head, Spacer(1, 14), _p(title or b["title"], H1), Spacer(1, 4), meta, Spacer(1, 6)]


def _doc(path, title, institution, now):
    space = "finance" if "finance" in institution.lower() else "douane"
    footer = BRAND[space]["footer"]

    def on_page(canvas, doc):
        canvas.saveState()
        w = A4[0]
        canvas.setStrokeColor(GOLD)
        canvas.setLineWidth(0.8)
        canvas.line(1.6 * cm, 1.45 * cm, w - 1.6 * cm, 1.45 * cm)
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.setFillColor(BLUE)
        canvas.drawString(1.6 * cm, 1 * cm, footer)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawCentredString(w / 2, 1 * cm, "Document d'aide à la décision — soumis à vérification humaine")
        canvas.drawRightString(w - 1.6 * cm, 1 * cm, f"Page {doc.page}")
        if doc.page > 1:
            canvas.setFont("Helvetica-Bold", 7.5)
            canvas.setFillColor(BLUE)
            canvas.drawString(1.6 * cm, A4[1] - 1.05 * cm, "CarthaGate")
            canvas.setFont("Helvetica", 7)
            canvas.setFillColor(MUTED)
            canvas.drawRightString(w - 1.6 * cm, A4[1] - 1.05 * cm, BRAND[space]["title"])
            canvas.setStrokeColor(LINE)
            canvas.line(1.6 * cm, A4[1] - 1.2 * cm, w - 1.6 * cm, A4[1] - 1.2 * cm)
        canvas.restoreState()
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.6 * cm,
                            bottomMargin=1.9 * cm, title=title, author=footer)
    return doc, on_page


def _save(db: Session, title: str, path, institution: str, user_id: int | None, meta: dict) -> Report:
    rep = Report(title=title, kind="PDF", path=str(path), meta=meta, institution=institution, created_by=user_id)
    db.add(rep)
    db.commit()
    return rep


def _stage(emit, key, label):
    emit({"type": "step", "key": key, "label": label, "status": "running"})
    return lambda: emit({"type": "step", "key": key, "label": label, "status": "done"})


def douane_report(db: Session, user_id: int | None, emit=None) -> Report:
    from . import douane
    emit = emit or (lambda e: None)
    now = datetime.utcnow()
    done = _stage(emit, "overview", "Synthèse de l'analyse")
    ov = douane.overview(db)
    done()
    done = _stage(emit, "advisor", "Priorités de contrôle")
    adv = douane.advisor(db, lambda e: None)
    done()
    done = _stage(emit, "cases", "Dossiers prioritaires et transmissions")
    cases = db.query(Case).filter(Case.status != "CLASSE").order_by(Case.priority_score.desc()).limit(15).all()
    tr = douane.transfers(db)
    done()
    done = _stage(emit, "pdf", "Création du rapport")
    path = REPORT_DIR / f"rapport_douane_{now:%Y%m%d_%H%M%S}.pdf"
    title = "Rapport d'analyse douanière — CarthaGate"
    doc, on_page = _doc(path, title, "Espace Douane", now)
    s = _header("douane", now, path.stem, "Analyse douanière — synthèse, priorités de contrôle, dossiers")
    s.append(_section(1, "Synthèse"))
    s.append(_p("Classement des situations analysées : " + " · ".join(f"{k} : {v}" for k, v in ov["classification"].items())))
    if ov.get("declarations_note"):
        s.append(_p(ov["declarations_note"], SMALL))
    s.append(_section(2, "Indicateurs clés"))
    s.append(_table([["Indicateur", "Valeur", "Détail"]] + [[k["label"], _n(k["value"], 0), _p(k["detail"], SMALL)] for k in ov["kpis"]],
                    [4.6 * cm, 2.4 * cm, 10.8 * cm]))
    s.append(_section(3, "Priorités de contrôle (3 maximum)"))
    s.append(_p(adv["text"]))
    for r in adv["recommendations"]:
        s.append(_p(f"Priorité {r['rank']} — {r['category']} — zone : {r['zone']} — point d'entrée : {r['entry_point']} — "
                    f"indice {r['priority_score']:.0f}/100 ({r['level']})"))
        s.append(_p("Pourquoi : " + " ".join(r["why"])))
        s.append(_p("Recommandation : " + r["action"], SMALL))
    s.append(_section(4, "Anomalies détectées — dossiers prioritaires"))
    if cases:
        s.append(_table([["Dossier", "Produit", "Motif", "Indice", "Statut"]] +
                        [[c.case_ref, _p(c.product), _p(c.motif.split(" — ")[0]), f"{c.priority_score:.0f}", _p(c.status.replace("_", " ").lower())]
                         for c in cases], [2.4 * cm, 4 * cm, 6.4 * cm, 1.4 * cm, 3 * cm]))
    else:
        s.append(_p("Aucun dossier ouvert."))
    s.append(_section(5, "Dossiers transmis à Finance"))
    if tr:
        s.append(_table([["Dossier", "Produit", "Transmis le", "Statut Finance"]] +
                        [[t["ref"], _p(t["product"]), t["transferred_at"][:10], t["finance_status"]] for t in tr[:20]],
                        [2.6 * cm, 7 * cm, 3 * cm, 4.6 * cm]))
    else:
        s.append(_p("Aucun dossier transmis."))
    s += [_section(6, "Sources / éléments disponibles"), _p(" · ".join(d.name for d in db.query(DataSource).filter(DataSource.status == "CONNECTED")))]
    s += [_section(7, "Limites"),
          _p("Les résultats sont des priorités de vérification, jamais des conclusions : une anomalie n'est pas une fraude, une "
             "observation n'est pas une vente, une corrélation n'est pas une preuve. Les déclarations détaillées, le registre des "
             "entreprises et les réseaux sociaux nécessitent une autorisation institutionnelle."),
          _section(8, "Validation humaine"), _p("Nom : ____________________    Décision : ____________________    Date : __________")]
    doc.build(s, onFirstPage=on_page, onLaterPages=on_page)
    done()
    return _save(db, title, path, "DOUANE", user_id, {"kind": "douane"})


def finance_report(db: Session, user_id: int | None, emit=None) -> Report:
    from . import finance
    emit = emit or (lambda e: None)
    now = datetime.utcnow()
    done = _stage(emit, "data", "Lecture des dossiers reçus")
    ov = finance.overview(db)
    done()
    done = _stage(emit, "analysis", "Analyse financière")
    an = finance.analysis(db, lambda e: None)
    done()
    done = _stage(emit, "pdf", "Création du rapport")
    path = REPORT_DIR / f"rapport_finance_{now:%Y%m%d_%H%M%S}.pdf"
    title = "Rapport d'analyse financière — CarthaGate"
    doc, on_page = _doc(path, title, "Espace Finance", now)
    s = _header("finance", now, path.stem, "Analyse financière des dossiers transmis")
    s.append(_section(1, "Indicateurs clés"))
    s.append(_table([["Indicateur", "Valeur"]] + [
        [k["label"], (" ; ".join(f"{_money(v['value'], v['unit'])} ({v['cases']} dossier(s))" for v in k["values"]) or "—") if "values" in k else str(k["value"])]
        for k in ov["kpis"]], [6 * cm, 11.8 * cm]))
    labels = {"Synthèse": "Synthèse financière"}
    i = 1
    for i, (sec, lines) in enumerate(an["sections"].items(), 2):
        s.append(_section(i, labels.get(sec, sec)))
        for l in lines:
            s.append(_p(f"• {l}"))
    s.append(_section(i + 1, "Dossiers prioritaires"))
    if an["priorities"]:
        s.append(_table([["Dossier", "Produit", "Montant", "Priorité", "Statut"]] +
                        [[p["ref"], _p(p["product"]), _money(p["value_concerned"], p["amount_unit"]), p["classification"], p["status_label"]]
                         for p in an["priorities"]], [2.6 * cm, 6 * cm, 3 * cm, 3 * cm, 2.6 * cm]))
    else:
        s.append(_p("Aucun dossier en attente."))
    s += [_section(i + 2, "Limites"), _p("Les montants indiqués correspondent à la valeur des opérations concernées et aux écarts potentiels "
                                 "calculés ; ils ne constituent ni une créance ni une estimation de recettes.")]
    doc.build(s, onFirstPage=on_page, onLaterPages=on_page)
    done()
    return _save(db, title, path, "FINANCE", user_id, {"kind": "finance"})


def case_report(db: Session, data: dict, institution: str, user_id: int | None) -> Report:
    """`data` is the institution-specific view of the dossier (Douane: case_full ; Finance: snapshot)."""
    now = datetime.utcnow()
    ref = data.get("ref")
    path = REPORT_DIR / f"dossier_{ref}_{institution.lower()}_{now:%Y%m%d_%H%M%S}.pdf"
    title = f"Dossier {ref} — {data.get('product')}"
    doc, on_page = _doc(path, title, f"Espace {institution.capitalize()}", now)
    unit = data.get("amount_unit")
    space = "finance" if institution == "FINANCE" else "douane"
    s = _header(space, now, path.stem, "Fiche dossier", f"DOSSIER {ref} — {str(data.get('product') or '').upper()}")
    s += [_section(1, "Pourquoi ce dossier a été signalé ?"),
         _p(data.get("motif")), _p(data.get("explanation")), _section(2, "Informations"),
         _table([["Élément", "Valeur"], ["Catégorie", data.get("category") or "—"], ["Période", data.get("period") or "—"],
                 ["Pays d'origine", _country_cell(data.get("country"), data.get("country_iso3"))], ["Zone", data.get("zone") or "Information non disponible"],
                 ["Classement", data.get("classification") or "—"], ["Indice de priorité", f"{(data.get('priority_score') or 0):.0f}/100"],
                 ["Valeur concernée", _money(data.get("value_concerned"), unit)], ["Écart potentiel à vérifier", _money(data.get("gap_to_verify"), unit)]],
                [6 * cm, 11 * cm]), _section(3, "Opérations concernées")]
    ops = data.get("operations") or []
    if ops:
        s.append(_table([["Date", "Libellé", "Valeur", "Quantité"]] +
                        [[o.get("date"), _p(o.get("label") or o.get("country") or ""), _money(o.get("value"), o.get("unit")),
                          _n(o.get("quantity"), 0) if o.get("quantity") else "—"] for o in ops[:40]], [2.4 * cm, 8 * cm, 3.4 * cm, 3.4 * cm]))
    s.append(_section(4, "Sources"))
    for src in (data.get("sources") or (data.get("evidence") or {}).get("sources") or []):
        s.append(_p(f"• {src.get('name')} — période : {src.get('period') or '—'} — mise à jour : {src.get('updated') or '—'}"))
    s.append(_p("Ce dossier signale une situation à vérifier ; il ne constitue ni une preuve ni une accusation.", SMALL))
    doc.build(s, onFirstPage=on_page, onLaterPages=on_page)
    return _save(db, title, path, institution, user_id, {"kind": "case", "ref": ref})
