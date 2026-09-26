import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Play } from 'lucide-react'
import NeuralPath, { RelationLegend } from '../../components/NeuralPath.jsx'
import { Card, ErrorBox, Loading, Note, PageGuide, PageHead, Select, useApi } from '../../components/ui.jsx'
import { REL_BADGE } from './CaseSheet.jsx'

/** Panneau « POURQUOI CE LIEN ? » : nature de chaque relation, jamais présentée comme une preuve. */
export function LinkPanel({ sel, graph }) {
  if (!sel) return (
    <aside className="link-panel"><div className="eyebrow">Pourquoi ce lien ?</div>
      <p className="small muted" style={{ marginTop: 8 }}>Cliquez sur un élément du parcours (pays, produit, zone, anomalie…) pour afficher ses liens et leur nature.</p></aside>
  )
  const label = (id) => graph.nodes.find((n) => n.id === id)?.label || id
  const n = sel.node
  return (
    <aside className="link-panel">
      <div className="eyebrow">{graph.layers[n.layer]}</div>
      <h3 style={{ fontSize: 17, marginTop: 4 }}>{n.label}</h3>
      {n.sub && <div className="small muted">{n.sub}</div>}
      {n.detail && <p className="small" style={{ marginTop: 8 }}>{n.detail}</p>}
      <div className="row" style={{ gap: 6, marginTop: 8 }}>
        {n.product_id && <Link className="btn small" to={`/douane/produits/${n.product_id}`}>Vue 360° du produit</Link>}
        {n.case_id && <Link className="btn small" to={`/douane/dossiers/${n.case_id}`}>Ouvrir le dossier</Link>}
        {n.layer === 6 && <Link className="btn small" to={`/douane/carte?zone=${encodeURIComponent(n.label)}`}>Voir sur la carte</Link>}
      </div>
      <div className="eyebrow" style={{ marginTop: 16 }}>Pourquoi ce lien ?</div>
      <ul className="rel-list">{sel.links.map((e, i) => (
        <li key={i}><span className={`rel ${REL_BADGE[e.relation] || 'na'}`}>{e.relation}</span>
          <div><b className="small">{label(e.source)} → {label(e.target)}</b><div className="small">{e.why}</div></div></li>))}</ul>
      <p className="tiny muted" style={{ marginTop: 10 }}>Une corrélation n'est jamais une preuve.</p>
    </aside>
  )
}

export default function Pathway() {
  const cat = useApi('/douane/catalog')
  const [pid, setPid] = useState(null)
  const [replay, setReplay] = useState(0)
  const [sel, setSel] = useState(null)
  const g = useApi(`/douane/pathway${pid ? `?product=${pid}` : ''}`)
  return (
    <div>
      <PageHead eyebrow="Espace Douane" title="Parcours intelligent des flux" sub="Des données séparées deviennent une information exploitable lorsqu'on les relie.">
        <Select value={pid} onChange={(v) => { setPid(v); setSel(null) }} options={(cat.data?.products || []).map((p) => ({ value: p.id, label: p.name }))} placeholder="Produits les plus prioritaires" style={{ width: 280 }} />
        <button className="btn" onClick={() => setReplay((r) => r + 1)}><Play size={14} />Rejouer l'analyse</button>
      </PageHead>
      <PageGuide purpose="Ce réseau relie, couche par couche, l'origine d'un produit, son entrée en Tunisie, les zones où il est commercialisé et les anomalies détectées, jusqu'à la décision Douane puis Finance."
        steps={['Choisissez un produit ou gardez les produits prioritaires.', 'Regardez les liaisons s’activer couche par couche.', 'Cliquez sur un élément pour comprendre chaque lien.']}
        why="Chaque lien porte sa nature : observé (source directe), vérifié (référentiel officiel ou décision humaine), corrélation statistique, hypothèse à vérifier, ou donnée non connectée. Les couches sans donnée sont affichées en pointillés plutôt que devinées." />
      {g.loading ? <Loading label="Construction du parcours…" /> : g.error ? <ErrorBox error={g.error} /> : (
        <Card>
          <Note>{g.data.note}</Note>
          <div className="pathway-layout">
            <NeuralPath graph={g.data} animateKey={replay} selectedId={sel?.node.id} onSelect={(node, links) => setSel({ node, links })} />
            <LinkPanel sel={sel} graph={g.data} />
          </div>
          <RelationLegend />
        </Card>
      )}
    </div>
  )
}
