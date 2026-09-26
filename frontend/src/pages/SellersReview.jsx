import { useState } from 'react'
import { Link } from 'react-router-dom'
import { MapPin } from 'lucide-react'
import { WINDOWS, fmt } from '../api.js'
import { AIButton, AIProgress, Reveal, useAIRun } from '../components/ai.jsx'
import { Empty, EvidenceButton, ExportMenu, Level, PageHead, Seg } from '../components/ui.jsx'
import { ModeSwitch } from '../mode.jsx'

export function SellerCards({ items, limit }) {
  return (
    <div className="grid g2">
      {(limit ? items.slice(0, limit) : items).map((s, i) => (
        <Reveal key={s.id} delay={i * 90}><SellerCard s={s} /></Reveal>
      ))}
    </div>
  )
}

export function SellerCard({ s }) {
  return (
    <div className="card seller-card">
      <div className="row between">
        <div><div className="eyebrow">Vendeur / commerce</div><h3 style={{ fontSize: 17, marginTop: 4 }}>{s.public_name}</h3>
          <div className="small muted">{s.platform}{s.location ? ` · ${s.location}` : ''}</div></div>
        <div style={{ textAlign: 'right' }}><div className="eyebrow">Indice de priorité</div><div className="big-num">{fmt.num(s.score)}<span className="small muted"> / 100</span></div><Level value={s.level} /></div>
      </div>
      <table className="t compact" style={{ marginTop: 10 }}><tbody>
        <tr><td className="muted">Produits observés</td><td>{s.products?.join(', ') || '—'}</td></tr>
        <tr><td className="muted">Produit principal</td><td>{s.main_product || '—'}</td></tr>
        <tr><td className="muted">Activité observée</td><td>{s.observations_period} publication(s) sur la période ({s.observations_total} au total){s.price_min != null ? ` · prix ${fmt.num(s.price_min)}–${fmt.num(s.price_max)} DT` : ''}</td></tr>
        <tr><td className="muted">Formalisation</td><td>{s.formalization}</td></tr>
        <tr><td className="muted">Activité douanière observable</td><td>{s.customs_activity}</td></tr>
        <tr><td className="muted">Cohérence</td><td>{s.consistency}</td></tr>
      </tbody></table>
      <div className="eyebrow" style={{ marginTop: 12 }}>Pourquoi cette fiche apparaît ?</div>
      {s.reasons.length ? <ul className="why">{s.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul> : <p className="small muted">Aucun élément particulier.</p>}
      <div className="row" style={{ gap: 6, marginTop: 12 }}>
        <EvidenceButton evidence={{ sources: [s.platform, 'Registre des entreprises', 'Déclarations douanières'], period: s.period, observations: s.observations_total }} />
        <Link className="btn small" to={`/intelligence/vendeurs/${s.seller_id}`}>Voir les produits</Link>
        {s.lat && <Link className="btn small" to={`/intelligence/carte?vendeur=${s.seller_id}`}><MapPin size={13} />Voir sur la carte</Link>}
        <Link className="btn small" to={`/investigation`} state={{ q: `Analyse du vendeur ${s.public_name}` }}>Générer une analyse</Link>
      </div>
      <p className="tiny muted" style={{ marginTop: 10 }}>Obligations douanières à vérifier — formalisation non vérifiée ne signifie pas activité illégale.</p>
    </div>
  )
}

export default function SellersReview() {
  const [win, setWin] = useState('30d')
  const ai = useAIRun()
  const res = ai.result
  return (
    <div>
      <PageHead title="Vendeurs à vérifier" sub="Activités commerciales dont la formalisation ou la cohérence avec les informations douanières disponibles doit être vérifiée.">
        <Seg value={win} onChange={setWin} options={WINDOWS} />
        <ModeSwitch compact />
      </PageHead>
      {ai.status === 'idle' && (
        <div className="launch">
          <h2>Analyse des activités commerciales</h2>
          <p className="muted">L'IA regroupe les vendeurs observés, vérifie les informations disponibles et recherche les écarts avec les flux douaniers.</p>
          <AIButton big onClick={() => ai.run(`/sellers/review/stream?window=${win}`)}>GÉNÉRER L'ANALYSE IA</AIButton>
        </div>
      )}
      {ai.status !== 'idle' && <AIProgress steps={ai.steps} status={ai.status} title="Analyse des activités commerciales" />}
      {ai.error && <Empty title="L'analyse n'a pas pu aboutir">{ai.error}</Empty>}
      {res && !res.available && <Reveal><Empty>{res.message}</Empty></Reveal>}
      {res?.available && (
        <div className="section">
          <div className="row between" style={{ marginBottom: 14 }}>
            <h2>{res.items.filter((s) => ['Prioritaire', 'Élevé'].includes(s.level)).length} vendeur(s) nécessitant une vérification prioritaire</h2>
            <div className="row"><ExportMenu dataset="sellers" /><button className="btn small" onClick={() => ai.run(`/sellers/review/stream?window=${win}`)}>Relancer l'analyse</button></div>
          </div>
          <SellerCards items={res.items} />
        </div>
      )}
    </div>
  )
}
