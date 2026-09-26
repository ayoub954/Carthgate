import { useState } from 'react'
import { Link } from 'react-router-dom'
import { X } from 'lucide-react'
import { fmt } from '../api.js'
import { AIBadge } from './ai.jsx'
import { EvidenceButton, Empty, Gauge, Level, Loading, useApi } from './ui.jsx'

/** Panneau « ZONE ANALYSÉE » — uniquement des informations publiques et des dossiers issus de l'analyse. */
export default function ZonePanel({ gov, onClose }) {
  const { data: z, loading } = useApi(`/douane/zones/${encodeURIComponent(gov)}`)
  const [view, setView] = useState(null)
  return (
    <aside className="zone-panel">
      <div className="row between"><div className="eyebrow">Zone analysée</div><button className="icon-btn" onClick={onClose} aria-label="Fermer"><X size={16} /></button></div>
      {loading ? <Loading /> : !z.available ? <Empty>{z.message}</Empty> : (
        <>
          <h2 style={{ marginTop: 4 }}>{z.governorate}</h2>
          <div className="facts one">
            <div><span>Gouvernorat</span><b>{z.governorate}</b></div>
            <div><span>Ville(s)</span><b>{z.cities.join(', ') || 'Information non disponible'}</b></div>
            <div><span>Activités commerciales observées</span><b>{fmt.num(z.shops)} commerce(s) · {fmt.num(z.observations)} observation(s) produit</b></div>
            <div><span>Produits principaux</span><b>{z.products.map((p) => p.label).slice(0, 3).join(', ') || 'Information non disponible'}</b></div>
            <div><span>Catégories principales</span><b>{z.categories.map((c) => c.label).slice(0, 3).join(', ') || 'Information non disponible'}</b></div>
            <div><span>Anomalies détectées</span><b>{z.anomalies.length} dossier(s)</b></div>
            <div><span>Évolution récente</span><b>{z.evolution.length ? z.evolution.slice(-3).map((e) => `${e.label} : ${e.value}`).join(' · ') : 'Information non disponible'}</b></div>
          </div>
          <div className="row between" style={{ marginTop: 10 }}><span className="small muted">Indice de priorité</span><Level value={z.level} /></div>
          <Gauge value={z.priority_index} />
          <div className="zone-why">
            <div className="row between"><b>Pourquoi cette zone attire l'attention ?</b><AIBadge label="Analyse IA" /></div>
            <ul className="why">{z.why.map((w, i) => <li key={i}>{w}</li>)}</ul>
          </div>
          <div className="row" style={{ gap: 6, marginTop: 10 }}>
            <button className={`btn small ${view === 'act' ? 'primary' : ''}`} onClick={() => setView(view === 'act' ? null : 'act')}>Voir les activités</button>
            <button className={`btn small ${view === 'prod' ? 'primary' : ''}`} onClick={() => setView(view === 'prod' ? null : 'prod')}>Voir les produits</button>
            <button className={`btn small ${view === 'ano' ? 'primary' : ''}`} onClick={() => setView(view === 'ano' ? null : 'ano')}>Voir les anomalies</button>
            <EvidenceButton evidence={z.evidence} />
          </div>
          {view === 'act' && <ul className="zone-list">{z.sellers.length ? z.sellers.map((s) => <li key={s.id}><b>{s.name}</b> <span className="muted">· {s.category}{s.city ? ` · ${s.city}` : ''}</span>{s.link && <> · <a href={s.link} target="_blank" rel="noreferrer">source</a></>}</li>) : <li className="muted">Aucun commerce nommé publiquement.</li>}</ul>}
          {view === 'prod' && <ul className="zone-list">{z.products.length ? z.products.map((p) => <li key={p.label}>{p.label} <span className="muted">· {p.value} dossier(s)</span></li>) : <li className="muted">Aucun produit rattaché.</li>}</ul>}
          {view === 'ano' && <ul className="zone-list">{z.anomalies.length ? z.anomalies.map((a) => <li key={a.id}><Link to={`/douane/dossiers/${a.id}`}>{a.ref}</Link> — {a.product} <span className="muted">· {a.kind} · {fmt.num(a.priority_score)}/100</span></li>) : <li className="muted">Aucune anomalie rattachée.</li>}</ul>}
        </>
      )}
    </aside>
  )
}
