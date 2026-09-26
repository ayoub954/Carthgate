import { useEffect, useRef, useState } from 'react'
import cytoscape from 'cytoscape'

const ORDER = ['CONTINENT', 'COUNTRY', 'CATEGORY', 'PRODUCT', 'ENTRY_MODE', 'ENTRY_POINT', 'OBSERVATIONS', 'SELLER', 'ZONE']
const EDGE_FR = { VERIFIED: 'Donnée officielle', OBSERVED: 'Observation', STATISTICAL: 'Association statistique', AI_INFERENCE: 'Rapprochement IA', UNAVAILABLE: 'Donnée non connectée' }
const TYPE_FR = { CONTINENT: 'Continent', COUNTRY: 'Pays', CATEGORY: 'Catégorie', PRODUCT: 'Produit', ENTRY_MODE: "Mode d'entrée", ENTRY_POINT: "Point d'entrée", OBSERVATIONS: 'Observations', SELLER: 'Vendeur', ZONE: 'Zone commerciale', HS_CODE: 'Chapitre', IMPORTER_HASH: 'Importateur' }
const EDGE_STYLE = {
  VERIFIED: { 'line-style': 'solid', 'line-color': '#0b0b0b', width: 1.6 },
  OBSERVED: { 'line-style': 'solid', 'line-color': '#2a78d6', width: 1.2 },
  STATISTICAL: { 'line-style': 'dashed', 'line-color': '#eb6834', width: 1.2 },
  AI_INFERENCE: { 'line-style': 'dotted', 'line-color': '#4a3aa7', width: 1.4 },
  UNAVAILABLE: { 'line-style': 'dotted', 'line-color': '#c3c2b7', width: 1 },
}

/** Trade Constellation: layered graph; click a node to highlight its connected path. */
export default function Constellation({ graph, height = 560, onSelect }) {
  const el = useRef(null)
  const [sel, setSel] = useState(null)
  useEffect(() => {
    if (!graph?.nodes?.length) return
    const layers = {}
    graph.nodes.forEach((n) => { (layers[n.type] = layers[n.type] || []).push(n) })
    const cols = ORDER.filter((t) => layers[t])
    const els = []
    cols.forEach((t, ci) => {
      layers[t].forEach((n, ri) => {
        els.push({ data: { id: n.id, label: n.label, type: t, unavailable: n.unavailable ? 1 : 0, raw: n },
          position: { x: ci * 210, y: (ri - (layers[t].length - 1) / 2) * 46 } })
      })
    })
    graph.edges.forEach((e, i) => els.push({ data: { id: `e${i}`, source: e.source, target: e.target, ev: e.evidence_type, rel: e.relation_type, src: e.source_key } }))
    const cy = cytoscape({
      container: el.current, elements: els, layout: { name: 'preset' }, wheelSensitivity: 0.2,
      style: [
        { selector: 'node', style: { label: 'data(label)', 'font-size': 10, color: '#52514e', 'text-valign': 'bottom', 'text-margin-y': 4,
          width: 12, height: 12, 'background-color': '#0b0b0b', 'text-wrap': 'ellipsis', 'text-max-width': 170 } },
        { selector: 'node[type="PRODUCT"]', style: { width: 22, height: 22, 'background-color': '#2a78d6', 'font-weight': 700, color: '#0b0b0b' } },
        { selector: 'node[type="ENTRY_POINT"], node[type="ENTRY_MODE"]', style: { shape: 'diamond' } },
        { selector: 'node[type="ZONE"]', style: { shape: 'round-rectangle', 'background-color': '#898781' } },
        { selector: 'node[type="SELLER"]', style: { width: 7, height: 7 } },
        { selector: 'node[unavailable=1]', style: { 'background-color': '#fff', 'border-width': 1.5, 'border-style': 'dashed', 'border-color': '#898781', color: '#898781' } },
        ...Object.entries(EDGE_STYLE).map(([k, v]) => ({ selector: `edge[ev="${k}"]`, style: { ...v, 'curve-style': 'bezier', opacity: 0.65, 'target-arrow-shape': 'none' } })),
        { selector: '.faded', style: { opacity: 0.08 } },
        { selector: '.hl', style: { opacity: 1, width: 2.4 } },
      ],
    })
    cy.on('tap', 'node', (evt) => {
      const n = evt.target
      const path = n.predecessors().union(n.successors()).union(n)
      cy.elements().addClass('faded').removeClass('hl')
      path.removeClass('faded').addClass('hl')
      setSel(n.data('raw'))
      onSelect?.(n.data('raw'))
    })
    cy.on('tap', 'edge', (evt) => setSel({ edge: true, ...evt.target.data() }))
    cy.on('tap', (evt) => { if (evt.target === cy) { cy.elements().removeClass('faded hl'); setSel(null) } })
    cy.fit(undefined, 30)
    return () => cy.destroy()
  }, [graph])
  return (
    <div>
      <div ref={el} style={{ height, border: '1px solid var(--border)', borderRadius: 12, background: 'var(--surface)' }} />
      <div className="legend">
        {Object.entries(EDGE_STYLE).map(([k, v]) => (
          <span key={k}><i style={{ width: 22, borderTop: `2px ${v['line-style']} ${v['line-color']}` }} />{EDGE_FR[k]}</span>
        ))}
      </div>
      {sel && (
        <div className="small" style={{ marginTop: 10 }}>
          {sel.edge ? <>Relation : <b>{EDGE_FR[sel.ev] || sel.ev}</b></>
            : <>Sélection : <b>{sel.label}</b> ({TYPE_FR[sel.type] || sel.type}) — cliquez sur le fond pour réinitialiser</>}
        </div>
      )}
    </div>
  )
}
